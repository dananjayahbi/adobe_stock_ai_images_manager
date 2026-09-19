"""Unit tests for Upscayl model discovery and CLI resolution.

Discovery is filesystem-driven, so these tests build throwaway model folders and
assert the rules that matter: a model is only offered when both halves of the
ncnn pair exist, the scale is inferred correctly from the filename, and the
Electron GUI is never mistaken for the headless binary.
"""

from pathlib import Path

import pytest

from services.upscale import catalog, runner


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    catalog.clear_cache()
    yield
    catalog.clear_cache()


@pytest.fixture()
def model_root(tmp_path):
    """Two model folders (bundled + outsourced), both empty to start."""
    bundled = tmp_path / "resources" / "models"
    outsourced = tmp_path / "Outsourced_models" / "models"
    bundled.mkdir(parents=True)
    outsourced.mkdir(parents=True)
    return bundled, outsourced


@pytest.fixture()
def fake_settings(tmp_path, model_root, monkeypatch):
    """Point the catalog at the throwaway folders."""
    from config import settings

    bundled, outsourced = model_root
    monkeypatch.setattr(settings, "UPSCAYL_APP_DIR", tmp_path)
    monkeypatch.setattr(settings, "UPSCAYL_MODEL_DIRS", [])
    catalog.clear_cache()
    return settings


def make_model(directory: Path, name: str, *, param: bool = True, blob: bool = True):
    """Write an ncnn pair, optionally leaving one half out."""
    if param:
        (directory / f"{name}.param").write_text("network\n", encoding="utf-8")
    if blob:
        (directory / f"{name}.bin").write_bytes(b"\x00\x01\x02")


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def test_discovers_a_model_from_both_folders(fake_settings, model_root):
    bundled, outsourced = model_root
    make_model(bundled, "upscayl-standard-4x")
    make_model(outsourced, "4xNomos8kSC")

    names = {model.name for model in catalog.list_models(fake_settings)}

    assert names == {"upscayl-standard-4x", "4xNomos8kSC"}


def test_reports_the_source_folder(fake_settings, model_root):
    bundled, outsourced = model_root
    make_model(bundled, "upscayl-standard-4x")
    make_model(outsourced, "4xNomos8kSC")

    by_name = {m.name: m for m in catalog.list_models(fake_settings)}

    assert by_name["upscayl-standard-4x"].source == catalog.SOURCE_BUNDLED
    assert by_name["4xNomos8kSC"].source == catalog.SOURCE_OUTSOURCED


def test_skips_a_model_missing_its_weight_blob(fake_settings, model_root):
    bundled, _ = model_root
    make_model(bundled, "complete-4x")
    make_model(bundled, "param-only-4x", blob=False)

    names = {model.name for model in catalog.list_models(fake_settings)}

    # A .param without its .bin cannot be loaded, so it must not be selectable.
    assert names == {"complete-4x"}


def test_skips_a_model_missing_its_network_description(fake_settings, model_root):
    bundled, _ = model_root
    make_model(bundled, "bin-only-4x", param=False)

    assert catalog.list_models(fake_settings) == []


def test_missing_directory_is_not_an_error(fake_settings, monkeypatch, tmp_path):
    from config import settings

    monkeypatch.setattr(settings, "UPSCAYL_APP_DIR", tmp_path / "nowhere")
    catalog.clear_cache()

    assert catalog.list_models(settings) == []


def test_duplicate_names_across_folders_are_reported_once(fake_settings, model_root):
    bundled, outsourced = model_root
    make_model(bundled, "shared-4x")
    make_model(outsourced, "shared-4x")

    models = catalog.list_models(fake_settings)

    assert len(models) == 1
    # The bundled copy wins because that folder is scanned first.
    assert models[0].source == catalog.SOURCE_BUNDLED


def test_custom_directories_are_scanned(fake_settings, monkeypatch, tmp_path):
    from config import settings

    custom = tmp_path / "my_models"
    custom.mkdir()
    make_model(custom, "my-custom-4x")
    monkeypatch.setattr(settings, "UPSCAYL_MODEL_DIRS", [custom])
    catalog.clear_cache()

    models = catalog.list_models(settings)

    assert [m.source for m in models] == [catalog.SOURCE_CUSTOM]


def test_refresh_picks_up_a_newly_added_model(fake_settings, model_root):
    bundled, _ = model_root
    assert catalog.list_models(fake_settings) == []

    make_model(bundled, "late-arrival-4x")
    names = {m.name for m in catalog.list_models(fake_settings, refresh=True)}

    assert names == {"late-arrival-4x"}


