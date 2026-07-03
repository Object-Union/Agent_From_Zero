"""Tests for Search tool."""


class TestMockSearch:
    """Behavior 1: Search returns mock results."""

    def test_search_returns_mock_results(self):
        """MockSearchAdapter returns canned results for any query."""
        from agent_from_zero.tools.search import create_search_tool

        tool = create_search_tool()
        result = tool.fn(query="What is Python?")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_search_query_included_in_result(self):
        """Search result references the query text."""
        from agent_from_zero.tools.search import create_search_tool

        tool = create_search_tool()
        result = tool.fn(query="machine learning")
        assert "machine learning" in result.lower()

    def test_search_tool_schema_is_valid(self):
        """Search tool has correct name, description, and parameter schema."""
        from agent_from_zero.tools.search import create_search_tool

        tool = create_search_tool()
        assert tool.name == "search"
        assert isinstance(tool.description, str)
        assert "query" in tool.parameters.get("properties", {})
        assert "query" in tool.parameters.get("required", [])
