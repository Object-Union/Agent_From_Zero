"""Session: file-based persistence with Markdown + YAML Frontmatter."""

import json
import os
import uuid
from datetime import datetime, timezone

import yaml


SESSIONS_DIR = ".scratch/sessions"


class Session:
    """An isolated conversation session, persisted to a markdown file."""

    def __init__(self, name: str, session_id: str | None = None):
        self.name = name
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.created_at = datetime.now(timezone.utc).isoformat()
        self._messages: list[dict] = []
        self.todo_items: list[dict] = []

    def add_message(self, message: dict) -> None:
        """Add a message to the session history."""
        self._messages.append(message)

    def get_messages(self) -> list[dict]:
        """Return all messages in this session."""
        return list(self._messages)

    def save(self, directory: str) -> None:
        """Write the session to a .md file with YAML frontmatter."""
        os.makedirs(directory, exist_ok=True)

        frontmatter = {
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "todo_items": self.todo_items,
        }

        parts = ["---"]
        parts.append(yaml.dump(frontmatter, allow_unicode=True, sort_keys=False).rstrip())
        parts.append("---")
        parts.append("")

        for msg in self._messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            heading = f"## {role}"

            # Preserve tool_call_id in the heading for tool messages
            if role == "tool" and msg.get("tool_call_id"):
                heading += f":{msg['tool_call_id']}"

            parts.append(heading)
            parts.append("")

            # For assistant messages with tool_calls, store them as JSON prefix
            if role == "assistant" and msg.get("tool_calls"):
                parts.append("[tool_calls] " + json.dumps(msg["tool_calls"], ensure_ascii=False))
                parts.append("")

            parts.append(str(content))
            parts.append("")

        path = os.path.join(directory, f"{self.name}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))

    @classmethod
    def load(cls, name: str, directory: str) -> "Session":
        """Load a session from its .md file."""
        path = os.path.join(directory, f"{name}.md")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Session file not found: {path}")

        content = open(path, encoding="utf-8").read()

        # Parse YAML frontmatter
        if not content.startswith("---"):
            raise ValueError(f"Session file '{path}' is missing YAML frontmatter.")

        # Find the closing ---
        end_idx = content.find("---", 3)
        if end_idx == -1:
            raise ValueError(f"Session file '{path}' has malformed frontmatter.")

        frontmatter_text = content[3:end_idx].strip()
        try:
            frontmatter = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError as e:
            raise ValueError(f"Session file '{path}' has invalid YAML frontmatter: {e}") from e

        if not isinstance(frontmatter, dict):
            raise ValueError(f"Session file '{path}' frontmatter is not a valid mapping.")

        session = cls(
            name=frontmatter.get("name", name),
            session_id=frontmatter.get("session_id"),
        )
        session.created_at = frontmatter.get("created_at", session.created_at)
        session.todo_items = frontmatter.get("todo_items", [])

        # Parse messages from markdown body
        body = content[end_idx + 3:].strip()
        session._messages = _parse_messages(body)

        return session


def _parse_messages(body: str) -> list[dict]:
    """Parse ## role sections from markdown body into message dicts.

    Supports:
        ## assistant                → {"role": "assistant", "content": "..."}
        ## tool:call_abc            → {"role": "tool", "tool_call_id": "call_abc", "content": "..."}
        [tool_calls] ... line       → tool_calls field on the preceding assistant message
    """
    messages = []
    lines = body.split("\n")
    current_role = None
    current_tool_call_id = None
    current_content: list[str] = []
    pending_tool_calls = None

    def _flush():
        nonlocal pending_tool_calls
        if current_role is not None:
            content_text = "\n".join(current_content).strip()
            msg = {"role": current_role, "content": content_text}
            if current_tool_call_id:
                msg["tool_call_id"] = current_tool_call_id
            if pending_tool_calls:
                msg["tool_calls"] = pending_tool_calls
                pending_tool_calls = None
            messages.append(msg)

    for line in lines:
        if line.startswith("## ") and len(line) > 3:
            _flush()
            heading = line[3:].strip()
            current_content = []
            current_tool_call_id = None
            pending_tool_calls = None

            # Check for tool:<call_id> format
            if heading.startswith("tool:"):
                current_role = "tool"
                current_tool_call_id = heading[5:]
            else:
                current_role = heading

        elif line.startswith("[tool_calls] ") and current_role == "assistant":
            try:
                pending_tool_calls = json.loads(line[len("[tool_calls] "):])
            except json.JSONDecodeError:
                pass  # Ignore malformed data
        elif current_role is not None:
            current_content.append(line)

    _flush()
    return messages


def list_sessions(directory: str) -> list[str]:
    """List available session names from the sessions directory."""
    if not os.path.isdir(directory):
        return []
    names = []
    for fname in os.listdir(directory):
        if fname.endswith(".md"):
            names.append(fname[:-3])  # strip .md extension
    return sorted(names)
