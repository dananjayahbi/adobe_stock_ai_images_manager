"""Structured run log for an adaptive auto-fix.

The operator asked for "a clear log to see what is happening", and the reason is
concrete: the previous single-shot fix reported "fixed 4 issue type(s)" while the
score did not move at all, giving no way to tell whether the corrections had
failed, been skipped, or been blocked by something outside the engine's control.

So the log records *decisions*, not just actions. Each pass states what it
targeted, what it changed, what the measurements did, and - critically - why it
stopped. A run that ends at 55% because a critical resolution issue caps the
score must say so, rather than leaving the operator to guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Log levels, ordered by how much attention they deserve.
LEVEL_INFO = "info"
LEVEL_CHANGE = "change"
LEVEL_WARN = "warn"
LEVEL_STOP = "stop"
LEVEL_DONE = "done"


@dataclass
class LogEntry:
    """One line of the run log."""

    level: str
    message: str
    #: Pass number the entry belongs to. 0 is setup, before any correction.
    pass_number: int = 0
    #: Score after this entry, when known.
    score: float | None = None

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "message": self.message,
            "pass": self.pass_number,
            "score": None if self.score is None else round(self.score, 4),
        }


@dataclass
class RunLog:
    """Ordered, append-only record of an auto-fix run."""

    entries: list[LogEntry] = field(default_factory=list)

    def add(
        self,
        level: str,
        message: str,
        *,
        pass_number: int = 0,
        score: float | None = None,
    ) -> None:
        self.entries.append(
            LogEntry(level=level, message=message, pass_number=pass_number, score=score)
        )

    def info(self, message: str, **kw) -> None:
        self.add(LEVEL_INFO, message, **kw)

    def change(self, message: str, **kw) -> None:
        self.add(LEVEL_CHANGE, message, **kw)

    def warn(self, message: str, **kw) -> None:
        self.add(LEVEL_WARN, message, **kw)

    def stop(self, message: str, **kw) -> None:
        self.add(LEVEL_STOP, message, **kw)

    def done(self, message: str, **kw) -> None:
        self.add(LEVEL_DONE, message, **kw)

    def to_list(self) -> list[dict]:
        return [entry.to_dict() for entry in self.entries]
