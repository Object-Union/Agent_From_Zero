# Agent_From_Zero

从零实现的最小可用 AI Agent——不依赖任何现有 agent 框架，核心 Runtime 自行实现。仅对接 DeepSeek API。

## Language

**Agent**:
一个可交互的 AI 实例，包含 tools、system prompt 和 session。
_Avoid_: Bot, assistant, worker

**Orchestrator**:
驱动 Agent 主循环的引擎：接收用户输入 → 调用 LLM → 解析输出 → 执行工具 → 返回结果。
_Avoid_: Runner, loop, engine, driver

**Tool**:
注册到 Tool Registry 的可调用函数，包含 name、description、parameter schema，由 LLM 自主决定调用。
_Avoid_: Plugin, function, action

**Session**:
一个独立对话窗口的完整对话历史，各 Session 之间彼此隔离。存为 `.scratch/sessions/<name>.md`（Markdown + YAML Frontmatter），允许"随时接着聊"。
_Avoid_: Conversation, thread, chat

**Context**:
每次调用 LLM 时实际发送的结构化消息（系统 prompt + 历史消息 + 思考过程 + 工具调用 trace）。由 Session 历史构建，超过 max_size（字符数）时触发 truncate + summarize。
_Avoid_: Payload, input, body

**TraceRecord**:
每次工具调用的结构化审计记录（tool_name、input、output/error、耗时、序号），输出到 stderr 和 `.scratch/sessions/<name>.trace.jsonl`。
_Avoid_: Log, audit trail
