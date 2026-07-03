"""Observability: structured trace records for tool calls."""

import json
import sys
from dataclasses import dataclass
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
        """Serialize to a compact JSON string (for .jsonl file)."""
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

    def to_display(self) -> str:
        """Human-readable one-liner for terminal display."""
        ms = f"{self.duration_ms:.0f}ms"
        args_summary = " ".join(
            str(v) for v in self.input_args.values() if v
        )[:60]

        if self.error:
            return f"  \033[31m✗\033[0m {self.tool_name}: {args_summary}  \033[31merror\033[0m  ({ms})"
        else:
            output_summary = (self.output or "")[:80].split("\n")[0]
            return f"  \033[32m✓\033[0m {self.tool_name}: {args_summary}  ({ms})"


def emit_trace(trace: TraceRecord) -> None:
    """Write a human-readable trace to stderr."""
    print(trace.to_display(), file=sys.stderr, flush=True)


def append_trace_to_file(trace: TraceRecord, filepath: str) -> None:
    """Append a trace record to a JSONL file (full structured data)."""
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(trace.to_json() + "\n")
