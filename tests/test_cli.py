"""Tests for CLI entry point and system prompt loading."""

import os
import tempfile


class TestSystemPromptLoading:
    """Behavior 5: System prompt is loaded from a file."""

    def test_load_prompt_from_file(self):
        """load_system_prompt() reads content from a .md file."""
        from agent_from_zero.cli import load_system_prompt

        content = load_system_prompt()
        assert isinstance(content, str)
        assert len(content) > 0

    def test_load_prompt_returns_default_when_file_missing(self, monkeypatch, tmp_path):
        """load_system_prompt() returns a sensible default if prompt file is absent."""
        from agent_from_zero.cli import load_system_prompt

        # Point to a non-existent file
        monkeypatch.chdir(tmp_path)
        content = load_system_prompt()
        assert isinstance(content, str)
        assert len(content) > 0  # default fallback


class TestParseArgs:
    """Behavior 6: CLI arguments are parsed correctly."""

    def test_default_values(self):
        """Default values for --max-size, --max-tool-calls, --model."""
        from agent_from_zero.cli import parse_args

        args = parse_args([])
        assert args.max_size == 80000
        assert args.max_tool_calls == 10
        assert args.model == "deepseek-chat"

    def test_model_override(self):
        """--model overrides the default model."""
        from agent_from_zero.cli import parse_args

        args = parse_args(["--model", "deepseek-chat-v3"])
        assert args.model == "deepseek-chat-v3"
