"""Tests for Orchestrator."""

from agent_from_zero.llm.base import LLMResponse


class TestOrchestratorProcessInput:
    """Orchestrator sends input to LLM and returns reply."""

    def test_process_input_calls_adapter_and_returns_reply(self):
        """Orchestrator.process_input() calls adapter.chat() and returns text."""
        from agent_from_zero.orchestrator import Orchestrator

        system_prompt = "You are a helpful assistant."

        class MockAdapter:
            def chat(self, messages, tools=None):
                assert messages[0]["role"] == "system"
                assert messages[0]["content"] == system_prompt
                assert messages[-1]["role"] == "user"
                assert messages[-1]["content"] == "hello"
                return LLMResponse(text="Mock reply")

        agent = Orchestrator(adapter=MockAdapter(), system_prompt=system_prompt)
        result = agent.process_input("hello")
        assert result == "Mock reply"

    def test_process_input_preserves_history(self):
        """Consecutive calls include prior messages in context."""
        from agent_from_zero.orchestrator import Orchestrator

        call_count = 0

        class MockAdapter:
            def chat(self, messages, tools=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    assert len(messages) == 2  # system + user
                    return LLMResponse(text="First reply")
                else:
                    assert len(messages) == 4  # system + user1 + assistant1 + user2
                    assert messages[2]["role"] == "assistant"
                    assert messages[2]["content"] == "First reply"
                    return LLMResponse(text="Second reply")

        agent = Orchestrator(adapter=MockAdapter(), system_prompt="You are helpful.")
        first = agent.process_input("Question 1")
        second = agent.process_input("Question 2")

        assert first == "First reply"
        assert second == "Second reply"
        assert call_count == 2


class TestOrchestratorInit:
    """Orchestrator initialization."""

    def test_requires_system_prompt(self):
        from agent_from_zero.orchestrator import Orchestrator

        class MockAdapter:
            def chat(self, messages, tools=None):
                return LLMResponse(text="ok")

        agent = Orchestrator(adapter=MockAdapter(), system_prompt="Be helpful.")
        assert agent is not None


class TestOrchestratorToolCalling:
    """Behaviors 6-9: Orchestrator handles tool_calls in the loop."""

    def _make_adapter(self, responses: list):
        """Helper: create a mock adapter that returns canned LLMResponses in order."""
        from agent_from_zero.orchestrator import Orchestrator

        class SequentialAdapter:
            def __init__(self, responses):
                self.responses = responses
                self.call_index = 0

            def chat(self, messages, tools=None):
                resp = self.responses[self.call_index]
                self.call_index += 1
                return resp

        return SequentialAdapter(responses)

    def test_single_tool_call_executes_and_returns_text(self):
        """When LLM returns a tool_call, execute it and feed result back; return final text."""
        from agent_from_zero.orchestrator import Orchestrator
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="echo",
                description="Echo back",
                parameters={
                    "type": "object",
                    "properties": {"msg": {"type": "string"}},
                    "required": ["msg"],
                },
                fn=lambda msg: f"ECHO: {msg}",
            )
        )

        # First call: tool_call, Second call: final text
        adapter = self._make_adapter([
            LLMResponse(
                tool_calls=[
                    {"id": "call_1", "name": "echo", "arguments": {"msg": "hello"}}
                ]
            ),
            LLMResponse(text="All done!"),
        ])

        agent = Orchestrator(adapter=adapter, system_prompt="You are helpful.", tool_registry=registry)
        result = agent.process_input("echo hello please")

        assert result == "All done!"
        assert adapter.call_index == 2  # 2 LLM calls: tool_call then final

    def test_chain_multiple_tool_calls(self):
        """Agent can chain multiple tool calls in one turn."""
        from agent_from_zero.orchestrator import Orchestrator
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="double",
                description="Double a number",
                parameters={
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                },
                fn=lambda x: x * 2,
            )
        )
        registry.register(
            Tool(
                name="triple",
                description="Triple a number",
                parameters={
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                },
                fn=lambda x: x * 3,
            )
        )

        # Two tool calls in sequence, then final text
        adapter = self._make_adapter([
            LLMResponse(
                tool_calls=[
                    {"id": "c1", "name": "double", "arguments": {"x": 5}}
                ]
            ),
            LLMResponse(
                tool_calls=[
                    {"id": "c2", "name": "triple", "arguments": {"x": 10}}
                ]
            ),
            LLMResponse(text="Processed!"),
        ])

        agent = Orchestrator(adapter=adapter, system_prompt="Be helpful.", tool_registry=registry)
        result = agent.process_input("double then triple")

        assert result == "Processed!"
        assert adapter.call_index == 3

    def test_max_tool_calls_stops_loop(self):
        """When max_tool_calls is reached, stop the loop even if LLM keeps calling tools."""
        from agent_from_zero.orchestrator import Orchestrator
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="inc",
                description="Increment",
                parameters={
                    "type": "object",
                    "properties": {"n": {"type": "integer"}},
                    "required": ["n"],
                },
                fn=lambda n: n + 1,
            )
        )

        # Return tool_calls forever — should stop at max_tool_calls
        adapter = self._make_adapter([
            LLMResponse(
                tool_calls=[{"id": "c1", "name": "inc", "arguments": {"n": 1}}]
            )
        ] * 20)  # Way more than max_tool_calls

        agent = Orchestrator(
            adapter=adapter,
            system_prompt="Be helpful.",
            tool_registry=registry,
            max_tool_calls=3,
        )
        result = agent.process_input("increment")

        assert "max tool calls" in result.lower()
        assert adapter.call_index == 3  # stopped at 3, not 20

    def test_tool_failure_reports_error(self):
        """When a tool raises, error is reported to user (not retried)."""
        from agent_from_zero.orchestrator import Orchestrator
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()
        registry.register(
            Tool(
                name="failer",
                description="Always fails",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                fn=lambda: (_ for _ in ()).throw(ValueError("Boom!")),
            )
        )

        adapter = self._make_adapter([
            LLMResponse(
                tool_calls=[
                    {"id": "c1", "name": "failer", "arguments": {}}
                ]
            ),
        ])

        agent = Orchestrator(adapter=adapter, system_prompt="Helpful.", tool_registry=registry)
        result = agent.process_input("test failure")

        assert "error" in result.lower()
        assert "Boom" in result

    def test_no_tools_works_as_plain_chat(self):
        """When no tool_registry provided, process_input still works (pure text)."""
        from agent_from_zero.orchestrator import Orchestrator

        adapter = self._make_adapter([LLMResponse(text="Hi!")])
        agent = Orchestrator(adapter=adapter, system_prompt="Be helpful.")

        result = agent.process_input("hello")
        assert result == "Hi!"
