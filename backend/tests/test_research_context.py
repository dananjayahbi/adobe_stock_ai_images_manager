"""Context-window measurement and history folding.

The behaviour under test is the one the operator asked for: a long research
conversation must not die when it outgrows the window, and the operator must be
able to see how full the window is *before* that happens.

The tests are written against the *observable* contract — what the model is shown,
and what the indicator reports — rather than against the token arithmetic, because
the arithmetic is an estimate and pinning it would make every future adjustment a
test failure.
"""

from __future__ import annotations

import pytest

from services.research import context


def turns(count: int, *, size: int = 100) -> list[dict]:
    """A synthetic conversation of alternating turns."""
    built: list[dict] = []
    for index in range(count):
        built.append(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"turn {index} " + ("x" * size),
            }
        )
    return built


class TestEstimation:
    def test_empty_text_costs_nothing(self):
        assert context.estimate_tokens("") == 0

    def test_a_longer_text_costs_more(self):
        assert context.estimate_tokens("x" * 400) > context.estimate_tokens("x" * 40)

    def test_message_overhead_is_counted(self):
        """A long tool-call conversation has many messages, so the per-message
        overhead is not negligible."""
        one = context.estimate_messages([{"role": "user", "content": "hi"}])
        five = context.estimate_messages([{"role": "user", "content": "hi"}] * 5)
        assert five > one * 4

    def test_a_multimodal_part_list_is_handled(self):
        """Content may be a part list rather than a string."""
        counted = context.estimate_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe this"},
                        {"type": "image_url", "image_url": {"url": "data:..."}},
                    ],
                }
            ]
        )
        assert counted > 0


class TestWindowReport:
    def test_the_system_prompt_is_reported_separately(self):
        """It is the part the operator never sees and cannot trim, so knowing its
        cost explains why a short-looking thread is already full."""
        messages = [
            {"role": "system", "content": "s" * 4000},
            {"role": "user", "content": "hi"},
        ]
        report = context.window_report(messages, 10_000)
        assert report.system_tokens == 1000
        assert report.system_tokens + report.history_tokens + report.message_tokens == (
            report.used_tokens
        )

    def test_the_share_and_percentage_agree(self):
        report = context.window_report([{"role": "user", "content": "x" * 2000}], 1000)
        assert report.used_share > 0
        assert report.percent == round(report.used_share * 100, 1)

    def test_a_zero_window_does_not_divide_by_zero(self):
        report = context.window_report([{"role": "user", "content": "x"}], 0)
        assert report.used_share == 0.0
        assert report.percent == 0.0
        assert report.level == "ok"

    def test_levels_are_three_bands(self):
        small = context.window_report([{"role": "user", "content": "x" * 40}], 100_000)
        warn = context.window_report([{"role": "user", "content": "x" * 3400}], 1000)
        critical = context.window_report([{"role": "user", "content": "x" * 3960}], 1000)
        assert small.level == "ok"
        assert warn.level == "warn"
        assert critical.level == "critical"

    def test_remaining_tokens_never_goes_negative(self):
        report = context.window_report([{"role": "user", "content": "x" * 100_000}], 100)
        assert report.remaining_tokens == 0

    def test_the_serialised_report_carries_every_field_the_ui_reads(self):
        payload = context.window_report([{"role": "user", "content": "x"}], 1000).to_dict()
        for key in (
            "used_tokens",
            "window_tokens",
            "remaining_tokens",
            "percent",
            "level",
            "compacted",
            "folded_turns",
            "degraded",
            "note",
        ):
            assert key in payload


class TestFoldingDecision:
    def test_a_short_conversation_is_left_alone(self):
        """Folding costs a model call, so it must not happen gratuitously."""
        assert not context.should_compact(turns(2), 100_000)

    def test_a_full_conversation_is_folded(self):
        assert context.should_compact(turns(40, size=4000), 20_000)

    def test_a_zero_window_disables_folding(self):
        """What a unit test wants: no summariser call, no surprise."""
        assert not context.should_compact(turns(100, size=4000), 0)


