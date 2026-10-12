"""The tools the research agent can call.

Design constraints, each of which is a deliberate choice:

* **Tools report; they never raise for an expected failure.** A blocked search or
  an unreadable page is a normal research outcome, and the agent must be told
  about it so it can adapt — raising would abort a run that could still succeed.
* **Numbers come from a tool, not from the model.** The confidence scores are
  computed here (including the collective average, so the model cannot get the
  arithmetic wrong), and the catalogue-size figure is the verbatim count printed
  on a result page rather than a model estimate.
* **Every market signal is labelled for what it is.** A search result count is
  evidence of *supply* (how much already exists), not of *demand* (how many
  customers would buy). Conflating the two is the single easiest way to produce a
  confident, wrong recommendation, so the tool output says so explicitly and the
  system prompt repeats it.

The registry is a data structure rather than a dispatch table of ``if`` branches
so the agent's tool list is *generated* from the tools that exist — a tool cannot
be added without the agent being told about it, or removed while still being
advertised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from services.adobe_categories import CATEGORY_CODES
from services.adobe_restrictions import scan_metadata
from services.duplicate_detector import metadata_similarity, tokenize_metadata
from services.research import blocked_store
from services.research import fetch as fetch_module
from services.research import search as search_module
from services.research import source_store
# Imported as a module (not by name) because ``validity`` is also the name of a
# key on :class:`ToolOutcome`; a by-name import of ``TARGET_AVERAGE`` would read
# as if it belonged to the outcome.
from services.research import validity as validity_module

#: Marketplaces that publish a catalogue count on their landing pages. A result
#: from one of these is *existing supply*, which is what "is this saturated?"
#: actually asks.
STOCK_MARKETPLACE_HOSTS = (
    "shutterstock.com",
    "adobe.com",
    "stock.adobe.com",
    "gettyimages.com",
    "istockphoto.com",
    "dreamstime.com",
    "alamy.com",
    "vecteezy.com",
    "freepik.com",
    "pond5.com",
    "envato.com",
    "depositphotos.com",
    "123rf.com",
    "canstockphoto.com",
    "bigstockphoto.com",
    "stockfresh.com",
)

#: Catalogue-size phrasings the marketplaces actually print, e.g.
#: "21+ Thousand Automated Robotics Warehouse ...". Captured verbatim so the
#: number in the report is quoted, never estimated.
_COUNT_PATTERNS = (
    re.compile(r"(?P<count>\d[\d,]*\+?)\s*(?:thousand|million|k|m)\b", re.I),
    re.compile(r"(?P<count>\d[\d,]{2,})\s*(?:stock|royalty-free|images|photos)\b", re.I),
)

#: How many queries ``market_overview`` runs. Three is enough to see both the
#: marketplace pages and the editorial discussion without spending a run's whole
#: tool budget in one call.
OVERVIEW_QUERY_COUNT = 3

#: Prompts above this pairwise similarity are treated as duplicates. Below the
#: duplicate detector's own 0.72 threshold on purpose: two *generation* prompts
#: that share 60% of their discriminating words will very likely produce similar
#: frames, and Adobe refuses similar content.
PROMPT_SIMILARITY_THRESHOLD = 0.55

#: Hard cap on prompts in one similarity check.
MAX_PROMPTS_PER_CHECK = 60


@dataclass
class ToolOutcome:
    """What a tool produced.

    ``text`` is what the model reads; ``summary`` is the one-liner the UI shows;
    ``sources``/``validity`` are structured payloads that become their own events
    so the operator gets a sources panel and a scorecard rather than having to
    read the model's prose.

    ``sources`` is normalised in ``__post_init__`` rather than trusted. A tool
    returning a **bare dict** instead of a one-element list passed every
    annotation and type check the project had, and then killed a live run
    mid-stream: the dict iterated as its own keys, and the accumulator called
    ``.get("url")`` on the string ``"title"``. Coercing at the dataclass boundary
    means one tool's slip is contained instead of becoming a dead run — and a
    dict is a natural thing to write for a single source, so this will recur.
    """

    text: str
    summary: str = ""
    sources: list[dict] = field(default_factory=list)
    validity: dict | None = None
    #: Set when the tool could not do its job, so the run can surface a notice.
    degraded: bool = False

    def __post_init__(self) -> None:
        # A bare dict is the common slip and is *promoted* rather than dropped:
        # the author clearly meant one source, so honour the intent.
        if isinstance(self.sources, dict):
            self.sources = [self.sources]
        elif self.sources is None:
            self.sources = []
        elif not isinstance(self.sources, list):
            # Anything else iterable (tuple, generator) becomes a list; a scalar
            # that is not a source is discarded rather than crashing the run.
            self.sources = list(self.sources) if hasattr(self.sources, "__iter__") else []
        self.sources = [
            entry for entry in self.sources if isinstance(entry, dict)
        ]


@dataclass(frozen=True)
class Tool:
    """One callable capability, with the schema the agent is shown.

    ``consumes_budget`` distinguishes **research** from **bookkeeping**. A research
    tool reaches outside the process for evidence (a search, a page fetch); a
    bookkeeping tool only records what the model has already worked out
    (``assess_validity``, ``check_prompt_similarity``).

    Charging both against one budget is a real defect, not a rounding error:
    measured live, a run spent its 10th and final call on ``assess_validity``, the
    loop then correctly judged the score below target and asked for a stronger
    candidate — with **zero calls left to look for one**. The quality mechanism was
    starved by the budget that was supposed to enable it. Bookkeeping is therefore
    free, and the budget bounds only the work that can run away.
    """

    name: str
    description: str
    parameters: dict
    run: Callable[[dict], ToolOutcome]
    #: False for tools that only record the model's own conclusions.
    consumes_budget: bool = True

    def spec(self) -> dict:
        """The declaration handed to the prompt builder."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# --------------------------------------------------------------------------- #
