"""Tool Registry: decorator, Tool dataclass, and registry for tool execution."""

from dataclasses import dataclass
from collections.abc import Callable


@dataclass
class Tool:
    """A registered tool: name, description, parameter schema, and callable."""

    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's arguments
    fn: Callable


class ToolRegistry:
    """Holds registered tools, generates OpenAI-compatible schemas, executes calls."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool in the registry."""
        self._tools[tool.name] = tool

    def list_tools(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict]:
        """Return OpenAI-compatible tool schemas for all registered tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    def execute(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool by name with given arguments. Returns result as string."""
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not found in registry")
        result = tool.fn(**arguments)
        return str(result)


def register_tool(name: str, description: str, parameters: dict):
    """Decorator: wraps a function as a Tool object.

    Usage:
        @register_tool(name="calc", description="...", parameters={...})
        def calculator(expression: str) -> str:
            ...
    """

    def decorator(fn):
        return Tool(name=name, description=description, parameters=parameters, fn=fn)

    return decorator
