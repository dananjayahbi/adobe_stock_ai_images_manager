"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from models import ImageStatus, PipelineStage, PromptStatus


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
    queued_stage: Optional[str] = None
    working_path: Optional[str] = None
    stage_updated_at: Optional[datetime] = None
    acceptance_report: Optional[dict[str, Any]] = None
    acceptance_score: Optional[float] = None
    refine_passes: int = 0
    stage_details: Optional[dict[str, Any]] = None
    category: Optional[int] = None
    #: Prompt Library link. Null when the image has no known source prompt.
    prompt_id: Optional[str] = None


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


class AutoFixResponse(BaseModel):
    """Outcome of an automatic correction attempt on one record.

    ``success`` on the endpoint means a corrected file was written - not that
    the image now passes. ``manual`` lists the issue codes that need a human
    decision and were deliberately left alone.

    In ``adaptive`` mode ``log`` is the primary payload: it explains every pass
    and, most importantly, why the loop stopped.
    """
    record_id: str
    #: "single" (one recipe pass) or "adaptive" (escalating repeat passes).
    mode: str = "single"
    fixed: list[str] = []
    remaining_fixable: list[str] = []
    manual: list[str] = []
    passes: int = 0
    initial_score: float = 0.0
    final_score: float = 0.0
    improved: bool = False
    #: Threshold verdicts, so the UI can distinguish "improved but still below"
    #: from "now passes" without re-deriving it from the score.
    initial_passed: bool = False
    final_passed: bool = False
    #: True when the written file verifiably carries an sRGB profile.
    srgb_embedded: bool = False
    history: list[dict[str, Any]] = []
    summary: str = ""

    # ---- Adaptive-mode detail (empty in single mode) ----
    #: Why the loop stopped. The single most useful field when the score
    #: plateaued, because the usual cause is a cap the engine cannot move.
    stop_reason: str = ""
    #: Per-dimension goal the run aimed for (0-1), when adaptive.
    target: float | None = None
    target_met: bool = False
    #: Structured decision log: one entry per pass, plus setup and stop reasons.
    log: list[dict[str, Any]] = []
    #: Per-dimension progress snapshots, before and after the run.
    progress_before: dict[str, Any] | None = None
    progress_after: dict[str, Any] | None = None

    #: The refreshed record, so the caller can update its list without refetching.
    record: RecordResponse


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
    #: Stage 3 only - the full upscale configuration. Omitted or partial bodies
    #: fall back to the configured defaults for every field.
    upscale: Optional["UpscaleSettingsPayload"] = None


class UpscaleSettingsPayload(BaseModel):
    """Stage 3 upscale options as sent by the UI.

    Every field is optional so the client can send only what the operator
    changed; the server validates and clamps the result.
    """
    model: Optional[str] = None
    model_scale: Optional[int] = None
    target_long_edge: Optional[int] = None
    gpu_id: Optional[int] = None
    tta: Optional[bool] = None
    tile_size: Optional[int] = None
    threads: Optional[list[int]] = None
    compression: Optional[int] = None
    embed_srgb: Optional[bool] = None
    allow_downscale: Optional[bool] = None


class UpscaleModelResponse(BaseModel):
    """One selectable ncnn model."""
    name: str
    label: str
    scale: int
    source: str
    description: str
    recommended: bool = False


class UpscaleDirectoryResponse(BaseModel):
    """Status of one model folder, so a missing path is visible in the UI."""
    source: str
    path: str
    exists: bool


class UpscaleCatalogResponse(BaseModel):
    """Everything the Stage 3 options panel needs to render itself."""
    models: list[UpscaleModelResponse]
    default_model: str
    sources: dict[str, str]
    directories: list[UpscaleDirectoryResponse]
    resolutions: list["UpscaleResolutionResponse"]
    defaults: "UpscaleDefaultsResponse"
    neural_available: bool
    executable: Optional[str] = None
    presets: dict


class UpscaleResolutionResponse(BaseModel):
    """A capacity preset offered in the picker."""
    long_edge: int
    label: str
    default: bool = False


class UpscaleDefaultsResponse(BaseModel):
    """The values the panel should open with."""
    target_long_edge: int
    gpu_id: int
    model_scale: int
    tta: bool
    tile_size: int
    compression: int
    embed_srgb: bool
    allow_downscale: bool


class UpscaleEstimateRequest(BaseModel):
    """Ask what an upscale would produce before committing GPU time."""
    record_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    upscale: Optional[UpscaleSettingsPayload] = None


class UpscaleEstimateResponse(BaseModel):
    """Predicted geometry plus any warnings for the chosen configuration."""
    source_dimensions: list[int]
    target_dimensions: list[int]
    scale: float
    model_scale: int
    will_upscale: bool
    will_downscale: bool
    estimated_megapixels: float
    exceeds_megapixel_ceiling: bool
    warnings: list[str] = []


class GpuDeviceResponse(BaseModel):
    """One Vulkan device the upscaler can be pointed at with ``-g``."""
    id: int
    name: str
    kind: str
    kind_label: str
    recommended: bool = False
    details: dict[str, str] = {}


