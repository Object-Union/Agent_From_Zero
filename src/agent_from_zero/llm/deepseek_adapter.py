import json

from openai import OpenAI

from agent_from_zero.llm.base import LLMError, LLMResponse


class DeepSeekAdapter:
    """DeepSeek API adapter via OpenAI-compatible interface."""

    DEFAULT_MODEL = "deepseek-chat"
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self, api_key: str, model: str | None = None):
        if not api_key:
            raise LLMError(
                "DeepSeek API key not set. "
                "Set the DEEPSEEK_API_KEY environment variable."
            )
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = self.DEFAULT_BASE_URL
        self._client = OpenAI(api_key=api_key, base_url=self.base_url)

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """Send messages to DeepSeek and return the LLM response.

        Returns LLMResponse with either text, tool_calls, or both.
        """
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0].message

        tool_calls = None
        if choice.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in choice.tool_calls
            ]

        return LLMResponse(text=choice.content, tool_calls=tool_calls)

    def chat_stream(self, messages: list[dict], tools: list[dict] | None = None):
        """Stream the LLM response, yielding (event_type, data) tuples.

        Event types:
            "thinking"   — reasoning/chain-of-thought content (data is str)
            "content"    — normal text content (data is str)
            "tool_calls" — accumulated tool calls (data is list[dict])
            "done"       — streaming complete (data is None)
        """
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        kwargs["stream_options"] = {"include_usage": True}

        response = self._client.chat.completions.create(**kwargs)

        accumulated_content = ""
        tool_calls_acc: dict[int, dict] = {}
        has_content = False
        has_thinking = False

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta is None:
                continue

            # Reasoning / thinking content (DeepSeek-specific field)
            reasoning = getattr(delta, "reasoning_content", None) or ""
            if reasoning:
                has_thinking = True
                yield ("thinking", reasoning)

            # Normal content
            if delta.content:
                has_content = True
                accumulated_content += delta.content
                yield ("content", delta.content)

            # Tool calls come as deltas — accumulate them
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }

                    acc = tool_calls_acc[idx]
                    if tc_delta.id:
                        acc["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        acc["name"] = tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        acc["arguments"] += tc_delta.function.arguments

        # If tool calls were accumulated, yield them
        if tool_calls_acc:
            tool_calls = []
            for tc in sorted(tool_calls_acc.values(), key=lambda x: x["id"]):
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": json.loads(tc["arguments"]) if tc["arguments"] else {},
                })
            yield ("tool_calls", tool_calls)

        yield ("done", None)
