"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from models import ImageLifecycleState, ImageStatus, PipelineStage, PromptStatus


class RecordResponse(BaseModel):
    """Schema for a single image record returned to the frontend."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    original_path: str
    thumbnail_path: Optional[str] = None
    status: ImageStatus
    #: Lifecycle state: the single coordinate the publish/download/export flow
    #: reads (see ``models.ImageLifecycleState``). ``status``/``stage`` stay
    #: alongside it because the pipeline screens still show them.
    state: ImageLifecycleState
    #: Derived badges (QUARANTINED, USED/UNUSED, ...), computed at
    #: serialization by ``services.image_lifecycle.compute_flags`` — never stored.
    flags: list[str]
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
    #: Operator-chosen upload filename. NULL means "derive it from the title".
    download_name: Optional[str] = None
    #: Upload filename proposed by the metadata model at generation time.
    #: Separate from ``download_name`` because it is a proposal, not a decision:
    #: the operator applies it (one record or a whole batch) or ignores it.
    suggested_filename: Optional[str] = None
    #: The name this asset is uploaded under — the value the CSV Filename column
    #: carries. Sent so the UI can show the same name the CSV will contain rather
    #: than the raw upload filename, which is a different string.
    upload_filename: Optional[str] = None
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
    #: The batch this image belongs to (batch pipeline v2). Null outside batches.
    batch_id: Optional[str] = None
    #: Gallery folder this image lives in. Null = ungrouped (top level).
    group_id: Optional[str] = None


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
    """Response returned after a successful (fast) approval action.

    The endpoint is a state flip into ``READY_TO_PUBLISH``: no metadata is
    generated, so ``title``/``keywords_count`` echo what already exists.
    """
    record_id: str
    status: ImageStatus
    state: ImageLifecycleState
    title: Optional[str] = None
    keywords_count: int = 0


class StateChangeRequest(BaseModel):
    """Request body for PATCH /api/records/{id}/state.

    Kept a plain string so the router can answer an unknown value with a 400
    that lists every accepted state, rather than a framework-shaped 422.
    """
    state: str


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


class GroupCreateRequest(BaseModel):
    """Create a gallery folder, optionally pre-filled with images."""

    name: str
    record_ids: list[str] = []


class GroupRenameRequest(BaseModel):
    """Rename a gallery folder."""

    name: str


class GroupAssignRequest(BaseModel):
    """Move records into a folder — or out of one with ``group_id: null``."""

    record_ids: list[str]
    group_id: Optional[str] = None


class GroupResponse(BaseModel):
    """A gallery folder with its current image count."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    image_count: int = 0
    created_at: datetime


class GroupListResponse(BaseModel):
    """All gallery folders, oldest-first (stable ordering for the UI)."""

    items: list[GroupResponse]


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


# --------------------------------------------------------------------------- #
# Manual promotion to ready-to-upload (gallery override)
# --------------------------------------------------------------------------- #

class PromoteStepStatus(BaseModel):
    """One requirement's state for one record in the promote pre-flight."""
    key: str
    label: str
    ok: bool
    detail: str = ""


class PromoteCheckItem(BaseModel):
    """Pre-flight report for a single record."""
    record_id: str
    filename: str
    stage: str
    #: False when the record must not be promoted (e.g. OCR_REJECTED).
    eligible: bool = True
    blocker: Optional[str] = None
    steps: list[PromoteStepStatus] = []


class PromoteCheckRequest(BaseModel):
    """Request body for the promote pre-flight check."""
    record_ids: list[str]


class PromoteCheckResponse(BaseModel):
    """Which requirements are missing per record, before anything runs."""
    items: list[PromoteCheckItem] = []
    missing: list[str] = []


