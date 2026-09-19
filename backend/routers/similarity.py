"""Duplicate-similarity API - Adobe's most common content-refusal reason.

Adobe's distinct-content guidance states plainly that "similar content is one of
the top reasons we refuse content submitted to Adobe Stock", and lists four
patterns it counts as too similar. Two of those are detectable from the data
this app already holds:

* **Subject and composition** - the same subject from slightly different angles.
* **Metadata patterns** - different images tagged with identical titles and
  keywords, "suggesting they serve the same customer need".

This router exposes a read-only scan over a set of records so an operator can
see which assets compete with each other *before* submitting, and drop down to
Adobe's recommended "three to five photos per subject, angle, or pose".

Nothing here mutates or blocks anything - it is advisory, because the correct
choice of which frame to keep is an editorial decision.

Source: helpx /submit-distinct-content/distinct-content-submission-best-practices.html
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import ImageRecord, PipelineStage
from services.duplicate_detector import (
    DuplicateCandidate,
    VISUAL_SIMILAR_DISTANCE,
    METADATA_SIMILARITY_THRESHOLD,
    find_duplicate_pairs,
    group_duplicates,
    hash_image_file,
    tokenize_metadata,
)
from services.storage import resolve_ready_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["similarity"])

#: Upper bound on how many records one scan will compare. The pair comparison is
#: O(n^2), so this keeps a careless request from pinning a worker.
MAX_SCAN_RECORDS = 400


class SimilarityScanRequest(BaseModel):
    """Request body for a duplicate scan."""

    record_ids: list[str] | None = Field(
        default=None,
        description="Records to scan. Omit to scan every record with metadata.",
    )
    keep_per_group: int = Field(
        default=5,
        ge=1,
        le=20,
        description="How many assets to recommend keeping per similar group.",
    )
    visual_distance: int = Field(
        default=VISUAL_SIMILAR_DISTANCE,
        ge=0,
        le=64,
        description="Perceptual-hash Hamming distance at or below which images count as similar.",
    )
    metadata_threshold: float = Field(
        default=METADATA_SIMILARITY_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Title+keyword Jaccard similarity at or above which metadata counts as reused.",
    )


class SimilarityGroupResponse(BaseModel):
    """One cluster of mutually similar records."""

    record_ids: list[str]
    reason: str
    suggested_keep: list[str]
    suggested_drop: list[str]


class SimilarityScanResponse(BaseModel):
    """Result of a duplicate scan."""

    scanned: int
    skipped: list[str]
    pair_count: int
    groups: list[SimilarityGroupResponse]
    #: Total assets the scan recommends leaving out of the submission.
    suggested_drop_count: int
    notes: list[str]


def _candidate_for(record: ImageRecord) -> DuplicateCandidate | None:
    """Build a comparison candidate, or None when the record has no image."""
    path = resolve_ready_path(record)
    if path is None:
        # Fall back to the original upload so unrefined records can still be
        # compared; a missing file yields hash 0, which the scan tolerates.
        from pathlib import Path

        original = getattr(record, "original_path", None)
        path = Path(original) if original else None

    hash_value = hash_image_file(path) if path is not None else 0

    tokens = tokenize_metadata(
        getattr(record, "generated_title", None),
        getattr(record, "generated_keywords", None),
    )

    # A record with neither a readable image nor any metadata cannot be compared.
    if hash_value == 0 and not tokens:
        return None

    return DuplicateCandidate(
        record_id=record.id,
        hash_value=hash_value,
        tokens=tokens,
    )


@router.post("/api/similarity/scan", response_model=SimilarityScanResponse)
async def scan_similarity(
    request: SimilarityScanRequest,
    db: Session = Depends(get_db),
) -> SimilarityScanResponse:
    """Find groups of records Adobe would likely consider too similar.

    Both signals are reported: a perceptual-hash match catches the same subject
    shot from a slightly different angle, while a metadata match catches the
    "different images, identical titles and keywords" pattern that Adobe names
    as its own refusal reason.
    """
    query = db.query(ImageRecord)

    if request.record_ids:
        if len(request.record_ids) > MAX_SCAN_RECORDS:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot scan more than {MAX_SCAN_RECORDS} records at once.",
            )
        query = query.filter(ImageRecord.id.in_(request.record_ids))
        # Order-preserving so the caller's ordering is reflected in the output.
        order = {rid: index for index, rid in enumerate(request.record_ids)}
        records = sorted(query.all(), key=lambda rec: order.get(rec.id, 0))
    else:
        # Metadata is what makes two records comparable, so restrict the default
        # scan to records that have reached the metadata stage.
        records = (
            query.filter(ImageRecord.stage.in_(
                [PipelineStage.METADATA_READY, PipelineStage.PUBLISHED]
            ))
            .order_by(ImageRecord.created_at.desc())
            .limit(MAX_SCAN_RECORDS)
            .all()
        )

    candidates: list[DuplicateCandidate] = []
    skipped: list[str] = []
    for record in records:
        candidate = _candidate_for(record)
        if candidate is None:
            skipped.append(record.id)
            continue
        candidates.append(candidate)

    pairs = find_duplicate_pairs(
        candidates,
        visual_distance=request.visual_distance,
        metadata_threshold=request.metadata_threshold,
    )
    groups = group_duplicates(pairs, keep_per_group=request.keep_per_group)

    notes: list[str] = []
    if groups:
        notes.append(
            "Adobe advises submitting your strongest three to five assets per "
            "subject, angle, or pose; submitting too many similar shots from the "
            "same shoot can result in content refusal."
        )
    if len(candidates) >= MAX_SCAN_RECORDS:
        notes.append(
            f"Only the {MAX_SCAN_RECORDS} most recent comparable records were "
            "scanned. Narrow the selection for a complete check."
        )

    return SimilarityScanResponse(
        scanned=len(candidates),
        skipped=skipped,
        pair_count=len(pairs),
        groups=[SimilarityGroupResponse(**group.to_dict()) for group in groups],
        suggested_drop_count=sum(len(group.suggested_drop) for group in groups),
        notes=notes,
    )