# Argument helpers
# --------------------------------------------------------------------------- #

def _text(arguments: dict, key: str, *, limit: int = 500) -> str:
    """Read a required string argument, tolerating a list or a number.

    Models routinely send ``{"query": ["a", "b"]}`` or a bare number where a
    string was asked for. Coercing here means a slightly-wrong call still runs
    instead of failing and burning a turn.
    """
    value = arguments.get(key)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value)
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def _list_of_text(arguments: dict, key: str, *, limit: int = 60) -> list[str]:
    """Read a list-of-strings argument, accepting a single string as one item."""
    value = arguments.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = [str(item) for item in value]
    else:
        return []
    return [item.strip() for item in items if str(item).strip()][:limit]


def _number(arguments: dict, key: str, default: float = 0.0) -> float:
    """Read a numeric argument, tolerating a percentage or a numeric string."""
    value = arguments.get(key)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        value = match.group(0) if match else None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _score(arguments: dict, key: str) -> float | None:
    """Read a 0-100 confidence score, or ``None`` when it was not supplied.

    Distinct from :func:`_number` because a *missing* score must stay missing.
    Returning a numeric sentinel does not work: it would be clamped into the
    valid range by :func:`_clamp_score` and a missing ``adobe_acceptance_confidence``
    would silently become **0**, which reads to the operator as a confident
    verdict that Adobe will refuse the idea.
    """
    if key not in arguments or arguments.get(key) is None:
        return None
    raw = arguments.get(key)
    if isinstance(raw, str) and not re.search(r"\d", raw):
        return None
    return _clamp_score(_number(arguments, key))


def _clamp_score(value: float) -> float:
    """Clamp a confidence score into 0-100.

    A model asked for 0-100 will occasionally answer 0.8 or 120; clamping keeps
    the scorecard meaningful instead of rejecting the assessment outright.
    """
    if 0 < value <= 1.0:
        # A 0-1 answer is rescaled rather than clamped to 1%, which would read
        # as "no confidence" when the model meant "80%".
        value *= 100
    return max(0.0, min(100.0, round(value, 1)))


