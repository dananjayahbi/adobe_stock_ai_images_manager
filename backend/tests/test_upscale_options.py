"""Unit tests for Stage 3 upscale option validation and output estimation.

The options layer is the boundary between an untrusted request body and a
subprocess invocation, so these tests focus on the two things that actually
break in production: out-of-range values reaching the CLI, and an unknown model
name producing a command the binary cannot resolve.
"""

import pytest

from services.upscale import catalog, options as upscale_options


@pytest.fixture()
def settings():
    from config import settings as cfg

    return cfg


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    """The catalog is cached module-wide; drop it between tests."""
    catalog.clear_cache()
    yield
    catalog.clear_cache()


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #


def test_default_options_match_the_configured_defaults(settings):
    resolved = upscale_options.default_options(settings)

    assert resolved.model_scale == settings.UPSCAYL_SCALE
    assert resolved.gpu_id == settings.UPSCAYL_GPU_ID
    assert resolved.target_long_edge == settings.UPSCAYL_TARGET_LONG_EDGE
    assert resolved.tta == settings.UPSCAYL_TTA
    # The format is not a field - it is fixed to JPEG and only surfaces in the
    # serialised form the API returns.
    assert resolved.to_dict()["format"] == "jpg"


def test_defaults_are_serialisable_for_the_api(settings):
    payload = upscale_options.default_options(settings).to_dict()

    assert payload["format"] == "jpg"
    assert payload["threads"] == list(upscale_options.DEFAULT_THREADS)
    assert set(payload) == {
        "model",
        "model_scale",
        "target_long_edge",
        "gpu_id",
        "tta",
        "tile_size",
        "threads",
        "compression",
        "embed_srgb",
        "allow_downscale",
        "format",
    }


def test_threads_arg_renders_the_colon_form(settings):
    resolved = upscale_options.default_options(settings)

    assert resolved.threads_arg == "1:2:2"


# --------------------------------------------------------------------------- #
# Validation of untrusted payloads
# --------------------------------------------------------------------------- #


def test_from_payload_accepts_a_partial_body(settings):
    resolved = upscale_options.from_payload({"target_long_edge": 5120}, settings)

    assert resolved.target_long_edge == 5120
    # Everything omitted falls back to the configured default.
    assert resolved.gpu_id == settings.UPSCAYL_GPU_ID


def test_from_payload_clamps_an_absurd_target_into_range(settings):
    too_small = upscale_options.from_payload({"target_long_edge": 10}, settings)
    too_large = upscale_options.from_payload({"target_long_edge": 999_999}, settings)

    assert too_small.target_long_edge == upscale_options.MIN_TARGET_LONG_EDGE
    assert too_large.target_long_edge == upscale_options.MAX_TARGET_LONG_EDGE


def test_from_payload_treats_a_tiny_tile_as_auto(settings):
    resolved = upscale_options.from_payload({"tile_size": 4}, settings)

    assert resolved.tile_size == upscale_options.TILE_AUTO


def test_from_payload_keeps_a_usable_tile_size(settings):
    resolved = upscale_options.from_payload({"tile_size": 256}, settings)

    assert resolved.tile_size == 256


def test_from_payload_falls_back_when_the_model_is_unknown(settings):
    resolved = upscale_options.from_payload({"model": "no-such-model"}, settings)

    # A bad model name must never reach the CLI: it would abort the batch.
    assert resolved.model == upscale_options.default_options(settings).model


def test_from_payload_coerces_string_booleans_and_numbers(settings):
    resolved = upscale_options.from_payload(
        {"tta": "true", "gpu_id": "1", "model_scale": "2", "compression": "75"},
        settings,
    )

    assert resolved.tta is True
    assert resolved.gpu_id == 1
    assert resolved.model_scale == 2
    assert resolved.compression == 75


def test_from_payload_rejects_an_invalid_model_scale(settings):
    resolved = upscale_options.from_payload({"model_scale": 7}, settings)

    # The CLI only accepts 2, 3 and 4; anything else is forced back to the
    # configured scale rather than failing the whole batch.
    assert resolved.model_scale in catalog.VALID_SCALES


def test_from_payload_clamps_compression(settings):
    low = upscale_options.from_payload({"compression": -20}, settings)
    high = upscale_options.from_payload({"compression": 500}, settings)

    assert 0 <= low.compression <= 100
    assert 0 <= high.compression <= 100


