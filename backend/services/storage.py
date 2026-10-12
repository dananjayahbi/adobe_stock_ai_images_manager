"""Storage management - directory creation, file saving, thumbnail generation."""

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)


def create_data_directories() -> None:
    """Create every storage directory the pipeline writes to on startup."""
    for dir_path in [
        settings.INBOX_DIR,
        settings.THUMBNAILS_DIR,
        settings.READY_DIR,
        settings.REFINED_DIR,
        settings.UPSCALED_DIR,
        settings.CONVERTED_DIR,
        settings.REMOVED_DIR,
        settings.WHITE_DIR,
        settings.SRGB_DIR,
        settings.QUARANTINE_DIR,
    ]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)


async def save_uploaded_file(upload_file: UploadFile, inbox_dir: Path) -> tuple[str, Path]:
    """Save an uploaded file to the inbox directory with a UUID filename.

    Returns:
        Tuple of (uuid_filename, full_path).
    """
    ext = Path(upload_file.filename or "file.jpg").suffix.lower()
    uuid_filename = f"{uuid.uuid4().hex}{ext}"
    full_path = Path(inbox_dir) / uuid_filename

    # Write atomically via temp file
    tmp_path = full_path.with_suffix(".tmp")
    with open(tmp_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    tmp_path.rename(full_path)

    return uuid_filename, full_path


def generate_thumbnail(source_path: Path | str, thumbnails_dir: Path | str, file_uuid: str) -> str:
    """Generate a 400x400 thumbnail using Pillow, maintaining aspect ratio.

    Saves as JPEG quality 85 with thumb_ prefix.
    Returns the thumbnail path as a string, or empty string on failure.
    """
    source = Path(source_path)
    thumb_dir = Path(thumbnails_dir)
    thumb_name = f"thumb_{file_uuid}.jpg"
    thumb_path = thumb_dir / thumb_name

    try:
        with Image.open(source) as img:
            img.thumbnail((400, 400), Image.Resampling.LANCZOS)
            # Convert to RGB if necessary (e.g., RGBA PNGs)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(str(thumb_path), "JPEG", quality=85)
        return str(thumb_path)
    except Exception:
        logger.exception("Failed to generate thumbnail for %s", source)
        return ""


def copy_to_ready(source_path: Path | str, ready_dir: Path | str, file_uuid: str) -> str:
    """Copy file from inbox to ready_to_upload preserving metadata.

    Returns the destination path as a string.
    """
    source = Path(source_path)
    dest = Path(ready_dir) / f"{file_uuid}{source.suffix.lower()}"
    shutil.copy2(str(source), str(dest))
    return str(dest)


def resolve_ready_path(record, ready_dir: Path | str | None = None) -> Path | None:
    """Return the staged ready-to-upload file for a record, if it exists.

    The staged filename is derived from the record id, but the *extension*
    depends on which file was staged: the inbox original for legacy approvals,
    or the refined/upscaled JPEG for stage-pipeline approvals. Probing the
    directory for ``{id}.*`` keeps both working without an extra DB column.
    """
    if record is None:
        return None

    ready_root = Path(ready_dir or settings.READY_DIR)
    record_id = getattr(record, "id", None)
    if not record_id:
        return None

    # Explicit candidate first: the recorded working file's extension is the
    # most likely match and avoids a directory scan in the common case.
    working = getattr(record, "working_path", None)
    suffixes: list[str] = []
    if working:
        suffixes.append(Path(working).suffix.lower())
    original = getattr(record, "original_path", None)
    if original:
        suffixes.append(Path(original).suffix.lower())
    suffixes.extend([".jpg", ".jpeg"])

    for suffix in dict.fromkeys(s for s in suffixes if s):
        candidate = ready_root / f"{record_id}{suffix}"
        if candidate.is_file():
            return candidate

    # Fall back to a scan so an unusual extension is still found.
    if ready_root.is_dir():
        for candidate in sorted(ready_root.glob(f"{record_id}.*")):
            if candidate.is_file() and candidate.suffix.lower() != ".tmp":
                return candidate

    return None


def resolve_current_path(record) -> Path | None:
    """The record's best file **on disk right now**, or ``None`` if it has none.

    Working copy first, then the inbox original — the same preference the
    publish path uses (``audit_orchestrator._resolve_staging_source``), so
    bundling a not-yet-published record ships exactly the bytes a later
    publish would stage.

    Existence is checked, unlike ``_current_path`` in the orchestrators: a
    path column can outlive the file behind it (tests, moved storage), and
    handing a missing file to the ZIP archiver is a 500, not a fallback.
    """
    if record is None:
        return None
    for candidate in (
        getattr(record, "working_path", None),
        getattr(record, "original_path", None),
    ):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def delete_record_files(record, cfg=None) -> list[str]:
    """Remove every on-disk artifact owned by a record.

    Deletes the inbox original, the generated thumbnail, the staged
    ready-to-upload copy, and any Stage 3/4 working copies (upscaled, refined),
    plus the Collector's PNG-to-JPEG conversion. Missing files are ignored.

    Returns the list of paths that were successfully removed.
    """
    removed: list[str] = []
    candidates: list[Path | None] = [
        Path(record.original_path) if record.original_path else None,
        Path(record.thumbnail_path) if record.thumbnail_path else None,
        resolve_ready_path(record, getattr(cfg, "READY_DIR", None)),
    ]

    # Stage working copies live in their own directories. Include the recorded
    # working_path plus any sibling pass/upscale artefacts for the record id.
    working_path = getattr(record, "working_path", None)
    if working_path:
        candidates.append(Path(working_path))

    for attribute in (
        "REFINED_DIR",
        "UPSCALED_DIR",
        "CONVERTED_DIR",
        "WHITE_DIR",
        "SRGB_DIR",
        "QUARANTINE_DIR",
    ):
        directory = getattr(cfg, attribute, None) or getattr(settings, attribute, None)
        if not directory:
            continue
        root = Path(directory)
        if not root.is_dir():
            continue
        candidates.extend(root.glob(f"{record.id}*"))

    for candidate in candidates:
        if candidate is None:
            continue
        try:
            if candidate.is_file():
                candidate.unlink()
                removed.append(str(candidate))
        except OSError:
            logger.warning("Failed to delete file %s", candidate)

    return removed