def _host_of(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url or "", re.I)
    return (match.group(1) if match else "").lower().removeprefix("www.")


def _is_marketplace(url: str) -> bool:
    host = _host_of(url)
    return any(host == known or host.endswith("." + known) for known in STOCK_MARKETPLACE_HOSTS)


def _largest_catalogue_count(results: list[search_module.SearchResult]) -> str:
    """The largest catalogue figure printed verbatim on a result, if any.

    Quoted, not computed: the figure comes from a marketplace's own landing page
    ("21+ Thousand …"), which is the only supply number available without an API.
    """
    best_value = 0.0
    best_label = ""
    for result in results:
        haystack = f"{result.title} {result.snippet}"
        for pattern in _COUNT_PATTERNS:
            for match in pattern.finditer(haystack):
                raw = match.group("count")
                digits = re.sub(r"[^\d.]", "", raw)
                try:
                    value = float(digits)
                except ValueError:
                    continue
                unit = match.group(0).lower()
                if "million" in unit or unit.strip().endswith("m"):
                    value *= 1_000_000
                elif "thousand" in unit or unit.strip().endswith("k"):
                    value *= 1_000
                if value > best_value:
                    best_value = value
                    best_label = match.group(0).strip()
    return best_label


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

def _tool_web_search(arguments: dict) -> ToolOutcome:
    """Search the web and return the hits as sources."""
    query = _text(arguments, "query", limit=search_module.MAX_QUERY_LENGTH)
    if not query:
        return ToolOutcome(
            text="That call had no `query` argument. Call web_search again with a query string.",
            summary="No query given",
            degraded=True,
        )

    response = search_module.run_search(query)
    return ToolOutcome(
        text=response.to_tool_text(),
        summary=(
            f"{len(response.results)} results for “{query}”"
            if response.ok
            else f"Search unavailable for “{query}”"
        ),
        sources=[result.to_dict() for result in response.results],
        degraded=not response.ok,
    )


def _tool_fetch_page(arguments: dict) -> ToolOutcome:
    """Read one page's text."""
    url = _text(arguments, "url", limit=1000)
    if not url:
        return ToolOutcome(
            text="That call had no `url` argument. Call fetch_page again with a URL from a search result.",
            summary="No URL given",
            degraded=True,
        )

    # Refuse a URL that already failed, BEFORE any network I/O. The same page
    # will fail the same way, and a retry costs a tool call plus the full
    # timeout to reach an answer we already have — so the check runs first,
    # with no socket opened, and the message tells the model why (the prior
    # error) and what to do instead (pick another source).
    blocked, prior_error = blocked_store.is_blocked(url)
    if blocked:
        return ToolOutcome(
            text=(
                f"Refused: {url} is on the blocked list — it previously failed "
                f"({prior_error}) and is not fetched again.\n"
                "Do not retry blocked URLs; use a different source."
            ),
            summary="Blocked: previously failed",
            degraded=True,
        )

    page = fetch_module.fetch_page(url)
    # A **list**, even on failure. `ToolOutcome.sources` is `list[dict]`, and
    # returning a bare dict here iterates its *keys* downstream: `_merge_sources`
    # then calls `.get("url")` on the string "title" and the whole run dies with
    # `AttributeError: 'str' object has no attribute 'get'`. That failure reached
    # production because the type annotation said `list[dict]` and nothing checked
    # the value — the list and the dict both satisfy "iterable of something".
    source = (
        [{"title": page.title or url, "url": url, "snippet": page.text[:280]}]
        if page.ok
        else []
    )

    text = page.to_tool_text()
    summary = (
        f"Read {_host_of(url) or url} ({len(page.text)} chars)"
        if page.ok
        else f"Could not read {url}"
    )
    if not page.ok:
        # Only a URL that *passed* validation counts as a read failure.
        # `fetch_page` reports validation refusals (bad scheme, private host,
        # no host) with `ok=False` too, but those are decided without any
        # request being made — recording them would block a URL that was never
        # actually tried, so `is_fetchable` separates the two cases.
        fetchable, _ = fetch_module.is_fetchable(url)
        if fetchable:
            blocked_store.add_failure(url, page.error)
            removed = source_store.remove_url(url)
            text += (
                "\nThis URL was added to the blocked list and will not be "
                "fetched again."
            )
            summary = f"Could not read {url}; blocked"
            if removed:
                # The model must know its priority set shrank, or it will keep
                # naming a source that is no longer on the list.
                text += " It was also removed from your priority sources."
                summary += "; removed from priority sources"

    return ToolOutcome(
        text=text,
        summary=summary,
        sources=source,
        degraded=not page.ok,
    )


