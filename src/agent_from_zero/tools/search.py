"""Search tool — mock implementation with replaceable adapter."""

from agent_from_zero.tool_registry import Tool


class SearchAdapter:
    """Interface for search backends. Replace this with a real implementation."""

    def search(self, query: str) -> str:
        raise NotImplementedError


class MockSearchAdapter(SearchAdapter):
    """Mock search that returns canned results."""

    def search(self, query: str) -> str:
        return (
            f"Search results for '{query}':\n"
            f"  1. Mock result A about {query}\n"
            f"  2. Mock result B about {query}\n"
            f"  3. Mock result C about {query}\n"
            f"\n(These are mock results. The search tool uses a replaceable adapter "
            f"— swap MockSearchAdapter for a real implementation later.)"
        )


_default_adapter = MockSearchAdapter()


def _search_fn(query: str) -> str:
    """Call the search adapter and return formatted results."""
    return _default_adapter.search(query)


def create_search_tool(adapter: SearchAdapter | None = None) -> Tool:
    """Create a search Tool. Pass an adapter to replace the mock with a real backend."""
    global _default_adapter
    if adapter is not None:
        _default_adapter = adapter
        return Tool(
            name="search",
            description="Search the web for information. Returns search results for the given query.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up",
                    }
                },
                "required": ["query"],
            },
            fn=_search_fn,
        )

    return Tool(
        name="search",
        description="Search the web for information. Returns search results for the given query.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up",
                }
            },
            "required": ["query"],
        },
        fn=_search_fn,
    )
