"""Validity assessment — what the confidence scores mean, and what they do not.

The operator asked for three scores so they can decide whether an idea is worth
pursuing. The scores are produced by :func:`services.research.tools._tool_assess_validity`
and the collective average is *computed* there rather than asked of the model.

This module owns the interpretation: the bands, the recommendation, and the
caveat. It exists separately from the tool because the meaning of a score is a
policy decision the UI, the tests and the model's own instructions all need to
agree on, and three copies of "70 means good" would drift.

The honest limitation, stated to the operator as well as here
-------------------------------------------------------------
Nothing in this feature can measure customer demand. There is no licensed
keyword-volume, sales, or download API in this app, and the web search tool
reports what a search engine returns — which is evidence about *supply* (how much
material already exists) and about what people write publicly, not about how many
customers would license an image. A confidence number produced here is therefore
a **judgement over gathered evidence**, and every surface that shows it says so.
Presenting it as a measured prediction would be the most damaging thing this
feature could do: the operator would make portfolio decisions on a number that
looks empirical and is not.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Score bands. Named rather than bare numbers so the UI, the recommendation and
#: the tests share one definition of "promising".
BAND_STRONG = "strong"
BAND_MODERATE = "moderate"
BAND_WEAK = "weak"
BAND_UNKNOWN = "unknown"

#: Lower bound (inclusive) of each band, strongest first.
_BANDS: tuple[tuple[float, str], ...] = (
    (70.0, BAND_STRONG),
    (45.0, BAND_MODERATE),
    (0.0, BAND_WEAK),
)

#: The collective average an idea must reach before it is worth pursuing.
#:
#: The operator's own instruction, and the reason "research a better idea" exists:
#: the point of that request is to find something *better*, so a replacement idea
#: that scores no higher than the rejected one has not answered it. Measured live:
#: a run researched a replacement and returned a collective average of **53%**
#: (below the 72% of the idea it replaced) and presented it as the answer.
#:
#: This is a **target for the agent to search against**, not a gate on the run.
#: The scores are a judgement over web evidence (see :data:`DISCLAIMER`), so
#: refusing to report an idea because it scored 78 would hide the very evidence
#: the operator needs to decide. The run always reports what it found; what the
#: target changes is that the agent keeps looking until it reaches the target or
#: demonstrably cannot.
TARGET_AVERAGE = 80.0

#: How many distinct candidate ideas the agent may research in one turn before it
#: must report the best it has. Bounded because each candidate costs tool calls,
#: and an unbounded search for an 80% idea could run until the budget is gone.
MAX_CANDIDATES = 4

#: The one-sentence meaning of each band, shown beside the score.
BAND_LABELS: dict[str, str] = {
    BAND_STRONG: "Strong — the evidence supports pursuing this",
    BAND_MODERATE: "Moderate — workable, but expect competition",
    BAND_WEAK: "Weak — the evidence does not support this yet",
    BAND_UNKNOWN: "Not assessed",
}

#: The recommendation shown with each collective band.
RECOMMENDATIONS: dict[str, str] = {
    BAND_STRONG: (
        "The evidence supports continuing. Proceed to generate the prompts, and "
        "keep the differentiation the research identified."
    ),
    BAND_MODERATE: (
        "Worth attempting with a sharper angle. Ask for a more specific variation "
        "of this idea, or continue and lean on the differentiation the research found."
    ),
    BAND_WEAK: (
        "The evidence does not support this idea as stated. Research a better idea, "
        "or narrow it substantially before generating anything."
    ),
    BAND_UNKNOWN: "No assessment was recorded for this run.",
}

#: Always shown with the scores. Kept here so it cannot be dropped from one
#: surface while another keeps it.
DISCLAIMER = (
    "These scores are the agent's judgement over the web evidence it gathered. "
    "They are not a measurement: this tool has no access to keyword volume, "
    "download counts or sales data, and search results show what already exists "
    "rather than how many customers would buy it. Treat them as a structured "
    "opinion to argue with, not a forecast."
)


def band_for(score: float) -> str:
    """The band a score falls into."""
    for threshold, band in _BANDS:
        if score >= threshold:
            return band
    return BAND_WEAK


@dataclass(frozen=True)
class ValidityView:
    """A presentation-ready view of an assessment."""

    customer_download_confidence: float
    adobe_acceptance_confidence: float
    collective_average: float
    collective_band: str
    download_band: str
    acceptance_band: str
    recommendation: str
    reasoning: str
    evidence: list[str]
    #: **What was actually assessed.** Without it the scorecard showed three
    #: numbers and a rationale with no statement of their subject, so on a
    #: "research a better idea" turn the operator could not tell which idea the
    #: numbers described — the one they rejected, or its replacement. Measured
    #: live: a replacement idea was scored and the card named nothing at all.
    subject: str = ""
    #: The average the idea is being judged against (:data:`TARGET_AVERAGE`).
    target_average: float = TARGET_AVERAGE
    disclaimer: str = DISCLAIMER

    @property
    def meets_target(self) -> bool:
        """Whether this idea reaches the bar the operator set."""
        return self.collective_average >= self.target_average

    def to_dict(self) -> dict:
        return {
            "customer_download_confidence": self.customer_download_confidence,
            "adobe_acceptance_confidence": self.adobe_acceptance_confidence,
            "collective_average": self.collective_average,
            "collective_band": self.collective_band,
            "collective_label": BAND_LABELS[self.collective_band],
            "download_band": self.download_band,
            "acceptance_band": self.acceptance_band,
            "recommendation": self.recommendation,
            "reasoning": self.reasoning,
            "evidence": self.evidence,
            "subject": self.subject,
            "target_average": self.target_average,
            "meets_target": self.meets_target,
            "disclaimer": self.disclaimer,
        }


def describe(assessment: dict | None) -> ValidityView | None:
    """Build the view for an assessment, or ``None`` when there is none.

    Returning ``None`` rather than a zeroed view is deliberate: a run with the
    validity check switched off must show *no* scorecard, not a scorecard reading
    "0 — weak", which would look like a verdict on the idea.
    """
    if not assessment:
        return None

    try:
        download = float(assessment.get("customer_download_confidence", 0.0))
        acceptance = float(assessment.get("adobe_acceptance_confidence", 0.0))
        collective = float(assessment.get("collective_average", 0.0))
    except (TypeError, ValueError):
        return None

    # Recompute the average rather than trusting the stored value, so a
    # hand-edited or older record cannot display numbers that disagree.
    expected = round((download + acceptance) / 2, 1)
    collective = expected if abs(expected - collective) > 0.05 else collective

    collective_band = band_for(collective)
    try:
        target = float(assessment.get("target_average", TARGET_AVERAGE))
    except (TypeError, ValueError):
        target = TARGET_AVERAGE

    view = ValidityView(
        customer_download_confidence=download,
        adobe_acceptance_confidence=acceptance,
        collective_average=collective,
        collective_band=collective_band,
        download_band=band_for(download),
        acceptance_band=band_for(acceptance),
        recommendation=RECOMMENDATIONS[collective_band],
        reasoning=str(assessment.get("reasoning") or "").strip(),
        evidence=[
            str(item).strip()
            for item in (assessment.get("evidence") or [])
            if str(item).strip()
        ],
        subject=str(assessment.get("subject") or "").strip(),
        target_average=target,
    )
    # A result below the operator's target gets a recommendation that says so,
    # rather than the generic band advice. "Strong" starts at 70, so an idea at 72
    # would otherwise be described as supporting a decision it misses by 8 points.
    if not view.meets_target:
        view = replace(
            view,
            recommendation=(
                f"This idea scores {collective}%, below the {target:g}% bar. "
                "Research a better idea, or ask for a sharper variation of this one, "
                "before generating anything."
            ),
        )
    return view


#: The two choices offered after an assessment, so the buttons and the system
#: prompt cannot disagree about what the operator is being asked.
CONTINUE_ACTION = "continue"
RESEARCH_AGAIN_ACTION = "research_again"

#: The message a "continue" press sends in a mode that writes prompts. Exported
#: because the agent has to *recognise* it to release the prompt gate (see
#: :func:`services.research.prompts.is_release_message`), and a second copy of the
#: wording in the agent would drift from this one the moment either changed.
CONTINUE_MESSAGE = "Continue with this idea and generate the prompts we discussed."

#: The "continue" message for a mode that never writes prompts.
#:
#: Measured live in "Find ideas": the card offered "Continue with these confidence
#: rates", whose message says *generate the prompts*. The mode forbids prompts
#: unconditionally, so the button promised an outcome the run could not produce —
#: the operator pressed it and got a second opinion instead of the prompts they had
#: just been told to expect. The decision the operator is making is the same in both
#: modes ("yes, this idea"), only its consequence differs, so the wording differs
#: and the *gate* is deliberately not released.
CONTINUE_IDEA_MESSAGE = (
    "Continue with this idea. Confirm the figures you assessed are the ones you "
    "stand behind, and restate the strongest idea in one line so I can act on it."
)

#: The message a "research a better idea" press sends.
RESEARCH_AGAIN_MESSAGE = (
    "Do not use that idea. Research and propose a better idea or niche "
    f"instead, and check its validity too. The collective average must be at "
    f"least {TARGET_AVERAGE:g}%."
)

RESEARCH_AGAIN_ACTION_BUTTON: dict[str, str] = {
    "id": RESEARCH_AGAIN_ACTION,
    "label": "Research a better idea or niche",
    "message": RESEARCH_AGAIN_MESSAGE,
}

#: The prompt-writing default. Kept as the module constant so existing callers and
#: tests keep a single source of truth for the common case; a mode that cannot
#: write prompts must call :func:`follow_up_actions` instead.
FOLLOW_UP_ACTIONS: tuple[dict[str, str], ...] = (
    {
        "id": CONTINUE_ACTION,
        "label": "Continue with these confidence rates",
        "message": CONTINUE_MESSAGE,
    },
    RESEARCH_AGAIN_ACTION_BUTTON,
)


def follow_up_actions(*, can_produce_prompts: bool) -> tuple[dict[str, str], ...]:
    """The post-assessment buttons for a mode.

    ``can_produce_prompts`` is a property of the *mode*, not of this turn: a gated
    research run reports ``wants_prompts`` as false (that is what the gate means)
    and still writes prompts the moment the operator continues. Keying on
    ``wants_prompts`` here would give a gated research run the no-prompts wording
    and make the Continue button look like it did nothing.

    Taking a boolean rather than the mode name keeps this module free of an import
    of the agent, which imports it.
    """
    if can_produce_prompts:
        return FOLLOW_UP_ACTIONS
    return (
        {
            "id": CONTINUE_ACTION,
            "label": "Continue with this idea",
            "message": CONTINUE_IDEA_MESSAGE,
        },
        RESEARCH_AGAIN_ACTION_BUTTON,
    )