# --------------------------------------------------------------------------- #
# Scale inference
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("4xNomos8kSC", 4),
        ("2xSomeModel", 2),
        ("realesr-animevideov3-x2", 2),
        ("realesr-animevideov3-x3", 3),
        ("digital-art-4x", 4),
        ("upscayl-standard-4x", 4),
    ],
)
def test_infers_scale_from_the_filename(name, expected):
    assert catalog._infer_scale(name) == expected


def test_scale_inference_falls_back_to_four():
    # No scale marker anywhere, so assume the most common network size.
    assert catalog._infer_scale("mystery-model") == 4


def test_inferred_scale_is_always_valid():
    for name in ("4xNomos8kSC", "mystery", "realesr-animevideov3-x2"):
        assert catalog._infer_scale(name) in catalog.VALID_SCALES


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #


def test_configured_model_wins_when_installed(fake_settings, model_root, monkeypatch):
    from config import settings

    bundled, _ = model_root
    make_model(bundled, "chosen-4x")
    monkeypatch.setattr(settings, "UPSCAYL_MODEL", "chosen-4x")
    catalog.clear_cache()

    assert catalog.default_model_name(settings=settings) == "chosen-4x"


def test_falls_back_when_the_configured_model_is_missing(
    fake_settings, model_root, monkeypatch
):
    from config import settings

    bundled, _ = model_root
    make_model(bundled, "4xNomos8kSC")
    monkeypatch.setattr(settings, "UPSCAYL_MODEL", "not-installed-4x")
    catalog.clear_cache()

    # A checkout without the configured weights must still upscale.
    assert catalog.default_model_name(settings=settings) == "4xNomos8kSC"


def test_returns_empty_string_when_nothing_is_installed(fake_settings):
    assert catalog.default_model_name(settings=fake_settings) == ""


def test_recommended_flag_marks_known_good_models(fake_settings, model_root):
    bundled, _ = model_root
    make_model(bundled, "4xNomos8kSC")
    make_model(bundled, "uniscale_restore")

    by_name = {m.name: m for m in catalog.list_models(fake_settings)}

    assert by_name["4xNomos8kSC"].recommended is True
    assert by_name["uniscale_restore"].recommended is False


def test_curated_description_is_used_and_unknown_names_fall_back():
    assert "Nomos" in catalog._describe("4xNomos8kSC")
    assert catalog._describe("brand-new-model")  # never empty


# --------------------------------------------------------------------------- #
# Catalog payload
# --------------------------------------------------------------------------- #


def test_catalog_payload_carries_everything_the_panel_needs(
    fake_settings, model_root, monkeypatch
):
    from config import settings

    bundled, _ = model_root
    make_model(bundled, "4xNomos8kSC")
    monkeypatch.setattr(settings, "UPSCAYL_EXE", None)
    monkeypatch.setattr(runner, "find_cli", lambda cfg=None: None)
    catalog.clear_cache()

    payload = catalog.catalog_payload(settings)

    assert set(payload) >= {
        "models",
        "default_model",
        "sources",
        "directories",
        "resolutions",
        "defaults",
        "neural_available",
        "executable",
        "presets",
    }
    assert payload["default_model"] == "4xNomos8kSC"
    assert [r["long_edge"] for r in payload["resolutions"]] == [2560, 3840, 5120, 6144, 7680]
    assert payload["presets"]["forced_format"] == "jpg"


def test_catalog_payload_reports_a_missing_binary(fake_settings, model_root, monkeypatch):
    bundled, _ = model_root
    make_model(bundled, "4xNomos8kSC")
    # Stub the probe rather than relying on PATH being empty, which is not true
    # on every machine.
    monkeypatch.setattr(runner, "find_cli", lambda cfg=None: None)
    catalog.clear_cache()

    payload = catalog.catalog_payload(fake_settings)

    # The panel warns on this instead of silently producing resampled output.
    assert payload["neural_available"] is False
    assert payload["executable"] is None


def test_catalog_payload_reports_an_available_binary(fake_settings, model_root, monkeypatch):
    bundled, _ = model_root
    make_model(bundled, "4xNomos8kSC")
    monkeypatch.setattr(runner, "find_cli", lambda cfg=None: r"C:\tools\upscayl-bin.exe")
    catalog.clear_cache()

    payload = catalog.catalog_payload(fake_settings)

    assert payload["neural_available"] is True
    assert payload["executable"] == r"C:\tools\upscayl-bin.exe"


