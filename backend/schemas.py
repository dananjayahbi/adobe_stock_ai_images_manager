"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models import ImageStatus


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
    created_at: datetime
    updated_at: datetime


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
