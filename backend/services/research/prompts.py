"""System prompts for the Prompt Research agent.

The default *style instruction* is not invented here: it is the operator's own
house template, supplied verbatim as the reference standard (see
``DEFAULT_STYLE_INSTRUCTION``). It is a **default**, exposed and editable in the
UI, because the whole point of the feature is that the operator should not have
to leave the app to get a prompt written the way they want it.

Two distinct instructions are kept apart on purpose:

* **Style instruction** — *how the images should look*. Ratio, lens, lighting,
  copy space, what must be absent, upscaling readiness. This is the part the
  operator edits.
* **Research instruction** — *how the agent should work*. Tool use, honesty about
  evidence, when to stop. Not exposed as a free-text field, because weakening it
  silently degrades every run's answer.

Merging them would let a style tweak ("make it more cinematic") quietly remove
the rule that says a blocked search must be reported.
"""

from __future__ import annotations

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

#: Rules extracted from the reference prompt. They are stated separately because
#: the operator may rewrite the *example* while still wanting these constraints,
#: and because a model reproduces a rule more reliably than it infers one.
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
RESEARCH_INSTRUCTION = """You are a stock-photography research agent inside a production tool that prepares
images for Adobe Stock. You help the operator choose a niche and write the generation
prompts for it.

HOW YOU WORK
- You act by calling tools. To call one, reply with ONLY this and nothing else:
  <tool_call>{"name": "tool_name", "arguments": {"argument": "value"}}</tool_call>
- Call ONE tool per turn. After the result comes back, decide whether to call
  another tool or to answer.
- When you have enough to answer, reply in plain prose with no tool call at all.
  That is how you finish. Do not write a tool call inside an answer.
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


def tool_list_text(specs: list[dict]) -> str:
    """Render a tool registry as the bulleted list the agent reads.

    Built from the registry rather than written by hand so a new tool cannot be
    added without the agent being told about it.
    """
    lines: list[str] = []
    for spec in specs:
        params = spec.get("parameters") or {}
        required = set(params.get("required") or [])
        described: list[str] = []
        for name, meta in (params.get("properties") or {}).items():
            marker = " (required)" if name in required else ""
            description = (meta or {}).get("description", "")
            described.append(f"{name}{marker}: {description}".strip())
        argument_text = "; ".join(described) if described else "no arguments"
        lines.append(f"- {spec['name']} — {spec.get('description', '')}")
        lines.append(f"    arguments: {argument_text}")
    return "\n".join(lines)


def _fill_tool_list(template: str, tool_list: str) -> str:
    """Substitute the tool list without ``str.format``.

    The instruction text contains literal JSON (``{"name": …}``) as the
    example tool call, so ``str.format`` would treat those braces as fields and
    raise ``KeyError: '"name"'``. A plain marker replacement keeps the example
    readable in the source.
    """
    return template.replace("__TOOL_LIST__", tool_list)


def compose_system_prompt(
    *,
    tool_specs: list[dict],
    style_instruction: str,
    mode: str,
    validity_check: bool,
    max_tools: int,
) -> str:
    """Build the full system prompt for one run.

    Assembled per run (rather than being one constant) because the tool list, the
    operator's style instruction, and the mode's objective all change what the
    agent should do, and a stale tool list is how an agent ends up calling a tool
    that no longer exists.
    """
    sections = [
        _fill_tool_list(RESEARCH_INSTRUCTION, tool_list_text(tool_specs)),
        "",
        "OBJECTIVE FOR THIS RUN",
        _objective(mode, validity_check),
        "",
        f"You have at most {max_tools} tool calls. Use fewer if the evidence is "
        "already sufficient, and always finish with a written answer.",
        "",
        STYLE_NOTE,
        "",
        "STYLE INSTRUCTION (the operator's house standard):",
        style_instruction.strip(),
        "",
        HOUSE_RULES,
    ]
    return "\n".join(sections)


def _objective(mode: str, validity_check: bool) -> str:
    """The mode-specific instruction block.

    Every prompt-producing objective states that the JSON contract in the user
    turn is mandatory. Saying it in one place only is how a model ends up
    answering in prose while the parser waits for a schema.
    """
    if mode == "static":
        return (
            "The operator gave you a hint and wants refined generation prompts for "
            "it. You do not need to research unless the hint is ambiguous; the "
            "operator's hint is the authority on the subject. Produce the requested "
            "number of prompts, each describing a different image. Answer in the "
            "JSON contract given in the operator's message — nothing else."
        )
    if mode == "batch":
        return (
            "The operator described a niche and asked for a set of prompts. Produce "
            "exactly the requested number, each describing a clearly different "
            "image inside that niche: vary the subject, setting, activity, time of "
            "day and camera position so no two would produce similar frames. "
            "Answer in the JSON contract given in the operator's message — nothing "
            "else. The non-similarity requirement is the point of this mode: a set "
            "of near-identical frames is a failed batch."
        )
    if mode == "research" and validity_check:
        return (
            "The operator wants a researched verdict before any prompts are written.\n"
            "1. Research the idea or niche using the tools. Find out what already "
            "exists, how crowded it is, and what the evidence actually supports.\n"
            "2. Call `assess_validity` with your findings to record the scores. That "
            "tool is the ONLY place the confidence numbers come from — do not state "
            "numbers it did not return.\n"
            "3. Then answer in prose: summarise what you found, give the operator a "
            "clear recommendation, and offer the two options — continue with this "
            "idea, or research a better one. Do NOT write the prompts yet: the "
            "operator decides first, and may ask for a different idea."
        )
    if mode == "research":
        return (
            "The operator wants researched prompts for an idea or niche, with no "
            "validity gate. Research it with the tools so the prompts reflect what "
            "already exists and are genuinely differentiated, then produce the "
            "requested number of prompts, each describing a different image. "
            "Answer in the JSON contract given in the operator's message — nothing "
            "else."
        )
    if mode == "ideas":
        return (
            "The operator asked you to find ideas rather than to write prompts. "
            "Research what is in demand and what is over-supplied, then propose a "
            "small number of distinct niches or concepts, strongest first. For each, "
            "say briefly why it is worth pursuing and what the competition looks "
            "like. Do NOT write prompts: the operator will pick one and ask for "
            "them."
        )
    return "Answer the operator's request using the tools available to you."
