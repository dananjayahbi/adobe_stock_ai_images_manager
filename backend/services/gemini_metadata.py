"""Metadata generator - titles and keywords via the local LLM gateway."""

import logging
from pathlib import Path

from config import settings
from services.llm_client import LLMError, chat_json

logger = logging.getLogger(__name__)

FORBIDDEN_TAGS = {"ai", "generative", "stock", "midjourney", "illustration", "image", "nobody", "copyspace"}

METADATA_PROMPT = """Generate Adobe Stock optimized metadata for this image. Respond with ONLY valid JSON (no markdown fences):
{
  "title": "<string, max 140 characters, natural English, descriptive, commercially appealing>",
  "description": "<string, detailed description of the image content>",
  "keywords": ["<25-35 relevant keyword strings, ordered most important first>"]

Rules:
- Title must be under 140 characters, natural English, descriptive
- Keywords must number between 25 and 35, ordered from most to least important
- Top 5 keywords must describe subject matter, action depicted, or dominant colors
- Do NOT include any of these forbidden terms: AI, generative, stock, midjourney, illustration, image, nobody, copyspace
- Do NOT include any trademarked terms, brand names, or copyrighted character references
}"""


def generate_metadata(file_path: str | Path, api_key: str | None = None) -> dict | None:
    """Generate title, description, and keywords for an approved image.

    Args:
        file_path: Path to the image file.
        api_key: Retained for call-site compatibility; the gateway key comes
            from settings.LLM_API_KEY (or the legacy GEMINI_API_KEY).

    Returns dict with title, description, keywords or None on failure.
    """
    if api_key:
        logger.debug("generate_metadata: explicit api_key ignored; using configured gateway key")

    try:
        data = chat_json(file_path, METADATA_PROMPT, temperature=0.2)
    except LLMError as exc:
        logger.error("Metadata generation failed for %s: %s", file_path, exc)
        return None

    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    keywords = data.get("keywords", [])

    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(kw).strip() for kw in keywords if str(kw).strip()]

    # Post-processing: truncate title at a word boundary
    if len(title) > 150:
        truncated = title[:150]
        last_space = truncated.rfind(" ")
        if last_space > 100:
            title = truncated[:last_space] + "..."
        else:
            title = truncated

    # Cap at 200 chars per user spec, plan says 140 but user says 200
    title = title[:200]

    # Post-processing: strip forbidden tags
    cleaned_keywords = [
        kw for kw in keywords if kw.lower() not in FORBIDDEN_TAGS
    ]

    # Cap at 35
    cleaned_keywords = cleaned_keywords[:35]

    if not title:
        logger.warning("Generated metadata has empty title for %s", file_path)
        return None

    return {
        "title": title,
        "description": description,
        "keywords": cleaned_keywords,
    }
