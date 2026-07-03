"""Integration tests — full Orchestrator flow with mock LLM + CLI subprocess."""

import os
import subprocess
import sys
import tempfile

import pytest

from agent_from_zero.llm.base import LLMResponse
from agent_from_zero.tool_registry import Tool, ToolRegistry


class TestOrchestratorIntegration:
    """Full end-to-end orchestrator flow with mock LLM, tools, and session."""

    def _make_sequential_adapter(self, responses):
        """Create a mock adapter that returns canned responses in order."""
        class Adapter:
            def __init__(self, resp):
                self.responses = resp
                self.i = 0

            def chat(self, messages, tools=None):
                r = self.responses[self.i]
                self.i += 1
                return r

        return Adapter(responses)

    def test_full_text_conversation(self):
        """Multiple text-only turns work correctly."""
        from agent_from_zero.orchestrator import Orchestrator

        adapter = self._make_sequential_adapter([
            LLMResponse(text="Hello!"),
            LLMResponse(text="I'm doing well, thanks!"),
        ])

        agent = Orchestrator(adapter=adapter, system_prompt="Be helpful.")
        r1 = agent.process_input("Hi")
        r2 = agent.process_input("How are you?")

        assert r1 == "Hello!"
        assert r2 == "I'm doing well, thanks!"
        assert len(agent._history) >= 5  # system + 2*(user+assistant)

    def test_conversation_with_tool_chain(self):
        """A full conversation where tools are called and final answer is returned."""
        from agent_from_zero.orchestrator import Orchestrator

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="calc",
                description="Calculate",
                parameters={
                    "type": "object",
                    "properties": {"expr": {"type": "string"}},
                    "required": ["expr"],
                },
                fn=lambda expr: str(eval(expr)),
            )
        )

        # Simulate: user asks calculation → tool call → LLM gets result → replies
        adapter = self._make_sequential_adapter([
            LLMResponse(
                tool_calls=[{"id": "c1", "name": "calc", "arguments": {"expr": "2+2"}}]
            ),
            LLMResponse(text="The answer is 4."),
        ])

        agent = Orchestrator(
            adapter=adapter,
            system_prompt="Helpful.",
            tool_registry=registry,
        )
        result = agent.process_input("What is 2+2?")
        assert "4" in result
        assert adapter.i == 2

    def test_session_roundtrip(self):
        """Orchestrator saves to session and can be resumed."""
        from agent_from_zero.orchestrator import Orchestrator
        from agent_from_zero.session import Session

        adapter = self._make_sequential_adapter([
            LLMResponse(text="Reply 1"),
            LLMResponse(text="Reply 2"),
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            session = Session(name="roundtrip-test")
            agent = Orchestrator(
                adapter=adapter,
                system_prompt="Helpful.",
                session=session,
                sessions_dir=tmpdir,
            )
            agent.process_input("msg 1")

            # Verify session file exists
            session_path = os.path.join(tmpdir, "roundtrip-test.md")
            assert os.path.isfile(session_path)

            # Load and resume
            loaded_session = Session.load("roundtrip-test", tmpdir)
            assert len(loaded_session.get_messages()) >= 2  # system + user + assistant

    def test_context_truncation_triggered(self):
        """When messages exceed max_size, context is truncated before LLM call."""
        from agent_from_zero.orchestrator import Orchestrator

        # Create an adapter that verifies it doesn't get too many messages
        small_max_size = 500

        class VerifyingAdapter:
            def chat(self, messages, tools=None):
                total = sum(len(str(m)) for m in messages)
                assert total < small_max_size * 2  # some tolerance
                return LLMResponse(text="ok")

        adapter = VerifyingAdapter()

        agent = Orchestrator(
            adapter=adapter,
            system_prompt="Helpful. " + "x" * 200,
            max_size=small_max_size,
        )

        # Add many large messages
        for i in range(10):
            agent._history.append({"role": "user", "content": f"Message {i} " + "x" * 200})
            agent._history.append({"role": "assistant", "content": f"Reply {i} " + "x" * 200})

        # process_input should trigger context truncation
        result = agent.process_input("hi")
        assert result == "ok"


class TestCLIIntegration:
    """Behavior CLI: run agent.py as subprocess with mock."""

    def test_agent_script_exists(self):
        """agent.py entry point is importable."""
        project_root = os.path.dirname(os.path.dirname(__file__))
        agent_path = os.path.join(project_root, "agent.py")
        assert os.path.isfile(agent_path), f"agent.py not found at {agent_path}"

    def test_agent_module_imports(self):
        """All modules import without error."""
        # Just verify the whole system imports cleanly
        import agent_from_zero
        import agent_from_zero.cli
        import agent_from_zero.context
        import agent_from_zero.orchestrator
        import agent_from_zero.session
        import agent_from_zero.tool_registry
        import agent_from_zero.observability
        import agent_from_zero.llm.base
        import agent_from_zero.llm.deepseek_adapter
        import agent_from_zero.tools.calculator
        import agent_from_zero.tools.search
        import agent_from_zero.tools.todo
        assert True  # no ImportError

    def test_help_flag_works(self):
        """python agent.py --help prints usage."""
        project_root = os.path.dirname(os.path.dirname(__file__))
        agent_path = os.path.join(project_root, "agent.py")
        python = sys.executable

        result = subprocess.run(
            [python, agent_path, "--help"],
            capture_output=True, text=True,
            cwd=project_root,
            env={**os.environ, "PYTHONPATH": os.path.join(project_root, "src")},
            timeout=10,
        )
        assert result.returncode == 0
        assert "usage" in result.stdout.lower() or "options" in result.stdout.lower()


class TestE2ESmoke:
    """E2E smoke tests with real DeepSeek API. Only run with --run-slow."""

    @pytest.mark.slow
    def test_real_api_text_reply(self):
        """Real DeepSeek API returns a text response."""
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            pytest.skip("DEEPSEEK_API_KEY not set")

        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key=api_key)
        messages = [
            {"role": "system", "content": "Reply with exactly: OK"},
            {"role": "user", "content": "Just say OK"},
        ]
        response = adapter.chat(messages)
        assert response.text is not None
        assert len(response.text) > 0

    @pytest.mark.slow
    def test_real_api_tool_call(self):
        """Real DeepSeek API uses calculator tool when asked to compute."""
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            pytest.skip("DEEPSEEK_API_KEY not set")

        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key=api_key)
        messages = [
            {"role": "system", "content": "You MUST use the calculator tool for ANY math question."},
            {"role": "user", "content": "What is 2 + 2?"},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Evaluate a math expression.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                        },
                        "required": ["expression"],
                    },
                },
            }
        ]
        response = adapter.chat(messages, tools=tools)
        # May return text or tool_calls — either is fine for smoke
        assert response.text is not None or response.tool_calls is not None
