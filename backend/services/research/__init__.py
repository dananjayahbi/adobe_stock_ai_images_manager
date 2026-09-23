"""Prompt Research — an agentic prompt-research workspace.

The package turns the app's existing single-shot LLM helpers into a small agent
that can *investigate* a niche before writing prompts for it:

* :mod:`services.research.search` — keyless web search, with a block reported
  rather than mistaken for an empty result set.
* :mod:`services.research.protocol` — the text tool-call protocol. The
  configured gateway does not support OpenAI ``tools``, so tool calls are
  exchanged as text and parsed here.
* :mod:`services.research.tools` — the tool registry the agent can call.
* :mod:`services.research.prompts` — the system prompts, including the editable
  operator instruction and the house photographic style.
* :mod:`services.research.events` — the streamed event vocabulary.
* :mod:`services.research.agent` — the loop that drives all of the above.
* :mod:`services.research.synthesis` — turning a brief into concrete prompts.
* :mod:`services.research.validity` — the confidence assessment.
* :mod:`services.research.runs` — run persistence and event replay.

Nothing here is imported by the image pipeline, so a failure in research can
never affect processing.
"""

from __future__ import annotations

__all__ = [
    "agent",
    "events",
    "prompts",
    "protocol",
    "runs",
    "search",
    "synthesis",
    "tools",
    "validity",
]
