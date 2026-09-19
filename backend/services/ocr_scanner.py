"""OCR scanner - Stage 2 text detection.

Distinct from ``services.qc_engine.check_text_ocr`` in three ways:

* It reports a per-word confidence so the operator can see *why* an image was
  rejected rather than a bare boolean.
* It classifies the finding as ``none``, ``gibberish`` (AI artefact noise) or
  ``embedded_text`` (readable words), because Adobe rejects both but for
  different reasons.
* It never fails the caller: an unavailable Tesseract binary yields a
  ``skipped`` result so the batch continues.
"""

from __future__ import annotations

import io
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

#: Well-known install locations, checked when ``tesseract`` is not on PATH.
_TESSERACT_FALLBACKS = (
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe",
)

#: Longest edge used for the OCR pass. Text detection does not benefit from
#: full resolution and downscaling roughly halves the runtime.
OCR_MAX_DIM = 1600

#: Below this many characters, a detection is treated as noise rather than text.
MIN_TEXT_LENGTH = 4

#: Mean word confidence below which a detection is considered gibberish.
GIBBERISH_CONFIDENCE = 60.0

#: Unique-character ratio below which the text is judged non-linguistic.
GIBBERISH_UNIQUE_RATIO = 0.40

_tesseract_path: str | None = None
_tesseract_checked = False


def resolve_tesseract() -> str | None:
    """Locate the Tesseract binary once per process, or None when absent."""
    global _tesseract_path, _tesseract_checked
    if _tesseract_checked:
        return _tesseract_path

    found = shutil.which("tesseract")
    if not found:
        for candidate in _TESSERACT_FALLBACKS:
            if candidate.exists():
                found = str(candidate)
                break

    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        logger.info("OCR scanner using Tesseract at %s", found)
    else:
        logger.warning(
            "Tesseract not found on PATH or at known locations; OCR will be skipped"
        )

    _tesseract_path = found
    _tesseract_checked = True
    return found


def is_available() -> bool:
    """True when a Tesseract binary can be resolved."""
    return resolve_tesseract() is not None


@dataclass
class OcrResult:
    """Outcome of scanning one image for text."""

    text_detected: bool
    classification: str  # "none" | "gibberish" | "embedded_text" | "skipped"
    text: str = ""
    mean_confidence: float = 0.0
    word_count: int = 0
    reason: str = ""
    #: True when the image should be blocked from further processing.
    blocked: bool = False
    #: Per-word findings, capped to keep the JSON payload small.
    words: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text_detected": self.text_detected,
            "classification": self.classification,
            "text": self.text,
            "mean_confidence": round(self.mean_confidence, 2),
            "word_count": self.word_count,
            "reason": self.reason,
            "blocked": self.blocked,
            "words": self.words,
        }


def _classify(text: str, mean_confidence: float) -> tuple[str, str, bool]:
    """Decide whether detected text is gibberish or readable.

    Returns ``(classification, reason, blocked)``.
    """
    if len(text) < MIN_TEXT_LENGTH:
        return "none", "", False

    condensed = text.lower().replace(" ", "")
    unique_ratio = len(set(condensed)) / max(len(condensed), 1)

    # Two independent gibberish signals: a model spitting out pseudo-glyphs
    # scores low on character variety, and Tesseract itself is unsure.
    if unique_ratio < GIBBERISH_UNIQUE_RATIO or mean_confidence < GIBBERISH_CONFIDENCE:
        return (
            "gibberish",
            "Gibberish text detected - a common generative AI artefact.",
            True,
        )

    return (
        "embedded_text",
        f"Readable text detected in the image: '{text[:120]}'",
        True,
    )


def scan_text(file_path: str | Path) -> OcrResult:
    """Scan an image for embedded text.

    Args:
        file_path: Image to scan.

    Returns:
        An :class:`OcrResult`. When Tesseract is unavailable the result is
        ``skipped`` and ``blocked`` is False, so an environment problem never
        silently deletes an image from the pipeline.
    """
    if not is_available():
        return OcrResult(
            text_detected=False,
            classification="skipped",
            reason="Tesseract is not installed; OCR was skipped.",
        )

    path = Path(file_path)
    if not path.exists():
        return OcrResult(
            text_detected=False,
            classification="skipped",
            reason=f"File not found: {file_path}",
        )

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if max(img.size) > OCR_MAX_DIM:
                img.thumbnail((OCR_MAX_DIM, OCR_MAX_DIM), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
        buffer.seek(0)

        with Image.open(buffer) as prepared:
            data = pytesseract.image_to_data(
                prepared, output_type=pytesseract.Output.DICT
            )
    except Exception as exc:  # noqa: BLE001 - OCR must never break the batch
        logger.exception("OCR scan failed for %s", path)
        return OcrResult(
            text_detected=False,
            classification="skipped",
            reason=f"OCR error (skipped): {exc}",
        )

    words: list[dict] = []
    confidences: list[float] = []
    for index, raw_text in enumerate(data.get("text", [])):
        token = (raw_text or "").strip()
        if not token:
            continue
        try:
            confidence = float(data["conf"][index])
        except (KeyError, IndexError, TypeError, ValueError):
            confidence = -1.0
        if confidence < 0:
            continue

        confidences.append(confidence)
        words.append(
            {
                "text": token,
                "confidence": round(confidence, 1),
                "left": int(data["left"][index]),
                "top": int(data["top"][index]),
                "width": int(data["width"][index]),
                "height": int(data["height"][index]),
            }
        )

    text = " ".join(word["text"] for word in words).strip()
    mean_confidence = (
        sum(confidences) / len(confidences) if confidences else 0.0
    )
    classification, reason, blocked = _classify(text, mean_confidence)

    return OcrResult(
        text_detected=bool(text),
        classification=classification,
        text=text[:2000],
        mean_confidence=mean_confidence,
        word_count=len(words),
        reason=reason,
        blocked=blocked,
        # Keep the payload bounded; the modal only needs a sample.
        words=words[:60],
    )
