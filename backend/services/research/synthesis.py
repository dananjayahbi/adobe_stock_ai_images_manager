"""Turning a research answer into concrete, validated prompts.

The agent writes prose. The Prompt Library needs individual prompt bodies, and
the operator needs to be told when one of them breaks a house rule. Both jobs
happen here so the *rules* are testable without running a model.

Four things are enforced rather than trusted:

1. **Structure.** The system prompt hands the model a JSON schema and the parser
   reads it. A schema beats a delimiter because the fields arrive *labelled* —
   the title, tags and category no longer have to be guessed out of prose — and
   because ``json.dumps`` escapes newlines, so the payload survives both a
   stored transcript and an SSE frame without a second parsing convention.
   If the model ignores the schema the parser falls back to the old delimited
   and paragraph paths, each announcing itself, because a run must not silently
   yield zero prompts.
2. **House rules.** Every prompt must end with the aspect-ratio token the
   operator's system prompt requires (``--ar 16:9`` is only the shipped
   default), must be a real paragraph, and must be clear of Adobe's restricted
   terms. A violation becomes a *warning attached to that prompt*, not a
   rejection: the operator is the final judge, and silently discarding the
   model's work would be worse than showing it with a flag.
3. **Distinctness.** Two prompts that share most of their discriminating words
   would become two near-identical images, and Adobe refuses similar content.
   Duplicates are reported and the weaker one is dropped from the *suggested*
   set while still being shown.
4. **Category validity.** Adobe's CSV import rejects a category code outside its
   own list, so an invented number is dropped rather than carried into a file
   that will fail at upload.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from services.adobe_categories import CATEGORY_CODES, category_name, resolve_category
from services.adobe_restrictions import scan_metadata
from services.duplicate_detector import metadata_similarity, tokenize_metadata

#: The delimiter the system prompt asks the model to use.
BLOCK_PREFIX = "### PROMPT"

#: A prompt below this many characters cannot carry the detail the house style
#: requires (lens, light, copy space, absences) and is almost certainly a stub.
MIN_PROMPT_LENGTH = 80

#: Upper bound, so one runaway paragraph cannot dominate the library.
MAX_PROMPT_LENGTH = 2_000

#: The *shipped default* aspect-ratio token — the one the default House Standard
#: carries. It is only a fallback for callers that pass no token: the ratio a run
#: actually enforces is read from the operator's system prompt
#: (:func:`services.research.prompts.aspect_token_for`), because the House
#: Standard, not this module, owns the aspect ratio.
ASPECT_TOKEN = "--ar 16:9"

#: An ``--ar H:W`` token in any spacing or case, so an operator's ``--ar 1:1``
#: and a model's ``--ar 16:9`` are recognised and compared by value rather than
#: by spelling.
AR_TOKEN = re.compile(r"--ar\s*(\d+)\s*:\s*(\d+)", re.I)


def normalise_aspect_token(token: str | None) -> str | None:
    """Canonical ``--ar H:W`` spelling of ``token``.

    Returns ``None`` when ``token`` is missing, empty, or names no ratio at all —
    which every caller reads as "there is no aspect requirement to enforce".
    """
    if not token:
        return None
    match = AR_TOKEN.search(str(token))
    if not match:
        return None
    return f"--ar {match.group(1)}:{match.group(2)}"


def _has_aspect_token(text: str, token: str) -> bool:
    """Whether ``text`` carries ``token``, comparing the ratio not the spelling."""
    match = AR_TOKEN.search(text or "")
    if not match:
        return False
    return f"--ar {match.group(1)}:{match.group(2)}" == token

#: Pairwise wording similarity at which two prompts are treated as one idea.
#: Lower than the duplicate detector's own threshold for *records*, because two
#: generation prompts that overlap this much will very likely produce similar
#: frames even though they are not identical text.
DUPLICATE_THRESHOLD = 0.55

#: Cap on prompts accepted from one answer, matching the UI's own maximum.
MAX_PROMPTS = 60

#: The JSON contract the system prompt asks the model to answer in.
#:
#: A schema rather than a delimiter: every field the library needs arrives
#: labelled, so nothing has to be inferred from prose, and a missing field is a
#: missing key instead of a silently truncated paragraph. The ``body``
#: description is a placeholder — :func:`prompt_format_instruction` rewrites it
#: with the aspect token from the operator's system prompt on every call.
JSON_CONTRACT: dict = {
    "summary": "one sentence describing what was produced",
    "prompts": [
        {
            "title": "short human label, max 60 characters",
            "body": (
                "the full generation prompt paragraph, ending with the aspect "
                "token the House Standard specifies"
            ),
            "tags": ["2-4 short topical tags"],
            "category": 1,
            "notes": "optional one-line note for the operator",
        }
    ],
}

#: Adobe's own category codes, so an invented number never reaches the CSV.
VALID_CATEGORIES = frozenset(CATEGORY_CODES)

#: Longest title the library's own column accepts (``Prompt.title`` is 200, but
#: a 200-character label is useless in a list).
MAX_TITLE_LENGTH = 60

#: Longest single tag, and the most tags kept per prompt.
MAX_TAG_LENGTH = 40
MAX_TAGS = 6

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)

_BLOCK = re.compile(
    rf"^\s*{re.escape(BLOCK_PREFIX)}\s*\d*\s*:?\s*$",
    re.I | re.M,
)
_NUMBERED = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*])\s+(?=\S)", re.M)
_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_RUN = re.compile(r"\n{3,}")


@dataclass
class DraftPrompt:
    """One parsed prompt, with everything the UI needs to show it.

    The fields beyond ``body`` are the ones the JSON contract supplies. They are
    optional because the prose fallbacks cannot invent a title or a category, and
    a missing field must read as *absent* rather than as a default the operator
    would mistake for the model's own choice.
    """

    body: str
    index: int
    title: str = ""
    tags: list[str] = field(default_factory=list)
    #: Adobe's numeric category code, or ``None`` when the model did not supply a
    #: usable one.
    category: int | None = None
    notes: str = ""
    warnings: list[str] = field(default_factory=list)
    #: True when this prompt overlaps another and was dropped from the set the
    #: UI offers to save.
    duplicate_of: int | None = None

    def to_dict(self) -> dict:
        return {
            "body": self.body,
            "index": self.index,
            "title": self.title,
            "tags": list(self.tags),
            "category": self.category,
            "category_name": category_name(self.category) if self.category else "",
            "notes": self.notes,
            "warnings": list(self.warnings),
            "duplicate_of": self.duplicate_of,
            "duplicate": self.duplicate_of is not None,
            "chars": len(self.body),
        }


def prompt_format_instruction(
    count: int, aspect_token: str | None = ASPECT_TOKEN
) -> str:
    """The output-format block appended to the objective for prompt-producing runs.

    Given to the model verbatim so the parser is reading a contract rather than
    guessing at prose. Four details are deliberate:

    * the schema is shown as JSON, not described, because a model reproduces a
      shape it can see far more reliably than one described in a sentence;
    * the count is stated as a target rather than a command, because asking for
      exactly N sometimes yields N copies of one idea — which is the failure this
      whole feature exists to avoid;
    * ``aspect_token`` is *passed in* (resolved from the operator's system prompt
      by :func:`services.research.prompts.aspect_token_for`) so the House
      Standard is the single owner of the ratio — the runtime must follow it,
      not override it. ``None`` means the House Standard sets no ratio, and the
      block then imposes none;
    * every entry must stay inside the operator's subject while genuinely
      differing from the others — near-identical prompts become near-identical
      images, and Adobe refuses similar content.
    """
    token = normalise_aspect_token(aspect_token)
    contract = json.loads(json.dumps(JSON_CONTRACT))
    if token:
        contract["prompts"][0]["body"] = (
            f"the full generation prompt paragraph, ending with {token}"
        )
        aspect_rule = (
            f"- Each `body` must end with the literal token `{token}` — the aspect "
            "ratio from the House Standard. Follow the House Standard exactly; "
            "never substitute a different ratio."
        )
    else:
        contract["prompts"][0]["body"] = (
            "the full generation prompt paragraph, ending with the aspect-ratio "
            "token (`--ar …`) the House Standard specifies"
        )
        aspect_rule = (
            "- Follow the House Standard's aspect ratio and end each `body` with "
            "its `--ar …` token exactly; if it specifies none, add no `--ar` token."
        )
    schema = json.dumps(contract, indent=2)
    return (
        f"\nOUTPUT FORMAT — this is a contract, not a suggestion\n"
        f"Reply with ONE JSON object and nothing else. No prose before it, no "
        f"prose after it, no markdown fence. It must match this template exactly:\n\n"
        f"{schema}\n\n"
        f"Rules for the JSON:\n"
        f"- `prompts` must contain {count} entr{'y' if count == 1 else 'ies'}.\n"
        f"{aspect_rule}\n"
        f"- Each `body` must describe a DIFFERENT image: stay inside the "
        "operator's subject or niche in every entry — never swap it for an "
        "unrelated topic — but change what is depicted: a different object or "
        "variant, a different arrangement, composition, camera angle and "
        "framing. Rewording one scene is not a variation.\n"
        f"- `category` must be one of Adobe's numeric codes: "
        f"{', '.join(f'{code}={name}' for code, name in CATEGORY_CODES.items())}.\n"
        f"- If you can only write {count} genuinely different images, return fewer "
        f"and say why in `summary` — do NOT pad the list with variations of one idea."
    )


def _strip_json_fence(text: str) -> str:
    """Unwrap a ```json fence, which models add even when told not to."""
    match = _JSON_FENCE.search(text)
    return match.group(1).strip() if match else text.strip()


def _parse_json_payload(answer: str) -> tuple[dict | None, str]:
    """Find and decode the JSON object in an answer.

    Returns ``(payload, error)``. The object is located by brace matching from the
    first ``{`` rather than by a regex, so a ``body`` containing a brace (or an
    ``--ar`` aspect token) cannot truncate the payload.
    """
    text = _strip_json_fence(answer or "")
    start = text.find("{")
    if start == -1:
        return None, "no JSON object in the answer"

    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(text)):
        char = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : position + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError as exc:
                    return None, f"the JSON was malformed ({exc.msg})"
                if not isinstance(parsed, dict):
                    return None, "the JSON was not an object"
                return parsed, ""
    return None, "the JSON object was never closed"


def _coerce_tags(value: object) -> list[str]:
    """Normalise the ``tags`` field, which models write as a list or a CSV string."""
    if isinstance(value, str):
        raw = [part for part in re.split(r"[,\n]", value)]
    elif isinstance(value, (list, tuple)):
        raw = [str(part) for part in value]
    else:
        return []

    tags: list[str] = []
    for item in raw:
        cleaned = _WHITESPACE.sub(" ", str(item)).strip().strip("#").strip()
        if cleaned and len(cleaned) <= MAX_TAG_LENGTH and cleaned.lower() not in (
            tag.lower() for tag in tags
        ):
            tags.append(cleaned)
    return tags[:MAX_TAGS]


def _coerce_category(value: object) -> tuple[int | None, str]:
    """Validate the model's category against Adobe's own list.

    Returns ``(code, warning)``. An out-of-range code is *reported* and dropped,
    not silently replaced with a default: the operator should know the model
    invented a category, and Adobe's importer rejects a code it does not know.
    """
    if value is None or value == "":
        return None, ""
    if isinstance(value, bool):
        return None, f"The model gave {value!r} as a category; ignored."
    try:
        code = int(value)
    except (TypeError, ValueError):
        resolved = resolve_category(value, default=0)
        if resolved:
            return resolved, ""
        return None, (
            f"The model's category {str(value)[:40]!r} is not one of Adobe's codes; "
            "left unset."
        )
    if code not in VALID_CATEGORIES:
        return None, (
            f"The model's category {code} is not one of Adobe's codes; left unset."
        )
    return code, ""


def _drafts_from_json(answer: str) -> tuple[list[DraftPrompt], str, str]:
    """Parse the JSON contract. Returns ``(prompts, note, summary)``."""
    payload, error = _parse_json_payload(answer)
    if payload is None:
        return [], "", ""

    raw_prompts = payload.get("prompts")
    if isinstance(raw_prompts, dict):
        raw_prompts = [raw_prompts]
    if not isinstance(raw_prompts, list):
        return [], (
            "The model's JSON had no `prompts` list, so the answer was read as prose."
        ), ""

    summary = _WHITESPACE.sub(" ", str(payload.get("summary") or "")).strip()

    drafts: list[DraftPrompt] = []
    notes: list[str] = []
    for position, item in enumerate(raw_prompts, start=1):
        # A bare string entry is tolerated: it is the one field the whole feature
        # depends on, and discarding it over a missing wrapper would be perverse.
        if isinstance(item, str):
            body = _clean_body(item)
            title, tags, category, note, extra = "", [], None, "", ""
        elif isinstance(item, dict):
            body = _clean_body(str(item.get("body") or item.get("prompt") or ""))
            title = _WHITESPACE.sub(" ", str(item.get("title") or "")).strip()
            title = title[:MAX_TITLE_LENGTH]
            tags = _coerce_tags(item.get("tags"))
            category, extra = _coerce_category(item.get("category"))
            note = _WHITESPACE.sub(" ", str(item.get("notes") or "")).strip()
        else:
            continue

        if not body:
            notes.append(f"Entry {position} in the JSON had no `body`; skipped.")
            continue

        warnings = [extra] if extra else []
        drafts.append(
            DraftPrompt(
                body=body,
                index=len(drafts) + 1,
                title=title,
                tags=tags,
                category=category,
                notes=note,
                warnings=warnings,
            )
        )

    if not drafts:
        return [], (
            "The model returned JSON, but no entry in it contained a usable prompt."
        ), summary

    notes.extend(
        _validate_payload(payload, raw_prompts)
    )
    return drafts[:MAX_PROMPTS], " ".join(notes).strip(), summary


def _validate_payload(payload: dict, raw_prompts: list) -> list[str]:
    """Structural complaints about the JSON envelope itself.

    Only the ``summary`` is checked. A missing ``title`` is *not* reported: the
    contract marks it optional, a title is derived from the body when the prompt
    is saved, and a note that fires on every compliant run is noise the operator
    learns to ignore — which would hide the notes that do matter.
    """
    notes: list[str] = []
    if not str(payload.get("summary") or "").strip():
        notes.append("The JSON had no `summary` field.")
    return notes


def _clean_body(raw: str) -> str:
    """Normalise one prompt body: drop stray numbering, collapse blank runs."""
    text = raw.strip()
    # A block whose first line repeats the heading number.
    text = re.sub(r"^\s*\d{1,2}[.)]\s+", "", text)
    text = _WHITESPACE.sub(" ", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


def parse_prompts(answer: str) -> tuple[list[DraftPrompt], str]:
    """Extract prompts from a model answer.

    Returns ``(prompts, note)``. ``note`` is empty on a clean parse and otherwise
    explains the fallback that was used, so the UI can tell the operator that the
    model did not follow the requested format instead of quietly presenting a
    guess as if it were structured output.
    """
    drafts, note, _summary = parse_prompts_with_summary(answer)
    return drafts, note


def parse_prompts_with_summary(answer: str) -> tuple[list[DraftPrompt], str, str]:
    """As :func:`parse_prompts`, but also returns the JSON ``summary`` field.

    The summary is the model's own one-line statement of what it produced, which
    the UI shows above the cards. It is empty on a prose fallback, because a
    fallback has no labelled fields to read it from.
    """
    text = (answer or "").strip()
    if not text:
        return [], "The model returned no answer, so no prompts were extracted.", ""

    # 1. The JSON contract. Tried first: when the model complies, every field is
    #    labelled and nothing has to be inferred from prose.
    drafts, json_note, summary = _drafts_from_json(text)
    if drafts:
        return drafts, json_note, summary

    # 2. The delimited blocks an earlier version of the contract asked for. Kept
    #    so a stored conversation replayed after an upgrade still parses.
    if _BLOCK.search(text):
        chunks = _BLOCK.split(text)
        # The first chunk is the prose summary before the first heading.
        prompts = [
            DraftPrompt(body=_clean_body(chunk), index=index)
            for index, chunk in enumerate(chunks[1:], start=1)
        ]
        prompts = [prompt for prompt in prompts if prompt.body]
        if prompts:
            return prompts[:MAX_PROMPTS], json_note, ""

    # 3. A numbered list, which many models produce unprompted.
    if len(_NUMBERED.findall(text)) >= 2:
        parts = _NUMBERED.split(text)
        prompts = [
            DraftPrompt(body=_clean_body(part), index=index)
            for index, part in enumerate(parts[1:], start=1)
        ]
        prompts = [prompt for prompt in prompts if prompt.body]
        if prompts:
            return prompts[:MAX_PROMPTS], (
                "The model did not return the requested JSON, so the prompts were "
                "recovered from its numbered list. Check them before saving."
            ), ""

    # 4. Blank-line separated paragraphs, keeping only ones that look like a
    #    prompt (long enough to carry the house style).
    paragraphs = [
        _clean_body(part)
        for part in re.split(r"\n\s*\n", text)
        if _clean_body(part)
    ]
    candidates = [
        paragraph
        for paragraph in paragraphs
        if len(paragraph) >= MIN_PROMPT_LENGTH or AR_TOKEN.search(paragraph)
    ]
    if not candidates:
        return [], (
            json_note
            or "The model's answer did not contain anything recognisable as a "
            "prompt. Try asking again, or rephrase the idea."
        ), ""
    prompts = [
        DraftPrompt(body=body, index=index)
        for index, body in enumerate(candidates, start=1)
    ]
    return prompts[:MAX_PROMPTS], (
        "The model did not return the requested JSON, so the prompts were "
        "recovered from its paragraphs. Check them before saving."
    ), ""


def validate_prompt(body: str, aspect_token: str | None = ASPECT_TOKEN) -> list[str]:
    """House-rule warnings for one prompt.

    Warnings rather than errors: the operator may have a reason to keep a prompt
    that omits the aspect token, and an image that violates a rule is still
    cheaper to fix now than after it has been generated.

    ``aspect_token`` is the ``--ar H:W`` token the operator's system prompt
    requires (pass ``None`` when it specifies none, and no aspect warning is
    raised) — the House Standard is the only authority on the ratio.
    """
    warnings: list[str] = []
    text = (body or "").strip()

    if len(text) < MIN_PROMPT_LENGTH:
        warnings.append(
            f"Very short ({len(text)} characters) — it may not carry enough detail "
            "to produce a controlled image."
        )
    if len(text) > MAX_PROMPT_LENGTH:
        warnings.append(f"Unusually long ({len(text)} characters); generators may ignore the tail.")

    token = normalise_aspect_token(aspect_token)
    if token and not _has_aspect_token(text, token):
        warnings.append(f"Missing the house aspect token `{token}`.")

    restricted = scan_metadata(text)
    if restricted:
        warnings.append(
            "Mentions terms on Adobe's known-restrictions list: "
            + ", ".join(sorted(restricted))
        )

    lowered = text.lower()
    for forbidden, reason in (
        ("watermark", "Adobe refuses watermarks"),
        ("logo", "brand marks are a refusal reason"),
        ("text overlay", "added text is a refusal reason"),
    ):
        if forbidden in lowered and "zero" not in lowered and "no " not in lowered:
            warnings.append(f"May depict {forbidden} — {reason}.")

    return warnings


def find_duplicates(prompts: list[DraftPrompt]) -> list[tuple[int, int, float]]:
    """Pairs of prompts too alike to be worth generating separately.

    Returns ``(left_index, right_index, score)`` tuples, strongest overlap first,
    using 1-based indices so a message can refer to "#2" as the operator sees it.
    """
    token_sets = [tokenize_metadata(prompt.body, None) for prompt in prompts]
    pairs: list[tuple[int, int, float]] = []
    for left in range(len(prompts)):
        for right in range(left + 1, len(prompts)):
            score = metadata_similarity(token_sets[left], token_sets[right])
            if score >= DUPLICATE_THRESHOLD:
                pairs.append((left + 1, right + 1, round(score, 3)))
    pairs.sort(key=lambda item: item[2], reverse=True)
    return pairs


def flag_duplicates(prompts: list[DraftPrompt]) -> list[tuple[int, int, float]]:
    """Mark overlapping prompts, keeping the first of each overlapping pair.

    The *first* is kept rather than the highest-scoring one because the model
    tends to order its output by strength, and the operator reads top-down. A
    prompt already flagged is not re-flagged, so a chain of similar prompts
    collapses to one kept entry instead of a confusing web of references.
    """
    pairs = find_duplicates(prompts)
    dropped: set[int] = set()
    for left, right, _score in pairs:
        if left in dropped or right in dropped:
            continue
        # 1-based indices in the pairs; DraftPrompt.index is also 1-based.
        prompts[right - 1].duplicate_of = left
        dropped.add(right)
    return pairs


def build_drafts(
    answer: str, aspect_token: str | None = ASPECT_TOKEN
) -> tuple[list[DraftPrompt], list[tuple[int, int, float]], str, str]:
    """Parse, validate and de-duplicate an answer in one pass.

    ``aspect_token`` is forwarded to :func:`validate_prompt` — the token the
    run's own system prompt requires, so validation follows the House Standard
    the model was actually given.

    Returns ``(drafts, duplicate_pairs, note, summary)``. Warnings are *appended*
    to any the parser already attached, so a structural complaint about one entry
    is not lost when the house-rule check runs.
    """
    drafts, note, summary = parse_prompts_with_summary(answer)
    for draft in drafts:
        draft.warnings = list(draft.warnings) + validate_prompt(draft.body, aspect_token)
    pairs = flag_duplicates(drafts)
    return drafts, pairs, note, summary


def saveable_prompts(drafts: list[DraftPrompt]) -> list[str]:
    """The prompt bodies the UI offers to save — duplicates excluded.

    A duplicate is still *shown* (with a warning) because the operator may
    disagree with the similarity call, but it is not pre-selected for saving: the
    default action should not create the near-identical pair Adobe refuses.
    """
    return [draft.body for draft in drafts if draft.duplicate_of is None]


def answer_text(answer: str) -> str:
    """A human-readable rendering of the model's answer.

    A prompt-producing run answers with the JSON contract, and storing that raw
    would put `{"summary": …` in the transcript and on the thread list. This turns
    a compliant payload into the summary plus the prompt bodies, and leaves any
    other answer untouched — including one that merely *mentions* JSON, which is
    why the payload has to actually contain prompts before anything is rewritten.
    """
    text = (answer or "").strip()
    if not text or "{" not in text:
        return text

    payload, error = _parse_json_payload(text)
    if payload is None or error:
        return text

    raw_prompts = payload.get("prompts")
    if not isinstance(raw_prompts, list) or not raw_prompts:
        return text

    bodies: list[str] = []
    for item in raw_prompts:
        if isinstance(item, dict):
            body = str(item.get("body") or item.get("prompt") or "").strip()
        elif isinstance(item, str):
            body = item.strip()
        else:
            continue
        if body:
            bodies.append(_clean_body(body))
    if not bodies:
        return text

    summary = _WHITESPACE.sub(" ", str(payload.get("summary") or "")).strip()
    lines: list[str] = []
    if summary:
        lines.extend([summary, ""])
    lines.append(f"{len(bodies)} prompt{'s' if len(bodies) != 1 else ''} written:")
    lines.append("")
    for position, body in enumerate(bodies, start=1):
        lines.extend([f"{position}. {body}", ""])
    return "\n".join(lines).strip()
