"""Tests for Context management."""

import pytest


def _make_messages(count: int, avg_len: int = 100) -> list[dict]:
    """Helper: generate a list of messages with roughly avg_len chars each."""
    msgs = []
    for i in range(count):
        content = f"Message {i:04d} " + "x" * (avg_len - 15)
        msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": content})
    return msgs


class TestCheckOverflow:
    """Behavior 1: Detect when context exceeds max_size."""

    def test_under_max_returns_false(self):
        """Small context doesn't trigger overflow."""
        from agent_from_zero.context import check_overflow

        messages = [{"role": "user", "content": "hello"}]
        assert check_overflow(messages, max_size=1000) is False

    def test_over_max_returns_true(self):
        """Large context triggers overflow."""
        from agent_from_zero.context import check_overflow

        messages = _make_messages(100, avg_len=200)  # ~20k chars
        assert check_overflow(messages, max_size=5000) is True

    def test_exactly_at_max(self):
        """Context at exactly max_size triggers overflow."""
        from agent_from_zero.context import check_overflow

        messages = [{"role": "user", "content": "a" * 10}]
        # 10 chars of content + role dict overhead
        total = sum(len(str(m)) for m in messages)
        assert check_overflow(messages, max_size=total) is True


class TestSplitForCompression:
    """Behavior 2: Split oldest 50% for summarization."""

    def test_splits_in_half(self):
        """Oldest ~50% of messages go to the summary pile."""
        from agent_from_zero.context import split_for_compression

        messages = _make_messages(10, avg_len=50)
        to_summarize, to_keep = split_for_compression(messages, max_size=100)

        assert len(to_summarize) + len(to_keep) == 10
        # Should be roughly half
        assert len(to_summarize) >= 3
        assert len(to_keep) >= 3

    def test_oldest_messages_in_summary_pile(self):
        """The messages to summarize are the earliest ones."""
        from agent_from_zero.context import split_for_compression

        messages = _make_messages(8, avg_len=50)
        to_summarize, to_keep = split_for_compression(messages, max_size=50)

        # to_summarize should contain the first messages
        assert to_summarize[0]["content"] == messages[0]["content"]
        # to_keep should contain the last messages
        assert to_keep[-1]["content"] == messages[-1]["content"]

    def test_system_message_always_kept(self):
        """System prompt message is never put in the summary pile."""
        from agent_from_zero.context import split_for_compression

        messages = [
            {"role": "system", "content": "You are a helpful assistant. " + "x" * 80},
        ] + _make_messages(10, avg_len=50)

        to_summarize, to_keep = split_for_compression(messages, max_size=100)

        # System message should be in to_keep, never in to_summarize
        system_in_summarize = any(m.get("role") == "system" for m in to_summarize)
        assert not system_in_summarize


class TestApplySummary:
    """Behavior 3: Apply summary to replace removed messages."""

    def test_summary_replaces_old_messages(self):
        """apply_summary replaces removed messages with a summary message."""
        from agent_from_zero.context import apply_summary

        original = _make_messages(10, avg_len=50)
        to_keep = original[-5:]  # keep last 5

        summary = "Earlier: user asked about X, assistant replied with Y."

        result = apply_summary(original, to_keep, summary)
        # Should have: system-marker summary + kept messages
        assert len(result) < 10  # fewer than original
        assert any("Earlier" in m["content"] for m in result)
        # kept messages should still be there
        for kept in to_keep:
            assert kept in result

    def test_result_under_max_size(self):
        """After compression, result should be under max_size."""
        from agent_from_zero.context import apply_summary, check_overflow

        original = _make_messages(20, avg_len=200)  # ~4k chars
        to_keep = original[-3:]
        summary = "Summary of previous conversation."

        result = apply_summary(original, to_keep, summary)
        assert not check_overflow(result, max_size=10000)


class TestBuildContext:
    """Behavior 4: Full context building (no LLM, just truncation logic)."""

    def test_no_compression_when_under_max(self):
        """build_context returns messages unchanged when under max_size."""
        from agent_from_zero.context import build_context

        messages = _make_messages(5, avg_len=20)
        result = build_context(messages, max_size=100000)

        assert len(result) == len(messages)
        assert result == messages

    def test_returns_reduced_messages_when_over_max(self):
        """build_context reduces message count when over max_size (truncate, no summary)."""
        from agent_from_zero.context import build_context

        messages = _make_messages(100, avg_len=200)
        result = build_context(messages, max_size=5000)

        # Result should be fewer than original
        assert len(result) < 100
        # And under max_size
        from agent_from_zero.context import check_overflow
        assert not check_overflow(result, max_size=5000)
