"""CLI entry point: argument parsing, system prompt loading, session selection."""

import argparse
import os
import sys

from agent_from_zero.session import SESSIONS_DIR, list_sessions


def parse_args(argv: list[str] | None = None):
    """Parse CLI arguments for agent.py."""
    parser = argparse.ArgumentParser(
        prog="agent",
        description="A minimal AI Agent from scratch.",
    )
    parser.add_argument(
        "--session", "-s", default=None, help="Session name to use or create"
    )
    parser.add_argument(
        "--model", default="deepseek-chat", help="DeepSeek model name"
    )
    parser.add_argument(
        "--max-size", type=int, default=80000, help="Context max character count"
    )
    parser.add_argument(
        "--max-tool-calls", type=int, default=10, help="Max tool calls per turn"
    )
    return parser.parse_args(argv)


def load_system_prompt() -> str:
    """Read the system prompt from system-prompt.md, or return a default.

    The file is looked up relative to the project root.
    """
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "system-prompt.md",
    )
    if os.path.isfile(prompt_path):
        with open(prompt_path, encoding="utf-8") as f:
            return f.read().strip()
    return "You are a helpful AI assistant. Answer the user's questions clearly and concisely."


def resolve_session(session_arg: str | None, sessions_dir: str) -> str:
    """Resolve a session name from CLI arg or interactive selection.

    Returns the chosen session name.
    """
    existing = list_sessions(sessions_dir)

    if session_arg:
        return session_arg

    # Interactive selection
    print("\nAvailable sessions:")
    if existing:
        for i, name in enumerate(existing, start=1):
            print(f"  {i}. {name}")
        print(f"  n. [New session]")
    else:
        print("  (none)")

    while True:
        try:
            choice = input("\nChoose a session (number, name, or 'n' for new): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if choice.lower() == "n":
            name = input("New session name: ").strip()
            if name:
                return name
            continue

        # Try by number
        if choice.isdigit() and existing:
            idx = int(choice) - 1
            if 0 <= idx < len(existing):
                return existing[idx]

        # Try by name
        if choice:
            return choice
