import json

from openai import OpenAI

from agent_from_zero.llm.base import LLMError, LLMResponse


class DeepSeekAdapter:
    """DeepSeek API adapter via OpenAI-compatible interface."""

    DEFAULT_MODEL = "deepseek-chat"
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
    DEFAULT_REASONING_EFFORT = "high"

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        thinking: bool = True,
        reasoning_effort: str | None = None,
    ):
        if not api_key:
            raise LLMError(
                "DeepSeek API key not set. "
                "Set the DEEPSEEK_API_KEY environment variable."
            )
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = self.DEFAULT_BASE_URL
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort or self.DEFAULT_REASONING_EFFORT
        self._client = OpenAI(api_key=api_key, base_url=self.base_url)

    def _build_kwargs(self, messages: list[dict], tools: list[dict] | None, stream: bool = False) -> dict:
        """Build common kwargs for API calls, including thinking mode if enabled."""
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}

        # Enable thinking mode on deepseek-chat / deepseek-v4-pro etc.
        if self.thinking:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            kwargs["reasoning_effort"] = self.reasoning_effort

        return kwargs

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """Send messages to DeepSeek and return the LLM response.

        Returns LLMResponse with text, tool_calls, and thinking (if enabled).
        """
        kwargs = self._build_kwargs(messages, tools, stream=False)
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

        # Capture reasoning/thinking content
        thinking = getattr(choice, "reasoning_content", None) or None

        return LLMResponse(text=choice.content, tool_calls=tool_calls, thinking=thinking)

    def chat_stream(self, messages: list[dict], tools: list[dict] | None = None):
        """Stream the LLM response, yielding (event_type, data) tuples.

        Event types:
            "thinking"   — reasoning/chain-of-thought content (data is str)
            "content"    — normal text content (data is str)
            "tool_calls" — accumulated tool calls (data is list[dict])
            "done"       — streaming complete (data is None)
        """
        kwargs = self._build_kwargs(messages, tools, stream=True)
        response = self._client.chat.completions.create(**kwargs)

        tool_calls_acc: dict[int, dict] = {}

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta is None:
                continue

            # Reasoning / thinking content
            reasoning = getattr(delta, "reasoning_content", None) or ""
            if reasoning:
                yield ("thinking", reasoning)

            # Normal content
            if delta.content:
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
