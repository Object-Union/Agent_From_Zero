from dataclasses import dataclass, field


class LLMError(Exception):
    """LLM 调用失败时抛出。"""
    pass


@dataclass
class LLMResponse:
    """An LLM's response — either a text reply or tool_calls (or both)."""

    text: str | None = None
    tool_calls: list[dict] | None = None
    # tool_calls entries: {"id": str, "name": str, "arguments": dict}