class TestSummariseHistory:
    def test_a_short_history_passes_through_untouched(self, monkeypatch):
        monkeypatch.setattr(
            context, "summarise_turns", lambda *a, **k: pytest.fail("must not be called")
        )
        result = context.summarise_history(turns(3), window_tokens=100_000)
        assert result.folded_turns == 0
        assert result.summary == ""
        assert len(result.messages) == 3

    def test_the_recent_turns_are_kept_verbatim(self, monkeypatch):
        """The operator's own requirement: the last few turns survive intact.

        A summary of "the idea you just gave me" is exactly what makes a follow-up
        ambiguous, so those turns must not be paraphrased.
        """
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        history = turns(30, size=4000)
        result = context.summarise_history(
            history, window_tokens=20_000, keep_recent=5
        )
        assert result.folded_turns == 25
        # The digest, then the five most recent turns, unchanged.
        assert result.messages[0]["content"].startswith(context.SUMMARY_PREFIX)
        assert [message["content"] for message in result.messages[1:]] == [
            turn["content"] for turn in history[-5:]
        ]

    def test_the_digest_is_marked_as_a_summary(self, monkeypatch):
        """The model must not cite the digest as an external source."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        result = context.summarise_history(turns(30, size=4000), window_tokens=20_000)
        head = result.messages[0]["content"]
        assert "CONVERSATION SUMMARY" in head
        assert "Do not cite it as an external source" in head
        assert "DIGEST" in head

    def test_a_kept_recent_count_of_zero_folds_everything(self, monkeypatch):
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        result = context.summarise_history(
            turns(20, size=4000), window_tokens=20_000, keep_recent=0
        )
        assert result.folded_turns == 20
        assert len(result.messages) == 1

    def test_an_oversized_single_exchange_still_folds(self, monkeypatch):
        """If even the 'recent' turns overflow, folding must still happen: the
        alternative is a hard failure at the provider."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        history = turns(4, size=40_000)
        result = context.summarise_history(
            history, window_tokens=20_000, keep_recent=10
        )
        assert result.folded_turns > 0
        assert result.messages[0]["content"].startswith(context.SUMMARY_PREFIX)

    def test_a_digest_that_could_not_be_built_is_reported_not_swallowed(self, monkeypatch):
        """A silent failure here would leave the request overflowing."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("", ""))
        result = context.summarise_history(turns(30, size=4000), window_tokens=20_000)
        assert result.degraded is True
        assert "too large" in result.note

    def test_an_empty_history_is_not_an_error(self):
        result = context.summarise_history([], window_tokens=1000)
        assert result.messages == []

    def test_blank_turns_are_dropped(self, monkeypatch):
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        history = [{"role": "user", "content": "   "}, *turns(30, size=4000)]
        result = context.summarise_history(history, window_tokens=20_000)
        assert all(message["content"].strip() for message in result.messages)


class TestSummariserFailure:
    def test_a_failed_summariser_call_falls_back_to_an_excerpt(self, monkeypatch):
        """Folding is what keeps a long run alive, so it must succeed in *some*
        form — a failure here would turn a full window into an unrecoverable one."""
        from services.llm_client import LLMError

        def exploding(*a, **k):  # noqa: ANN002, ANN003
            raise LLMError("HTTP 500")

        monkeypatch.setattr(context, "stream_chat", exploding)
        digest, note = context.summarise_turns(turns(4))
        assert digest
        assert "local excerpt" in note

    def test_an_empty_summariser_reply_falls_back(self, monkeypatch):
        monkeypatch.setattr(context, "stream_chat", lambda *a, **k: iter([]))
        digest, note = context.summarise_turns(turns(4))
        assert digest
        assert note

    def test_the_fallback_excerpt_is_bounded(self, monkeypatch):
        from services.llm_client import LLMError

        def exploding(*a, **k):  # noqa: ANN002, ANN003
            raise LLMError("boom")

        monkeypatch.setattr(context, "stream_chat", exploding)
        digest, _ = context.summarise_turns(turns(80, size=10_000))
        assert len(digest) <= context.MAX_SUMMARY_CHARS

    def test_a_successful_summary_has_no_note(self, monkeypatch):
        monkeypatch.setattr(
            context, "stream_chat", lambda *a, **k: iter([("content", "A digest.")])
        )
        digest, note = context.summarise_turns(turns(4))
        assert digest == "A digest."
        assert note == ""

    def test_a_long_digest_is_capped(self, monkeypatch):
        """A runaway generation would re-create the problem it was called to fix."""
        monkeypatch.setattr(
            context, "stream_chat", lambda *a, **k: iter([("content", "z" * 50_000)])
        )
        digest, _ = context.summarise_turns(turns(4))
        assert len(digest) == context.MAX_SUMMARY_CHARS


class TestSummariserInput:
    def test_a_huge_transcript_is_bounded_before_it_is_sent(self):
        """Folding several whole web pages into one request would itself overflow
        the window, which is the problem being solved."""
        rendered = context._summariser_input(turns(50, size=5000))
        assert len(rendered) <= context.SUMMARISER_INPUT_CHARS + 200

    def test_the_head_and_tail_are_both_kept(self):
        """The head holds the original request, the tail the latest findings —
        the two things a digest most needs."""
        history = [
            {"role": "user", "content": "ORIGINAL-REQUEST " + "a" * 30_000},
            {"role": "assistant", "content": "LATEST-FINDING " + "b" * 30_000},
        ]
        rendered = context._summariser_input(history)
        assert "ORIGINAL-REQUEST" in rendered
        assert "LATEST-FINDING" in rendered

    def test_roles_are_labelled(self):
        rendered = context._summariser_input(turns(2))
        assert "OPERATOR" in rendered
        assert "AGENT" in rendered


class TestTheFoldLeavesRoomForTheDigest:
    """Folding to the threshold is not enough to fit.

    The digest is spliced into the *same* request as the turns that are kept, so a
    conversation folded down to exactly the threshold still overflows once the
    digest is added. Measured live before this reserve existed, the result sat at
    **100% of the window** — a request the provider truncates from the front, which
    loses the system prompt. That is the exact failure folding exists to prevent,
    so it is asserted here as a ratio, not as a token count.
    """

    def test_the_reserve_is_below_the_fold_threshold(self):
        assert context.fold_budget(100_000) < context.compact_threshold(100_000)

    def test_a_history_folded_to_the_reserve_really_fits(self, monkeypatch):
        """The observable claim: after folding, the conversation plus the digest
        is inside the window — not merely smaller than it was."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("D" * 600, ""))
        window = 20_000
        result = context.summarise_history(turns(60, size=4000), window_tokens=window)
        report = context.window_report(result.messages, window, folded=result)
        assert report.used_share < 1.0

    def test_a_zero_window_has_a_zero_reserve(self):
        assert context.fold_budget(0) == 0