def _tool_market_overview(arguments: dict) -> ToolOutcome:
    """Check how much already exists for a niche — supply, not demand.

    Runs a few differently-angled queries, because one query answers "does this
    exist" and three answer "how much of it exists". The result is explicit about
    the distinction: the marketplace share is a **saturation** signal, and the
    catalogue figure is **supply**. Neither is demand, and the text says so,
    because this is the tool most likely to be over-read.
    """
    niche = _text(arguments, "niche", limit=200)
    if not niche:
        return ToolOutcome(
            text="That call had no `niche` argument. Call market_overview again with the niche.",
            summary="No niche given",
            degraded=True,
        )

    queries = [
        f"{niche} stock photos",
        f"{niche} stock photo site:shutterstock.com OR site:adobe.com",
        f"{niche} stock photography market saturated",
    ][:OVERVIEW_QUERY_COUNT]

    collected: list[search_module.SearchResult] = []
    failures: list[str] = []
    fallback_used = False
    for query in queries:
        response = search_module.run_search(query)
        if response.ok:
            collected.extend(response.results)
            # Keyed on the evidence tier rather than on "a fallback happened": a
            # same-tier fallback is not a degraded source, and claiming it was
            # would put a false caveat on good general-index results.
            if response.degraded_source:
                fallback_used = True
        else:
            failures.append(f"{query!r}: {response.error}")

    if not collected:
        return ToolOutcome(
            text=(
                f"No market overview could be assembled for {niche!r} because every "
                "search failed.\n" + "\n".join(f"- {failure}" for failure in failures) + "\n"
                "This is NOT evidence that the niche is empty. Report that the "
                "overview could not be gathered and set your confidence low."
            ),
            summary="Market overview unavailable",
            degraded=True,
        )

    marketplace = [result for result in collected if _is_marketplace(result.url)]
    catalogue = _largest_catalogue_count(marketplace or collected)
    share = round(100 * len(marketplace) / len(collected))

    lines = [
        f"Market overview for {niche!r} — assembled from {len(queries)} searches, "
        f"{len(collected)} results.",
        "",
        f"- Stock marketplaces among the results: {len(marketplace)} of {len(collected)} ({share}%).",
        f"- Largest catalogue figure printed on a result: {catalogue or 'none found'}.",
        "",
        "How to read this:",
        "- The marketplace share measures how much of the top results are stock "
        "catalogues. A high share means this niche is heavily supplied — expect "
        "strong competition and be specific to stand out.",
        "- The catalogue figure is a real number printed by a marketplace page. It "
        "counts how much already EXISTS. It is NOT how many customers search for "
        "it, and you must not describe it as demand.",
        "- No tool here can measure customer demand. If you have no other evidence, "
        "say the demand picture is unverified rather than implying it is good.",
    ]
    if fallback_used:
        lines.append("")
        lines.append(
            "- Some or all of these results came from the news fallback rather than "
            "the general search index. News coverage shows what is being written "
            "about the topic; it does NOT show how many competing stock images "
            "exist, so treat the marketplace share as incomplete."
        )
    if failures:
        lines.append("")
        lines.append("Searches that failed (do not read these as 'no competition'):")
        lines.extend(f"- {failure}" for failure in failures)

    return ToolOutcome(
        text="\n".join(lines),
        summary=(
            f"{len(marketplace)}/{len(collected)} results are marketplaces; "
            f"catalogue {catalogue or 'unknown'}"
            + (" (news fallback)" if fallback_used else "")
        ),
        sources=[result.to_dict() for result in collected],
        # A *partial* failure degrades the step too: the share was computed over
        # fewer results than the overview claims, and a step that silently
        # under-reports is exactly what the operator needs to see.
        degraded=bool(failures) or fallback_used,
    )


