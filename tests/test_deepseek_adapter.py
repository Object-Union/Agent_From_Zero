"""Tests for DeepSeekAdapter."""

import pytest
from unittest.mock import patch, MagicMock

from agent_from_zero.llm.base import LLMError


class TestDeepSeekAdapterChat:
    """Behavior 1: Adapter formats messages, calls DeepSeek, returns LLMResponse."""

    def test_chat_returns_text_response(self):
        """When LLM returns text (no tool_calls), LLMResponse.text is set."""
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key="sk-test", model="deepseek-chat")
        messages = [{"role": "user", "content": "hello"}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello, human!"
        mock_response.choices[0].message.tool_calls = None

        with patch.object(adapter._client.chat.completions, "create", return_value=mock_response) as mock_create:
            result = adapter.chat(messages)

        assert result.text == "Hello, human!"
        assert result.tool_calls is None
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "deepseek-chat"
        assert call_kwargs["messages"] == messages

    def test_chat_returns_tool_calls(self):
        """When LLM returns tool_calls, LLMResponse.tool_calls is populated."""
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key="sk-test", model="deepseek-chat")
        messages = [{"role": "user", "content": "2+2"}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_tc = MagicMock()
        mock_tc.id = "call_abc"
        mock_tc.function.name = "calculator"
        mock_tc.function.arguments = '{"expression": "2+2"}'
        mock_response.choices[0].message.tool_calls = [mock_tc]

        with patch.object(adapter._client.chat.completions, "create", return_value=mock_response):
            result = adapter.chat(messages)

        assert result.text is None
        assert result.tool_calls == [
            {"id": "call_abc", "name": "calculator", "arguments": {"expression": "2+2"}}
        ]

    def test_chat_passes_tools_to_api(self):
        """When tools are provided, they are passed to the API call."""
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key="sk-test", model="deepseek-chat")
        messages = [{"role": "user", "content": "hi"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Evaluate math expressions",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"}
                        },
                        "required": ["expression"],
                    },
                },
            }
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.choices[0].message.tool_calls = None

        with patch.object(adapter._client.chat.completions, "create", return_value=mock_response) as mock_create:
            adapter.chat(messages, tools=tools)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["tools"] == tools

    def test_chat_missing_api_key_raises_error(self):
        """Adapter raises LLMError when DEEPSEEK_API_KEY is not set."""
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        with pytest.raises(LLMError, match="API key"):
            DeepSeekAdapter(api_key="", model="deepseek-chat")


class TestDeepSeekAdapterChatStream:
    """Streaming: chat_stream() yields content, thinking, and tool_calls chunks."""

    def _make_chunk(self, content=None, reasoning=None, tool_calls=None, finish_reason=None):
        """Helper: create a mock streaming chunk with the given delta."""
        chunk = MagicMock()
        chunk.choices = []
        delta = MagicMock()
        delta.content = content
        if hasattr(delta, "reasoning_content"):
            pass  # Will set below
        # Use a dict-style approach since reasoning_content may not be on all SDK versions
        if tool_calls:
            delta.tool_calls = tool_calls
        else:
            delta.tool_calls = None

        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = finish_reason
        chunk.choices = [choice]

        # Set reasoning_content via configure_mock
        type(delta).reasoning_content = MagicMock()
        delta.reasoning_content = reasoning

        return chunk

    def test_stream_yields_content_chunks(self):
        """Streaming yields ('content', text) for each content delta."""
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key="sk-test")
        messages = [{"role": "user", "content": "hi"}]

        chunks = [
            self._make_chunk(content="Hello"),
            self._make_chunk(content=", "),
            self._make_chunk(content="world!"),
            self._make_chunk(finish_reason="stop"),
        ]

        with patch.object(adapter._client.chat.completions, "create", return_value=chunks):
            events = list(adapter.chat_stream(messages))

        # Collect content events
        content_parts = [data for event, data in events if event == "content"]
        assert "".join(content_parts) == "Hello, world!"
        # Should have a "done" event at the end
        assert events[-1][0] == "done"

    def test_stream_yields_thinking_chunks(self):
        """Streaming yields ('thinking', text) for reasoning deltas."""
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key="sk-test")
        messages = [{"role": "user", "content": "complex question"}]

        chunks = [
            self._make_chunk(reasoning="Let me think..."),
            self._make_chunk(reasoning=" The answer is 42."),
            self._make_chunk(content="42", finish_reason="stop"),
        ]

        with patch.object(adapter._client.chat.completions, "create", return_value=chunks):
            events = list(adapter.chat_stream(messages))

        thinking_parts = [data for event, data in events if event == "thinking"]
        assert "Let me think... The answer is 42." in "".join(thinking_parts)

    def test_stream_accumulates_tool_calls(self):
        """Streaming accumulates tool_call deltas and yields at end."""
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key="sk-test")
        messages = [{"role": "user", "content": "2+2"}]

        # Simulate tool_call streaming across multiple chunks
        tc_chunk_1 = MagicMock()
        tc_chunk_1.index = 0
        tc_chunk_1.id = "call_xyz"
        tc_chunk_1.function = MagicMock()
        tc_chunk_1.function.name = "calculator"
        tc_chunk_1.function.arguments = None

        tc_chunk_2 = MagicMock()
        tc_chunk_2.index = 0
        tc_chunk_2.id = None
        tc_chunk_2.function = MagicMock()
        tc_chunk_2.function.name = None
        tc_chunk_2.function.arguments = '{"expr'

        tc_chunk_3 = MagicMock()
        tc_chunk_3.index = 0
        tc_chunk_3.id = None
        tc_chunk_3.function = MagicMock()
        tc_chunk_3.function.name = None
        tc_chunk_3.function.arguments = 'ession":'

        tc_chunk_4 = MagicMock()
        tc_chunk_4.index = 0
        tc_chunk_4.id = None
        tc_chunk_4.function = MagicMock()
        tc_chunk_4.function.name = None
        tc_chunk_4.function.arguments = ' "2+2"}'

        chunks = [
            self._make_chunk(content="Let me", reasoning="Hmm, user wants math"),
            self._make_chunk(tool_calls=[tc_chunk_1]),
            self._make_chunk(tool_calls=[tc_chunk_2]),
            self._make_chunk(tool_calls=[tc_chunk_3]),
            self._make_chunk(tool_calls=[tc_chunk_4]),
            self._make_chunk(finish_reason="tool_calls"),
        ]

        with patch.object(adapter._client.chat.completions, "create", return_value=chunks):
            events = list(adapter.chat_stream(messages))

        # Should have content, thinking, and tool_calls events
        event_types = [e[0] for e in events]
        assert "thinking" in event_types
        assert "content" in event_types
        assert "tool_calls" in event_types
        assert "done" in event_types

        # Verify tool_calls data
        tc_events = [data for event, data in events if event == "tool_calls"]
        assert len(tc_events) == 1
        tc_data = tc_events[0]
        assert tc_data[0]["name"] == "calculator"
        assert tc_data[0]["arguments"] == {"expression": "2+2"}


class TestDeepSeekAdapterInit:
    """Adapter initialization defaults."""

    def test_default_model_is_deepseek_chat(self):
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key="sk-test")
        assert adapter.model == "deepseek-chat"

    def test_default_base_url_points_to_deepseek(self):
        from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter

        adapter = DeepSeekAdapter(api_key="sk-test")
        assert "api.deepseek.com" in adapter.base_url
