"""System prompt assembly for the Prompt Research agent.

:func:`compose_system_prompt` stacks three sections, each owned by a different
party:

* **Research instruction** — *how the agent should work*: tool-call protocol,
  evidence rules, when to finish, and the answer format the parser reads. Not
  operator-editable, because weakening it silently degrades every run's answer
  (a style tweak must not be able to remove the rule that a blocked search gets
  reported).
* **Runtime section** — the per-run objective (mode + validity gate), the tool
  budget, and any uploaded priority sources. Generated fresh each turn.
* **Operator system prompt** — one plain text per mode from
  :mod:`services.research.system_prompts`, pasted verbatim: structure, template,
  styles and rules all live there, no placeholders, no length limit.

``DEFAULT_STYLE_INSTRUCTION`` and ``HOUSE_RULES`` are the *shipped default* of
that operator section (the old style block, kept verbatim so an untouched
install behaves exactly as before) — the editable copy lives in the
system-prompts store, not here.
"""

from __future__ import annotations

#: The collective average an idea must reach, rendered into the objective text.
#:
#: Read from :mod:`services.research.validity` so the instruction the agent reads,
#: the tool that records the score and the card the operator sees cannot disagree
#: about the bar. Imported lazily inside :func:`_objective`'s callers rather than
#: at module scope: ``validity`` imports nothing from here, but keeping the
#: constant as a string at module scope would freeze it at import time and make a
#: changed target invisible to a long-running server.
def _target_text() -> str:
    from services.research import validity

    return f"{validity.TARGET_AVERAGE:g}%"


def _candidates_text() -> str:
    from services.research import validity

    return str(validity.MAX_CANDIDATES)


#: The operator's reference prompt, used as the default style instruction.
#:
#: Kept verbatim: it is the standard the generated prompts are measured against,
#: and paraphrasing it would change what the feature produces.
DEFAULT_STYLE_INSTRUCTION = (
    "Epic commercial stock photograph of a vast, futuristic automated "
    "fulfillment center floor. Several unmanned AMRs, AGV tugs, and high-reach "
    "automated stackers are stationed across a gleaming epoxy floor marked with "
    "concentric amber and yellow transit curves. Towering high-bay storage racks "
    "flank the sides under soft volumetric daylight from architectural ceiling "
    "louvers. Wide-angle 20mm lens, f/6.3, deep cinematic focus across the entire "
    "16:9 frame, leaving clean editorial copy space in the upper third. Completely "
    "unmanned, pristine surfaces, zero text, zero brand logos, ready for "
    "high-resolution upscaling. --ar 16:9"
)

#: The shipped house rules. A **default**: the operator may edit them
#: (:mod:`services.research.house_style`), and this is what a reset restores and
#: what a run with no saved rules uses.
#:
#: Kept as a constant because it is the contract the tests assert against — the
#: ratio token and the refusal-reason rules must survive any edit of the operator's
#: copy, which is exactly why the tests read *this*, not the saved value.
HOUSE_RULES = """House rules for every prompt you produce:
- Aspect ratio is ALWAYS 16:9, and the prompt must end with the literal token `--ar 16:9`.
- Describe a wide, deep-focus composition with clean editorial copy space
  (the upper third is the house default).
- Specify the lens and aperture explicitly (e.g. wide-angle 20mm, f/6.3) and say
  that focus is deep and cinematic across the whole frame.
- Light naturally and volumetrically; never add sunrays, lens flares, light leaks
  or other non-natural elements.
- State the absence of text, logos, watermarks, brand marks, signage and people
  where the concept allows it, because any of those is an Adobe refusal reason.
- Say the frame is clean, pristine and ready for high-resolution upscaling.
- Photographic realism only: no illustration, 3D render, painting, or stylised
  treatment. Adobe rejects AI artefacts, over-processing and added grain.
- Prefer surfaces and materials a real photograph would show (concrete, epoxy,
  brushed metal, glass) over abstract or decorative descriptions.
- Keep the subject plausible and commercially useful: the kind of image an art
  director would license for a campaign, article or presentation."""

#: What the operator may change. Stated to the model so it knows which parts of
#: its instruction are fixed house rules and which are the operator's taste.
STYLE_NOTE = (
    "The style instruction below is the operator's house standard. Follow its "
    "look, lens, lighting and framing choices, and apply the house rules on top "
    "of it."
)