class PromoteRunRequest(BaseModel):
    """Request body for running the missing steps and promoting."""
    record_ids: list[str]
    #: Include the LLM semantic audit in the acceptance QC re-run.
    use_semantic: bool = False


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
    #: One key per lifecycle state (zero-filled), counted from the ``state``
    #: column — the publish-queue view's counterpart to the per-stage ``counts``.
    state_counts: dict[str, int] = {}


class MetadataUpdateRequest(BaseModel):
    """Manual metadata edit for a single record (Stage 6)."""
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    category: Optional[int] = None


class CsvExportRequest(BaseModel):
    """Request body for the Adobe Stock CSV export.

    ``record_ids`` omitted (or null) exports every eligible record; supplying ids
    exports exactly those rows, which is what "select some and generate the CSV
    for them" needs. ``only_ready`` controls the eligibility filter: the Gallery
    legitimately exports *published* assets, and a force-accepted record may not
    have reached METADATA_READY yet, so the caller can widen it deliberately.
    """

    record_ids: Optional[list[str]] = None
    #: When true (the default), only records whose metadata is ready are exported.
    only_ready: bool = True


class RenameItemRequest(BaseModel):
    """One requested filename in a bulk rename."""

    record_id: str
    name: str


class RenameRequest(BaseModel):
    """Body for renaming one or more assets for the Adobe Stock upload.

    Adobe matches a CSV row to an uploaded file by filename, so the name is part
    of the deliverable. Names are normalised server-side (slugified, forced to a
    JPEG extension, truncated to the filename cap) and reported back so
    the operator sees exactly what will be uploaded.
    """

    items: list[RenameItemRequest]
    #: When true, every name is rebuilt from the record's generated title,
    #: ignoring ``items``. Used by the "rename them all" button.
    regenerate: bool = False


class RenameResultItem(BaseModel):
    """Per-record outcome of a rename attempt."""

    record_id: str
    filename: str
    download_name: Optional[str] = None
    changed: bool = False
    error: Optional[str] = None


class RenameResponse(BaseModel):
    """Outcome of a bulk rename."""

    items: list[RenameResultItem]
    updated: int = 0
    failed: int = 0


class ForcedAcceptRequest(BaseModel):
    """Body for force-accepting records that the gate flagged.

    ``reason`` is stored with the override, because an override that leaves no
    trace is indistinguishable from a bug in the gate.
    """

    record_ids: list[str]
    reason: str = ""


class ForcedAcceptResultItem(BaseModel):
    """Per-record outcome of a forced acceptance."""

    record_id: str
    accepted: bool
    previous_stage: str
    new_stage: Optional[str] = None
    score: Optional[float] = None
    reason: str = ""


class ForcedAcceptResponse(BaseModel):
    """Outcome of a bulk forced acceptance."""

    items: list[ForcedAcceptResultItem]
    accepted: int = 0
    refused: int = 0


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
    min_brave_rate: float = 0.1
    max_brave_rate: float = 10.0
    min_tool_calls: int = 4
    max_tool_calls: int = 80
    min_keyword_target: int = 5
    max_keyword_target: int = 49
    min_metadata_delay: float = 0.0
    max_metadata_delay: float = 30.0
    max_extra_instructions: int = 2000
    max_priority_terms_chars: int = 2000


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
    #: Web-search provider settings. The research agent's evidence source.
    #: ``brave_search_enabled`` is what the operator chose; ``effective_uses_brave``
    #: is what will actually happen (an enabled provider with no key is not used),
    #: so the UI can never show "active" for a configuration that cannot run.
    brave_search_enabled: bool = False
    brave_search_api_key_masked: str = ""
    brave_search_api_key_set: bool = False
    brave_search_rate_limit: float = 1.0
    effective_uses_brave: bool = False
    effective_search_provider: str = "duckduckgo"
    #: The research agent's tool budget. Research calls only — the bookkeeping
    #: tools (`assess_validity`, `check_prompt_similarity`) are not charged.
    research_max_tool_calls: int = 24
    #: Metadata generation: how many keywords to ask for, the pause between
    #: calls, and any operator instruction appended to the prompt. Resolved
    #: values - what the next generation will actually use.
    metadata_keyword_target: int = 49
    metadata_delay_seconds: float = 2.0
    metadata_extra_instructions: str = ""
    metadata_priority_terms: str = ""
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
    #: Brave Search. ``brave_search_enabled`` switches the research agent's
    #: primary provider; the key follows the same blank-means-unchanged contract
    #: as ``llm_api_key``.
    brave_search_enabled: Optional[bool] = None
    brave_search_api_key: Optional[str] = None
    brave_search_rate_limit: Optional[float] = None
    clear_brave_search_key: bool = False
    research_max_tool_calls: Optional[int] = None
    #: Metadata generation options (all optional - omitted fields are untouched).
    metadata_keyword_target: Optional[int] = None
    metadata_delay_seconds: Optional[float] = None
    metadata_extra_instructions: Optional[str] = None
    metadata_priority_terms: Optional[str] = None


