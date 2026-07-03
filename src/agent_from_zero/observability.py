"""Observability: structured trace records for tool calls."""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TraceRecord:
    """A structured audit record for a single tool call."""

    tool_name: str
    input_args: dict
    call_index: int
    duration_ms: float
    output: str | None = None
    error: str | None = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def to_json(self) -> str:
        """Serialize to a compact JSON string."""
        return json.dumps(
            {
                "tool_name": self.tool_name,
                "input_args": self.input_args,
                "output": self.output,
                "error": self.error,
                "duration_ms": self.duration_ms,
                "call_index": self.call_index,
                "timestamp": self.timestamp,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def emit_trace(trace: TraceRecord) -> None:
    """Write a trace record to stderr as a compact JSON line."""
    print(f"[TRACE] {trace.to_json()}", file=sys.stderr, flush=True)


def append_trace_to_file(trace: TraceRecord, filepath: str) -> None:
    """Append a trace record to a JSONL file. Creates the file if it doesn't exist."""
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(trace.to_json() + "\n")