#: The working rules for the agent itself. Deliberately NOT operator-editable:
#: they are what keep a run honest and terminating.
#:
#: Contains ``__TOOL_LIST__`` and ``__ANSWER_FORMAT__`` markers, substituted by
#: :func:`_fill_markers` rather than ``str.format`` (the text contains literal
#: JSON braces, which ``str.format`` would read as fields).
RESEARCH_INSTRUCTION = """You are a stock-photography research agent inside a production tool that prepares
images for Adobe Stock. You help the operator choose a niche and write the generation
prompts for it.

TOOL CALL PROTOCOL — read this carefully; a malformed call is discarded
- You act by calling tools. To call one, reply with EXACTLY this and nothing else:
  <tool_call>{"name": "tool_name", "arguments": {"argument_name": "value"}}</tool_call>
- `name` must be one of the tool names listed below, spelled exactly.
- `arguments` must use the argument names listed for that tool, spelled exactly.
  Do not invent argument names, do not rename them, and do not nest them.
- Every required argument must carry a REAL value from the operator's request. Never
  send an empty string, `null`, `""`, `"value"`, `"..."` or a placeholder. A call
  with a missing or empty required argument is rejected and does nothing.
- Call ONE tool per turn. Wait for its result before deciding what to do next.
- Put the tool call in its OWN turn. Never mix a tool call with prose or with the
  final answer: text written alongside a call is discarded.
- Do NOT describe a call you are about to make. Do not write "I will search for…"
  or "let me check…" and then stop. Either emit the call, or answer.
- If a call is rejected, the rejection message tells you exactly what was missing
  and shows the exact shape to resend. Read it and resend correctly. A rejected
  call costs you a turn but not a tool-call slot.
- Never invent tool output. If you did not read it from a tool result, do not
  present it as a fact.

TOOLS YOU HAVE
__TOOL_LIST__

EVIDENCE RULES — these matter more than sounding confident
- Search snippets are evidence of what exists, not of how many customers want it.
  Never claim to know search volume, download counts, or sales figures unless a
  tool result literally contains that number.
- If a search fails or is blocked, say so plainly and lower your confidence. A
  failed search is NEVER evidence that a niche is empty, unserved or uncrowded.
- Treat the presence of many strong existing results as competition, and say so.
- Distinguish what you verified from what you are inferring. Label inferences.
- It is better to answer "the evidence is thin" than to produce a confident
  answer the evidence does not support.

FINISHING — the single most important rule
- You finish by writing your ANSWER in the exact format below. The format is not
  optional and it is not a style preference: the tool parses your reply, and a
  reply in the wrong shape is DISCARDED. The operator then sees a run that stopped
  with no result, and your work is lost.
- Your final reply must contain NO tool-call markup at all. No `<tool_call>`, no
  `<DSML>` tags, no fenced JSON example. Markup anywhere in the final answer makes
  the whole answer unparseable.
- Answer as soon as you can answer well. Do not stop part-way to narrate, and do
  not announce that you are about to finish — just finish.
- If the evidence is thin, still deliver the answer in the required format and say
  in it that the evidence is thin. An incomplete answer in the right format is
  usable; a complete answer in the wrong format is thrown away.

__ANSWER_FORMAT__

WRITING PROMPTS
- A prompt must be one self-contained paragraph an image generator can use
  directly, not a list of instructions to a person.
- Every prompt must describe a DIFFERENT image. Vary the subject, the setting,
  the time of day, the weather, the camera position and the human/robot activity
  — not just the wording. Two prompts that would produce near-identical frames
  are a defect, because Adobe refuses similar content.
- Never include text, logos, brands, real people, celebrities, trademarks,
  landmarks under copyright, or currency in a prompt.
- Be specific and physical. "A wide shot of a warehouse" is useless; name the
  machines, surfaces, materials, colour temperature and what is happening."""

#: What the agent must do when the run is *not* asked for prompts. Stated as a
#: format block for the same reason the JSON contract is: the alternative — leaving
#: "how to finish" implicit for these modes — is a model that narrates and stops.
PROSE_ANSWER_FORMAT = """ANSWER FORMAT
Write your answer as plain prose. It must contain no tool-call markup, no
`<tool_call>` tags and no DSML tags. Nothing parses your prose, so write it for
the operator to read: lead with the conclusion, then the evidence behind it."""


