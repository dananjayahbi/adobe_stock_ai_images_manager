"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from models import ImageStatus, PipelineStage


class RecordResponse(BaseModel):
    """Schema for a single image record returned to the frontend."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    original_path: str
    thumbnail_path: Optional[str] = None
    status: ImageStatus
    width: Optional[int] = None
    height: Optional[int] = None
    megapixels: Optional[float] = None
    file_size_bytes: int
    laplacian_variance: Optional[float] = None
    ocr_text_detected: bool = False
    ocr_text_content: Optional[str] = None
    semantic_confidence_score: Optional[float] = None
    semantic_flags: Optional[list[str]] = None
    generated_title: Optional[str] = None
    generated_description: Optional[str] = None
    generated_keywords: Optional[list[str]] = None
    is_used: bool = False
    used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Stage pipeline
    stage: PipelineStage = PipelineStage.COLLECTED
    working_path: Optional[str] = None
    stage_updated_at: Optional[datetime] = None
    acceptance_report: Optional[dict[str, Any]] = None
    acceptance_score: Optional[float] = None
    refine_passes: int = 0
    stage_details: Optional[dict[str, Any]] = None
    category: Optional[int] = None


class RecordListResponse(BaseModel):
    """Paginated list of image records."""
    items: list[RecordResponse]
    total: int
    page: int
    page_size: int


class UploadResponse(BaseModel):
    """Response returned after a successful batch file upload."""
    record_ids: list[str]
    count: int


class ApproveRequest(BaseModel):
    """Request body for approving an image record with optional metadata overrides."""
    override_title: Optional[str] = None
    override_description: Optional[str] = None
    override_keywords: Optional[list[str]] = None


class ApproveResponse(BaseModel):
    """Response returned after a successful approval action."""
    record_id: str
    status: ImageStatus
    title: Optional[str] = None
    keywords_count: int = 0


class UsedRequest(BaseModel):
    """Request body for marking one or more records as used/unused."""
    is_used: bool = True


class BulkUsedRequest(BaseModel):
    """Request body for marking many records as used/unused at once."""
    record_ids: list[str]
    is_used: bool = True


class DeleteRequest(BaseModel):
    """Request body for deleting many records at once."""
    record_ids: list[str]


class BulkActionResult(BaseModel):
    """Outcome of a bulk mutation, reporting per-record failures."""
    updated: int = 0
    deleted: int = 0
    missing: list[str] = []
    failed: list[str] = []


class UploadTableItem(BaseModel):
    """One row of the copy/paste upload table for Adobe Stock submissions."""
    record_id: str
    filename: str
    title: str
    description: str
    keywords: list[str]
    keywords_csv: str
    thumbnail_url: Optional[str] = None
    download_url: str


class UploadTableResponse(BaseModel):
    """Ordered rows for the generated upload table."""
    items: list[UploadTableItem]
    missing: list[str] = []


# --------------------------------------------------------------------------- #
# Stage pipeline
# --------------------------------------------------------------------------- #

class StageDefinitionResponse(BaseModel):
    """Static description of one production stage."""
    number: int
    key: str
    name: str
    description: str
    stages: list[str]
    terminal: bool


class StageRunRequest(BaseModel):
    """Request body for kicking off a batch stage operation."""
    record_ids: list[str]
    #: Stage 6 only - pause between LLM calls, overriding the configured default.
    delay_seconds: Optional[float] = None
    #: Whether to include the LLM semantic audit in Stage 4/5 scoring.
    use_semantic: bool = True


class JobItemResponse(BaseModel):
    """Per-record progress inside a batch job."""
    record_id: str
    filename: str
    status: str
    message: str = ""
    score: Optional[float] = None
    duration_seconds: Optional[float] = None


class JobResponse(BaseModel):
    """State of a batch stage job."""
    id: str
    stage: str
    kind: str
    status: str
    message: str = ""
    total: int
    processed: int
    succeeded: int
    failed: int
    skipped: int
    progress: float
    created_at: float
    finished_at: Optional[float] = None
    duration_seconds: float
    items: list[JobItemResponse] = []


class StageCountResponse(BaseModel):
    """Record counts grouped by pipeline stage."""
    stage: PipelineStage
    number: int
    name: str
    count: int


class StageSummaryResponse(BaseModel):
    """Aggregate pipeline state for the workspace header."""
    counts: list[StageCountResponse]
    total: int
    ready: int
    rejected: int
    incompatible: int
    average_score: Optional[float] = None


class MetadataUpdateRequest(BaseModel):
    """Manual metadata edit for a single record (Stage 6)."""
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    category: Optional[int] = None


class CsvExportRequest(BaseModel):
    """Request body for the Adobe Stock CSV export."""
    record_ids: Optional[list[str]] = None


class CategoryResponse(BaseModel):
    """One Adobe Stock category option."""
    code: int
    name: str
