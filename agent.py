#!/usr/bin/env python
"""Agent from Zero — a minimal AI Agent built from scratch."""

import os
import sys

# Load .env file before anything else
from dotenv import load_dotenv
load_dotenv()

# Ensure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agent_from_zero.cli import parse_args, load_system_prompt, resolve_session
from agent_from_zero.llm.deepseek_adapter import DeepSeekAdapter
from agent_from_zero.orchestrator import Orchestrator
from agent_from_zero.session import Session, SESSIONS_DIR, list_sessions
from agent_from_zero.tool_registry import ToolRegistry, Tool
from agent_from_zero.tools.calculator import calculator
from agent_from_zero.tools.search import create_search_tool
from agent_from_zero.tools.todo import create_todo_tool, TodoList


def _build_tool_registry(todo_list: TodoList) -> ToolRegistry:
    """Build and return the ToolRegistry with all built-in tools."""
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="calculator",
            description=(
                "Evaluate a mathematical expression safely. "
                "Supports basic arithmetic (+, -, *, /, **), "
                "functions (abs, round, min, max, pow), "
                "and constants (pi, e)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate, e.g. '2 + 3 * 4'",
                    }
                },
                "required": ["expression"],
            },
            fn=calculator,
        )
    )
    registry.register(create_search_tool())
    registry.register(create_todo_tool(todo_list=todo_list))
    return registry


def main():
    args = parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Resolve session
    session_name = resolve_session(args.session, SESSIONS_DIR)
    sessions_dir_abs = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), SESSIONS_DIR
    )

    # Create TodoList — shared instance between tool and session
    todo_list = TodoList()

    # Load existing or create new
    if session_name in list_sessions(sessions_dir_abs):
        session = Session.load(session_name, sessions_dir_abs)
        todo_list.restore_from(session.todo_items)
        print(f"Resumed session: {session_name}")
    else:
        session = Session(name=session_name)
        print(f"Created new session: {session_name}")

    system_prompt = load_system_prompt()
    tool_registry = _build_tool_registry(todo_list)

    adapter = DeepSeekAdapter(
        api_key=api_key,
        model=args.model,
        thinking=args.thinking,
        reasoning_effort=args.reasoning_effort,
    )
    orchestrator = Orchestrator(
        adapter=adapter,
        system_prompt=system_prompt,
        tool_registry=tool_registry,
        max_tool_calls=args.max_tool_calls,
        max_size=args.max_size,
        session=session,
        sessions_dir=sessions_dir_abs,
        todo_list=todo_list,
    )
    orchestrator.run_repl()


if __name__ == "__main__":
    main()