def _tool_assess_validity(arguments: dict) -> ToolOutcome:
    """Record the two confidence scores; the average is computed here.

    The model supplies only what it can actually judge — how likely a customer
    is to want this, and how likely Adobe is to accept it. The collective average
    is arithmetic, so it is computed rather than asked for: a model asked for
    three numbers will occasionally return three that do not agree.
    """
    download = _score(arguments, "customer_download_confidence")
    acceptance = _score(arguments, "adobe_acceptance_confidence")
    subject = _text(arguments, "subject", limit=300)

    # `subject` is checked here as well as being declared required in the schema.
    # The schema requirement is enforced by the agent loop's argument validator;
    # this is the last line of defence, because `call_tool` is a public entry point
    # and a scorecard with no subject is the exact defect the argument exists to
    # prevent — three numbers and a rationale with no statement of what they judged.
    if not subject:
        return ToolOutcome(
            text=(
                "assess_validity needs a `subject`: the exact idea or niche these "
                "scores describe, in one short phrase. Without it the operator "
                "cannot tell which idea the numbers are about — which matters most "
                "on a 'research a better idea' turn. Call it again with `subject`."
            ),
            summary="No subject given",
            degraded=True,
        )

    if download is None or acceptance is None:
        missing = [
            name
            for name, value in (
                ("customer_download_confidence", download),
                ("adobe_acceptance_confidence", acceptance),
            )
            if value is None
        ]
        return ToolOutcome(
            text=(
                "assess_validity needs both `customer_download_confidence` and "
                "`adobe_acceptance_confidence` as numbers from 0 to 100. Missing: "
                + ", ".join(missing)
                + ". Call it again with both. Do not guess a value you cannot "
                "support from the evidence you gathered."
            ),
            summary=f"Scores missing: {', '.join(missing)}",
            degraded=True,
        )

    reasoning = _text(arguments, "reasoning", limit=2000)
    evidence = _list_of_text(arguments, "evidence", limit=12)
    collective = round((download + acceptance) / 2, 1)

    assessment = {
        "customer_download_confidence": download,
        "adobe_acceptance_confidence": acceptance,
        "collective_average": collective,
        # The idea these numbers describe. Recorded so the scorecard can name its
        # subject: without it, a "research a better idea" turn produced three
        # numbers and a rationale with no statement of *which* idea they were
        # about, and the operator could not tell the replacement from the idea
        # they had just rejected.
        "subject": subject,
        # The bar the operator set, recorded with the scores so a reader can see
        # whether the idea cleared it without knowing the constant.
        "target_average": validity_module.TARGET_AVERAGE,
        "reasoning": reasoning,
        "evidence": evidence,
        # The UI shows this so the operator is never told the numbers came from
        # a measurement when they are a judgement over the gathered evidence.
        "basis": "agent judgement over the gathered web evidence",
    }

    meets = collective >= validity_module.TARGET_AVERAGE
    # Multi-idea aware: on a "Find new ideas" turn the operator may have asked
    # for several ideas, and each one must be reported WITH its own score.
    # Nothing here may tell the model to stop after one assessment or to hide a
    # below-target idea — the count comes from the operator's message (the
    # objective), and a below-target score is presented as lower confidence.
    return ToolOutcome(
        text=(
            "Assessment recorded:\n"
            f"- Subject assessed: {assessment['subject']}\n"
            f"- Customer download confidence: {download}\n"
            f"- Adobe Stock acceptance confidence: {acceptance}\n"
            f"- Collective average: {collective}\n"
            f"- Target: {validity_module.TARGET_AVERAGE:g}\n\n"
            + (
                "This clears the target. Report this idea together with its "
                "scores when you answer. If the operator asked for several "
                "ideas, assess each remaining idea the same way — one "
                "`assess_validity` call per idea — before you answer, and "
                "present every idea with its own score. For a single-idea "
                "request, summarise your findings and offer the two options — "
                "continue with this idea, or research a better one. Do not "
                "write the prompts yet."
                if meets
                else (
                    f"This is BELOW the {validity_module.TARGET_AVERAGE:g}% "
                    "target — report it with its real score, never a "
                    "rounded-up one. Do not drop an idea the operator asked "
                    "for just because it scored under the target: present it "
                    "with its real score and mark it as lower confidence. If "
                    "the operator asked for several ideas, assess each "
                    "remaining distinct idea too — one `assess_validity` call "
                    "per idea — and present them all with their scores. For a "
                    "single-idea request, research a *different* candidate "
                    "idea and score that one too, until one reaches the "
                    f"target or you have tried {validity_module.MAX_CANDIDATES} "
                    "candidates. If none reaches it, say so plainly and report "
                    "the best one with its real score."
                )
            )
        ),
        summary=(
            f"Confidence recorded — download {download}, acceptance {acceptance}, "
            f"average {collective}"
            + ("" if meets else f" (below the {validity_module.TARGET_AVERAGE:g}% target)")
        ),
        validity=assessment,
    )


