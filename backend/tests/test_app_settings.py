"""Tests for the runtime application settings store and its API.

The behaviour that matters here is not "does it persist a string" but the three
contracts the Settings modal depends on:

1. A stored value overrides the environment; an unset value falls back to it.
2. The API key is never returned in a usable form, and a save that leaves the
   field blank cannot destroy a working key.
3. An invalid base URL or an out-of-range context window is rejected with a
   message rather than stored and discovered later during a batch.
"""

import json

import pytest

from services import app_settings, llm_budget


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Redirect the store into tmp_path and start from empty overrides."""
    from config import settings

    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "APP_SETTINGS_PATH", path)
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://env.example/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "env-model")
    monkeypatch.setattr(settings, "LLM_API_KEY", "env-key-12345678")
    monkeypatch.setattr(settings, "LLM_IMAGE_MAX_DIM", 1024)
    return path


# --------------------------------------------------------------------------- #
# Resolution and layering
# --------------------------------------------------------------------------- #

def test_environment_values_apply_when_nothing_is_stored(store):
    effective = app_settings.resolve()

    assert effective.base_url == "http://env.example/v1"
    assert effective.model == "env-model"
    assert effective.api_key == "env-key-12345678"
    assert effective.has_api_key is True


def test_stored_values_override_the_environment(store):
    app_settings.update(
        {
            "llm_base_url": "https://custom.example/v1",
            "llm_model": "custom-model",
            "llm_api_key": "sk-custom-abcdefgh",
        }
    )

    effective = app_settings.resolve()
    assert effective.base_url == "https://custom.example/v1"
    assert effective.model == "custom-model"
    assert effective.api_key == "sk-custom-abcdefgh"


def test_partial_update_leaves_other_fields_alone(store):
    app_settings.update({"llm_model": "first-model"})
    app_settings.update({"llm_context_window": 65536})

    effective = app_settings.resolve()
    assert effective.model == "first-model"
    assert effective.context_window == 65536
    # Untouched fields still come from the environment.
    assert effective.base_url == "http://env.example/v1"


def test_missing_store_file_falls_back_without_error(store):
    assert not store.exists()
    assert app_settings.load_raw() == {}
    assert app_settings.resolve().model == "env-model"


def test_corrupt_store_file_falls_back_without_raising(store):
    store.write_text("{ this is not json", encoding="utf-8")

    assert app_settings.load_raw() == {}
    assert app_settings.resolve().model == "env-model"


def test_non_object_store_file_is_ignored(store):
    store.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    assert app_settings.load_raw() == {}
    assert app_settings.resolve().model == "env-model"


def test_environment_context_window_applies_when_nothing_is_stored(store):
    """`.env` can declare the window for a model whose size we cannot guess."""
    from config import settings

    settings.LLM_CONTEXT_WINDOW = 131_072

    assert app_settings.resolve().context_window == 131_072


def test_stored_context_window_overrides_the_environment(store):
    from config import settings

    settings.LLM_CONTEXT_WINDOW = 131_072
    app_settings.update({"llm_context_window": 8192})

    assert app_settings.resolve().context_window == 8192


def test_environment_context_window_is_clamped_when_absurd(store):
    from config import settings

    settings.LLM_CONTEXT_WINDOW = 99_999_999

    assert app_settings.resolve().context_window == app_settings.MAX_CONTEXT_WINDOW


def test_reset_clears_overrides(store):
    app_settings.update({"llm_model": "custom"})
    assert app_settings.resolve().model == "custom"

    app_settings.save_raw({})
    assert app_settings.resolve().model == "env-model"


# --------------------------------------------------------------------------- #
# Secret handling
# --------------------------------------------------------------------------- #

def test_public_view_never_exposes_the_raw_key(store):
    app_settings.update({"llm_api_key": "sk-secret-value-9876"})

    public = app_settings.read_public()
    serialized = json.dumps(public)

    assert "sk-secret-value-9876" not in serialized
    assert public["llm_api_key_masked"].endswith("9876")
    assert public["llm_api_key_set"] is True


def test_blank_key_on_save_keeps_the_stored_key(store):
    """A UI that round-trips an empty field must not wipe the credential."""
    app_settings.update({"llm_api_key": "sk-original-key-1234"})
    app_settings.update({"llm_model": "another-model", "llm_api_key": ""})

    assert app_settings.resolve().api_key == "sk-original-key-1234"


def test_echoing_the_mask_keeps_the_stored_key(store):
    app_settings.update({"llm_api_key": "sk-original-key-1234"})
    mask = app_settings.read_public()["llm_api_key_masked"]

    app_settings.update({"llm_api_key": mask})

    assert app_settings.resolve().api_key == "sk-original-key-1234"


def test_clear_api_key_removes_it_deliberately(store):
    """Clearing must fall back to the environment, matching "never set"."""
    app_settings.update({"llm_api_key": "sk-original-key-1234"})
    assert app_settings.resolve().api_key == "sk-original-key-1234"

    app_settings.update({"clear_api_key": True})

    # The override is gone, so the .env key applies again rather than the key
    # being shadowed by an empty string.
    assert app_settings.resolve().api_key == "env-key-12345678"
    assert "llm_api_key" not in app_settings.load_raw()


def test_clear_api_key_without_an_environment_key_leaves_nothing(store):
    from config import settings

    settings.LLM_API_KEY = ""
    settings.GEMINI_API_KEY = ""
    app_settings.update({"llm_api_key": "sk-original-key-1234"})

    app_settings.update({"clear_api_key": True})

    assert app_settings.resolve().api_key == ""
    assert app_settings.resolve().has_api_key is False


def test_short_key_is_masked_entirely(store):
    """Revealing the tail of a short key would disclose most of it."""
    app_settings.update({"llm_api_key": "abc123"})

    masked = app_settings.read_public()["llm_api_key_masked"]
    assert "abc123" not in masked


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "url",
    ["ftp://example.com", "example.com/v1", "//example.com", "  "],
)
def test_invalid_base_url_is_rejected(store, url):
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.update({"llm_base_url": url})


def test_base_url_trailing_slash_is_normalised(store):
    app_settings.update({"llm_base_url": "https://api.example.com/v1/"})

    assert app_settings.resolve().base_url == "https://api.example.com/v1"


def test_empty_model_is_rejected(store):
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.update({"llm_model": "   "})


@pytest.mark.parametrize("window", [0, 100, 10_000_000, -5])
def test_out_of_range_context_window_is_rejected(store, window):
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.update({"llm_context_window": window})


def test_hand_edited_context_window_is_clamped_on_read(store):
    """An absurd value in the file degrades to something usable, not a crash."""
    app_settings.save_raw({"llm_context_window": 99_999_999})

    window = app_settings.resolve().context_window
    assert window == app_settings.MAX_CONTEXT_WINDOW


# --------------------------------------------------------------------------- #
# Context window -> request limits
# --------------------------------------------------------------------------- #

def test_image_tokens_grow_with_resolution():
    small = llm_budget.estimate_image_tokens(512, 512)
    large = llm_budget.estimate_image_tokens(2048, 2048)

    assert small < large


def test_the_window_does_not_constrain_image_size_in_the_supported_range(store):
    """A declared window must not silently degrade image quality.

    Documents the deliberate design. A vision encoder rescales to a 768px short
    side before accounting, so one image costs ~765 tokens whatever its original
    size - inside the image share of even the smallest supported window (4096).
    The window therefore governs the *reply* budget rather than the detail we
    upload, and the cap is simply the operator's preference.
    """
    assert llm_budget.resolve_image_max_dim(4096, 2048) == 2048
    assert llm_budget.resolve_image_max_dim(1_000_000, 2048) == 2048


def test_a_degenerate_window_steps_the_image_cap_down(store):
    """The cap is a safety net for a window below the supported floor.

    Such a window is only reachable by setting ``LLM_CONTEXT_WINDOW`` in the
    environment, since the API rejects anything under
    ``MIN_CONTEXT_WINDOW``. Without this, a misconfigured window would send an
    image that alone overruns the model.
    """
    degenerate = llm_budget.resolve_image_max_dim(1024, 2048)
    generous = llm_budget.resolve_image_max_dim(200_000, 2048)

    assert degenerate < generous
    assert degenerate == 512


def test_image_cap_never_exceeds_the_operator_preference(store):
    """The window may lower the cap; it must never raise it past the setting."""
    assert llm_budget.resolve_image_max_dim(1_000_000, 768) == 768


def test_image_cap_is_always_a_standard_size(store):
    for window in (512, 1024, 2048, 4096, 131_072):
        assert llm_budget.resolve_image_max_dim(window, 2048) in llm_budget.IMAGE_CAPS


def test_completion_budget_shrinks_as_the_prompt_grows():
    """A long prompt eats into the room left for the answer.

    Uses a 40k window so the arithmetic is legible: the reply share is 10k
    tokens, and a 30k-token prompt leaves less than that, so the prompt - not
    the model ceiling - becomes the binding constraint.
    """
    short = llm_budget.completion_token_budget(40_000, prompt="hi", model="m")
    long = llm_budget.completion_token_budget(
        40_000, prompt="x" * 120_000, model="m"
    )

    assert short == 10_000, "the reply share should be the limit here"
    assert long < short


def test_completion_budget_is_sized_from_the_model_ceiling():
    """A known reasoning family is given room up front, not the bare minimum."""
    reasoning = llm_budget.completion_token_budget(200_000, model="deepseek-v4.1-flash")
    unknown = llm_budget.completion_token_budget(200_000, model="some-model")

    assert reasoning > 4096
    assert reasoning > unknown


def test_model_output_ceiling_recognises_reasoning_families():
    assert llm_budget.model_output_ceiling("deepseek-v4.1-flash") == 32_768
    assert llm_budget.model_output_ceiling("o3-mini") == 32_768
    assert llm_budget.model_output_ceiling("claude-3-5-sonnet") == 32_768
    assert (
        llm_budget.model_output_ceiling("totally-unknown")
        == llm_budget.DEFAULT_OUTPUT_CEILING
    )


def test_model_output_ceiling_is_case_insensitive():
    assert llm_budget.model_output_ceiling("DeepSeek-R1") == 32_768


def test_completion_budget_is_capped_on_a_large_window():
    """An unbounded budget invites a runaway generation."""
    budget = llm_budget.completion_token_budget(2_000_000, model="deepseek-v4.1-flash")

    assert budget <= llm_budget.ABSOLUTE_MAX_COMPLETION_TOKENS


def test_completion_budget_is_large_enough_for_a_reasoning_model():
    """A 4096 cap silently broke the reasoning model this app is configured for.

    Measured: one metadata pass spent 2,503 reasoning tokens for an 867-char
    answer, another spent 8,054. The budget has to leave room for the hidden
    chain of thought, not just the visible JSON.
    """
    budget = llm_budget.completion_token_budget(
        200_000, prompt="x" * 2000, model="deepseek-v4.1-flash"
    )

    assert budget > 4096


def test_completion_budget_escalates_on_retry():
    """Each retry asks for more room, since only truncation reveals the need."""
    first = llm_budget.completion_token_budget(200_000, attempt=1, model="m")
    second = llm_budget.completion_token_budget(200_000, attempt=2, model="m")

    assert first < second


def test_completion_budget_escalation_is_capped():
    """Escalation must stop somewhere, or a retry loop could ask for anything."""
    budget = llm_budget.completion_token_budget(2_000_000, attempt=20, model="m")

    assert budget <= llm_budget.ABSOLUTE_MAX_COMPLETION_TOKENS


def test_completion_budget_never_exceeds_the_context_window():
    """A budget larger than the window would itself be rejected."""
    budget = llm_budget.completion_token_budget(4096, prompt="")

    assert budget <= 4096


def test_completion_budget_has_a_floor():
    """A window already consumed by the prompt still yields a usable budget."""
    budget = llm_budget.completion_token_budget(4096, prompt="x" * 40_000)

    assert budget == llm_budget.COMPLETION_BUDGET_FLOOR


# --------------------------------------------------------------------------- #
# Truncation detection
# --------------------------------------------------------------------------- #

def test_truncation_is_detected_from_finish_reason():
    envelope = {
        "choices": [{"finish_reason": "length", "message": {"content": ""}}],
    }

    assert llm_budget.is_truncated(envelope) is True


def test_a_completed_reply_is_not_truncation():
    envelope = {
        "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
    }

    assert llm_budget.is_truncated(envelope) is False


def test_an_envelope_without_choices_is_not_truncation():
    """An empty choices list is a different fault, handled separately."""
    assert llm_budget.is_truncated({}) is False
    assert llm_budget.is_truncated({"choices": []}) is False


def test_reasoning_tokens_prefers_the_reported_usage():
    envelope = {
        "choices": [{"message": {"reasoning_content": "x" * 4000}}],
        "usage": {"completion_tokens_details": {"reasoning_tokens": 2503}},
    }

    assert llm_budget.reasoning_tokens(envelope) == 2503


def test_reasoning_tokens_falls_back_to_the_message_length():
    """Providers disagree on where this is reported, so both are read."""
    envelope = {"choices": [{"message": {"reasoning_content": "x" * 4000}}]}

    assert llm_budget.reasoning_tokens(envelope) == 1000


def test_reasoning_tokens_is_zero_for_a_plain_reply():
    envelope = {"choices": [{"message": {"content": "{}"}}]}

    assert llm_budget.reasoning_tokens(envelope) == 0


# --------------------------------------------------------------------------- #
# Non-destructive resolution (the connection probe)
# --------------------------------------------------------------------------- #

def test_resolve_with_applies_candidates_without_storing_them(store):
    overrides = {"llm_base_url": "https://candidate.example/v1", "llm_model": "cand"}

    candidate = app_settings.resolve_with(overrides)

    assert candidate.base_url == "https://candidate.example/v1"
    assert candidate.model == "cand"
    # Nothing was written, so the real configuration is unchanged.
    assert app_settings.load_raw() == {}
    assert app_settings.resolve().base_url == "http://env.example/v1"


def test_resolve_with_keeps_the_effective_key_for_a_blank_override(store):
    app_settings.update({"llm_api_key": "sk-stored-key"})

    candidate = app_settings.resolve_with({"llm_api_key": ""})

    assert candidate.api_key == "sk-stored-key"


def test_resolve_with_uses_a_submitted_key(store):
    candidate = app_settings.resolve_with({"llm_api_key": "sk-candidate"})

    assert candidate.api_key == "sk-candidate"
    assert candidate.has_api_key is True


def test_resolve_with_rejects_an_invalid_candidate_url(store):
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.resolve_with({"llm_base_url": "nope"})


def test_resolve_with_rejects_an_out_of_range_candidate_window(store):
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.resolve_with({"llm_context_window": 10})


def test_validate_accepts_a_complete_payload(store):
    app_settings.validate(
        {
            "llm_base_url": "https://ok.example/v1",
            "llm_model": "m",
            "llm_context_window": 32768,
        }
    )


def test_validate_rejects_an_empty_model(store):
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.validate({"llm_model": "   "})


# --------------------------------------------------------------------------- #
# API surface
# --------------------------------------------------------------------------- #

def test_get_settings_returns_masked_key_and_effective_values(client, store):
    from config import settings

    monkey_settings = settings
    monkey_settings.LLM_API_KEY = "sk-api-key-4321"

    response = client.get("/api/settings")
    assert response.status_code == 200

    body = response.json()
    assert body["llm_api_key_set"] is True
    assert "sk-api-key-4321" not in response.text
    assert body["effective_base_url"] == "http://env.example/v1"
    assert body["bounds"]["min_context_window"] == app_settings.MIN_CONTEXT_WINDOW


def test_put_settings_persists_and_returns_the_new_view(client, store):
    response = client.put(
        "/api/settings",
        json={
            "llm_base_url": "https://api.openai.com/v1",
            "llm_model": "gpt-4o-mini",
            "llm_context_window": 131072,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["effective_base_url"] == "https://api.openai.com/v1"
    assert body["effective_model"] == "gpt-4o-mini"
    assert body["llm_context_window"] == 131072
    assert store.exists()


def test_put_settings_rejects_a_bad_url_with_a_message(client, store):
    response = client.put("/api/settings", json={"llm_base_url": "not-a-url"})

    assert response.status_code == 400
    assert "http" in response.json()["detail"].lower()


def test_put_settings_rejects_a_context_window_outside_the_bounds(client, store):
    response = client.put("/api/settings", json={"llm_context_window": 10})

    assert response.status_code == 400
    assert "between" in response.json()["detail"].lower()


def test_reset_endpoint_clears_overrides(client, store):
    client.put("/api/settings", json={"llm_model": "custom-model"})
    assert client.get("/api/settings").json()["effective_model"] == "custom-model"

    response = client.post("/api/settings/reset")

    assert response.status_code == 200
    assert response.json()["effective_model"] == "env-model"


# --------------------------------------------------------------------------- #
# Source folder (browse/import APIs)
# --------------------------------------------------------------------------- #

class TestSourceFolderSetting:
    def test_roundtrip_through_put_and_get(self, client, store, tmp_path):
        folder = tmp_path / "photos"
        folder.mkdir()

        put = client.put("/api/settings", json={"source_folder": str(folder)})
        assert put.status_code == 200
        assert put.json()["source_folder"] == str(folder)

        assert client.get("/api/settings").json()["source_folder"] == str(folder)

    def test_blank_value_clears_the_setting(self, client, store, tmp_path):
        client.put("/api/settings", json={"source_folder": str(tmp_path)})

        put = client.put("/api/settings", json={"source_folder": "   "})

        assert put.status_code == 200
        assert put.json()["source_folder"] == ""
        assert client.get("/api/settings").json()["source_folder"] == ""

    def test_omitted_field_is_left_untouched(self, client, store, tmp_path):
        client.put("/api/settings", json={"source_folder": str(tmp_path)})

        put = client.put("/api/settings", json={"llm_model": "keep-folder"})

        assert put.json()["source_folder"] == str(tmp_path)

    def test_value_is_stored_trimmed(self, client, store, tmp_path):
        put = client.put(
            "/api/settings", json={"source_folder": f"  {tmp_path}  "}
        )
        assert put.json()["source_folder"] == str(tmp_path)
