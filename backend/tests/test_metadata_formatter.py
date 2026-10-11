"""Tests for the metadata formatter: priority ordering + aesthetic-term filter.

Task 05: high-intent commercial keywords must occupy the first 10 positions,
forbidden aesthetic adjectives must be filtered, and the settings field that
drives the priority list must round-trip. The formatter is pure, so it is
tested directly - no LLM round trip.
"""

from __future__ import annotations

import pytest

from services import metadata_formatter as mf


class TestBannedTerms:
    @pytest.mark.parametrize(
        "keyword",
        [
            "photorealistic",
            "PhotoRealistic",
            "hyper-detailed",
            "hyper detailed",
            "trending on artstation",
            "in the style of Greg Rutkowski",
            "cinematic lighting",
            "masterpiece",
            "8k",
            "",
            "   ",
        ],
    )
    def test_banned(self, keyword):
        assert mf.is_banned_keyword(keyword) is True

    @pytest.mark.parametrize(
        "keyword",
        [
            "sunset",
            "beach",
            "background",
            "photography",      # contains 'photo' but not a banned form
            "realistic style",  # 'photorealistic' is banned, plain 'realistic' is not
            "detailed anatomy", # substring is 'detailed', only 'hyper-detailed' banned
        ],
    )
    def test_allowed(self, keyword):
        assert mf.is_banned_keyword(keyword) is False


class TestPriorityOrdering:
    def test_priority_terms_move_to_front(self):
        keywords = [
            "sunset", "background", "beach", "digital art", "orange sky",
        ]
        ordered = mf.apply_priority(keywords, ("background", "digital art"))
        assert ordered[:2] == ["background", "digital art"]
        # Relative order inside each side is preserved (stable move).
        assert ordered[2:] == ["sunset", "beach", "orange sky"]

    def test_word_granularity_matching(self):
        # 'digital' must not drag an unrelated longer word along.
        ordered = mf.apply_priority(["digitalism"], ("digital art",))
        assert ordered == ["digitalism"]

    def test_exact_substring_match_still_works(self):
        ordered = mf.apply_priority(
            ["digital art background", "other"], ("digital art",)
        )
        assert ordered[0] == "digital art background"

    def test_first_matching_term_wins_position(self):
        ordered = mf.apply_priority(
            ["background texture"], ("texture", "background")
        )
        # The first *matching* term in the priority list ('texture') decides
        # the bucket, so later matching terms cannot reposition the keyword.
        assert ordered[0] == "background texture"
        assert mf.apply_priority(
            ["background texture"], ("background", "texture")
        ) == ["background texture"]

    def test_empty_priority_terms_is_a_noop(self):
        keywords = ["zeta", "alpha"]
        assert mf.apply_priority(keywords, ()) == keywords


class TestFormatKeywords:
    def test_filter_then_order_then_cap(self):
        raw = [
            "photorealistic", "sunset", "background", "hyper-detailed sky",
            "beach", "digital art", "masterpiece",
        ]
        out = mf.format_keywords(
            raw, priority_terms=("background", "digital art"), limit=10
        )
        assert out == ["background", "digital art", "sunset", "beach"]

    def test_limit_caps_after_priority(self):
        raw = [f"term{i}" for i in range(20)] + ["background"]
        out = mf.format_keywords(raw, priority_terms=("background",), limit=10)
        assert len(out) == 10
        assert out[0] == "background"

    def test_default_terms_apply_when_none_passed(self):
        out = mf.format_keywords(["wallpaper", "cat", "texture"])
        # DEFAULT_PRIORITY_TERMS lists 'texture' before 'wallpaper'.
        assert out[0] == "texture"
        assert out[1] == "wallpaper"

    def test_explicit_empty_terms_disables_reordering(self):
        out = mf.format_keywords(
            ["wallpaper", "cat"], priority_terms=()
        )
        assert out == ["wallpaper", "cat"]


