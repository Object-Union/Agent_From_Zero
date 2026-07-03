"""Tests for Tool Registry."""

import pytest


class TestToolRegistry:
    """Behaviors 2-3: Tool registration, schema generation, and execution."""

    def test_register_and_list_tools(self):
        """Tools can be registered and retrieved."""
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        tool = Tool(
            name="add",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            fn=add,
        )
        registry.register(tool)

        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "add"

    def test_get_schemas_returns_openai_format(self):
        """get_schemas() returns OpenAI-compatible tool schemas."""
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        registry.register(
            Tool(
                name="add",
                description="Add two numbers",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                },
                fn=add,
            )
        )

        schemas = registry.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "add"
        assert schemas[0]["function"]["description"] == "Add two numbers"
        assert schemas[0]["function"]["parameters"]["required"] == ["a", "b"]

    def test_execute_dispatches_to_tool_fn(self):
        """execute() calls the correct tool with arguments and returns result."""
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()

        def greet(name: str) -> str:
            return f"Hello, {name}!"

        registry.register(
            Tool(
                name="greet",
                description="Greet someone",
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                fn=greet,
            )
        )

        result = registry.execute("greet", {"name": "World"})
        assert result == "Hello, World!"

    def test_execute_unknown_tool_raises_error(self):
        """execute() raises KeyError when tool not found."""
        from agent_from_zero.tool_registry import ToolRegistry

        registry = ToolRegistry()

        with pytest.raises(KeyError, match="nonexistent"):
            registry.execute("nonexistent", {})

    def test_multiple_tools_coexist(self):
        """Registry supports multiple tools with independent execution."""
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()

        def double(x: int) -> int:
            return x * 2

        def triple(x: int) -> int:
            return x * 3

        registry.register(
            Tool(
                name="double",
                description="Double a number",
                parameters={
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                },
                fn=double,
            )
        )
        registry.register(
            Tool(
                name="triple",
                description="Triple a number",
                parameters={
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                },
                fn=triple,
            )
        )

        assert registry.execute("double", {"x": 5}) == "10"
        assert registry.execute("triple", {"x": 5}) == "15"

    def test_execute_converts_result_to_string(self):
        """execute() always returns a string (for LLM consumption)."""
        from agent_from_zero.tool_registry import Tool, ToolRegistry

        registry = ToolRegistry()

        registry.register(
            Tool(
                name="count",
                description="Return a count",
                parameters={"type": "object", "properties": {}, "required": []},
                fn=lambda: 42,
            )
        )

        result = registry.execute("count", {})
        assert result == "42"
        assert isinstance(result, str)


class TestRegisterToolDecorator:
    """Behavior 5: @register_tool decorator creates Tool from function."""

    def test_decorator_creates_tool_object(self):
        """@register_tool wraps a function and returns a Tool."""
        from agent_from_zero.tool_registry import register_tool, Tool

        @register_tool(
            name="greet",
            description="Greet someone",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        assert isinstance(greet, Tool)
        assert greet.name == "greet"
        assert greet.description == "Greet someone"
        assert greet.fn("World") == "Hello, World!"

    def test_decorator_works_with_registry(self):
        """@register_tool result can be directly fed to ToolRegistry.register()."""
        from agent_from_zero.tool_registry import register_tool, ToolRegistry

        @register_tool(
            name="add",
            description="Add numbers",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        )
        def add(a: int, b: int) -> int:
            return a + b

        registry = ToolRegistry()
        registry.register(add)  # add is a Tool now

        assert registry.execute("add", {"a": 3, "b": 4}) == "7"