class TestRetentionShrinksToFit:
    """`keep_recent` is a target, not a guarantee.

    A tool result can be the whole text of a web page, so five of them can exceed a
    small window on their own. Keeping all five would leave the conversation as full
    as it was before folding, and the run would die on its next turn.
    """

    def test_five_oversized_turns_are_not_all_kept(self, monkeypatch):
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        history = turns(10, size=20_000)
        result = context.summarise_history(
            history, window_tokens=20_000, keep_recent=5
        )
        assert result.folded_turns > 5
        assert len(result.messages) < 6

    def test_the_newest_turn_is_always_kept(self, monkeypatch):
        """A digest with no verbatim anchor cannot be acted on, so at least the
        most recent turn must survive the trimming."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        history = turns(8, size=30_000)
        result = context.summarise_history(
            history, window_tokens=4_000, keep_recent=5
        )
        assert result.messages[-1]["content"] == history[-1]["content"]

    def test_a_comfortable_window_still_keeps_the_full_target(self, monkeypatch):
        """The trimming must not fire when there is room: the operator asked for
        the last few requests to survive intact."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        history = turns(30, size=4000)
        result = context.summarise_history(
            history, window_tokens=20_000, keep_recent=5
        )
        assert [m["content"] for m in result.messages[1:]] == [
            t["content"] for t in history[-5:]
        ]


