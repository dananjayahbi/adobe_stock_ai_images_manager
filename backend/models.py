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


class BatchStatus(str, enum.Enum):
    """Lifecycle of one batch pipeline run (batch pipeline v2)."""

    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Batch(Base):
    """A configured, customisable processing run (batch pipeline v2).

    A batch declares *what kind of images* it holds (``media_type``) and *which
    steps run on them* (``steps``: ``[{key, config}]`` in canonical order). The
    operator uploads records into a draft batch, optionally configures each
    step, then runs the whole pipeline in one go.

    ``step_progress`` is written by the pipeline runner as it advances so the
    processing page can poll one endpoint for live per-step status.
    """

    __tablename__ = "batches"
    __table_args__ = (
        Index("ix_batches_status", "status"),
        Index("ix_batches_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: "raster" (photo pipeline) or "png" (transparent-background pipeline).
    media_type: Mapped[str] = mapped_column(String(20), nullable=False, default="raster")
    #: Ordered step list: [{"key": "ocr", "config": {...}}, ...].
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    #: The step profile this batch was seeded from, if any (informational).
    profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    #: Per-step live status: {key: {status, message, counts}} — polled by the UI.
    step_progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: Set when status == failed: which step failed and why.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StepProfile(Base):
    """A saved, reusable step recipe (batch pipeline v2).

    Profiles let the operator skip the step picker: choose the media type, pick
    the profile, and the batch is created with those steps *and their configs*
    already filled in.
    """

    __tablename__ = "step_profiles"
    __table_args__ = (
        Index("ix_step_profiles_media_type", "media_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    media_type: Mapped[str] = mapped_column(String(20), nullable=False, default="raster")
    #: [{"key": "upscale", "config": {...}}, ...] — same shape as Batch.steps.
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class PromptStatus(str, enum.Enum):
    """Lifecycle of a generation prompt in the Prompt Library.

    ``USED`` is deliberately derivable (binding any image marks a prompt used)
    but also settable by hand, because an operator may know a prompt was
    consumed elsewhere without collecting its output here.
    """
    DRAFT = "DRAFT"
    USED = "USED"
    ARCHIVED = "ARCHIVED"


class Prompt(Base):
    """A reusable image-generation prompt.

    Prompts are the *source* of the images collected in Stage 1, so they are
    first-class records rather than a text field on an image. One prompt can
    produce many images, which is why the link lives on ``ImageRecord.prompt_id``
    (many-to-one) instead of storing prompt text per image.

    ``body`` holds the raw prompt text; ``negative_prompt`` is kept separate
    because most generators take it as a distinct field. ``params`` stores
    generator-specific settings (model, aspect ratio, seed, …) as free JSON so
    new generators need no schema change.
    """

    __tablename__ = "prompts"
    __table_args__ = (
        Index("ix_prompts_status", "status"),
        Index("ix_prompts_title", "title"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Free-form generator settings, e.g. {"model": "...", "aspect": "1:1"}.
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: Optional grouping label, e.g. "Ayurvedic herbs".
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)

    status: Mapped[PromptStatus] = mapped_column(
        Enum(PromptStatus), default=PromptStatus.DRAFT, nullable=False
    )
    #: Set the first time an image is bound, or when marked used manually.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


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
    #: Operator-chosen upload filename, including the extension.
    #:
    #: Adobe matches a CSV row to an uploaded image **by filename**, so the name
    #: is a real deliverable, not a display detail. When NULL the name is derived
    #: from the generated title (see ``services/asset_naming``); when set it wins
    #: everywhere - the CSV Filename column, the download, and the ZIP entry - so
    #: the three can never disagree.
    download_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: Upload filename proposed by the metadata model, including the extension.
    #:
    #: Separate from ``download_name`` on purpose. This one is a *proposal* made
    #: at generation time (the model has just looked at the image and knows what
    #: it shows, so it names it better than a truncated title can), while
    #: ``download_name`` is the operator's decision. Keeping them apart means the
    #: proposal can be reviewed and re-applied without any way for a model's
    #: output to silently become the delivered filename.
    suggested_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Gallery usage tracking - set once the asset has been consumed/published.
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: The generation prompt this image came from, if it was recorded.
    #: Nullable because images may be collected without a known prompt, and
    #: one prompt legitimately produces many images.
    prompt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    #: The batch this image was uploaded with (batch pipeline v2). NULL for
    #: records created outside a batch, so the legacy stage workspace is unaffected.
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    #: Gallery folder this image belongs to. NULL = ungrouped (top level).
    group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def upload_filename(self) -> str:
        """The name this asset is uploaded to Adobe under.

        **The single source of truth for the delivered filename.** The CSV's
        Filename column, the ZIP entry, the download's Content-Disposition and
        the preview modal all read this property, so they cannot disagree — and a
        disagreement is not cosmetic: Adobe matches a CSV row to an uploaded file
        *by name*, so a mismatch means the metadata silently never lands.

        Returns the operator's explicit ``download_name`` when set, otherwise the
        title-derived name. The import is deferred because ``services`` imports
        this module, so a top-level import would be circular.
        """
        from services.asset_naming import effective_download_name

        return effective_download_name(self)


class ImageGroup(Base):
    """A gallery folder: a named set of images the operator groups by hand.

    Deliberately *not* a hierarchy — folders are a flat organizing device
    ("the ones for this client"), and ``ImageRecord.group_id`` is the single
    edge, so moving an image is a one-column update.
    """

    __tablename__ = "image_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    @property
    def image_count(self) -> int:
        """Number of images currently in this folder (computed on read)."""
        from database import SessionLocal
        from sqlalchemy import func

        with SessionLocal() as db:
            return (
                db.query(func.count(ImageRecord.id))
                .filter(ImageRecord.group_id == self.id)
                .scalar()
                or 0
            )


class ResearchRunStatus(str, enum.Enum):
    """Lifecycle of one Prompt Research conversation."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResearchRun(Base):
    """One Prompt Research conversation.

    A conversation is a *durable* object rather than process state, because the
    whole point of the feature is that the operator returns to a research thread
    — to pick one of the proposed ideas, to answer "continue with these
    confidence rates", or to accept the prompts it produced. An in-memory store
    (like the stage job registry) would lose the thread on every restart and the
    research would have to be repeated.

    ``messages`` holds the conversation and ``events`` the streamed transcript
    (thinking, tool steps, sources, scores) as JSON, so a reloaded page replays
    what actually happened instead of showing a bare result. Both are JSON rather
    than child tables: they are read whole, never queried across, and a run's
    transcript is a document.
    """

    __tablename__ = "research_runs"
    __table_args__ = (
        Index("ix_research_runs_created_at", "created_at"),
        Index("ix_research_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: The operator's opening message, kept separate so the thread list can show
    #: it without parsing the message document.
    seed_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="static")
    status: Mapped[ResearchRunStatus] = mapped_column(
        Enum(ResearchRunStatus), default=ResearchRunStatus.RUNNING, nullable=False
    )

    #: ``[{"role", "content", "created_at"}]`` — what the model is shown.
    messages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    #: The streamed transcript, replayed by the UI when the page reloads.
    events: Mapped[list | None] = mapped_column(JSON, nullable=True)
    #: The run's derived result: prompts, sources, confidence, notices.
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: The settings a run used, so a reopened conversation shows the same style
    #: instruction it was researched with.
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    #: Set when the run failed, so the thread shows why instead of an empty thread.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