class SettingsTestRequest(BaseModel):
    """Optional candidate values to verify before saving."""

    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_context_window: Optional[int] = None
    #: When set, the probe also exercises the search provider so a bad key or a
    #: missing entitlement surfaces here rather than mid-research-run.
    probe_search: Optional[bool] = None
    brave_search_api_key: Optional[str] = None
    brave_search_enabled: Optional[bool] = None


class SettingsSearchProbe(BaseModel):
    """Outcome of the web-search half of a connection probe.

    A failure is a normal result, not an HTTP error: the modal renders it inline.
    """

    ok: bool
    provider: str = ""
    provider_label: str = ""
    results: int = 0
    error: Optional[str] = None


class SettingsTestResponse(BaseModel):
    """Outcome of an endpoint probe.

    A failure is a normal result, not an HTTP error: the modal renders the
    message inline so the operator can correct a typo and retry.
    """

    ok: bool
    model: Optional[str] = None
    reply: Optional[str] = None
    error: Optional[str] = None
    #: Present only when the request asked for a search probe, so the modal can
    #: report the two halves of the configuration separately.
    search: Optional[SettingsSearchProbe] = None


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
    #: Folder-style grouping label ("Mantis batch 1"); NULL = ungrouped.
    group_name: Optional[str] = None
    status: PromptStatus
    used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    #: How many image records are currently bound to this prompt.
    bound_count: int = 0


class PromptListResponse(BaseModel):
    """All prompts, newest first, with their binding counts.

    ``used``/``unused``/``archived`` count the *status* axis; ``bound``/
    ``unbound`` count the independent *binding* axis. They are reported
    separately rather than summed because a prompt can be consumed without any
    of its images being collected here — "used" and "bound" are different
    states, and the sidebar labels the two groups accordingly.
    """

    items: list[PromptResponse]
    total: int
    used: int
    unused: int
    bound: int = 0
    unbound: int = 0
    archived: int = 0
    #: Every group with its prompt count, busiest first — served with the list
    #: so the filter chips cannot drift from the rows they filter.
    groups: list[dict[str, Any]] = []


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
    group_name: Optional[str] = None
    status: Optional[PromptStatus] = None


class PromptUpdateRequest(BaseModel):
    """Partial update for a prompt; omitted fields are left untouched.

    ``group_name`` sent as ``None`` or ``""`` clears the group (the explicit
    empty contract the other optional text fields use), while omitting it
    leaves the folder alone.
    """

    title: Optional[str] = None
    body: Optional[str] = None
    negative_prompt: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    group_name: Optional[str] = None
    status: Optional[PromptStatus] = None


class PromptGroupAssignRequest(BaseModel):
    """Add one or more prompts to a group (folder).

    The group is *named here*: folders are created by assignment, not up front,
    so isolating a batch is one round trip. An empty ``group_name`` removes the
    prompts from their folder.
    """

    prompt_ids: list[str]
    group_name: str = ""


