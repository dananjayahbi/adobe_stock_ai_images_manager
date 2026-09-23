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

from dataclasses import dataclass

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
    disclaimer: str = DISCLAIMER

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
    return ValidityView(
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
    )


#: The two choices offered after an assessment, so the buttons and the system
#: prompt cannot disagree about what the operator is being asked.
CONTINUE_ACTION = "continue"
RESEARCH_AGAIN_ACTION = "research_again"

FOLLOW_UP_ACTIONS: tuple[dict[str, str], ...] = (
    {
        "id": CONTINUE_ACTION,
        "label": "Continue with these confidence rates",
        "message": (
            "Continue with this idea and generate the prompts we discussed."
        ),
    },
    {
        "id": RESEARCH_AGAIN_ACTION,
        "label": "Research a better idea or niche",
        "message": (
            "Do not use that idea. Research and propose a better idea or niche "
            "instead, and check its validity too."
        ),
    },
)