def tool_list_text(specs: list[dict]) -> str:
    """Render a tool registry as the bulleted list the agent reads.

    Built from the registry rather than written by hand so a new tool cannot be
    added without the agent being told about it.

    Each entry carries a **literal call template** in addition to the prose
    description. That is deliberate: a model reproduces a shape it can copy far
    more reliably than one it has to assemble from a list of parameter names, and
    a wrong argument name makes the call unparseable or the tool unusable.
    """
    from services.research import toolcall

    lines: list[str] = []
    for spec in specs:
        params = spec.get("parameters") or {}
        required = set(params.get("required") or [])
        described: list[str] = []
        for name, meta in (params.get("properties") or {}).items():
            marker = " (REQUIRED)" if name in required else " (optional)"
            description = (meta or {}).get("description", "")
            described.append(f"        {name}{marker}: {description}".rstrip())
        lines.append(f"- {spec['name']} — {spec.get('description', '')}")
        if described:
            lines.append("    arguments:")
            lines.extend(described)
        else:
            lines.append("    arguments: none")
        lines.append(f"    call it exactly like this: {toolcall.format_call_shape(spec['name'], params)}")
    return "\n".join(lines)


def _fill_tool_list(template: str, tool_list: str) -> str:
    """Substitute the tool list without ``str.format``.

    The instruction text contains literal JSON (``{"name": …}``) as the
    example tool call, so ``str.format`` would treat those braces as fields and
    raise ``KeyError: '"name"'``. A plain marker replacement keeps the example
    readable in the source.
    """
    return template.replace("__TOOL_LIST__", tool_list)


def _fill_markers(template: str, tool_list: str, answer_format: str) -> str:
    """Substitute both markers in the instruction block.

    ``__ANSWER_FORMAT__`` states the exact shape of the final reply, which differs
    by mode: a prompt run must end with the JSON contract, everything else with
    prose. Leaving it implicit is what let a research run answer in prose, parse to
    zero prompts, and report success with nothing in it.
    """
    return (
        template.replace("__TOOL_LIST__", tool_list)
        .replace("__ANSWER_FORMAT__", answer_format)
    )


def is_release_message(message: str) -> bool:
    """Whether this turn releases the prompt gate on a validity-gated run.

    A validity-gated run deliberately does **not** ask for prompts: the agent
    scores the idea and stops so the operator can decide. The "Continue with these
    confidence rates" button then has to tell the agent that prompts are wanted
    *now* — and the agent cannot infer that from the words alone, because
    :attr:`RunRequest.wants_prompts` is computed from the mode and the gate, not
    from the message.

    Measured live: pressing Continue sent the canned message, the run re-ran with
    the gate still on, `wants_prompts` stayed False, no ANSWER FORMAT block was
    substituted, the objective still said "Do NOT write the prompts yet" — and the
    operator received a second assessment instead of the prompts. That is the
    reported "the agent didn't provide the prompt at the end".

    Recognised by the **shared constant** rather than a substring, so the wording
    lives in one place: :data:`services.research.validity.CONTINUE_MESSAGE` is what
    the button sends and what this matches.
    """
    from services.research import validity

    normalised = " ".join((message or "").split()).casefold()
    if not normalised:
        return False
    if normalised == " ".join(validity.CONTINUE_MESSAGE.split()).casefold():
        return True
    # A typed equivalent, for an operator who does not use the button. Deliberately
    # narrow: it must not fire on "continue researching", which asks for more work.
    return normalised in _RELEASE_PHRASES


#: Typed equivalents of the Continue button, matched exactly (after normalisation)
#: so ordinary prose that happens to contain "continue" cannot release the gate.
_RELEASE_PHRASES = frozenset(
    {
        "continue",
        "continue with this idea",
        "continue and generate the prompts",
        "generate the prompts",
        "write the prompts",
        "yes, generate the prompts",
        "go ahead and write the prompts",
    }
)