def test_from_payload_ignores_unknown_keys(settings):
    resolved = upscale_options.from_payload({"nonsense": "value"}, settings)

    assert resolved == upscale_options.default_options(settings)


def test_from_payload_reads_config_defaults(settings, monkeypatch):
    monkeypatch.setattr(settings, "UPSCAYL_TARGET_LONG_EDGE", 7680)
    monkeypatch.setattr(settings, "UPSCAYL_GPU_ID", 1)
    monkeypatch.setattr(settings, "UPSCAYL_TTA", True)

    resolved = upscale_options.from_payload({}, settings)

    assert resolved.target_long_edge == 7680
    assert resolved.gpu_id == 1
    assert resolved.tta is True


# --------------------------------------------------------------------------- #
# Estimation
# --------------------------------------------------------------------------- #


def test_estimate_scales_up_toward_the_target(settings):
    resolved = upscale_options.default_options(settings)

    estimate = upscale_options.estimate_output(896, 1200, resolved)

    assert estimate["will_upscale"] is True
    assert estimate["will_downscale"] is False
    # Aspect ratio is preserved, so the long edge lands on the target.
    assert estimate["target_dimensions"][1] == resolved.target_long_edge
    assert estimate["target_dimensions"][0] < estimate["target_dimensions"][1]


def test_estimate_warns_when_the_source_already_meets_the_target(settings):
    resolved = upscale_options.default_options(settings)

    estimate = upscale_options.estimate_output(4000, 5000, resolved)

    assert estimate["will_upscale"] is False
    assert estimate["warnings"]
    assert "native size" in estimate["warnings"][0]


def test_estimate_allows_downscaling_when_opted_in(settings):
    resolved = upscale_options.from_payload(
        {"target_long_edge": 2000, "allow_downscale": True}, settings
    )

    estimate = upscale_options.estimate_output(4000, 5000, resolved)

    assert estimate["will_downscale"] is True
    assert estimate["target_dimensions"] == [1600, 2000]


def test_estimate_flags_an_output_over_the_megapixel_ceiling(settings):
    resolved = upscale_options.default_options(settings)

    # A source that is already past the ceiling: it is passed through at native
    # size, so the warning has to come from the source, not from a bigger target.
    estimate = upscale_options.estimate_output(11000, 10000, resolved)

    assert estimate["estimated_megapixels"] > 100
    assert estimate["exceeds_megapixel_ceiling"] is True
    assert any("MP ceiling" in warning for warning in estimate["warnings"])


def test_estimate_warns_when_tta_is_enabled(settings):
    resolved = upscale_options.from_payload({"tta": True}, settings)

    estimate = upscale_options.estimate_output(896, 1200, resolved)

    assert any("tta" in warning.lower() for warning in estimate["warnings"])


def test_estimate_warns_when_a_2x_model_is_asked_for_more(settings):
    resolved = upscale_options.from_payload(
        {"model": "realesr-animevideov3-x2", "model_scale": 2, "target_long_edge": 7680},
        settings,
    )

    estimate = upscale_options.estimate_output(896, 1200, resolved)

    assert any("2x" in warning for warning in estimate["warnings"])


def test_estimate_handles_a_degenerate_source(settings):
    resolved = upscale_options.default_options(settings)

    estimate = upscale_options.estimate_output(0, 0, resolved)

    assert estimate["will_upscale"] is False
    assert estimate["estimated_megapixels"] == 0


def test_with_target_returns_a_copy(settings):
    resolved = upscale_options.default_options(settings)

    retargeted = upscale_options.with_target(resolved, 7680)

    assert retargeted.target_long_edge == 7680
    assert resolved.target_long_edge == settings.UPSCAYL_TARGET_LONG_EDGE


@pytest.mark.parametrize(
    ("long_edge", "expected"),
    [(2560, "2K"), (3840, "4K"), (5120, "5K"), (6144, "6K"), (7680, "8K")],
)
def test_capacity_label_names_each_preset(long_edge, expected):
    assert upscale_options.capacity_label(long_edge) == expected


def test_capacity_label_falls_back_to_pixels():
    # A hand-edited config value is still described honestly.
    assert upscale_options.capacity_label(4500) == "4500px"