def _tool_check_restrictions(arguments: dict) -> ToolOutcome:
    """Check proposed wording against Adobe's known-restrictions list.

    A real pre-flight check: Adobe maintains a ~300-entry restricted list, and a
    prompt that names a protected brand, landmark or character is a refusal
    waiting to happen. Catching it while the prompt is still text is far cheaper
    than catching it after an image has been generated and upscaled.
    """
    terms = _list_of_text(arguments, "terms", limit=30)
    if not terms:
        blob = _text(arguments, "text", limit=4000)
        terms = [blob] if blob else []
    if not terms:
        return ToolOutcome(
            text=(
                "That call had no `terms` argument. Call check_restrictions again "
                "with the wording to check, as a list of strings."
            ),
            summary="No terms given",
            degraded=True,
        )

    hits = scan_metadata(*terms)
    if not hits:
        return ToolOutcome(
            text=(
                "No restricted terms found in the submitted wording. It is clear "
                "against Adobe's known-restrictions list.\n"
                "Note this checks the published restricted list only — it does not "
                "prove the concept is free of intellectual property."
            ),
            summary="Clear of the restricted list",
        )

    return ToolOutcome(
        text=(
            "RESTRICTED TERMS FOUND: "
            + ", ".join(sorted(hits))
            + "\nThese appear on Adobe's known-restrictions list and would be a "
            "refusal reason. Remove or replace them before writing the prompts."
        ),
        summary=f"Restricted terms found: {', '.join(sorted(hits))}",
        degraded=True,
    )


