"""Pin the stage-runner keyword table against the runners' real signatures.

Why this file exists
--------------------
``routers/stages.py`` builds the keyword arguments for a stage runner from a
static table. When that table listed ``metadata`` under the semantic-audit
stages, the router passed ``use_semantic`` to ``run_metadata_stage``, which does
not accept it. The resulting ``TypeError`` was raised *inside* a FastAPI
``BackgroundTask``, so it was logged while the HTTP request had already returned
success - the job sat at "running" forever, every item stayed "pending", and the
operator saw "generating metadata never lands" with no error anywhere in the UI.

An introspection test is the right guard here: the failure mode is a *signature*
mismatch, so the test compares signatures directly rather than exercising one
stage at a time.
"""

from __future__ import annotations

import inspect

import pytest

from routers.stages import (
    STAGE_RUNNERS,
    STAGES_WITH_DELAY,
    STAGES_WITH_SEMANTIC,
    _stage_kwargs,
)
from schemas import StageRunRequest
from tasks import stage_orchestrator

#: Keywords the dispatcher may inject, mapped to the table that decides them.
DISPATCHED_KEYWORDS = {"use_semantic", "delay_seconds", "options"}


def _accepted_keywords(func) -> set[str]:
    """Keyword-only parameters the callable declares."""
    params = inspect.signature(func).parameters.values()
    return {
        p.name
        for p in params
        if p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD)
    }


def test_every_stage_key_has_a_runner():
    for stage_key in ("ocr", "upscale", "refine", "compatibility", "metadata", "gallery"):
        assert stage_key in STAGE_RUNNERS, f"{stage_key} has no runner registered"


@pytest.mark.parametrize("stage_key", sorted(STAGE_RUNNERS))
def test_dispatched_keywords_are_accepted_by_the_runner(stage_key):
    """The regression: a keyword the runner does not declare kills the task."""
    runner = STAGE_RUNNERS[stage_key]
    accepted = _accepted_keywords(runner)

    kwargs = _stage_kwargs(stage_key, StageRunRequest(record_ids=["x"]), "job-1")
    injected = set(kwargs) - {"job_id"}

    unexpected = injected - accepted
    assert not unexpected, (
        f"stage '{stage_key}' would be called with {sorted(unexpected)}, "
        f"which {runner.__name__} does not accept (accepts {sorted(accepted)})"
    )


@pytest.mark.parametrize("stage_key", sorted(STAGE_RUNNERS))
def test_the_dispatcher_only_injects_known_keywords(stage_key):
    """Guards against a typo silently producing an unsupported keyword."""
    kwargs = _stage_kwargs(stage_key, StageRunRequest(record_ids=["x"]), "job-1")

    assert set(kwargs) - {"job_id"} <= DISPATCHED_KEYWORDS


def test_every_runner_accepts_a_job_id():
    """``job_id`` is always passed, so every runner must declare it."""
    for stage_key, runner in STAGE_RUNNERS.items():
        assert "job_id" in _accepted_keywords(runner), f"{stage_key} lacks job_id"


def test_metadata_does_not_receive_use_semantic():
    """The exact mismatch that broke metadata generation.

    ``run_metadata_stage`` generates titles and keywords; it never runs the
    semantic audit, so it has no ``use_semantic`` parameter.
    """
    assert "metadata" not in STAGES_WITH_SEMANTIC

    kwargs = _stage_kwargs("metadata", StageRunRequest(record_ids=["x"]), "job-1")
    assert "use_semantic" not in kwargs


def test_metadata_receives_delay_seconds():
    """The rate-limit pacing knob is metadata-specific."""
    assert "metadata" in STAGES_WITH_DELAY

    kwargs = _stage_kwargs(
        "metadata", StageRunRequest(record_ids=["x"], delay_seconds=1.5), "job-1"
    )
    assert kwargs["delay_seconds"] == 1.5


def test_refine_and_compatibility_receive_use_semantic():
    for stage_key in ("refine", "compatibility"):
        assert stage_key in STAGES_WITH_SEMANTIC
        kwargs = _stage_kwargs(stage_key, StageRunRequest(record_ids=["x"]), "job-1")
        assert "use_semantic" in kwargs


def test_upscale_receives_options_rather_than_use_semantic():
    """Upscale takes a validated options object, not the semantic flag."""
    kwargs = _stage_kwargs("upscale", StageRunRequest(record_ids=["x"]), "job-1")

    assert "options" in kwargs
    assert "use_semantic" not in kwargs
    assert "options" in _accepted_keywords(STAGE_RUNNERS["upscale"])


def test_the_semantic_and_delay_tables_are_disjoint():
    """No runner declares both, so listing one twice would be a bug."""
    assert STAGES_WITH_SEMANTIC.isdisjoint(STAGES_WITH_DELAY)


def test_crash_guard_marks_the_job_failed_rather_than_hanging(monkeypatch):
    """A runner that dies must not leave a job stuck at "running".

    Without this, the operator sees an endlessly "running" job with every item
    "pending" and no error - the exact symptom reported.
    """
    from services.jobs import STATUS_FAILED, JobItem, registry
    from routers import stages as stages_router

    job = registry.create(
        "metadata", "metadata-generate", [JobItem(record_id="r1", filename="a.jpg")]
    )
    assert job.items[0].status == "pending"

    def exploding_runner(*args, **kwargs):
        raise TypeError("run_metadata_stage() got an unexpected keyword argument")

    stages_router._run_stage_job("metadata", exploding_runner, ["r1"], {"job_id": job.id})

    refreshed = registry.get(job.id)
    assert refreshed is not None
    assert refreshed.status == STATUS_FAILED
    assert refreshed.items[0].status == "failed"
    assert "TypeError" in refreshed.items[0].message


def test_crash_guard_does_not_raise(monkeypatch):
    """The guard runs inside a background task, so it must never propagate."""
    from services.jobs import registry
    from routers import stages as stages_router

    job = registry.create("metadata", "metadata-generate", [])

    def exploding_runner(*args, **kwargs):
        raise RuntimeError("boom")

    # Must not raise.
    stages_router._run_stage_job("metadata", exploding_runner, [], {"job_id": job.id})


def test_crash_guard_tolerates_a_missing_job():
    """An unknown job id must not turn a crash into a second crash."""
    from routers import stages as stages_router

    def exploding_runner(*args, **kwargs):
        raise RuntimeError("boom")

    stages_router._run_stage_job("metadata", exploding_runner, [], {"job_id": "nope"})
