"""Semantic quality control via the local OpenAI-compatible LLM gateway."""

import logging
from pathlib import Path

from config import settings
from services.llm_client import LLMError, chat_json

logger = logging.getLogger(__name__)

AUDIT_PROMPT = """Analyze this image for commercial stock photography viability. Evaluate for:
1. AI generation artifacts (unnatural textures, repeating patterns, melting boundaries, extra fingers, asymmetric features)
2. Anatomical issues (impossible geometry, distorted body parts)
3. Aesthetic quality (composition, lighting, color balance)
4. Commercial viability (would a buyer use this for advertising, editorial, or design?)
5. IP/trademark violations (recognizable logos, copyrighted characters, branded products)

Respond with ONLY valid JSON (no markdown fences) containing exactly these fields:
{
  "confidence_score": <float 0.0-1.0>,
  "flags": [<list of string issues found>],
  "is_commercially_viable": <boolean>
}

A confidence_score >= 0.75 means the image is acceptable. Lower scores indicate problems."""


def audit_image(file_path: str | Path, api_key: str | None = None) -> dict:
    """Send image to the LLM gateway for semantic QC analysis.

    Args:
        file_path: Path to the image file.
        api_key: Retained for call-site compatibility; the gateway key comes
            from settings.LLM_API_KEY (or the legacy GEMINI_API_KEY).

    Returns dict with passed, confidence_score, flags, reason.
    """
    if api_key:
        logger.debug("audit_image: explicit api_key ignored; using configured gateway key")

    try:
        data = chat_json(file_path, AUDIT_PROMPT, temperature=0.1)
    except LLMError as exc:
        logger.error("Semantic audit failed for %s: %s", file_path, exc)
        return {
            "passed": False,
            "confidence_score": 0.0,
            "flags": [],
            "reason": f"Semantic audit failed: {exc}",
        }

    confidence = float(data.get("confidence_score", 0.0) or 0.0)
    flags = data.get("flags", [])
    if not isinstance(flags, list):
        flags = [str(flags)]
    flags = [str(f) for f in flags]
    is_viable = data.get("is_commercially_viable", False)

    confidence = max(0.0, min(1.0, confidence))
    passed = confidence >= settings.MIN_SEMANTIC_CONFIDENCE

    reason = ""
    if not passed:
        reason = (
            f"Semantic confidence {confidence:.2f} below threshold "
            f"{settings.MIN_SEMANTIC_CONFIDENCE}"
        )
        if flags:
            reason += f". Flags: {'; '.join(flags[:5])}"
    elif not is_viable:
        passed = False
        reason = "Image deemed not commercially viable by semantic audit"

    return {
        "passed": passed,
        "confidence_score": confidence,
        "flags": flags,
        "reason": reason,
    }