class TestPriorityTermsSetting:
    @pytest.fixture()
    def store(self, tmp_path, monkeypatch):
        from config import settings

        path = tmp_path / "app_settings.json"
        monkeypatch.setattr(settings, "APP_SETTINGS_PATH", path)
        return path

    def test_round_trip(self, store):
        from services import app_settings

        app_settings.update(
            {"metadata_priority_terms": "hero image, banner, wall art"}
        )
        public = app_settings.read_public()
        assert public["metadata_priority_terms"] == "hero image, banner, wall art"
        meta = app_settings.resolve_metadata()
        assert meta.priority_terms == ("hero image", "banner", "wall art")

    def test_default_is_empty(self, store):
        from services import app_settings

        assert app_settings.read_public()["metadata_priority_terms"] == ""
        assert app_settings.resolve_metadata().priority_terms == ()

    def test_blank_clears(self, store):
        from services import app_settings

        app_settings.update({"metadata_priority_terms": "a, b"})
        app_settings.update({"metadata_priority_terms": ""})
        assert app_settings.resolve_metadata().priority_terms == ()

    def test_overlong_value_is_rejected(self, store):
        from services import app_settings

        with pytest.raises(app_settings.SettingsValidationError):
            app_settings.update(
                {"metadata_priority_terms": "x" * 2001}
            )
        assert app_settings.load_raw() == {}

    def test_parse_dedupes_and_normalises(self, store):
        terms = mf.parse_priority_terms("  Hero , hero,\nBANNER ;,bAnNeR\t")
        assert terms == ("hero", "banner")


class TestGeneratorConsumesPriorityTerms:
    def test_generate_metadata_reorders_and_filters(
        self, isolated_app_settings, monkeypatch, tmp_path
    ):
        """The stored priority list must reach the final keyword array."""
        from PIL import Image

        from config import settings
        from services import app_settings, gemini_metadata

        monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
        app_settings.update({"metadata_priority_terms": "background, texture"})

        image = tmp_path / "shot.jpg"
        Image.new("RGB", (64, 64), (90, 120, 30)).save(image, "JPEG")

        def fake_chat_json(file_path, prompt, temperature=0.2):
            return {
                "title": "Golden field at dusk",
                "filename": "golden-field",
                "description": "A calm rural landscape.",
                "keywords": [
                    "photorealistic", "rural", "background", "sunset",
                    "texture", "hyper-detailed", "field",
                ],
                "category": 1,
            }

        monkeypatch.setattr(gemini_metadata, "chat_json", fake_chat_json)
        result = gemini_metadata.generate_metadata(image)
        assert result is not None
        keywords = result["keywords"]
        # Banned terms are gone.
        assert "photorealistic" not in keywords
        assert "hyper-detailed" not in keywords
        # Priority terms lead, in their configured order.
        assert keywords[0] == "background"
        assert keywords[1] == "texture"


class TestDigitalSourceType:
    def test_embedder_declares_trained_algorithmic_media(self):
        """The IPTC disclosure tag must be part of every embed command."""
        from services import exiftool_embedder

        assert exiftool_embedder.DIGITAL_SOURCE_TYPE_TRAINED.endswith(
            "trainedAlgorithmicMedia"
        )

    def test_embed_command_carries_the_tag(self, monkeypatch, tmp_path):
        import subprocess

        from services import exiftool_embedder

        target = tmp_path / "ready.jpg"
        target.write_bytes(b"fake")

        seen: dict = {}

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="1 updated", stderr="")

        monkeypatch.setattr(exiftool_embedder.subprocess, "run", fake_run)
        monkeypatch.setattr(exiftool_embedder, "_resolve_executable", lambda: "exiftool")

        ok = exiftool_embedder.embed_metadata(
            target,
            {"title": "T", "description": "D", "keywords": ["a", "b"]},
        )
        assert ok is True
        joined = " ".join(seen["cmd"])
        assert "-XMP-iptcExt:DigitalSourceType=" in joined
        assert "trainedAlgorithmicMedia" in joined
