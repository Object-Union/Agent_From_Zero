"""Tests for Todo tool."""

import pytest


class TestTodo:
    """Behaviors 3-6: Todo manages a list of items."""

    def _make_tool(self):
        """Helper: create a fresh todo tool."""
        from agent_from_zero.tools.todo import create_todo_tool
        return create_todo_tool()

    def test_add_returns_confirmation(self):
        """add action returns confirmation with the item text."""
        tool = self._make_tool()
        result = tool.fn(action="add", item="Buy milk")
        assert "Buy milk" in result

    def test_list_shows_items(self):
        """list action shows all added items."""
        tool = self._make_tool()
        tool.fn(action="add", item="Task A")
        tool.fn(action="add", item="Task B")

        result = tool.fn(action="list", item="")
        assert "Task A" in result
        assert "Task B" in result

    def test_complete_marks_item_done(self):
        """complete action marks an item by index."""
        tool = self._make_tool()
        tool.fn(action="add", item="Task 1")
        tool.fn(action="add", item="Task 2")

        result = tool.fn(action="complete", item="1")
        assert "Task 1" in result.lower() or "completed" in result.lower()

        # Listing should still show it
        list_result = tool.fn(action="list", item="")
        assert "Task 1" in list_result

    def test_complete_invalid_index_errors(self):
        """complete with out-of-range index returns error."""
        tool = self._make_tool()
        tool.fn(action="add", item="Only item")

        result = tool.fn(action="complete", item="99")
        assert "error" in result.lower() or "not found" in result.lower()

    def test_invalid_action_errors(self):
        """Unknown action returns error."""
        tool = self._make_tool()

        result = tool.fn(action="delete", item="something")
        assert "error" in result.lower() or "unknown" in result.lower()

    def test_schema_is_valid(self):
        """Todo tool has correct schema."""
        tool = self._make_tool()
        assert tool.name == "todo"
        props = tool.parameters.get("properties", {})
        assert "action" in props
        assert "item" in props
