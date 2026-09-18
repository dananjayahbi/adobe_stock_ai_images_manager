"""Secure local ingestion, validation, normalization, and thumbnail derivation."""

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.storage import StorageLayout
from app.persistence import Database, hash_file


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


class ValidationFailure(ValueError):
    """Input cannot safely enter active processing."""


@dataclass(frozen=True)
class IngestionResult:
    asset_id: str
    display_name: str
    source_path: Path
    source_hash: str
    accepted: bool = True
    duplicate: bool = False


class IngestionService:
    def __init__(self, layout: StorageLayout, max_file_size: int, database: Database | None = None):
        self.layout = layout
        self.layout.ensure_exists()
        self.max_file_size = max_file_size
        self.database = database or Database(self.layout.root / "studio.sqlite3")
        self.database.initialize()

    def ingest(self, source: Path, filename: str, batch_id: str) -> IngestionResult:
        source = Path(source)
        if not source.is_file():
            raise ValidationFailure("source file is not available")
        if source.stat().st_size > self.max_file_size:
            raise ValidationFailure("file exceeds the configured upload limit")

        display_name = self._display_name(filename)
        self._validate_image(source)
        source_hash = hash_file(source)
        registration = self.database.create_asset(display_name, source_hash, batch_id)
        if registration.duplicate:
            existing = self.database.connection.execute(
                "SELECT filename FROM assets WHERE id = ?", (registration.asset_id,)
            ).fetchone()
            return IngestionResult(
                registration.asset_id,
                existing["filename"],
                self.layout.inbox / f"{registration.asset_id}.source",
                source_hash,
                duplicate=True,
            )

        destination = self.layout.temporary / f"{uuid4().hex}.upload"
        shutil.copyfile(source, destination)
        self._flush_and_verify(destination, source_hash)
        published = self.layout.inbox / f"{registration.asset_id}.source"
        destination.replace(published)
        self.database.connection.execute(
            "INSERT INTO files(id, asset_id, role, relative_path, content_hash, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (str(uuid4()), registration.asset_id, "original", published.relative_to(self.layout.root).as_posix(), source_hash),
        )
        self.database.connection.commit()
        return IngestionResult(registration.asset_id, display_name, published, source_hash)

    def create_thumbnail(self, result: IngestionResult, max_dimension: int = 400) -> Path:
        target = self.layout.thumbnails / f"{result.asset_id}-{result.source_hash[:16]}.jpg"
        if target.exists():
            return target
        temporary = self.layout.temporary / f"{uuid4().hex}.thumbnail"
        with Image.open(result.source_path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            image.save(temporary, format="JPEG", quality=82, optimize=True)
        self._validate_image(temporary)
        temporary.replace(target)
        return target

    def normalize(self, result: IngestionResult, quality: int = 92) -> Path:
        """Create one idempotent RGB JPEG derivative without modifying the source."""
        target = self.layout.normalized / f"{result.asset_id}-{result.source_hash[:16]}.jpg"
        if target.exists():
            return target
        if not 70 <= quality <= 100:
            raise ValueError("JPEG quality must be between 70 and 100")
        temporary = self.layout.temporary / f"{uuid4().hex}.normalized"
        with Image.open(result.source_path) as image:
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized.save(temporary, format="JPEG", quality=quality, optimize=True)
        self._validate_image(temporary)
        temporary.replace(target)
        return target

    @staticmethod
    def _display_name(filename: str) -> str:
        name = Path(filename).name.replace("\x00", "")
        name = _SAFE_NAME.sub("_", name).strip(" .")
        if not name or name in {".", ".."}:
            raise ValidationFailure("filename is empty or unsafe")
        return name[:255]

    @staticmethod
    def _validate_image(path: Path) -> None:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValidationFailure("unsupported image format")
                if image.width < 1 or image.height < 1 or image.width * image.height > 100_000_000:
                    raise ValidationFailure("image dimensions exceed safe limits")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValidationFailure("multi-frame images are not supported")
        except (UnidentifiedImageError, OSError) as error:
            raise ValidationFailure("image could not be safely decoded") from error

    @staticmethod
    def _flush_and_verify(path: Path, expected_hash: str) -> None:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.flush()
        if hash_file(path) != expected_hash:
            path.unlink(missing_ok=True)
            raise ValidationFailure("stored source hash does not match upload")