def aspect_token_for(mode: str) -> str | None:
    """The ``--ar H:W`` token the operator's system prompt for ``mode`` requires.

    The system prompt is the single owner of the House Standard — including the
    aspect ratio — so the runtime reads the token from it rather than
    hardcoding one (an untouched install still resolves to the shipped
    ``--ar 16:9`` default, because that is what its default text says). ``None``
    means the text specifies no ratio: callers then impose and validate none,
    because the system prompt is the only authority.
    """
    from services.research import synthesis, system_prompts

    match = synthesis.AR_TOKEN.search(system_prompts.effective(mode) or "")
    if not match:
        return None
    return f"--ar {match.group(1)}:{match.group(2)}"


def answer_format_block(
    *, wants_prompts: bool, count: int = 1, mode: str = "generate"
) -> str:
    """The answer-format section for a run.

    For a prompt run this is the JSON contract (from
    :func:`services.research.synthesis.prompt_format_instruction`), with the
    aspect token resolved from this mode's system prompt so the contract and
    the House Standard cannot disagree about the ratio; otherwise the prose
    block. Kept here so the system prompt and the user turn cannot disagree
    about what the model is being asked to emit.
    """
    if not wants_prompts:
        return PROSE_ANSWER_FORMAT
    from services.research import synthesis

    return synthesis.prompt_format_instruction(
        max(1, count), aspect_token=aspect_token_for(mode)
    ).strip()


def compose_system_prompt(
    *,
    tool_specs: list[dict],
    mode: str,
    validity_check: bool,
    max_tools: int,
    wants_prompts: bool = True,
    count: int = 1,
    released: bool = False,
    source_guidance: str = "",
) -> str:
    """Build the full system prompt for one run.

    Assembled as, in order:

    1. **The transport block** (:data:`RESEARCH_INSTRUCTION` with the tool list
       and the answer format substituted in) — machinery the agent cannot work
       without: tool-call syntax, evidence rules, the parseable finish.
    2. **The runtime section** — the per-run objective (which encodes the mode
       and the validity gate), the tool budget, and the operator's priority
       sources when any are uploaded.
    3. **The operator's system prompt** (:mod:`services.research.system_prompts`)
       — one plain text, pasted verbatim, no substitution and no placeholders.
       Structure, template, styles and rules all live here; the shipped default
       is the old style block, so an unchanged install behaves as before.

    ``released`` is the operator having pressed Continue on a validity-gated
    run, which is the one case where that mode *does* want the JSON prompt
    contract.
    """
    from services.research import system_prompts

    sections = [
        _fill_markers(
            RESEARCH_INSTRUCTION,
            tool_list_text(tool_specs),
            answer_format_block(
                wants_prompts=wants_prompts, count=count, mode=mode
            ),
        ),
        "",
        "OBJECTIVE FOR THIS RUN",
        _objective(mode, validity_check, released=released, count=count),
        "",
        f"You have at most {max_tools} tool calls. Use fewer if the evidence is "
        "already sufficient, and always finish with the answer described above.",
    ]
    if source_guidance.strip():
        # It changes *where the agent looks*, so it sits before the operator's
        # content guidance — the same position the old composer used.
        sections.extend(["", source_guidance.strip()])
    sections.extend(["", system_prompts.effective(mode).strip()])
    return "\n".join(sections)


