"""Orchestrator: drives the agent main loop with tool-calling and session support."""

import json
import sys
import time

from agent_from_zero.context import build_context, check_overflow, context_size, split_for_compression, apply_summary
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

            self._auto_compact()
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

            self._auto_compact()
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
            thinking_accumulated = ""

            for event_type, data in stream:
                if event_type == "thinking":
                    thinking_accumulated += data
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
                    thinking=thinking_accumulated or None,
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

        # Per DeepSeek docs: with tool_calls, MUST preserve reasoning_content
        if response.thinking:
            assistant_msg["reasoning_content"] = response.thinking

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

    def _auto_compact(self) -> None:
        """Silently compact context if it overflows max_size."""
        if not check_overflow(self._history, self._max_size):
            return

        result = self._do_compact(label="auto-compacted")
        if result is None:
            return

        print(
            f"\n  \033[90m[{result}]\033[0m\n",
            file=sys.stderr, flush=True,
        )

    def _do_compact(self, label: str = "compressed") -> str | None:
        """Shared compression logic: summarize oldest 50% of messages.

        Returns status message on success, or None if nothing to compress.
        """
        to_summarize, to_keep = split_for_compression(self._history, self._max_size)
        if not to_summarize:
            return None

        old_count = len(self._history)
        old_size = context_size(self._history)

        try:
            summary_prompt = (
                "Summarize the following conversation history briefly. "
                "Keep key facts, decisions, and user context. "
                "Respond in the same language as the conversation."
            )
            summary_messages = list(to_summarize)
            summary_messages.append({"role": "user", "content": summary_prompt})
            response = self._adapter.chat(summary_messages)
            summary_text = response.text or "(unable to summarize)"
        except Exception as e:
            summary_text = f"(compression failed: {e})"

        self._history = apply_summary(self._history, to_keep, summary_text)
        new_size = context_size(self._history)

        result = (
            f"Context {label}: {old_count} messages → {len(self._history)} messages, "
            f"{old_size:,} → {new_size:,} chars"
        )
        return result

    def compact(self) -> str:
        """Manually compress context at any time, regardless of max_size.

        Returns a status message describing what happened.
        """
        if not self._history:
            return "Nothing to compact (no history)."

        result = self._do_compact(label="compressed")
        if result is None:
            return "Not enough messages to compress (need at least 5 non-system messages)."
        return result

    def _context_info(self) -> str:
        """Return a one-liner with current context stats."""
        size = context_size(self._history)
        pct = size / self._max_size * 100 if self._max_size else 0
        msgs = len(self._history)
        return (
            f"\033[90m[context: {size:,} / {self._max_size:,} chars "
            f"({pct:.0f}%) | {msgs} messages]\033[0m"
        )

    def _print_context_info(self) -> None:
        """Print context stats to stderr."""
        print(self._context_info(), file=sys.stderr, flush=True)

    def run_repl(self) -> None:
        """Run the interactive REPL with streaming output."""
        print("Agent ready. Type your message (/compact, /context, Ctrl+C to exit).\n")
        try:
            while True:
                user_input = input("> ")
                if not user_input.strip():
                    continue

                # Handle slash commands
                cmd = user_input.strip().lower()
                if cmd == "/compact":
                    result = self.compact()
                    self._print_context_info()
                    print(f"\n  {result}\n")
                    if self._session:
                        self._session._messages = self._history
                        self._sync_todo_to_session()
                        self._session.save(self._sessions_dir)
                    continue
                elif cmd == "/context":
                    self._print_context_info()
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

                # Show context size after each turn
                self._print_context_info()

                # Save to session after each user turn
                if self._session:
                    self._session._messages = self._history
                    self._sync_todo_to_session()
                    self._session.save(self._sessions_dir)

        except KeyboardInterrupt:
            print("\nGoodbye.")
        except EOFError:
            print("\nGoodbye.")
