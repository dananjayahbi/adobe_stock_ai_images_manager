"""Metadata formatter - commercial keyword ordering and aesthetic-term filtering.

Three portal-side rules that a raw LLM answer routinely violates:

1. **Top-10 priority**: Adobe weights the first ten keyword positions most, so
   the operator's high-intent commercial terms are stably moved to the front
   (only positions move; the remaining relative order is preserved).
2. **Aesthetic adjective filter**: hype words that model-generated imagery
   leans on (``photorealistic``, ``hyper-detailed``, ``trending on
   artstation``...) add no search value and flag the asset as AI-flavoured
   copy. Exact matches and substring forms are both dropped.
3. **AI provenance**: the IPTC ``DigitalSourceType`` tag is written as
   ``trainedAlgorithmicMedia`` at the embed point (see
   :mod:`services.exiftool_embedder`) - declared, not hidden.

Kept separate from :mod:`services.gemini_metadata` so the rules are unit
testable without an LLM round trip.
"""

from __future__ import annotations

import re

#: Exact keyword matches to drop - pure hype words with no search intent.
AESTHETIC_BANNED_EXACT: frozenset[str] = frozenset(
    {
        "photorealistic",
        "photo realistic",
        "photorealism",
        "hyperrealistic",
        "hyper realistic",
        "hyper-detailed",
        "hyper detailed",
        "hyperrealism",
        "ultra detailed",
        "ultra-detailed",
        "highly detailed",
        "insanely detailed",
        "trending on artstation",
        "artstation",
        "trending",
        "award winning",
        "award-winning",
        "masterpiece",
        "epic",
        "8k",
        "4k",
        "unreal engine",
        "octane render",
        "cinematic lighting",
        "depth of field",
        "bokeh",
        "adorable",  # sentiment, not search intent
    }
)

#: Substring forms - caught wherever they appear inside a longer keyword.
AESTHETIC_BANNED_PARTIAL: tuple[str, ...] = (
    "in the style of",
    "trending on",
    "hyper-detailed",
    "hyper detailed",
    "photorealistic",
    "photo realistic",
    "hyperrealistic",
)

#: Phrases the formatter *moves* to the front of the keyword list. The
#: operator overrides this list per installation via the
#: ``metadata_priority_terms`` app setting; this is the built-in default.
DEFAULT_PRIORITY_TERMS: tuple[str, ...] = (
    "ai generated",
    "artificial intelligence",
    "generative ai",
    "digital art",
    "concept art",
    "illustration",
    "background",
    "texture",
    "wallpaper",
    "icon",
    "logo design",
    "banner",
    "card background",
    "frame",
    "decorative",
    "abstract",
    "seamless",
    "pattern",
)

_WORD = re.compile(r"[a-z0-9]+")


def is_banned_keyword(keyword: str) -> bool:
    """True when a keyword is a forbidden aesthetic/hype term."""
    lowered = keyword.strip().lower()
    if not lowered:
        return True
    if lowered in AESTHETIC_BANNED_EXACT:
        return True
    return any(term in lowered for term in AESTHETIC_BANNED_PARTIAL)


def parse_priority_terms(raw: str | None) -> tuple[str, ...]:
    """Split the operator's comma/newline-separated priority list into terms."""
    if not raw:
        return ()
    parts = re.split(r"[,\n;]+", str(raw))
    seen: set[str] = set()
    terms: list[str] = []
    for part in parts:
        term = " ".join(part.split()).strip().lower()
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
    return tuple(terms)


def _matches(keyword_lower: str, term: str) -> bool:
    """Term match at word granularity: 'digital art' does not hit 'digital artsy'."""
    if keyword_lower == term:
        return True
    kw_tokens = _WORD.findall(keyword_lower)
    term_tokens = _WORD.findall(term)
    if not term_tokens or len(term_tokens) > len(kw_tokens):
        return False
    # Contiguous token subsequence match.
    for start in range(len(kw_tokens) - len(term_tokens) + 1):
        if kw_tokens[start : start + len(term_tokens)] == term_tokens:
            return True
    return False


def apply_priority(keywords: list[str], priority_terms: tuple[str, ...]) -> list[str]:
    """Stably move priority-term keywords to the front (top-10 slots).

    Ordering within each side is preserved, duplicates are impossible (input
    is already deduplicated), and a keyword matching several terms lands at
    the position of its *first* matching term.
    """
    if not priority_terms or not keywords:
        return keywords

    buckets: dict[int, list[str]] = {}
    rest: list[str] = []
    for keyword in keywords:
        lowered = keyword.lower()
        hit = next(
            (idx for idx, term in enumerate(priority_terms) if _matches(lowered, term)),
            None,
        )
        if hit is None:
            rest.append(keyword)
        else:
            buckets.setdefault(hit, []).append(keyword)

    ordered: list[str] = []
    for idx in sorted(buckets):
        ordered.extend(buckets[idx])
    ordered.extend(rest)
    return ordered


def format_keywords(
    keywords: list[str],
    *,
    priority_terms: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> list[str]:
    """Full pass: filter banned terms, apply priority order, cap length.

    ``priority_terms`` defaults to :data:`DEFAULT_PRIORITY_TERMS` when None
    (an empty tuple explicitly passed means "no priority ordering").
    """
    terms = DEFAULT_PRIORITY_TERMS if priority_terms is None else priority_terms
    cleaned = [kw for kw in keywords if kw and not is_banned_keyword(kw)]
    ordered = apply_priority(cleaned, terms)
    if limit is not None:
        ordered = ordered[:limit]
    return ordered
