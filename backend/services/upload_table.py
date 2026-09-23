"""Builds the copy/paste upload table used for Adobe Stock submissions.

This module is the single source of truth for *what a downloaded asset is
called*. Three call sites depend on that name agreeing exactly, because Adobe
matches a CSV row to an uploaded file by filename:

* the CSV exporter (``services/csv_export.py``),
* the single-asset download endpoint,
* the ZIP bundle endpoint.

Adobe's published CSV requirement is **"Filename: 30 characters maximum"**,
counted on the complete filename *including* the extension. That is a hard
portal-side limit, so names are truncated to fit rather than emitted long and
rejected.

Because truncation can make two long titles collide, the length cap alone is not
enough for the ZIP/CSV path: :func:`build_download_name` accepts an optional
``disambiguator`` (normally the record id) which is appended when - and only
when - the slug had to be shortened.
"""

import re
from pathlib import Path

from models import ImageRecord

#: Characters that are unsafe in a download filename.
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

#: Runs of separator characters, collapsed to a single hyphen.
#:
#: Without this, a title like "trailing --- hyphens" produced
#: ``trailing-----hyphens``: ugly in the portal and wasteful of Adobe's
#: 30-character budget, which is counted per character.
_SEPARATOR_RUN = re.compile(r"[-_]{2,}")

#: Adobe: "Filename | 30 characters maximum". Counted on the whole filename.
MAX_FILENAME_LENGTH = 30

#: Reserved room for a disambiguating suffix, e.g. ``-7f3a2b``.
_DISAMBIGUATOR_ROOM = 7


def _slugify(value: str) -> str:
    """Lower-case, hyphen-separated, filesystem-safe token.

    Collapses any run of unsafe characters *and* any run of separator characters
    into a single hyphen, so the result is stable regardless of how the source
    was punctuated.
    """
    cleaned = _UNSAFE_FILENAME.sub("-", value)
    cleaned = _SEPARATOR_RUN.sub("-", cleaned)
    return cleaned.strip("-_").lower()


def _suffix_for(record: ImageRecord, staged_path: Path | str | None) -> str:
    """Extension to use, preferring the file that will actually be uploaded."""
    if staged_path is not None:
        return Path(staged_path).suffix.lower() or ".jpg"

    working = getattr(record, "working_path", None)
    if working:
        return Path(working).suffix.lower() or ".jpg"
    return Path(record.original_path or "").suffix.lower() or ".jpg"


def build_download_name(
    record: ImageRecord,
    staged_path: Path | str | None = None,
    *,
    disambiguator: str | None = None,
    max_length: int = MAX_FILENAME_LENGTH,
) -> str:
    """Human-friendly, Adobe-compliant download filename for a record.

    Prefers the generated title (slugified) so the operator can identify the
    asset after downloading; falls back to the original filename stem, then to
    the record id.

    The extension comes from ``staged_path`` when given, because the CSV must
    name the file exactly as it will be uploaded - and the staged file may be
    the refined JPEG rather than the original upload.

    Args:
        record: The record being named.
        staged_path: The file that will be uploaded, when known.
        disambiguator: Short unique token appended if the slug is truncated.
            Required for correctness whenever several records share a ZIP or
            CSV, because truncation can otherwise collide.
        max_length: Cap on the complete filename, extension included.

    Returns:
        A filename no longer than ``max_length`` characters.
    """
    suffix = _suffix_for(record, staged_path)

    source = (record.generated_title or "").strip()
    if not source:
        source = Path(record.filename or "").stem
    if not source:
        source = record.id

    slug = _slugify(source)

    # Reserve space for the extension; the stem is what gets shortened.
    stem_budget = max(max_length - len(suffix), 1)

    if len(slug) > stem_budget:
        if disambiguator:
            token = _slugify(disambiguator).replace("-", "")[:_DISAMBIGUATOR_ROOM]
            token = token[: max(stem_budget - 1, 1)]
            # Shorten the slug first, then append the token, so the token is
            # never itself truncated away by the length check below.
            head_budget = max(stem_budget - len(token) - 1, 1)
            slug = f"{slug[:head_budget].rstrip('-')}-{token}"
        else:
            slug = slug[:stem_budget].rstrip("-")

    if not slug:
        slug = _slugify(record.id)[:stem_budget] or "asset"

    return f"{slug}{suffix}"


def build_upload_row(
    record: ImageRecord,
    base_url: str,
    *,
    staged_path: Path | str | None = None,
    disambiguator: str | None = None,
) -> dict:
    """Convert a READY record into a single upload-table row."""
    # Imported here rather than at module scope: `asset_naming` imports from
    # this module (for the slug rule and the length cap), so a top-level import
    # would be circular.
    from services import asset_naming

    keywords = [str(keyword) for keyword in (record.generated_keywords or [])]
    thumbnail_url = None
    if record.thumbnail_path:
        thumbnail_name = Path(record.thumbnail_path).name
        thumbnail_url = f"{base_url}/thumbnails/{thumbnail_name}"

    return {
        "record_id": record.id,
        # The upload table is what the operator copies from when pasting into the
        # portal, so it must show the same name the CSV and ZIP use - including
        # an operator-chosen override.
        "filename": asset_naming.effective_download_name(record, staged_path),
        "title": record.generated_title or "",
        "description": record.generated_description or "",
        "keywords": keywords,
        "keywords_csv": ", ".join(keywords),
        "thumbnail_url": thumbnail_url,
        "download_url": f"{base_url}/api/records/{record.id}/download",
    }
