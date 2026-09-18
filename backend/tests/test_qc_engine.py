"""Unit tests for the deterministic QC engine."""

from services import qc_engine


def test_resolution_passes_at_four_megapixels(sample_jpeg):
    result = qc_engine.check_resolution(sample_jpeg(2000, 2000))

    assert result["passed"] is True
    assert result["width"] == 2000
    assert result["height"] == 2000
    assert result["megapixels"] == 4.0


def test_resolution_fails_below_threshold(sample_jpeg):
    result = qc_engine.check_resolution(sample_jpeg(1000, 1000))

    assert result["passed"] is False
    assert result["megapixels"] == 1.0
    assert result["reason"]


def test_sharpness_returns_variance_and_fails_on_flat_image(sample_jpeg):
    detailed = qc_engine.check_sharpness(sample_jpeg(800, 800))
    flat = qc_engine.check_sharpness(sample_jpeg(800, 800, solid=True, name="flat.jpg"))

    assert isinstance(detailed["laplacian_variance"], float)
    assert detailed["laplacian_variance"] > 0
    # A solid-color image has no edges, so variance collapses to ~0.
    assert flat["passed"] is False
    assert flat["laplacian_variance"] < 120.0


def test_color_space_reports_srgb(sample_jpeg):
    result = qc_engine.check_color_space(sample_jpeg(600, 600))

    assert result["passed"] is True
    assert result["color_space"]


def test_run_all_checks_returns_aggregate(sample_jpeg):
    result = qc_engine.run_all_checks(sample_jpeg(2000, 2000))

    assert set(result) == {"passed", "checks", "reasons"}
    assert result["passed"] is True
    assert result["reasons"] == []
    assert set(result["checks"]) == {"resolution", "sharpness", "color_space", "text_ocr"}
    assert result["checks"]["resolution"]["passed"] is True


def test_run_all_checks_fails_for_missing_file(tmp_path):
    result = qc_engine.run_all_checks(tmp_path / "does-not-exist.jpg")

    assert result["passed"] is False
    assert result["checks"] == {}
    assert "File not found" in result["reasons"][0]
