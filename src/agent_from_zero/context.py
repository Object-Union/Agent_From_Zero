"""Context management: overflow detection, split for compression, summary application."""


def _message_size(messages: list[dict]) -> int:
    """Total character count of serialized messages."""
    return sum(len(str(m)) for m in messages)


def check_overflow(messages: list[dict], max_size: int) -> bool:
    """Return True if total message size meets or exceeds max_size."""
    return _message_size(messages) >= max_size


def split_for_compression(
    messages: list[dict], max_size: int
) -> tuple[list[dict], list[dict]]:
    """Split messages into (to_summarize, to_keep).

    The oldest ~50% of messages go to to_summarize. System messages are
    always kept (never summarized away). Returns (to_summarize, to_keep).
    """
    # Always keep system messages out of the summary pile
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    if len(non_system) <= 4:
        # Too few messages to compress meaningfully; keep all
        return ([], messages)

    split_idx = max(len(non_system) // 2, 2)
    to_summarize = non_system[:split_idx]
    to_keep = system_msgs + non_system[split_idx:]

    return (to_summarize, to_keep)


def apply_summary(
    original_messages: list[dict],
    kept_messages: list[dict],
    summary: str,
) -> list[dict]:
    """Replace summarized messages with a synthetic summary message.

    Returns a new message list: [summary marker] + kept_messages.
    The summary marker acts as an assistant/system note capturing what was removed.
    """
    result = [
        {
            "role": "system",
            "content": f"[Earlier conversation summary]: {summary}",
        }
    ]
    result.extend(kept_messages)
    return result


def build_context(
    history: list[dict],
    max_size: int = 80000,
    summary: str | None = None,
) -> list[dict]:
    """Build a context from message history, truncating if needed.

    If no summary is provided and context overflows, simply keeps the newest
    messages that fit within max_size (truncation only, no compression).

    If a summary is provided, it replaces the oldest messages.
    """
    if not check_overflow(history, max_size):
        return list(history)

    if summary:
        to_summarize, to_keep = split_for_compression(history, max_size)
        return apply_summary(history, to_keep, summary)

    # No summary available — truncate: keep newest messages that fit
    result: list[dict] = []
    current_size = 0
    # Always keep system message first
    for m in history:
        if m.get("role") == "system":
            result.append(m)
            current_size += len(str(m))

    # Then keep newest messages that fit
    non_system = [m for m in history if m.get("role") != "system"]
    for m in reversed(non_system):
        sz = len(str(m))
        if current_size + sz < max_size:
            result.insert(len(result), m)
            current_size += sz
        else:
            break

    return result