def _objective(mode: str, validity_check: bool, released: bool = False, count: int = 1) -> str:
    """The mode-specific instruction block.

    Every prompt-producing objective states that the JSON contract is mandatory.
    Saying it in one place only is how a model ends up answering in prose while
    the parser waits for a schema — which is the silent-drop failure the operator
    sees as "the agent stopped without giving me prompts".

    ``released`` is the operator having pressed Continue on a gated run, which is
    the one case where a gated research run *does* want prompts.

    ``count`` feeds the prompt-producing modes: ``generate`` is single-or-many
    decided by one knob. ``ideas`` deliberately does **not** use it — there is
    no count control for that mode; the operator says how many ideas they want
    in the message itself, and the objective tells the agent to read it there.
    """
    if mode in ("static", "generate"):
        return (
            "The operator gave you a description and wants generation prompts for "
            "it. You do not need to research unless the request is ambiguous; the "
            "operator's description is the authority on the subject. Base the "
            "subject on THIS message: every prompt stays inside the description or "
            "niche the operator just gave — never swap it for an unrelated topic "
            "and never carry a subject over from earlier in the conversation. "
            f"Produce exactly {max(1, count)} prompt(s), each a genuinely "
            "different image: change what is depicted — a different object or "
            "variant, a different arrangement, composition, camera angle and "
            "framing — not just the wording, so no two would produce similar "
            "frames. If the description names one specific object, that object "
            "appears in every prompt and only its depiction changes. Your FINAL "
            "reply must be the JSON object from ANSWER FORMAT — nothing before it, "
            "nothing after it."
        )
    if mode == "batch":
        return (
            "The operator described a niche and asked for a set of prompts. Produce "
            "exactly the requested number, each a genuinely different image inside "
            "that niche: for every prompt choose a different subject or variant the "
            "niche contains, plus a different arrangement, composition, camera "
            "angle and framing — never the same subject reworded. Stay inside the "
            "niche the operator gave in THIS message; do not drift to unrelated "
            "topics or reuse a subject from earlier in the conversation. Your "
            "FINAL reply must be the JSON object from ANSWER FORMAT. The "
            "non-similarity requirement is the point of this mode: a set of "
            "near-identical frames is a failed batch."
        )
    # Checked BEFORE the gated branch: that branch matches on `validity_check`
    # alone, so a released run would otherwise fall into "Do NOT write the prompts
    # yet" and the operator's Continue press would be ignored.
    if mode == "research" and validity_check and released:
        return (
            "The operator has reviewed your confidence assessment and asked you to "
            "proceed.\n"
            "1. Research anything further you still need with the tools. You do not "
            "need to re-score an idea you already assessed.\n"
            "2. Produce the requested number of prompts for the idea that was "
            "assessed, each describing a different image.\n"
            "Your FINAL reply must be the JSON object from ANSWER FORMAT — nothing "
            "before it, nothing after it."
        )
    if mode == "research" and validity_check:
        return (
            "The operator wants a researched verdict before any prompts are written.\n"
            "1. Research the idea or niche using the tools. Find out what already "
            "exists, how crowded it is, and what the evidence actually supports.\n"
            "2. Call `assess_validity` with your findings to record the scores. That "
            "tool is the ONLY place the confidence numbers come from — do not state "
            "numbers it did not return. Always pass `subject`: the exact idea the "
            "scores describe.\n"
            f"3. If the collective average is below {_target_text()}, do NOT present "
            "that idea as the answer. Research a *different* candidate and score it "
            "too, until one reaches the target or you have tried "
            f"{_candidates_text()} candidates. Then report the best one with its real "
            "score and say plainly whether it reached the target.\n"
            "4. Answer in the prose format from ANSWER FORMAT: name the idea you "
            "assessed, summarise what you found, give the operator a clear "
            "recommendation, and offer the two options — continue with this idea, "
            "or research a better one.\n"
            "Do NOT write the prompts yet: the operator decides first, and may ask "
            "for a different idea."
        )
    if mode == "research":
        return (
            "The operator wants researched prompts for an idea or niche, with no "
            "validity gate. Research it with the tools so the prompts reflect what "
            "already exists and are genuinely differentiated, then produce the "
            "requested number of prompts, each describing a different image. Your "
            "FINAL reply must be the JSON object from ANSWER FORMAT — nothing "
            "before it, nothing after it."
        )
    if mode == "ideas":
        scoring = (
            " The operator asked for a validity check: call `assess_validity` "
            "separately for EACH idea you propose (pass `subject` = the idea) "
            "so each one gets its own real scorecard, and present every idea "
            "together with the score its own call returned."
            if validity_check
            else ""
        )
        return (
            "The operator asked you to find ideas rather than to write prompts. "
            "Research what is in demand and what is over-supplied, then propose "
            "EXACTLY the number of distinct niche(s) or concept(s) they asked "
            "for in their message — read it from their wording; if they did "
            "not say how many, propose five — strongest first. Deliver all of "
            "them: do not stop after one idea and do not drop any from your "
            "answer. Rate each idea against the "
            f"{_target_text()} collective-confidence target to rank and "
            "recommend — recommend the strongest, say plainly when an idea "
            "falls short of that level, and mark weaker ones as lower "
            "confidence, but present them with their real scores rather than "
            "holding them back. For each, say briefly why it is worth pursuing "
            "and what the competition looks like. Do NOT write prompts: the "
            f"operator will pick one and ask for them.{scoring}"
        )
    return "Answer the operator's request using the tools available to you."
