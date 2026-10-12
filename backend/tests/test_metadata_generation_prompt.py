"""Generation-brief-as-context for metadata generation.

The contract: an image bound to a prompt is generated from a brief that says
what it is *meant* to show - for a picture that is hard to read, the brief is
the strongest available statement of intent. Three properties are pinned:

* ``brief_for`` composes the binding correctly and returns ``""`` for every
  "nothing to add" case (no binding, deleted row, blank title and body) -
  those records must produce prompts byte-identical to the pre-feature ones.
* The brief reaches the prompt with its ordering rules: understanding only,
  TRUST THE PIXELS when brief and picture disagree, never copy phrases.
* The metadata stage plumbs the bound record's brief - and an unbound record
  passes nothing.
"""

from __future__ import annotations

import pytest

from models import ImageRecord, PipelineStage, Prompt
from services import gemini_metadata, prompt_context
from tests.test_stage_pipeline import _make_record, pipeline_env  # noqa: F401


@pytest.fixture()
def generator(monkeypatch):
    """``generate_metadata`` with ``chat_json`` captured instead of called."""
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    seen: dict = {}

    def fake_chat_json(path, prompt, **kwargs):
        seen["prompt"] = prompt
        return {"title": "T", "description": "D", "keywords": ["a"], "category": 8}

    monkeypatch.setattr(gemini_metadata, "chat_json", fake_chat_json)

    def run(generation_prompt=None):
        result = gemini_metadata.generate_metadata(
            "whatever.jpg", generation_prompt=generation_prompt
        )
        assert result is not None
        return seen["prompt"]

    return run


def _store_prompt(factory, *, title="", body="") -> str:
    """Persist a Prompt row and return its id (mirrors the orchestrators'
    session handling: open, commit, close)."""
    db = factory()
    try:
        row = Prompt(title=title, body=body)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


class TestBriefFor:
    def test_title_and_body_compose_with_a_label(self, db_session_factory):
        prompt_id = _store_prompt(
            db_session_factory,
            title="Ayurvedic herbs",
            body="A brass bowl of dried herbs on dark slate, soft window light.",
        )
        db = db_session_factory()
        try:
            brief = prompt_context.brief_for(db, prompt_id)
        finally:
            db.close()
        assert brief.startswith("Title: Ayurvedic herbs")
        assert "brass bowl of dried herbs" in brief

    def test_body_alone_is_unlabelled_prose(self, db_session_factory):
        prompt_id = _store_prompt(db_session_factory, body="A lone lighthouse at dusk.")
        db = db_session_factory()
        try:
            brief = prompt_context.brief_for(db, prompt_id)
        finally:
            db.close()
        assert brief == "A lone lighthouse at dusk."

    @pytest.mark.parametrize("prompt_id", [None, "", "missing-prompt-id"])
    def test_everything_unbound_reads_as_empty(
        self, db_session_factory, prompt_id
    ):
        db = db_session_factory()
        try:
            assert prompt_context.brief_for(db, prompt_id) == ""
        finally:
            db.close()

    def test_a_prompt_that_is_blank_in_both_fields_is_empty(self, db_session_factory):
        prompt_id = _store_prompt(db_session_factory, title="", body="")
        db = db_session_factory()
        try:
            assert prompt_context.brief_for(db, prompt_id) == ""
        finally:
            db.close()

    def test_a_huge_brief_is_truncated_to_the_context_budget(self, db_session_factory):
        prompt_id = _store_prompt(db_session_factory, body="word " * 2000)
        db = db_session_factory()
        try:
            brief = prompt_context.brief_for(db, prompt_id)
        finally:
            db.close()
        assert len(brief) <= prompt_context.MAX_BRIEF_CHARS + 1  # + ellipsis
        assert brief.endswith("…")


class TestTheBriefReachesThePrompt:
    def test_understanding_only_and_the_ordering_rules(self, generator):
        prompt = generator("A brass bowl of herbs on slate.")
        assert "Original generation prompt (context only" in prompt
        assert "A brass bowl of herbs on slate." in prompt
        # Intent is subordinate to the picture:
        assert "TRUST THE PIXELS" in prompt
        # ...and never a source of phrases:
        assert "Never copy phrases from this brief" in prompt

    @pytest.mark.parametrize("brief", [None, "", "   "])
    def test_no_brief_means_no_context_block(self, generator, brief):
        prompt = generator(brief)
        assert "Original generation prompt" not in prompt

    def test_braces_in_a_brief_cannot_break_prompt_formatting(self, generator):
        """The block is appended AFTER .format(), like the operator text."""
        prompt = generator("A sign reading {literal_braces} in a shop window.")
        assert "{literal_braces}" in prompt


class TestTheStagePassesTheBrief:
    def test_a_bound_record_sends_its_brief(self, pipeline_env, monkeypatch):
        from tasks import stage_orchestrator

        prompt_id = _store_prompt(
            pipeline_env["factory"],
            title="Harbour Crane",
            body="Rusty harbour crane against a pale morning sky.",
        )
        record_id, _ = _make_record(
            pipeline_env["factory"],
            pipeline_env["tmp_path"],
            name="crane.jpg",
            stage=PipelineStage.COMPATIBLE,
        )

        db = pipeline_env["factory"]()
        try:
            db.get(ImageRecord, record_id).prompt_id = prompt_id
            db.commit()
        finally:
            db.close()

        captured: dict = {}

        def fake_generate(*args, **kwargs):
            captured.update(kwargs)
            return {"title": "T", "description": "D", "keywords": ["a"], "category": 8}

        monkeypatch.setattr(
            stage_orchestrator.gemini_metadata, "generate_metadata", fake_generate
        )

        stage_orchestrator.run_metadata_stage(
            pipeline_env["factory"],
            [record_id],
            pipeline_env["settings"],
            delay_seconds=0,
        )

        brief = captured.get("generation_prompt")
        assert brief and "Title: Harbour Crane" in brief
        assert "pale morning sky" in brief

    def test_an_unbound_record_sends_no_brief(self, pipeline_env, monkeypatch):
        from tasks import stage_orchestrator

        record_id, _ = _make_record(
            pipeline_env["factory"],
            pipeline_env["tmp_path"],
            name="unbound.jpg",
            stage=PipelineStage.COMPATIBLE,
        )

        captured: dict = {}

        def fake_generate(*args, **kwargs):
            captured.update(kwargs)
            return {"title": "T", "description": "D", "keywords": ["a"], "category": 8}

        monkeypatch.setattr(
            stage_orchestrator.gemini_metadata, "generate_metadata", fake_generate
        )

        stage_orchestrator.run_metadata_stage(
            pipeline_env["factory"],
            [record_id],
            pipeline_env["settings"],
            delay_seconds=0,
        )

        assert not captured.get("generation_prompt")
