"""Filename-as-context for metadata generation.

The gap this pins: the metadata model receives the pixels plus the prompt and
nothing else, yet generated images are saved under names that *describe* what
they depict - for a picture that is hard to read, the name is often the only
thing that says what it is. The contract has two halves:

* A descriptive original name reaches the prompt, with orders to use it
  *together* with vision, drop it when it does not help, and never copy it
  into the output (an original name may carry dates/identifiers).
* A code-shaped name (uuid, record id, camera-roll default) reaches nothing -
  the model falls back to vision alone rather than reading a meaningless stem.
"""

from __future__ import annotations

import pytest

from models import PipelineStage
from services import gemini_metadata
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

    def run(original_filename=None):
        result = gemini_metadata.generate_metadata(
            "whatever.jpg", original_filename=original_filename
        )
        assert result is not None
        return seen["prompt"]

    return run


class TestADescriptiveNameReachesThePrompt:
    """The name supplements the pixels - both are offered, name subordinate."""

    def test_the_name_and_vision_are_both_on_the_table(self, generator):
        prompt = generator("A Coastal Cliff At Sunrise.png")
        assert 'The image file is named "A Coastal Cliff At Sunrise"' in prompt
        # The ordering rule: use both when the name helps...
        assert "TOGETHER with what you can see" in prompt
        # ...fall back to vision alone when it does not...
        assert "ignore it and rely on the image alone" in prompt
        # ...and never let the original leak into the deliverable.
        assert "Never copy this name" in prompt

    def test_it_is_labelled_context_not_an_output_field(self, generator):
        prompt = generator("robot_worker_in_factory_line.png")
        assert "context only - not an output field" in prompt

    def test_the_extension_and_extra_whitespace_are_dropped(self, generator):
        prompt = generator("  Coastal Cliff   Sunrise 01.png ")
        assert '"Coastal Cliff Sunrise 01"' in prompt
        assert ".png" not in prompt.split("Original file name", 1)[1]

    def test_braces_in_a_name_cannot_break_prompt_formatting(self, generator):
        """The block is appended AFTER .format(), like the operator text."""
        prompt = generator("weird {brace} thing.png")
        assert '"weird {brace} thing"' in prompt


class TestCodeShapedNamesFallBackToVision:
    """No description to lean on means no context block - exactly as before."""

    @pytest.mark.parametrize(
        "name",
        [
            None,
            "",
            "   ",
            # Storage renames uploads to uuid4().hex:
            "3f8a2b1c9d4e5f6a7b8c9d0e1f2a3b4c.png",
            "3f8a2b1c-9d4e-5f6a-7b8c-9d0e1f2a3b4c.jpg",
            # Pipeline copies are {record_id}.*:
            "1042.jpg",
            # Camera-roll / screenshot defaults name the take, not the content:
            "IMG_1234.JPG",
            "DSC0001.jpg",
            "Screenshot 2024-01-02 10.15.00.png",
        ],
    )
    def test_no_context_block_is_added(self, generator, name):
        prompt = generator(name)
        assert "Original file name" not in prompt

    def test_a_real_description_starting_like_a_code_survives(self, generator):
        """Whole-stem matching only: `img_2_layer_cake` is a description."""
        prompt = generator("img_2_layer_cake.png")
        assert 'The image file is named "img_2_layer_cake"' in prompt


class TestTheStagePassesTheOriginalFilename:
    """The plumbing: the record's name, not the uuid path on disk."""

    def test_metadata_stage_sends_record_filename(self, pipeline_env, monkeypatch):
        from tasks import stage_orchestrator

        captured: dict = {}

        def fake_generate(*args, **kwargs):
            captured.update(kwargs)
            return {"title": "T", "description": "D", "keywords": ["a"], "category": 8}

        monkeypatch.setattr(
            stage_orchestrator.gemini_metadata, "generate_metadata", fake_generate
        )

        record_id, _ = _make_record(
            pipeline_env["factory"],
            pipeline_env["tmp_path"],
            name="Robot Welder In Auto Factory.png",
            stage=PipelineStage.COMPATIBLE,
        )

        stage_orchestrator.run_metadata_stage(
            pipeline_env["factory"],
            [record_id],
            pipeline_env["settings"],
            delay_seconds=0,
        )

        assert captured.get("original_filename") == "Robot Welder In Auto Factory.png"