class GpuListResponse(BaseModel):
    """The devices this machine exposes, plus the index to default to.

    ``available`` is False when no CLI is installed or enumeration produced
    nothing, which tells the panel to fall back rather than render an empty
    picker.
    """
    devices: list[GpuDeviceResponse]
    default_gpu_id: int
    available: bool


class JobItemResponse(BaseModel):
    """Per-record progress inside a batch job."""
    record_id: str
    filename: str
    status: str
    message: str = ""
    score: Optional[float] = None
    #: 0-100 progress within this record, when the stage can report it.
    progress: Optional[float] = None
    detail: str = ""
    duration_seconds: Optional[float] = None


class JobResponse(BaseModel):
    """State of a batch stage job."""
    id: str
    stage: str
    kind: str
    status: str
    message: str = ""
    progress_label: str = ""
    total: int
    processed: int
    succeeded: int
    failed: int
    skipped: int
    progress: float
    created_at: float
    finished_at: Optional[float] = None
    duration_seconds: float
    current_record_id: Optional[str] = None
    items: list[JobItemResponse] = []


# Resolve the forward references introduced by the upscale schemas, which are
# declared after StageRunRequest for readability.
StageRunRequest.model_rebuild()
UpscaleCatalogResponse.model_rebuild()


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


# --------------------------------------------------------------------------- #
# Application settings (Settings modal)
# --------------------------------------------------------------------------- #

class SettingsDefaults(BaseModel):
    """Values that apply when the operator has stored nothing."""

    llm_base_url: str
    llm_model: str
    llm_context_window: int


class SettingsBounds(BaseModel):
    """Valid range for a numeric setting, so the UI can validate locally."""

    min_context_window: int
    max_context_window: int


class SettingsResponse(BaseModel):
    """Current LLM configuration.

    ``llm_*`` fields are what the operator stored (empty when unset);
    ``effective_*`` fields are what a request would actually use right now,
    after the stored value and the environment are merged. The UI shows both so
    an empty field never looks like "no endpoint configured".

    ``llm_api_key`` is deliberately absent - only a mask and a boolean are
    exposed, because the raw key is never needed by the client.
    """

    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key_masked: str = ""
    llm_api_key_set: bool = False
    llm_context_window: int
    effective_base_url: str
    effective_model: str
    effective_context_window: int
    #: Long edge an image is downscaled to, derived from the context window.
    effective_image_max_dim: int
    defaults: SettingsDefaults
    bounds: SettingsBounds


class SettingsUpdateRequest(BaseModel):
    """Partial update for the LLM configuration.

    Omitted fields are left untouched. ``llm_api_key`` set to an empty string or
    to the mask returned by ``GET`` keeps the stored key; use
    ``clear_api_key`` to remove it deliberately.
    """

    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_context_window: Optional[int] = None
    clear_api_key: bool = False


class SettingsTestRequest(BaseModel):
    """Optional candidate values to verify before saving."""

    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_context_window: Optional[int] = None


class SettingsTestResponse(BaseModel):
    """Outcome of an endpoint probe.

    A failure is a normal result, not an HTTP error: the modal renders the
    message inline so the operator can correct a typo and retry.
    """

    ok: bool
    model: Optional[str] = None
    reply: Optional[str] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Prompt Library (Stage 1 — Collector)
# --------------------------------------------------------------------------- #

class PromptResponse(BaseModel):
    """A generation prompt plus its live binding count.

    ``bound_count`` is computed from the records table rather than stored, so it
    can never drift from the actual bindings. The UI uses it to show
    "3 images" on a prompt block and to render the used state.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    body: str
    negative_prompt: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    status: PromptStatus
    used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    #: How many image records are currently bound to this prompt.
    bound_count: int = 0


class PromptListResponse(BaseModel):
    """All prompts, newest first, with their binding counts."""

    items: list[PromptResponse]
    total: int
    used: int
    unused: int


class PromptCreateRequest(BaseModel):
    """Body for creating a prompt.

    ``title`` is optional: a prompt written straight into the body is still
    valid, and the UI derives a display title from the first line. Sending
    neither a title nor a body is rejected.
    """

    title: Optional[str] = None
    body: str
    negative_prompt: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    status: Optional[PromptStatus] = None


class PromptUpdateRequest(BaseModel):
    """Partial update for a prompt; omitted fields are left untouched."""

    title: Optional[str] = None
    body: Optional[str] = None
    negative_prompt: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    status: Optional[PromptStatus] = None


class PromptBindRequest(BaseModel):
    """Bind (or unbind) images to a prompt.

    Binding one prompt to many images is the normal case, so the record list is
    the payload rather than a single id. ``unbind`` reverses the operation
    without deleting the prompt.
    """

    record_ids: list[str]
    unbind: bool = False


class PromptBindResponse(BaseModel):
    """Outcome of a bind/unbind, with the refreshed prompt."""

    updated: int = 0
    missing: list[str] = []
    #: Records that were already bound elsewhere and were re-pointed.
    rebound: list[str] = []
    prompt: PromptResponse