class PromptGroupAssignResponse(BaseModel):
    """How many prompts moved, which ids were unknown, and the resulting name."""

    updated: int = 0
    missing: list[str] = []
    group_name: Optional[str] = None


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


# --------------------------------------------------------------------------- #
# Prompt Research (agentic prompt research workspace)
# --------------------------------------------------------------------------- #

class ResearchRunRequest(BaseModel):
    """Start a research conversation.

    ``mode`` selects the objective (see ``services.research.agent``); ``count`` is
    the number of prompts wanted, used only by the modes with a count control.

    ``stream_first`` creates the conversation **without** running the opening turn,
    so the caller can stream it. A buffered first turn would leave the live view
    blank for the whole first minute, which is the opposite of the feature.
    """

    message: str
    mode: str = "generate"
    count: int = 1
    validity_check: bool = False
    stream_first: bool = False


class ResearchFollowUpRequest(BaseModel):
    """Continue an existing conversation.

    The two confidence-score buttons send their message through this endpoint, so
    a click and a typed sentence follow exactly the same path — the agent does
    not need to distinguish them.
    """

    message: str
    count: Optional[int] = None
    validity_check: Optional[bool] = None


class ResearchRunSummary(BaseModel):
    """A conversation as it appears in the thread list."""

    id: str
    title: str
    seed_message: str
    mode: str
    status: str
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    #: How many prompts this run produced, so the list can show it.
    prompt_count: int = 0
    #: Whether the run recorded a confidence assessment.
    has_validity: bool = False


class ResearchRunResponse(BaseModel):
    """A full conversation, including its transcript for replay."""

    id: str
    title: str
    seed_message: str
    mode: str
    status: str
    messages: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ResearchRunListResponse(BaseModel):
    """All conversations, newest first."""

    items: list[ResearchRunSummary]
    total: int


class ResearchAcceptRequest(BaseModel):
    """Push accepted prompts from a run into the Prompt Library."""

    prompts: list[str]
    tags: Optional[list[str]] = None
    negative_prompt: Optional[str] = None
    #: Optional per-prompt metadata, positionally matching ``prompts``. Carries
    #: the title, tags and category the JSON contract supplied, so they reach the
    #: library instead of being thrown away at the last step.
    details: Optional[list[dict[str, Any]]] = None


class ResearchAcceptResponse(BaseModel):
    """Which prompts were added, and which were already in the library."""

    created: list[dict[str, Any]] = []
    skipped: list[str] = []
    count: int = 0


class ResearchSettingsResponse(BaseModel):
    """The research page's own defaults, so the UI never hard-codes them."""

    modes: list[dict[str, Any]] = []
    max_prompts: int = 60
    max_tool_calls: int = 10
    disclaimer: str = ""
    #: The resolved context window, and the thresholds the live indicator uses.
    #: Served so the bar cannot disagree with the backend about when a run is
    #: close to its limit or when the history gets compacted.
    context_window: int = 0
    keep_recent_turns: int = 5
    compact_at_share: float = 0.7
    warn_at_share: float = 0.85
    #: The collective average an idea must reach. Served so the card's verdict and
    #: the agent's own instruction quote the same number.
    target_average: float = 80.0


class SystemPromptsResponse(BaseModel):
    """The per-mode system prompts, so the editor serves itself.

    ``items`` holds the **effective** texts (saved edit or shipped default) and
    ``is_custom`` says which is which, both derived server-side — "is this
    modified" is a fact about the stored document, not something the client
    should guess by comparing against a constant it fetched separately.
    """

    items: dict[str, str] = {}
    defaults: dict[str, str] = {}
    is_custom: dict[str, bool] = {}


class SystemPromptUpdateRequest(BaseModel):
    """Replace one mode's system prompt.

    An empty ``text`` restores the shipped default (reset-by-clearing).
    """

    mode: str
    text: str = ""
