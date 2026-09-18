"""Deterministic technical quality-control audit for registered image artifacts."""

from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path

import cv2
from PIL import Image, UnidentifiedImageError

from app.core.policy import CheckSeverity, PolicyBaseline


class AuditOutcome(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class CheckResult:
    rule_id: str
    passed: bool
    severity: CheckSeverity
    outcome: str
    message: str
    observed_value: object = None
    threshold: object = None
    detector_version: str = "wave5-qc-1"


@dataclass(frozen=True)
class TechnicalAudit:
    input_hash: str
    policy_version: str
    checks: tuple[CheckResult, ...]
    outcome: AuditOutcome
    eligible: bool

    def check(self, rule_id: str) -> CheckResult:
        return next(check for check in self.checks if check.rule_id == rule_id)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _resolution(image: Image.Image, policy: PolicyBaseline) -> CheckResult:
    megapixels = image.width * image.height / 1_000_000
    passed = megapixels >= policy.minimum_megapixels
    outcome = "PASS" if passed else "FAIL"
    return CheckResult(
        "RESOLUTION", passed, CheckSeverity.HARD, outcome,
        "Decoded dimensions meet the minimum." if passed else "Decoded dimensions are below the minimum.",
        {"width": image.width, "height": image.height, "megapixels": round(megapixels, 6), "aspect_ratio": image.width / image.height},
        policy.minimum_megapixels,
    )


def _color(image: Image.Image) -> CheckResult:
    passed = image.mode == "RGB"
    return CheckResult(
        "COLOR_SPACE", passed, CheckSeverity.INFO if passed else CheckSeverity.WARNING,
        "PASS" if passed else "REVIEW_REQUIRED",
        "RGB artifact requires no channel conversion." if passed else "Non-RGB or transparency requires explicit normalization review.",
        {"mode": image.mode, "profile": bool(image.info.get("icc_profile"))},
    )


def _jpeg(path: Path, image: Image.Image, policy: PolicyBaseline) -> CheckResult:
    valid = image.format == "JPEG" and image.mode == "RGB" and path.stat().st_size <= policy.maximum_file_size_mb * 1024 * 1024
    severity = CheckSeverity.HARD if image.format == "JPEG" and image.mode == "RGB" else CheckSeverity.WARNING
    return CheckResult(
        "JPEG_STRUCTURE", valid, severity, "PASS" if valid else ("REVIEW_REQUIRED" if severity is CheckSeverity.WARNING else "FAIL"),
        "JPEG structure and size are valid." if valid else "Artifact is not a valid bounded RGB JPEG.",
        {"format": image.format, "bytes": path.stat().st_size, "mode": image.mode},
        {"format": "JPEG", "maximum_bytes": policy.maximum_file_size_mb * 1024 * 1024},
    )


def _sharpness(path: Path, policy: PolicyBaseline) -> CheckResult:
    pixels = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if pixels is None:
        return CheckResult("SHARPNESS", False, CheckSeverity.WARNING, "NOT_EVALUATED", "Unable to decode grayscale pixels.")
    measured = round(float(cv2.Laplacian(pixels, cv2.CV_64F).var()), 6)
    passed = measured >= policy.sharpness_warning_threshold
    return CheckResult(
        "SHARPNESS", passed, CheckSeverity.INFO if passed else CheckSeverity.WARNING,
        "PASS" if passed else "WARN",
        "Laplacian variance is above the provisional calibration point." if passed else "Laplacian variance is below the provisional calibration point; inspect visually.",
        measured, policy.sharpness_warning_threshold,
    )


def _ocr(path: Path) -> CheckResult:
    try:
        import pytesseract
        from PIL import Image as PilImage
        text = pytesseract.image_to_string(PilImage.open(path), config="--psm 11").strip()
    except Exception:
        return CheckResult("OCR", False, CheckSeverity.WARNING, "NOT_EVALUATED", "OCR is unavailable or failed.")
    token_count = len(text.split())
    return CheckResult(
        "OCR", True, CheckSeverity.INFO, "WARN" if token_count else "PASS",
        "Text detected; human review is required for readability and rights context." if token_count else "No text was detected.",
        {"detected_token_count": token_count},
    )


def run_technical_qc(path: Path, policy: PolicyBaseline) -> TechnicalAudit:
    path = Path(path)
    input_hash = _hash(path)
    try:
        with Image.open(path) as image:
            image.load()
            checks = (_resolution(image, policy), _color(image), _jpeg(path, image, policy), _sharpness(path, policy), _ocr(path))
    except (UnidentifiedImageError, OSError, ValueError):
        checks = (CheckResult("DECODE", False, CheckSeverity.HARD, "NOT_EVALUATED", "Artifact could not be decoded."),)

    if any(not check.passed and check.severity is CheckSeverity.HARD for check in checks):
        outcome = AuditOutcome.FAIL
    elif any(check.outcome == "NOT_EVALUATED" for check in checks):
        outcome = AuditOutcome.NOT_EVALUATED
    elif any(check.outcome == "REVIEW_REQUIRED" for check in checks):
        outcome = AuditOutcome.REVIEW_REQUIRED
    elif any(check.outcome == "WARN" for check in checks):
        outcome = AuditOutcome.WARN
    else:
        outcome = AuditOutcome.PASS
    return TechnicalAudit(input_hash, policy.version, checks, outcome, outcome in {AuditOutcome.PASS, AuditOutcome.WARN})
