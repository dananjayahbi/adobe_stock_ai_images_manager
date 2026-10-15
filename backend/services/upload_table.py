"""Builds the copy/paste upload table used for Adobe Stock submissions.

This module is the single source of truth for *what a downloaded asset is
called*. Three call sites depend on that name agreeing exactly, because Adobe
matches a CSV row to an uploaded file by filename:

* the CSV exporter (``services/csv_export.py``),
* the single-asset download endpoint,
* the ZIP bundle endpoint.

Adobe's CSV guidance *lists* **"Filename: 30 characters maximum"**, but that
figure is advisory (the uploader accepts longer names — the enforced rule is
that the CSV Filename matches the uploaded file exactly). Names are therefore
kept full and descriptive, truncated only to a filesystem-safe cap
(``settings.CSV_MAX_FILENAME_LENGTH``, currently 100) rather than clipped at 30.

Because long titles can still collide, a *batch* de-duplicates its names before
export (see :func:`services.asset_naming.deduplicate`), carving the numeric
suffix out of the stem so the full name still fits the cap.
"""

import re
from pathlib import Path

from config import settings
from models import ImageRecord

#: Characters that are unsafe in a download filename.
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

#: Runs of separator characters, collapsed to a single hyphen.
#:
#: Without this, a title like "trailing --- hyphens" produced
#: ``trailing-----hyphens``: ugly in the portal and wasteful of the filename
#: budget, which is counted per character.
_SEPARATOR_RUN = re.compile(r"[-_]{2,}")

#: Full delivered filename cap, including the extension. Adobe's "30 characters"
#: figure is advisory; this is the tool's filesystem-safe ceiling
#: (:data:`config.CSV_MAX_FILENAME_LENGTH`).
MAX_FILENAME_LENGTH = settings.CSV_MAX_FILENAME_LENGTH


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
    max_length: int = MAX_FILENAME_LENGTH,
) -> str:
    """Human-friendly, Adobe-compliant download filename for a record.

    Prefers the generated title (slugified) so the operator can identify the
    asset after downloading; falls back to the original filename stem, then to
    the record id.

    The extension comes from ``staged_path`` when given, because the CSV must
    name the file exactly as it will be uploaded - and the staged file may be
    the refined JPEG rather than the original upload.

    The name is **derived from the title alone**, with no identifier mixed in.

    An earlier version appended a short token carved out of the record id
    whenever the slug had to be truncated, which produced names like
    ``futuristic-automat-b2d58dd.jpg``: the operator sees a filename with a
    meaningless code in it, and the filename is a *deliverable* here, not an
    internal key. Uniqueness inside a batch is handled where the batch is known
    - by :func:`services.asset_naming.deduplicate`, which appends a readable
    ``-2``/``-3`` only on an actual collision - so this function does not need
    to guess.

    Args:
        record: The record being named.
        staged_path: The file that will be uploaded, when known.
        max_length: Cap on the complete filename, extension included. Callers
            that must fit a suffix onto the name pass a smaller figure.

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
        slug = slug[:stem_budget].rstrip("-")

    if not slug:
        slug = _slugify(record.id)[:stem_budget] or "asset"

    return f"{slug}{suffix}"


def build_upload_row(
    record: ImageRecord,
    base_url: str,
    *,
    staged_path: Path | str | None = None,
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
