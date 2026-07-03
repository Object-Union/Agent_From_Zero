from dataclasses import dataclass, field


class LLMError(Exception):
    """LLM 调用失败时抛出。"""
    pass


@dataclass
class LLMResponse:
    """An LLM's response — text, tool_calls, and/or thinking content."""

    text: str | None = None
    tool_calls: list[dict] | None = None
    thinking: str | None = None  # reasoning/chain-of-thought (deepseek-reasoner)
    # tool_calls entries: {"id": str, "name": str, "arguments": dict}
