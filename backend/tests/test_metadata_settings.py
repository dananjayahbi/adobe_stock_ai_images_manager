"""Tests for metadata-generation settings (the /settings page's options).

The defect this guards: settings that exist only in the UI, or that a save
silently drops, look identical to working settings until a batch comes out
wrong. These tests round-trip every field through the real store and assert
the generator actually reads them.
"""

from __future__ import annotations

import pytest

from services import app_settings


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Isolated app-settings store (mirrors conftest's autouse fixture)."""
    from config import settings

    path = tmp_path / "app_settings.json"
    monkeypatch.setattr(settings, "APP_SETTINGS_PATH", path)
    return path


class TestReadPublic:
    def test_defaults_are_returned_with_bounds(self, store):
        public = app_settings.read_public()
        assert public["metadata_keyword_target"] == 49
        assert public["metadata_delay_seconds"] == 2.0
        assert public["metadata_extra_instructions"] == ""
        assert public["bounds"]["min_keyword_target"] == 5
        assert public["bounds"]["max_keyword_target"] == 49
        assert public["bounds"]["max_extra_instructions"] == 2000

    def test_stored_values_are_returned(self, store):
        app_settings.update(
            {
                "metadata_keyword_target": 30,
                "metadata_delay_seconds": 1.5,
                "metadata_extra_instructions": "Never mention minimalism.",
            }
        )
        public = app_settings.read_public()
        assert public["metadata_keyword_target"] == 30
        assert public["metadata_delay_seconds"] == 1.5
        assert public["metadata_extra_instructions"] == "Never mention minimalism."


class TestUpdate:
    def test_partial_update_leaves_other_metadata_fields_alone(self, store):
        app_settings.update(
            {"metadata_keyword_target": 30, "metadata_delay_seconds": 3.0}
        )
        app_settings.update({"metadata_keyword_target": 40})
        public = app_settings.read_public()
        assert public["metadata_keyword_target"] == 40
        assert public["metadata_delay_seconds"] == 3.0  # untouched

    def test_extra_instructions_round_trip_and_clear(self, store):
        app_settings.update({"metadata_extra_instructions": "  Prefer studio shots.  "})
        assert (
            app_settings.read_public()["metadata_extra_instructions"]
            == "Prefer studio shots."
        )
        # Blank clears back to the default (no instructions).
        app_settings.update({"metadata_extra_instructions": ""})
        assert app_settings.read_public()["metadata_extra_instructions"] == ""

    @pytest.mark.parametrize(
        "payload",
        [
            {"metadata_keyword_target": 4},     # below min
            {"metadata_keyword_target": 50},    # above Adobe's 49 ceiling
            {"metadata_delay_seconds": -1.0},   # negative pacing
            {"metadata_delay_seconds": 31.0},   # absurd pause
            {"metadata_extra_instructions": "x" * 2001},  # over the cap
        ],
    )
    def test_out_of_range_values_are_rejected(self, store, payload):
        with pytest.raises(app_settings.SettingsValidationError):
            app_settings.update(payload)
        # A rejected save must not half-apply: the store stays clean.
        assert app_settings.load_raw() == {}

    def test_validate_rejects_without_storing(self, store):
        with pytest.raises(app_settings.SettingsValidationError):
            app_settings.validate({"metadata_keyword_target": 0})
        assert app_settings.load_raw() == {}

    def test_reset_clears_metadata_overrides(self, store):
        app_settings.update({"metadata_keyword_target": 12})
        app_settings.save_raw({})
        assert app_settings.read_public()["metadata_keyword_target"] == 49


class TestResolveMetadata:
    def test_resolve_reads_the_store(self, store):
        app_settings.update({"metadata_keyword_target": 25})
        meta = app_settings.resolve_metadata()
        assert meta.keyword_target == 25

    def test_resolve_clamps_a_hand_edited_store(self, store):
        # A hand-edited file must degrade, not raise on a read path.
        app_settings.save_raw({"metadata_keyword_target": 9999})
        assert app_settings.resolve_metadata().keyword_target == 49

    def test_env_fallback_for_keyword_target(self, store, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "METADATA_KEYWORD_TARGET", 20)
        assert app_settings.resolve_metadata().keyword_target == 20

    def test_env_fallback_for_delay(self, store, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "METADATA_CALL_DELAY_SECONDS", 0.5)
        assert app_settings.resolve_metadata().delay_seconds == 0.5


class TestGeneratorConsumesTheSettings:
    def test_keyword_target_caps_the_generated_list(self, store, monkeypatch, tmp_path):
        """The stored target must reach the prompt AND the final cap - a target
        that only changes the prompt would let a verbose model overrun it."""
        from PIL import Image

        from config import settings
        from services import gemini_metadata

        monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

        app_settings.update({"metadata_keyword_target": 10})

        image = tmp_path / "img.jpg"
        Image.new("RGB", (32, 32), (200, 100, 50)).save(image, "JPEG")

        seen_prompt: dict = {}

        def fake_chat_json(path, prompt, **kwargs):
            seen_prompt["text"] = prompt
            return {
                "title": "A Title",
                "description": "Desc",
                "keywords": [f"kw{i}" for i in range(30)],
            }

        monkeypatch.setattr(gemini_metadata, "chat_json", fake_chat_json)

        meta = gemini_metadata.generate_metadata(image)

        assert meta is not None
        assert "up to 10 keyword strings" in seen_prompt["text"]
        assert len(meta["keywords"]) == 10  # capped at the target, not 30

    def test_extra_instructions_are_appended_to_the_prompt(
        self, store, monkeypatch, tmp_path
    ):
        from PIL import Image

        from config import settings
        from services import gemini_metadata

        monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
        app_settings.update(
            {"metadata_extra_instructions": "Never use the word minimalist."}
        )

        image = tmp_path / "img.jpg"
        Image.new("RGB", (32, 32), (10, 120, 200)).save(image, "JPEG")

        seen_prompt: dict = {}

        def fake_chat_json(path, prompt, **kwargs):
            seen_prompt["text"] = prompt
            return {"title": "T", "description": "D", "keywords": ["a"]}

        monkeypatch.setattr(gemini_metadata, "chat_json", fake_chat_json)
        gemini_metadata.generate_metadata(image)

        assert "Never use the word minimalist." in seen_prompt["text"]

    def test_instructions_with_braces_do_not_break_prompt_formatting(
        self, store, monkeypatch, tmp_path
    ):
        """Operator text is appended AFTER .format(), so literal braces are
        safe - this pins that ordering."""
        from PIL import Image

        from config import settings
        from services import gemini_metadata

        monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
        app_settings.update(
            {"metadata_extra_instructions": 'Use {braces} literally, e.g. "x {y}".'}
        )

        image = tmp_path / "img.jpg"
        Image.new("RGB", (32, 32), (10, 120, 200)).save(image, "JPEG")

        seen: dict = {}
        monkeypatch.setattr(
            gemini_metadata,
            "chat_json",
            lambda path, prompt, **kw: seen.update(prompt=prompt)
            or {"title": "T", "description": "D", "keywords": ["a"]},
        )
        gemini_metadata.generate_metadata(image)

        assert 'Use {braces} literally' in seen["prompt"]


class TestSettingsApi:
    def test_get_returns_metadata_fields(self, client):
        body = client.get("/api/settings").json()
        assert body["metadata_keyword_target"] == 49
        assert body["metadata_delay_seconds"] == 2.0
        assert body["metadata_extra_instructions"] == ""

    def test_put_applies_metadata_fields(self, client):
        body = client.put(
            "/api/settings",
            json={
                "metadata_keyword_target": 25,
                "metadata_delay_seconds": 0.5,
                "metadata_extra_instructions": "Focus on commercial usage.",
            },
        ).json()
        assert body["metadata_keyword_target"] == 25
        assert body["metadata_delay_seconds"] == 0.5
        assert body["metadata_extra_instructions"] == "Focus on commercial usage."

    def test_put_rejects_an_out_of_range_target(self, client):
        response = client.put(
            "/api/settings", json={"metadata_keyword_target": 100}
        )
        assert response.status_code == 400
        assert "49" in response.json()["detail"]