def _tool_check_prompt_similarity(arguments: dict) -> ToolOutcome:
    """Flag prompts that are too alike to be worth generating separately.

    This is the batch mode's core guarantee. Adobe's most common content refusal
    is *similar content*, and a model asked for fifteen prompts about one niche
    will happily produce fifteen that differ only in adjectives — which would
    become fifteen near-identical images, most of them wasted generations.
    """
    prompts = _list_of_text(arguments, "prompts", limit=MAX_PROMPTS_PER_CHECK)
    # Drop the protocol markup before measuring. Measured live: the model emitted
    # a malformed tool-call turn, and the run then offered that raw
    # `<tool_call>{…}</tool_call>` string as a "prompt" — so the similarity tool
    # was asked to compare 0 real prompts and reported "not enough prompts to
    # compare", which reads as a tool fault rather than a malformed answer.
    from services.research import protocol as protocol_module

    prompts = [
        cleaned
        for cleaned in (protocol_module.strip_tool_calls(prompt) for prompt in prompts)
        if cleaned
    ]
    if len(prompts) < 2:
        return ToolOutcome(
            text=(
                "Similarity needs at least two prompts. Call check_prompt_similarity "
                "again with the full list you intend to return."
            ),
            summary="Not enough prompts to compare",
            degraded=True,
        )

    token_sets = [tokenize_metadata(prompt, None) for prompt in prompts]

    pairs: list[tuple[int, int, float]] = []
    for left in range(len(prompts)):
        for right in range(left + 1, len(prompts)):
            score = metadata_similarity(token_sets[left], token_sets[right])
            if score >= PROMPT_SIMILARITY_THRESHOLD:
                pairs.append((left, right, round(score, 3)))
    pairs.sort(key=lambda item: item[2], reverse=True)

    if not pairs:
        return ToolOutcome(
            text=(
                f"All {len(prompts)} prompts are sufficiently distinct "
                f"(no pair reaches {PROMPT_SIMILARITY_THRESHOLD:.2f} shared wording). "
                "You may return them as they are."
            ),
            summary=f"{len(prompts)} prompts, no overlaps",
        )

    lines = [
        f"{len(pairs)} overlapping pair(s) found — these would likely produce similar "
        "images and risk Adobe's 'similar content' refusal:",
    ]
    for left, right, score in pairs[:12]:
        lines.append(f"- #{left + 1} and #{right + 1} share {score:.0%} of their wording")
        lines.append(f"    #{left + 1}: {prompts[left][:110]}")
        lines.append(f"    #{right + 1}: {prompts[right][:110]}")
    lines.append("")
    lines.append(
        "Rewrite the flagged prompts so each describes a genuinely different image: "
        "change the subject, the setting, the activity, the time of day, the weather "
        "or the camera position — not just the adjectives."
    )
    return ToolOutcome(
        text="\n".join(lines),
        summary=f"{len(pairs)} overlapping prompt pair(s)",
        degraded=True,
    )


def _tool_list_categories(arguments: dict) -> ToolOutcome:  # noqa: ARG001 - no args
    """Return Adobe Stock's category codes."""
    lines = [f"{code} = {name}" for code, name in sorted(CATEGORY_CODES.items())]
    return ToolOutcome(
        text=(
            "Adobe Stock category codes:\n" + "\n".join(lines) + "\n\n"
            "Use one of these names when a prompt needs a category."
        ),
        summary=f"{len(CATEGORY_CODES)} categories",
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

#: Tools available in every mode.
_BASE_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="web_search",
        description="Search the web. Use it to see what already exists for a niche.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"],
        },
        run=_tool_web_search,
    ),
    Tool(
        name="fetch_page",
        description="Read one web page in full, given a URL from a search result.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "An http(s) URL to read."}
            },
            "required": ["url"],
        },
        run=_tool_fetch_page,
    ),
    Tool(
        name="market_overview",
        description=(
            "Check how heavily a niche is already supplied: what share of results "
            "are stock marketplaces, and the catalogue size printed on a "
            "marketplace page. Measures supply, never demand."
        ),
        parameters={
            "type": "object",
            "properties": {
                "niche": {
                    "type": "string",
                    "description": "The niche or concept to check.",
                }
            },
            "required": ["niche"],
        },
        run=_tool_market_overview,
    ),
    Tool(
        name="check_restrictions",
        description=(
            "Check proposed wording against Adobe's known-restrictions list "
            "(brands, landmarks, characters, protected symbols)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The words or phrases to check.",
                }
            },
            "required": ["terms"],
        },
        run=_tool_check_restrictions,
    ),
    Tool(
        name="list_categories",
        description="List Adobe Stock's category codes and names.",
        parameters={"type": "object", "properties": {}},
        run=_tool_list_categories,
    ),
)