def test_catalog_payload_marks_the_default_resolution(
    fake_settings, model_root, monkeypatch
):
    from config import settings

    bundled, _ = model_root
    make_model(bundled, "4xNomos8kSC")
    monkeypatch.setattr(settings, "UPSCAYL_EXE", None)
    monkeypatch.setattr(settings, "UPSCAYL_TARGET_LONG_EDGE", 5120)
    catalog.clear_cache()

    payload = catalog.catalog_payload(settings)

    defaults = [r for r in payload["resolutions"] if r["default"]]
    assert [r["long_edge"] for r in defaults] == [5120]


# --------------------------------------------------------------------------- #
# CLI resolution
# --------------------------------------------------------------------------- #


def test_rejected_names_cover_the_electron_gui():
    # Upscayl.exe is the Electron shell: it ignores every CLI flag, so treating
    # it as the upscaler would silently produce resampled output.
    assert "upscayl.exe" in runner.CLI_REJECTED_NAMES
    assert "upscayl" in runner.CLI_REJECTED_NAMES


def test_find_cli_prefers_the_headless_binary(tmp_path, monkeypatch):
    from config import settings

    app_dir = tmp_path / "upscayl-2.15.0"
    binary = app_dir / "resources" / "bin" / "upscayl-bin.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"MZ")

    # The GUI sits at the app root and must lose to the real binary.
    (app_dir / "Upscayl.exe").write_bytes(b"MZ")

    monkeypatch.setattr(settings, "UPSCAYL_EXE", None)
    monkeypatch.setattr(settings, "UPSCAYL_APP_DIR", app_dir)

    assert runner.find_cli(settings) == str(binary)


def test_find_cli_rejects_an_exe_pointing_at_the_gui(tmp_path, monkeypatch):
    from config import settings

    app_dir = tmp_path / "upscayl-2.15.0"
    gui = app_dir / "Upscayl.exe"
    app_dir.mkdir(parents=True)
    gui.write_bytes(b"MZ")

    monkeypatch.setattr(settings, "UPSCAYL_EXE", gui)
    monkeypatch.setattr(settings, "UPSCAYL_APP_DIR", app_dir)

    # No headless binary anywhere, so the answer is "not available" rather than
    # a path that would ignore our flags.
    assert runner.find_cli(settings) is None


def test_find_cli_accepts_an_explicit_binary(tmp_path, monkeypatch):
    from config import settings

    binary = tmp_path / "upscayl-bin.exe"
    binary.write_bytes(b"MZ")

    monkeypatch.setattr(settings, "UPSCAYL_EXE", binary)

    assert runner.find_cli(settings) == str(binary)


def test_find_cli_accepts_an_app_folder(tmp_path, monkeypatch):
    from config import settings

    binary = tmp_path / "resources" / "bin" / "upscayl-bin.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"MZ")

    monkeypatch.setattr(settings, "UPSCAYL_EXE", tmp_path)

    assert runner.find_cli(settings) == str(binary)


def test_is_neural_available_tracks_find_cli(tmp_path, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "UPSCAYL_EXE", None)
    monkeypatch.setattr(settings, "UPSCAYL_APP_DIR", tmp_path / "absent")
    monkeypatch.setattr(runner, "shutil", type("S", (), {"which": staticmethod(lambda n: None)}))

    assert runner.is_neural_available(settings) is False


# --------------------------------------------------------------------------- #
# Pass planning and measurement
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("longest", "target", "model_scale", "expected"),
    [
        (896, 3840, 4, 2),  # 896*4 = 3584 < 3840, so a second pass is needed
        (2000, 3840, 4, 1),  # 2000*4 = 8000 >= 3840, one pass is enough
        (1200, 1200, 4, 1),
    ],
)
def test_passes_needed(longest, target, model_scale, expected):
    assert runner._passes_needed(longest, target, model_scale) == expected


def test_passes_needed_is_capped():
    # Never chain more than the configured maximum, however large the target.
    assert runner._passes_needed(10, 12000, 4) <= runner.MAX_CLI_PASSES


def test_measure_returns_dimensions_for_a_real_jpeg(sample_jpeg):
    assert runner.measure(sample_jpeg(320, 240)) == (320, 240)


def test_measure_returns_none_for_a_missing_file(tmp_path):
    assert runner.measure(tmp_path / "nope.jpg") is None


def test_measure_accepts_a_string_path(sample_jpeg):
    path = sample_jpeg(200, 100)
    assert runner.measure(str(path)) == (200, 100)
