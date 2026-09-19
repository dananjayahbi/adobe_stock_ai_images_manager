"""SQLAlchemy ORM models for the image pipeline."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from database import Base


class ImageStatus(str, enum.Enum):
    """Valid states in the image record lifecycle state machine."""
    PENDING = "PENDING"
    AUDITING = "AUDITING"
    PASSED = "PASSED"
    FLAGGED = "FLAGGED"
    APPROVED = "APPROVED"
    READY = "READY"


class PipelineStage(str, enum.Enum):
    """Workflow position of a record across the seven production stages.

    ``ImageStatus`` remains the QC verdict and the download gate; ``stage`` is
    the orthogonal workflow coordinate that drives the stage workspace UI.

    1. COLLECTED       - ingested, awaiting an OCR sweep
    2. OCR_CLEAR       - scanned, no blocking text found
       OCR_REJECTED    - scanned, embedded/gibberish text found (terminal)
    3. UPSCALED        - upscaled (or upscale skipped/unavailable)
    4. REFINED         - corrective adjustments applied
    5. COMPATIBLE      - passed the acceptance gate
       INCOMPATIBLE    - could not reach the acceptance gate (terminal)
    6. METADATA_READY  - title/description/keywords generated
    7. PUBLISHED       - staged for Adobe Stock upload
    """
    COLLECTED = "COLLECTED"
    OCR_CLEAR = "OCR_CLEAR"
    OCR_REJECTED = "OCR_REJECTED"
    UPSCALED = "UPSCALED"
    REFINED = "REFINED"
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    METADATA_READY = "METADATA_READY"
    PUBLISHED = "PUBLISHED"


#: Stage -> the stage number it belongs to (1-7).
STAGE_NUMBERS: dict["PipelineStage", int] = {
    PipelineStage.COLLECTED: 1,
    PipelineStage.OCR_CLEAR: 2,
    PipelineStage.OCR_REJECTED: 2,
    PipelineStage.UPSCALED: 3,
    PipelineStage.REFINED: 4,
    PipelineStage.COMPATIBLE: 5,
    PipelineStage.INCOMPATIBLE: 5,
    PipelineStage.METADATA_READY: 6,
    PipelineStage.PUBLISHED: 7,
}

#: Human-readable stage names for the UI.
STAGE_LABELS: dict["PipelineStage", str] = {
    PipelineStage.COLLECTED: "Collector",
    PipelineStage.OCR_CLEAR: "OCR Clear",
    PipelineStage.OCR_REJECTED: "OCR Rejected",
    PipelineStage.UPSCALED: "Upscaled",
    PipelineStage.REFINED: "Refined",
    PipelineStage.COMPATIBLE: "Compatible",
    PipelineStage.INCOMPATIBLE: "Incompatible",
    PipelineStage.METADATA_READY: "Metadata Ready",
    PipelineStage.PUBLISHED: "Published",
}


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImageRecord(Base):
    """Primary database model tracking images through the processing pipeline."""

    __tablename__ = "image_records"
    __table_args__ = (
        Index("ix_image_records_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[ImageStatus] = mapped_column(
        Enum(ImageStatus), default=ImageStatus.PENDING, nullable=False
    )

    # ------------------------------------------------------------------ #
    # Stage pipeline tracking
    # ------------------------------------------------------------------ #
    stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage), default=PipelineStage.COLLECTED, nullable=False
    )
    # Stage key this record has been explicitly pushed into, awaiting a run.
    # NULL means "not queued". Cleared automatically on every stage advance.
    queued_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: Path of the current working file (original, upscaled, or refined copy).
    #: ``original_path`` always keeps pointing at the untouched inbox original.
    working_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    #: Timestamp of the last stage transition, for the workspace timeline.
    stage_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Latest acceptance report (score, sub-scores, issues) as JSON.
    acceptance_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: Cached 0..1 acceptance score for cheap sorting/filtering.
    acceptance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Number of automatic refinement passes already applied.
    refine_passes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Free-form per-stage detail, e.g. {"upscale": {...}, "ocr": {...}}.
    stage_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: Adobe Stock category code (1-21) for the CSV export.
    category: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Image properties
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    megapixels: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # QC metrics
    laplacian_variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_text_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ocr_text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # List of human-readable flag strings, e.g. ["sharpness: ... below minimum 120.0"].
    semantic_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Generated metadata
    generated_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Gallery usage tracking - set once the asset has been consumed/published.
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
