from pathlib import Path

from PIL import Image, ImageDraw

from app.core.policy import PolicyBaseline
from app.qc import AuditOutcome, run_technical_qc


def save_image(path: Path, size=(2000, 2000), color=(30, 80, 150), fmt="JPEG"):
    Image.new("RGB", size, color).save(path, format=fmt, quality=92)


def test_resolution_boundary_and_jpeg_checks(tmp_path: Path):
    image = tmp_path / "large.jpg"
    save_image(image, (2000, 2000))

    audit = run_technical_qc(image, PolicyBaseline())

    assert audit.outcome in {AuditOutcome.PASS, AuditOutcome.WARN, AuditOutcome.NOT_EVALUATED}
    assert audit.check("RESOLUTION").observed_value["megapixels"] == 4.0
    assert audit.check("JPEG_STRUCTURE").passed is True
    assert audit.input_hash
    assert audit.policy_version == "wave1-baseline-2026-09"


def test_low_resolution_is_hard_failure_and_blocks_eligibility(tmp_path: Path):
    image = tmp_path / "small.jpg"
    save_image(image, (100, 100))

    audit = run_technical_qc(image, PolicyBaseline())

    resolution = audit.check("RESOLUTION")
    assert resolution.passed is False
    assert resolution.severity.value == "hard"
    assert audit.outcome is AuditOutcome.FAIL
    assert audit.eligible is False


def test_rgba_png_is_explicitly_review_required_not_silently_srgb(tmp_path: Path):
    image = tmp_path / "transparent.png"
    Image.new("RGBA", (2000, 2000), (30, 80, 150, 100)).save(image, format="PNG")

    audit = run_technical_qc(image, PolicyBaseline())

    color = audit.check("COLOR_SPACE")
    assert color.passed is False
    assert color.severity.value == "warning"
    assert audit.outcome in {AuditOutcome.REVIEW_REQUIRED, AuditOutcome.NOT_EVALUATED}


def test_sharpness_result_is_repeatable_and_ocr_is_non_blocking(tmp_path: Path):
    image = tmp_path / "text.jpg"
    canvas = Image.new("RGB", (2000, 2000), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((100, 100), "Sample label", fill="black")
    canvas.save(image, format="JPEG", quality=92)

    first = run_technical_qc(image, PolicyBaseline())
    second = run_technical_qc(image, PolicyBaseline())

    assert first.check("SHARPNESS").observed_value == second.check("SHARPNESS").observed_value
    assert first.check("OCR").outcome in {"PASS", "WARN", "REVIEW_REQUIRED", "NOT_EVALUATED"}
    assert first.check("OCR").severity.value in {"info", "warning"}
