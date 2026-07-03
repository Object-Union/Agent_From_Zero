"""Tests for Trace / Observability."""

import json
import os
import tempfile

from agent_from_zero.llm.base import LLMResponse, LLMError


class TestTraceRecord:
    """Behavior 1: TraceRecord captures structured audit data."""

    def test_trace_record_has_required_fields(self):
        """TraceRecord has tool_name, input_args, output, duration_ms, call_index."""
        from agent_from_zero.observability import TraceRecord

        tr = TraceRecord(
            tool_name="calculator",
            input_args={"expression": "2+2"},
            output="4",
            duration_ms=12.5,
            call_index=1,
        )
        assert tr.tool_name == "calculator"
        assert tr.input_args == {"expression": "2+2"}
        assert tr.output == "4"
        assert tr.duration_ms == 12.5
        assert tr.call_index == 1

    def test_trace_record_error_field(self):
        """TraceRecord.error is set when a tool fails."""
        from agent_from_zero.observability import TraceRecord

        tr = TraceRecord(
            tool_name="failer",
            input_args={},
            error="ValueError: Boom!",
            duration_ms=0.5,
            call_index=3,
        )
        assert tr.is_error is True
        assert tr.output is None

    def test_trace_record_to_json(self):
        """TraceRecord.to_json() returns a valid JSON string."""
        from agent_from_zero.observability import TraceRecord

        tr = TraceRecord(
            tool_name="search",
            input_args={"query": "Python"},
            output="Mock results",
            duration_ms=45.0,
            call_index=2,
        )
        data = json.loads(tr.to_json())
        assert data["tool_name"] == "search"
        assert data["input_args"] == {"query": "Python"}
        assert data["output"] == "Mock results"
        assert data["duration_ms"] == 45.0
        assert data["call_index"] == 2
        assert "timestamp" in data


class TestTraceOutput:
    """Behavior 2-3: Trace is written to stderr and .jsonl file."""

    def test_emit_to_stderr(self, capsys):
        """emit_trace() writes a human-readable line to stderr."""
        from agent_from_zero.observability import TraceRecord, emit_trace

        tr = TraceRecord(
            tool_name="calculator",
            input_args={"expression": "1+1"},
            output="2",
            duration_ms=3.0,
            call_index=1,
        )
        emit_trace(tr)

        captured = capsys.readouterr()
        assert captured.err != ""
        assert "calculator" in captured.err
        assert "1+1" in captured.err

    def test_append_to_jsonl(self):
        """append_trace_to_file() appends a line to the .jsonl file."""
        from agent_from_zero.observability import TraceRecord, append_trace_to_file

        tr = TraceRecord(
            tool_name="echo",
            input_args={"msg": "hi"},
            output="ECHO: hi",
            duration_ms=1.0,
            call_index=1,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.trace.jsonl")
            append_trace_to_file(tr, path)

            assert os.path.isfile(path)
            lines = open(path).readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["tool_name"] == "echo"

    def test_multiple_traces_in_jsonl(self):
        """Multiple trace calls produce one line each in the jsonl file."""
        from agent_from_zero.observability import TraceRecord, append_trace_to_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "multi.trace.jsonl")
            for i in range(3):
                tr = TraceRecord(
                    tool_name="inc",
                    input_args={"n": i},
                    output=str(i + 1),
                    duration_ms=1.0,
                    call_index=i + 1,
                )
                append_trace_to_file(tr, path)

            lines = open(path).readlines()
            assert len(lines) == 3


class TestOrchestratorLLMError:
    """Behavior 4: Orchestrator handles LLMError without losing session state."""

    def test_llm_error_reports_to_user(self):
        """When adapter raises LLMError, orchestrator returns error message."""
        from agent_from_zero.orchestrator import Orchestrator

        class FailingAdapter:
            def chat(self, messages, tools=None):
                raise LLMError("API connection failed")

        agent = Orchestrator(
            adapter=FailingAdapter(),
            system_prompt="Helpful.",
        )
        result = agent.process_input("hello")
        assert "error" in result.lower()
        assert "API" in result

    def test_llm_error_preserves_session(self):
        """When LLMError occurs, session is NOT corrupted — previous messages remain."""
        from agent_from_zero.orchestrator import Orchestrator

        call_count = 0

        class SometimesFailingAdapter:
            def chat(self, messages, tools=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return LLMResponse(text="First reply ok")
                raise LLMError("API timeout")

        agent = Orchestrator(
            adapter=SometimesFailingAdapter(),
            system_prompt="Helpful.",
        )
        first = agent.process_input("msg 1")
        assert first == "First reply ok"

        second = agent.process_input("msg 2")
        assert "error" in second.lower()

        # The history should still contain the first exchange
        assert len(agent._history) >= 2  # system + user1 + assistant1 (error path may vary)
        assert any(m.get("content") == "First reply ok" for m in agent._history)
