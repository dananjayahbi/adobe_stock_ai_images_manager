"""Builds the copy/paste upload table used for Adobe Stock submissions."""

import re
from pathlib import Path

from models import ImageRecord

# Characters that are unsafe in a download filename.
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def build_download_name(record: ImageRecord) -> str:
    """Human-friendly download filename for a record.

    Prefers the generated title (slugified) so the operator can identify the
    asset after downloading; falls back to the original filename.
    """
    suffix = Path(record.original_path or "").suffix.lower() or ".jpg"
    source = (record.generated_title or "").strip()

    if source:
        slug = _UNSAFE_FILENAME.sub("-", source).strip("-")[:80].lower()
        if slug:
            return f"{slug}{suffix}"

    original = Path(record.filename or "").stem
    slug = _UNSAFE_FILENAME.sub("-", original).strip("-")[:80].lower()
    return f"{slug or record.id}{suffix}"


def build_upload_row(record: ImageRecord, base_url: str) -> dict:
    """Convert a READY record into a single upload-table row."""
    keywords = [str(keyword) for keyword in (record.generated_keywords or [])]
    thumbnail_url = None
    if record.thumbnail_path:
        thumbnail_name = Path(record.thumbnail_path).name
        thumbnail_url = f"{base_url}/thumbnails/{thumbnail_name}"

    return {
        "record_id": record.id,
        "filename": record.filename,
        "title": record.generated_title or "",
        "description": record.generated_description or "",
        "keywords": keywords,
        "keywords_csv": ", ".join(keywords),
        "thumbnail_url": thumbnail_url,
        "download_url": f"{base_url}/api/records/{record.id}/download",
    }