class TestCompactingARunningConversation:
    """`summarise_history` fits the *stored* history at run start. This is the
    other half: a single turn can add many large tool results, so a run that
    started comfortably inside the window can push itself out of it."""

    @staticmethod
    def running(size: int = 4000, middle: int = 20) -> list[dict]:
        """A run whose tool results have pushed it past a 20k window."""
        return [
            {"role": "system", "content": "SYSTEM-INSTRUCTIONS " + "s" * 2000},
            *turns(middle, size=size),
            {"role": "user", "content": "CURRENT-QUESTION"},
        ]

    def test_a_zero_window_is_a_no_op(self):
        messages = self.running()
        returned, folded = context.compact_live_messages(messages, window_tokens=0)
        assert returned is messages
        assert folded.folded_turns == 0

    def test_a_conversation_that_fits_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(
            context, "summarise_turns", lambda *a, **k: pytest.fail("must not be called")
        )
        messages = self.running(size=10)
        returned, folded = context.compact_live_messages(
            messages, window_tokens=100_000
        )
        assert returned is messages
        assert folded.folded_turns == 0

    def test_a_full_conversation_is_folded(self, monkeypatch):
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        messages = self.running()
        returned, folded = context.compact_live_messages(
            messages, window_tokens=20_000
        )
        assert folded.folded_turns > 0
        assert len(returned) < len(messages)

    def test_the_system_prompt_is_pinned(self, monkeypatch):
        """It carries the instructions, and it is the part the operator cannot
        see or trim — losing it is what makes a run "stop for no reason"."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        returned, _ = context.compact_live_messages(
            self.running(), window_tokens=20_000
        )
        assert returned[0]["role"] == "system"
        assert returned[0]["content"].startswith("SYSTEM-INSTRUCTIONS")

    def test_the_current_question_is_pinned(self, monkeypatch):
        """The digest must not paraphrase the question the run is answering."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        returned, _ = context.compact_live_messages(
            self.running(), window_tokens=20_000
        )
        assert returned[-1]["content"] == "CURRENT-QUESTION"

    def test_the_digest_is_spliced_in_not_appended(self, monkeypatch):
        """Appending it would leave the folded turns in place and reclaim nothing."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        returned, _ = context.compact_live_messages(
            self.running(), window_tokens=20_000
        )
        assert returned[1]["content"].startswith(context.SUMMARY_PREFIX)
        assert "DIGEST" in returned[1]["content"]

    def test_the_recent_results_are_kept_verbatim(self, monkeypatch):
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        messages = self.running()
        returned, _ = context.compact_live_messages(messages, window_tokens=20_000)
        # The newest turn before the question survives unparaphrased.
        assert returned[-2]["content"] == messages[-2]["content"]

    def test_folding_brings_the_run_back_inside_the_window(self, monkeypatch):
        """The point of the exercise: the measured percentage must come *down*.
        Before the reserve existed the live probe reported 100% after folding."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("DIGEST", ""))
        window = 20_000
        messages = self.running(size=6000, middle=14)
        before = context.window_report(messages, window).used_share
        returned, _ = context.compact_live_messages(messages, window_tokens=window)
        after = context.window_report(returned, window).used_share
        assert before >= context.COMPACT_AT_SHARE
        assert after < before

    def test_a_degraded_digest_is_reported(self, monkeypatch):
        """A silent failure would leave the request overflowing."""
        monkeypatch.setattr(context, "summarise_turns", lambda *a, **k: ("", ""))
        returned, folded = context.compact_live_messages(
            self.running(), window_tokens=20_000
        )
        assert folded.degraded is True
        assert folded.note
        # And the conversation is left intact rather than half-rewritten.
        assert len(returned) == len(self.running())

    def test_nothing_between_the_prompt_and_the_question_is_not_folded(self):
        """The opening turn has no tool results yet, so there is nothing to fold."""
        messages = [
            {"role": "system", "content": "s" * 40_000},
            {"role": "user", "content": "CURRENT-QUESTION"},
        ]
        returned, folded = context.compact_live_messages(
            messages, window_tokens=1000
        )
        assert returned is messages
        assert folded.folded_turns == 0
