"""Validating a tool call's arguments *before* the tool runs.

The model writes its own call, and a wrong one is expensive in a way that is easy
to miss: the call is counted against the run's budget, the tool returns a
degraded outcome, and the model — having "done the search" — reasons on from a
result that says nothing. Measured live: a ``market_overview`` call arrived with
an empty ``niche``, the tool answered "No niche given", and the turn was spent.

The registry already declares which arguments are required, so the check belongs
here rather than in each tool: one implementation, driven by the same schema the
model was shown, and therefore impossible to drift from it.

Two jobs:

* **Reject an incomplete call with a correction.** The returned text names the
  missing argument, shows the exact JSON shape to send, and — importantly — is
  marked as a *failure* so the model does not read it as evidence.
* **Never charge for a rejected call.** The agent counts a call only once this
  module accepts it, so a malformed call costs a turn, not a budget slot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

#: Arguments whose name suggests free text, used to build the corrective example
#: so the model sees a plausible value rather than the literal string "value".
_EXAMPLE_VALUES: dict[str, str] = {
    "query": "search terms",
    "niche": "the niche or idea to research",
    "url": "https://example.com/page",
    "text": "the text to check",
    "prompts": "the prompts to compare",
}


@dataclass(frozen=True)
class CallValidation:
    """The verdict on one call's arguments."""

    ok: bool
    #: Names of required arguments that were missing or blank.
    missing: tuple[str, ...] = ()
    #: The correction to feed back, empty when the call is acceptable.
    text: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "missing": list(self.missing)}


def _is_blank(value: object) -> bool:
    """Whether an argument was supplied but carries no usable content.

    A *present but empty* argument is the failure that matters. A key the model
    never wrote is usually an honest mistake; ``{"niche": ""}`` is a call the
    model believed was complete, and the tool would otherwise run on nothing.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def required_arguments(parameters: dict | None) -> tuple[str, ...]:
    """The required argument names from a tool's JSON-schema ``parameters``."""
    if not isinstance(parameters, dict):
        return ()
    required = parameters.get("required") or []
    if not isinstance(required, (list, tuple)):
        return ()
    return tuple(str(name) for name in required if str(name).strip())


def example_arguments(parameters: dict | None) -> dict:
    """A plausible argument object for a tool, for the corrective message."""
    if not isinstance(parameters, dict):
        return {}
    properties = parameters.get("properties") or {}
    if not isinstance(properties, dict):
        return {}
    example: dict = {}
    for name in required_arguments(parameters):
        meta = properties.get(name) or {}
        kind = meta.get("type") if isinstance(meta, dict) else None
        if kind == "array":
            example[name] = ["first item"]
        elif kind in ("number", "integer"):
            example[name] = 1
        else:
            example[name] = _EXAMPLE_VALUES.get(name, f"the {name}")
    return example


def format_call_shape(name: str, parameters: dict | None) -> str:
    """The literal JSON the model must emit to call this tool successfully."""
    payload = json.dumps({"name": name, "arguments": example_arguments(parameters)})
    return f"<tool_call>{payload}</tool_call>"


def validate_arguments(
    name: str,
    arguments: dict,
    parameters: dict | None,
) -> CallValidation:
    """Check a call's arguments against the tool's declared requirements.

    Returns a passing verdict when the tool declares nothing required, so a tool
    with optional-only arguments is never blocked.
    """
    required = required_arguments(parameters)
    if not required:
        return CallValidation(ok=True)

    supplied = arguments if isinstance(arguments, dict) else {}
    missing = tuple(
        key for key in required if _is_blank(supplied.get(key))
    )
    if not missing:
        return CallValidation(ok=True)

    listed = ", ".join(f"`{key}`" for key in missing)
    supplied_keys = ", ".join(sorted(supplied)) or "none"
    return CallValidation(
        ok=False,
        missing=missing,
        text=(
            f"CALL REJECTED — `{name}` was not run. It is missing required "
            f"argument{'s' if len(missing) != 1 else ''}: {listed}. "
            f"You supplied: {supplied_keys}.\n\n"
            f"Send it again in exactly this shape, with real values (not "
            f"placeholders):\n{format_call_shape(name, parameters)}\n\n"
            "This call did NOT count against your budget. Do not treat this "
            "message as evidence about the subject — it says nothing about it."
        ),
    )