#: Only offered when a set of prompts is being produced, because it is
#: meaningless while the agent is still deciding *what* to write.
_SIMILARITY_TOOL = Tool(
    name="check_prompt_similarity",
    description=(
        "Check a set of drafted prompts against each other and flag any pair too "
        "alike to be worth generating separately. Always call this before "
        "returning more than one prompt."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The full list of drafted prompts.",
            }
        },
        "required": ["prompts"],
    },
    run=_tool_check_prompt_similarity,
    # Bookkeeping: it compares prompts the model already wrote. Charging for it
    # would let the final quality check be the thing that exhausts the budget.
    consumes_budget=False,
)

#: Only offered when the operator enabled the validity check, so the scores
#: cannot appear in a run that was not asked to assess anything.
_VALIDITY_TOOL = Tool(
    name="assess_validity",
    description=(
        "Record your confidence assessment for one idea. Call it once per "
        "idea you propose — each call scores the idea named in its `subject` "
        "— after researching and before answering. Each call computes that "
        "idea's collective average."
    ),
    parameters={
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": (
                    "The exact idea or niche these scores describe, in one short "
                    "phrase — for example 'cold-storage warehouse robotics'. Always "
                    "state it: on a 'research a better idea' turn the operator must "
                    "be able to tell which idea the numbers are about."
                ),
            },
            "customer_download_confidence": {
                "type": "number",
                "description": "0-100: how likely a customer is to want this image.",
            },
            "adobe_acceptance_confidence": {
                "type": "number",
                "description": "0-100: how likely Adobe Stock is to accept it.",
            },
            "reasoning": {
                "type": "string",
                "description": "Why these scores — the evidence and its limits.",
            },
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Short bullets of the evidence behind the scores.",
            },
        },
        "required": [
            "subject",
            "customer_download_confidence",
            "adobe_acceptance_confidence",
            "reasoning",
        ],
    },
    run=_tool_assess_validity,
    # Bookkeeping, and the single most important one to exempt: measured live, a
    # run spent its last budgeted call here, the loop then correctly judged the
    # score below target and asked for a stronger candidate with no calls left.
    consumes_budget=False,
)


def tools_for(
    *,
    wants_prompts: bool,
    validity_check: bool,
) -> tuple[Tool, ...]:
    """The tool set for one run.

    Gating here rather than inside the tools keeps the agent's advertised
    capabilities honest: a tool it is not shown is one it cannot call, so the
    validity scorecard cannot appear in a run where the operator switched the
    check off.
    """
    tools: list[Tool] = list(_BASE_TOOLS)
    if wants_prompts:
        tools.append(_SIMILARITY_TOOL)
    if validity_check:
        tools.append(_VALIDITY_TOOL)
    return tuple(tools)


def registry_for(**kwargs) -> dict[str, Tool]:
    """The tool set as a name → tool mapping, for dispatch."""
    return {tool.name: tool for tool in tools_for(**kwargs)}


def specs_for(**kwargs) -> list[dict]:
    """The tool declarations, for the system prompt."""
    return [tool.spec() for tool in tools_for(**kwargs)]


def call_tool(registry: dict[str, Tool], name: str, arguments: dict) -> ToolOutcome:
    """Run a tool, converting an unexpected crash into a reported failure.

    A tool bug must not kill the run: the agent can be told "that call failed"
    and still produce an answer from the evidence it already has. The exception
    is logged with a traceback because it *is* a bug worth fixing.
    """
    tool = registry.get(name)
    if tool is None:
        return ToolOutcome(
            text="", summary=f"Unknown tool {name!r}", degraded=True
        )
    try:
        return tool.run(arguments or {})
    except Exception as exc:  # noqa: BLE001 - a tool bug must not abort the run
        import logging

        logging.getLogger(__name__).exception("Tool %s crashed", name)
        return ToolOutcome(
            text=(
                f"The tool {name!r} failed with an internal error: "
                f"{type(exc).__name__}: {exc}. Continue without it, or try a "
                "different tool."
            ),
            summary=f"{name} failed",
            degraded=True,
        )
