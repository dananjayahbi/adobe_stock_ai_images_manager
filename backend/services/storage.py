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
    """Create inbox, thumbnails, and ready directories on startup if they don't exist."""
    for dir_path in [settings.INBOX_DIR, settings.THUMBNAILS_DIR, settings.READY_DIR]:
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
