"""Which research turns are executing **right now**, in this process.

Why this is not the persisted ``ResearchRun.status``
---------------------------------------------------
Two different questions were being answered by one field:

* *"What happened to this conversation?"* — history. Belongs in the database.
* *"Is a turn running at this instant?"* — concurrency. Belongs in memory.

Conflating them caused a real deadlock: a conversation is created with status
``RUNNING`` because it is **awaiting its first turn**, and the stream endpoint's
guard — "refuse a run that is already running" — then refused the very turn that
was supposed to start. The run could never be streamed at all.

Using the in-memory set instead has a second, larger benefit: a run left at
``RUNNING`` by a crashed process no longer blocks every future turn on that
conversation forever. Process-local state cannot outlive the process, which is
exactly the lifetime the question has.

This mirrors the stage job registry's reasoning (``services/jobs.py``): the app is
a single-user local tool, and a "currently executing" flag has no meaning beyond
the life of the process serving it.
"""

from __future__ import annotations

import threading

#: Run ids with a turn executing in this process.
_IN_FLIGHT: set[str] = set()

#: Guards the set. The stream endpoint is async but the guard is checked and
#: updated from request handlers, which FastAPI runs in a thread pool for a sync
#: endpoint and on the event loop for an async one — so the lock is required.
_LOCK = threading.Lock()


def is_running(run_id: str) -> bool:
    """Whether a turn for this conversation is executing right now."""
    with _LOCK:
        return run_id in _IN_FLIGHT


def begin(run_id: str) -> bool:
    """Claim the conversation for a turn.

    Returns ``False`` when a turn is already executing, which is the signal to
    refuse the request. Claiming atomically is what makes two concurrent requests
    safe: check-then-act would let both pass.
    """
    with _LOCK:
        if run_id in _IN_FLIGHT:
            return False
        _IN_FLIGHT.add(run_id)
        return True


def end(run_id: str) -> None:
    """Release the conversation. Safe to call when it was never claimed."""
    with _LOCK:
        _IN_FLIGHT.discard(run_id)


def clear() -> None:
    """Drop all claims. Used by tests so one test cannot affect the next."""
    with _LOCK:
        _IN_FLIGHT.clear()
