"""Orchestrator: drives the agent main loop with tool-calling and session support."""

import json
import sys
import time

from agent_from_zero.context import build_context
from agent_from_zero.llm.base import LLMError
from agent_from_zero.observability import TraceRecord, emit_trace, append_trace_to_file
from agent_from_zero.tool_registry import ToolRegistry


class Orchestrator:
    """Drives the agent main loop: input → LLM → [tool_call? → execute → loop] → output.

    If a Session is provided, history is loaded from it on init and saved after
    each user turn.
    """

    def __init__(
        self,
        adapter,
        system_prompt: str,
        tool_registry: ToolRegistry | None = None,
        max_tool_calls: int = 10,
        max_size: int = 80000,
        session=None,
        sessions_dir: str = ".scratch/sessions",
        todo_list=None,
    ):
        self._adapter = adapter
        self._system_prompt = system_prompt
        self._tool_registry = tool_registry
        self._max_tool_calls = max_tool_calls
        self._max_size = max_size
        self._session = session
        self._sessions_dir = sessions_dir
        self._todo_list = todo_list
        self._history: list[dict] = []

        # Restore history from session if available
        if self._session:
            self._history = self._session.get_messages()

    def process_input(self, user_input: str) -> str:
        """Handle one user message: build context, call LLM, handle tool_calls, return reply.

        Uses the non-streaming _run_loop for compatibility with tests.
        """
        if not self._history:
            self._history.append(
                {"role": "system", "content": self._system_prompt}
            )

        self._history.append({"role": "user", "content": user_input})

        result = self._run_loop()

        # Save to session after each user turn
        if self._session:
            self._session._messages = self._history  # sync history
            self._sync_todo_to_session()
            self._session.save(self._sessions_dir)

        return result

    def _sync_todo_to_session(self) -> None:
        """Sync TodoList state into the session for persistence."""
        if self._session and self._todo_list:
            self._session.todo_items = self._todo_list.get_items()

    def _run_loop(self) -> str:
        """Inner loop (non-streaming): call LLM, handle tool_calls or return text."""
        tools = None
        if self._tool_registry:
            tools = self._tool_registry.get_schemas()

        tool_call_count = 0

        while True:
            if tool_call_count >= self._max_tool_calls:
                error_msg = (
                    f"Reached max tool calls limit ({self._max_tool_calls}). "
                    f"Stopping here."
                )
                return error_msg

            messages = build_context(list(self._history), max_size=self._max_size)
            try:
                response = self._adapter.chat(messages, tools=tools)
            except LLMError as e:
                error_msg = f"LLM error: {e}"
                return error_msg

            # If LLM returns text without tool_calls, we're done
            if response.text and not response.tool_calls:
                self._history.append({"role": "assistant", "content": response.text})
                return response.text

            # Handle tool_calls
            if response.tool_calls:
                error_msg, tool_call_count = self._execute_tools(response, tool_call_count)
                if error_msg is not None:
                    return error_msg
                continue  # Tool executed, loop again

            # No text and no tool_calls — shouldn't happen, but handle gracefully
            return ""

    def _run_loop_stream(self):
        """Streaming inner loop: yield display events, handle tool_calls transparently.

        Yields (event_type, data) tuples:
            "thinking"  — reasoning text
            "content"   — output text chunk
            "done"      — streaming complete (this turn)
        """
        tools = None
        if self._tool_registry:
            tools = self._tool_registry.get_schemas()

        tool_call_count = 0

        while True:
            if tool_call_count >= self._max_tool_calls:
                yield ("content", f"\n[Reached max tool calls limit ({self._max_tool_calls})]")
                yield ("done", None)
                return

            messages = build_context(list(self._history), max_size=self._max_size)

            try:
                stream = self._adapter.chat_stream(messages, tools=tools)
            except LLMError as e:
                yield ("content", f"\n[LLM error: {e}]")
                yield ("done", None)
                return

            # Collect tool calls and accumulate content
            tool_calls_accumulated = []
            content_accumulated = ""

            for event_type, data in stream:
                if event_type == "thinking":
                    yield ("thinking", data)
                elif event_type == "content":
                    content_accumulated += data
                    yield ("content", data)
                elif event_type == "tool_calls":
                    tool_calls_accumulated = data
                elif event_type == "done":
                    pass  # Will handle after loop

            if tool_calls_accumulated:
                # Build a synthetic LLMResponse for _execute_tools
                from agent_from_zero.llm.base import LLMResponse
                response = LLMResponse(
                    text=content_accumulated or None,
                    tool_calls=tool_calls_accumulated,
                )
                error_msg, tool_call_count = self._execute_tools(response, tool_call_count)
                if error_msg is not None:
                    yield ("content", f"\n{error_msg}")
                    yield ("done", None)
                    return
                continue  # Loop back for LLM to see tool results
            else:
                # Final text response — add to history and return
                self._history.append({"role": "assistant", "content": content_accumulated})
                yield ("done", None)
                return content_accumulated

    def _execute_tools(self, response, tool_call_count: int) -> tuple[str | None, int]:
        """Execute tool_calls from a response and update history.

        Returns (error_msg, new_count). error_msg is None on success.
        Side effect: updates self._history with assistant and tool messages.
        """
        assistant_content = response.text or ""
        assistant_msg: dict = {"role": "assistant", "content": assistant_content}
        assistant_msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False),
                },
            }
            for tc in response.tool_calls
        ]
        self._history.append(assistant_msg)

        for tc in response.tool_calls:
            tool_call_count += 1

            tool_name = tc["name"]
            tool_args = tc.get("arguments", {})
            t_start = time.monotonic()

            try:
                result = self._tool_registry.execute(tool_name, tool_args)
                duration_ms = (time.monotonic() - t_start) * 1000
                trace = TraceRecord(
                    tool_name=tool_name,
                    input_args=tool_args,
                    output=result,
                    duration_ms=round(duration_ms, 2),
                    call_index=tool_call_count,
                )
                emit_trace(trace)
                if self._session:
                    trace_path = self._sessions_dir.replace("sessions", "") + f"sessions/{self._session.name}.trace.jsonl"
                    append_trace_to_file(trace, trace_path)
            except Exception as e:
                duration_ms = (time.monotonic() - t_start) * 1000
                error_msg = f"Error executing tool '{tool_name}': {e}"
                trace = TraceRecord(
                    tool_name=tool_name,
                    input_args=tool_args,
                    error=str(e),
                    duration_ms=round(duration_ms, 2),
                    call_index=tool_call_count,
                )
                emit_trace(trace)
                self._history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": error_msg,
                })
                return (error_msg, tool_call_count)

            self._history.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        return (None, tool_call_count)

    def run_repl(self) -> None:
        """Run the interactive REPL with streaming output."""
        print("Agent ready. Type your message (Ctrl+C to exit).\n")
        try:
            while True:
                user_input = input("> ")
                if not user_input.strip():
                    continue

                # Prepare context
                if not self._history:
                    self._history.append(
                        {"role": "system", "content": self._system_prompt}
                    )
                self._history.append({"role": "user", "content": user_input.strip()})

                # Stream the response
                thinking_prefix_printed = False
                for event_type, data in self._run_loop_stream():
                    if event_type == "thinking":
                        if not thinking_prefix_printed:
                            print("\n  \033[2m", end="", flush=True)  # dim
                            thinking_prefix_printed = True
                        print(data, end="", file=sys.stderr, flush=True)
                    elif event_type == "content":
                        if thinking_prefix_printed:
                            sys.stderr.write("\033[0m")  # reset
                            sys.stderr.flush()
                            thinking_prefix_printed = False
                            print("\n", end="", flush=True)
                        print(data, end="", flush=True)
                    elif event_type == "done":
                        if thinking_prefix_printed:
                            sys.stderr.write("\033[0m")
                            sys.stderr.flush()
                        print()  # final newline

                # Save to session after each user turn
                if self._session:
                    self._session._messages = self._history
                    self._sync_todo_to_session()
                    self._session.save(self._sessions_dir)

        except KeyboardInterrupt:
            print("\nGoodbye.")
        except EOFError:
            print("\nGoodbye.")
