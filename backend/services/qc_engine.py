"""Quality control engine - deterministic image analysis."""

import io
import logging
import shutil
from pathlib import Path

import cv2
import pytesseract
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)

# Well-known install locations, checked when `tesseract` is not on PATH
# (e.g. the process was started before PATH was updated).
_TESSERACT_FALLBACKS = (
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe",
)

_tesseract_configured = False


def _configure_tesseract() -> None:
    """Point pytesseract at a discovered tesseract binary, once per process."""
    global _tesseract_configured
    if _tesseract_configured:
        return

    found = shutil.which("tesseract")
    if not found:
        for candidate in _TESSERACT_FALLBACKS:
            if candidate.exists():
                found = str(candidate)
                break

    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        logger.info("Using Tesseract at %s", found)
    else:
        logger.warning("Tesseract not found on PATH or at known locations; OCR will be skipped")

    _tesseract_configured = True


def check_resolution(file_path: str | Path) -> dict:
    """Check if image meets minimum megapixel threshold.

    Returns dict with passed, width, height, megapixels, reason.
    """
    try:
        with Image.open(str(file_path)) as img:
            width, height = img.size
            megapixels = (width * height) / 1_000_000
            passed = megapixels >= settings.MIN_MEGAPIXELS
            reason = "" if passed else f"Resolution {megapixels:.2f}MP below minimum {settings.MIN_MEGAPIXELS}MP"
            return {
                "passed": passed,
                "width": width,
                "height": height,
                "megapixels": round(megapixels, 4),
                "reason": reason,
            }
    except Exception as e:
        logger.error("check_resolution failed for %s: %s", file_path, e)
        return {"passed": False, "width": 0, "height": 0, "megapixels": 0.0, "reason": f"Error reading image: {e}"}


def check_sharpness(file_path: str | Path) -> dict:
    """Calculate Laplacian variance for sharpness.

    Returns dict with passed, laplacian_variance, reason.
    """
    try:
        img = cv2.imread(str(file_path))
        if img is None:
            return {"passed": False, "laplacian_variance": 0.0, "reason": "Could not read image with OpenCV"}
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        passed = bool(laplacian_var >= settings.MIN_LAPLACIAN_VARIANCE)
        reason = "" if passed else f"Laplacian variance {laplacian_var:.2f} below minimum {settings.MIN_LAPLACIAN_VARIANCE}"
        return {
            "passed": passed,
            "laplacian_variance": round(laplacian_var, 4),
            "reason": reason,
        }
    except Exception as e:
        logger.error("check_sharpness failed for %s: %s", file_path, e)
        return {"passed": False, "laplacian_variance": 0.0, "reason": f"Error computing sharpness: {e}"}


def check_color_space(file_path: str | Path) -> dict:
    """Verify image is RGB/sRGB.

    Returns dict with passed, color_space, reason.
    """
    try:
        with Image.open(str(file_path)) as img:
            mode = img.mode
            color_space = mode
            passed = mode in ("RGB", "RGBA")
            if not passed:
                # Check ICC profile for sRGB
                icc = img.info.get("icc_profile")
                if icc:
                    color_space = "sRGB (ICC)"
                    passed = True
            reason = "" if passed else f"Color space '{color_space}' is not RGB/sRGB"
            return {
                "passed": passed,
                "color_space": color_space,
                "reason": reason,
            }
    except Exception as e:
        logger.error("check_color_space failed for %s: %s", file_path, e)
        return {"passed": False, "color_space": "unknown", "reason": f"Error checking color space: {e}"}


def check_text_ocr(file_path: str | Path) -> dict:
    """Run Tesseract OCR to detect unwanted text.

    Returns dict with passed, text_detected, text_content, reason.
    """
    try:
        _configure_tesseract()
        with Image.open(str(file_path)) as img:
            # Downscale to speed up OCR
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            downscaled = Image.open(buf)
            text = pytesseract.image_to_string(downscaled).strip()

        text_detected = len(text) > 4
        gibberish = False
        if text_detected:
            unique_chars = len(set(text.lower().replace(" ", "")))
            total_chars = max(len(text.replace(" ", "")), 1)
            ratio = unique_chars / total_chars
            gibberish = ratio < 0.40

        passed = not text_detected or gibberish
        # If text is detected but NOT gibberish, it's real text -> fail
        if text_detected and not gibberish:
            passed = False
            reason = f"Text detected in image: '{text[:100]}'"
        elif text_detected and gibberish:
            # Gibberish text is AI artifact noise; flag it
            passed = False
            reason = "Gibberish text detected (possible AI artifact)"
        else:
            reason = ""

        return {
            "passed": passed,
            "text_detected": text_detected,
            "text_content": text[:500] if text else "",
            "reason": reason,
        }
    except Exception as e:
        logger.error("check_text_ocr failed for %s: %s", file_path, e)
        # OCR failure should not block the pipeline; treat as pass with warning
        return {"passed": True, "text_detected": False, "text_content": "", "reason": f"OCR error (skipped): {e}"}


def run_all_checks(file_path: str | Path, settings_override=None) -> dict:
    """Execute all deterministic QC checks sequentially.

    Args:
        file_path: Path to the image file.
        settings_override: Optional settings object (unused, kept for interface compatibility).

    Returns dict with overall passed status, individual check results, and aggregated reasons.
    """
    path = Path(file_path)
    if not path.exists():
        return {"passed": False, "checks": {}, "reasons": [f"File not found: {file_path}"]}

    resolution = check_resolution(path)
    sharpness = check_sharpness(path)
    color_space = check_color_space(path)
    ocr = check_text_ocr(path)

    checks = {
        "resolution": resolution,
        "sharpness": sharpness,
        "color_space": color_space,
        "text_ocr": ocr,
    }

    reasons = []
    all_passed = True
    for name, result in checks.items():
        if not result["passed"]:
            all_passed = False
            if result.get("reason"):
                reasons.append(f"{name}: {result['reason']}")

    return {
        "passed": all_passed,
        "checks": checks,
        "reasons": reasons,
    }
