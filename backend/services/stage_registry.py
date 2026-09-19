"""Stage registry - the single source of truth for pipeline stage metadata.

Keeping stage numbering, ordering, and terminal-state information in one module
lets the API, orchestrator, and frontend all agree without duplicating tables.
"""

from __future__ import annotations

from dataclasses import dataclass

from models import PipelineStage


@dataclass(frozen=True)
class StageDefinition:
    """Static description of one of the seven production stages."""

    number: int
    key: str
    name: str
    description: str
    #: Stages a record may hold while "sitting" in this stage.
    stages: tuple[PipelineStage, ...]
    #: True when reaching this stage completes the pipeline.
    terminal: bool = False

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "stages": [stage.value for stage in self.stages],
            "terminal": self.terminal,
        }


STAGE_DEFINITIONS: tuple[StageDefinition, ...] = (
    StageDefinition(
        number=1,
        key="collector",
        name="Collector",
        description="AI-generated images saved locally, waiting for an OCR sweep.",
        stages=(PipelineStage.COLLECTED,),
    ),
    StageDefinition(
        number=2,
        key="ocr",
        name="OCR Detector",
        description="Scans for embedded text. Text found removes the image from the pipeline.",
        stages=(PipelineStage.OCR_CLEAR, PipelineStage.OCR_REJECTED),
    ),
    StageDefinition(
        number=3,
        key="upscale",
        name="Upscale",
        description="Raises resolution to the Adobe Stock megapixel target.",
        stages=(PipelineStage.UPSCALED,),
    ),
    StageDefinition(
        number=4,
        key="refine",
        name="Image Refiner",
        description="Applies corrective adjustments until the acceptance score clears 80%.",
        stages=(PipelineStage.REFINED,),
    ),
    StageDefinition(
        number=5,
        key="compatibility",
        name="Compatibility Check",
        description="Runs the full acceptance algorithm and gates at the 80% threshold.",
        stages=(PipelineStage.COMPATIBLE, PipelineStage.INCOMPATIBLE),
    ),
    StageDefinition(
        number=6,
        key="metadata",
        name="Metadata & CSV",
        description="Generates titles, descriptions, keywords, and the Adobe Stock CSV.",
        stages=(PipelineStage.METADATA_READY,),
    ),
    StageDefinition(
        number=7,
        key="gallery",
        name="Gallery",
        description="Upload-ready assets at 80%+ confidence.",
        stages=(PipelineStage.PUBLISHED,),
        terminal=True,
    ),
)

#: Stage -> definition lookup.
STAGE_BY_VALUE: dict[str, StageDefinition] = {
    stage.value: definition
    for definition in STAGE_DEFINITIONS
    for stage in definition.stages
}

#: Numeric stage -> definition lookup.
STAGE_BY_NUMBER: dict[int, StageDefinition] = {
    definition.number: definition for definition in STAGE_DEFINITIONS
}

#: Stages that terminate processing; nothing advances out of these automatically.
TERMINAL_STAGES: frozenset[PipelineStage] = frozenset(
    {PipelineStage.OCR_REJECTED, PipelineStage.INCOMPATIBLE}
)

#: Ordered list used by "run the next stage" batch operations.
ORDERED_STAGES: tuple[PipelineStage, ...] = tuple(
    stage for definition in STAGE_DEFINITIONS for stage in definition.stages
)


def stage_number(stage: PipelineStage) -> int:
    """Return the 1-7 stage number for a stage value."""
    definition = STAGE_BY_VALUE.get(stage.value)
    return definition.number if definition else 0


def stage_name(stage: PipelineStage) -> str:
    """Return the human-readable name for a stage value."""
    definition = STAGE_BY_VALUE.get(stage.value)
    return definition.name if definition else stage.value


def is_terminal(stage: PipelineStage) -> bool:
    """True when the stage ends automated processing."""
    return stage in TERMINAL_STAGES


def next_stage(stage: PipelineStage) -> PipelineStage | None:
    """Return the stage a record advances to, or None when terminal."""
    if is_terminal(stage):
        return None
    for definition in STAGE_DEFINITIONS:
        if stage in definition.stages:
            index = STAGE_DEFINITIONS.index(definition)
            if index + 1 >= len(STAGE_DEFINITIONS):
                return None
            return STAGE_DEFINITIONS[index + 1].stages[0]
    return None


def serialize_registry() -> list[dict]:
    """Full registry payload for the frontend."""
    return [definition.to_dict() for definition in STAGE_DEFINITIONS]
