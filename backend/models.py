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

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
