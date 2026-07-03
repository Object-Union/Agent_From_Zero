"""Todo tool — session-scoped to-do list management."""

from agent_from_zero.tool_registry import Tool


class TodoList:
    """A simple in-memory to-do list."""

    def __init__(self):
        self._items: list[dict] = []  # [{item: str, done: bool}]

    def add(self, item: str) -> str:
        """Add an item to the list."""
        self._items.append({"item": item, "done": False})
        index = len(self._items)
        return f"Added todo #{index}: {item}"

    def list_items(self) -> str:
        """Return a formatted list of all items."""
        if not self._items:
            return "Your todo list is empty."
        lines = ["Your todo list:"]
        for i, entry in enumerate(self._items, start=1):
            status = "[x]" if entry["done"] else "[ ]"
            lines.append(f"  {i}. {status} {entry['item']}")
        return "\n".join(lines)

    def complete(self, index_str: str) -> str:
        """Mark an item as done by its number."""
        try:
            index = int(index_str) - 1
        except (ValueError, TypeError):
            return f"Error: '{index_str}' is not a valid item number."
        if index < 0 or index >= len(self._items):
            return f"Error: item #{index_str} not found."
        self._items[index]["done"] = True
        return f"Completed #{index_str}: {self._items[index]['item']}"

    def get_items(self) -> list[dict]:
        """Export items for persistence."""
        return list(self._items)

    def restore_from(self, items: list[dict]) -> None:
        """Restore items from persisted state."""
        self._items = list(items)


def _make_handler(todo_list: TodoList):
    """Create a handler function bound to a specific TodoList instance."""

    def handler(action: str, item: str = "") -> str:
        action = action.strip().lower()
        if action == "add":
            if not item.strip():
                return "Error: 'item' is required for add action."
            return todo_list.add(item.strip())
        elif action == "list":
            return todo_list.list_items()
        elif action == "complete":
            return todo_list.complete(item)
        else:
            return f"Error: unknown action '{action}'. Valid actions: add, list, complete."

    return handler


def create_todo_tool(todo_list: TodoList | None = None) -> Tool:
    """Create a todo Tool bound to a TodoList instance.

    Pass an existing TodoList to share state (e.g., for session persistence).
    If omitted, creates a fresh in-memory list.
    """
    if todo_list is None:
        todo_list = TodoList()

    return Tool(
        name="todo",
        description=(
            "Manage a to-do list. Actions: 'add' (needs item text), "
            "'list' (show all items), 'complete' (mark item #N as done)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "One of: add, list, complete",
                    "enum": ["add", "list", "complete"],
                },
                "item": {
                    "type": "string",
                    "description": "Item text for add, or item number for complete",
                },
            },
            "required": ["action", "item"],
        },
        fn=_make_handler(todo_list),
    )
