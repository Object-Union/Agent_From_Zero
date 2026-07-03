# Agent From Zero

从零实现的最小可用 AI Agent——不依赖任何现有 agent 框架，核心 Runtime 自行实现。

```
78 tests passed (76 unit/integration + 2 E2E smoke against real DeepSeek API)
```

---

## 需求 vs 设计

### 要求 1：从零完成，不依赖现有 agent 框架

| 设计要求 | 我们的实现 |
|----------|-----------|
| 不能依赖 LangGraph / OpenHands / OpenClaw | 零 agent 框架依赖。仅用 `openai` SDK 做 HTTP 通信层，Agent 逻辑全自建 |
| 允许用 AI 工具辅助开发 | ✅ |
| 核心 Agent Runtime 自行实现 | [Orchestrator](src/agent_from_zero/orchestrator.py) — 整个 loop 引擎从头写 |

### 要求 2：实现基本循环

**Loop 步骤：**

| 要求步骤 | 对应代码 |
|----------|---------|
| Step 1: 接收用户输入 | `Orchestrator.process_input()` → CLI `input("> ")` |
| Step 2: 判断直接回复还是调用工具 | `_run_loop()` 检查 `LLMResponse.tool_calls` |
| Step 3: 调用工具 | `ToolRegistry.execute()` |
| Step 4: 根据结果判断继续 loop 还是返回 | LLM 返回 text → 结束；返回 tool_calls → 继续 |

**工具相关（至少 3 个）：**

| 要求 | 实现 |
|------|------|
| calculator | [tools/calculator.py](src/agent_from_zero/tools/calculator.py) — AST 安全解析，白名单校验 |
| search（可 mock） | [tools/search.py](src/agent_from_zero/tools/search.py) — MockSearchAdapter，接口可替换 |
| 自定义工具 | [tools/todo.py](src/agent_from_zero/tools/todo.py) — add / list / complete 三个 action |

**工具注册机制：**

| 要求 | 实现 |
|------|------|
| 每个工具包含名称、描述、参数 Schema | [tool_registry.py](src/agent_from_zero/tool_registry.py) — `Tool` dataclass + `ToolRegistry` |
| LLM 基于 Schema 自主决策调用 | `ToolRegistry.get_schemas()` 生成 OpenAI-compatible JSON Schema，传给 DeepSeek API |
| LLM 输出解析逻辑 | [llm/deepseek_adapter.py](src/agent_from_zero/llm/deepseek_adapter.py) — 解析 `tool_calls` vs `text`，返回 `LLMResponse` |

**Session 管理：**

| 要求 | 实现 |
|------|------|
| 窗口 1 和窗口 2 独立 session | [session.py](src/agent_from_zero/session.py) — 每个 Session 独立文件 `.scratch/sessions/<name>.md` |
| 随时接着聊，互不影响 | Markdown + YAML Frontmatter 持久化；启动时交互式选择或 `--session` 指定 |
| 待办事项跨 session 持久化 | TodoList ↔ Session.todo_items 双向同步，重启不丢失 |

**Context 有效管理：**

| 要求 | 实现 |
|------|------|
| 记住之前状态 | `Orchestrator._history` 累积所有消息（system / user / assistant / tool） |
| 支持追问（纯对话 + 带工具） | `process_input()` 每次将新输入追加到 history，调 LLM 时送完整 context |
| Context 内容选择 | 完整塞入：系统 prompt + 历史消息 + 思考过程 + 工具调用 trace |
| 自动压缩 | 达到 `max_size` 时自动调 LLM 摘要最早 50% 消息，Fallback 截断 |
| 手动压缩命令 | `/compact` — 任意时刻手动触发压缩 |
| 实时监控 | 每轮显示 Context 大小；`/context` 随时查看 |

**流式输出 + 思考过程：**

| 特性 | 实现 |
|------|------|
| 文本流式输出 | `chat_stream()` — 逐 chunk 打印到 stdout，无缓冲延迟 |
| 思考过程展示 | DeepSeek `reasoning_content` → stderr 灰色缩进显示 |
| 工具调用链 | streaming 期间累积 tool_calls，完成后透明执行继续 loop |

**额外要求：**

| 要求 | 实现 |
|------|------|
| 基本异常处理 | LLM 调用失败 → 报用户 + Session 不丢失；工具失败 → 报用户，不自动修正 |
| 工具调用 trace / 执行日志 | [observability.py](src/agent_from_zero/observability.py) — stderr 人可读短行 + `.trace.jsonl` 完整 JSON |

### 要求 3：测试用例构建

| 要求 | 实现 |
|------|------|
| 构建测试用例 | [tests/](tests/) — 78 个测试（76 unit/integration + 2 E2E） |

测试切面从高到低：

| 切面 | 文件 | 内容 |
|------|------|------|
| E2E | [test_integration.py](tests/test_integration.py) | 真 DeepSeek API 冒烟（`--run-slow`） |
| CLI 集成 | [test_integration.py](tests/test_integration.py) | agent.py 子进程、模块导入、--help |
| Orchestrator Loop | [test_orchestrator.py](tests/test_orchestrator.py) | 文本回复、链式工具、上限、失败路径 |
| Session + Context | [test_session.py](tests/test_session.py) + [test_context.py](tests/test_context.py) | CRUD、隔离、持久化、截断 |
| Tool Registry + Tools | [test_tool_registry.py](tests/test_tool_registry.py) + [test_tools/](tests/test_tools/) | 注册、schema、calculator/search/todo |
| LLM Adapter | [test_deepseek_adapter.py](tests/test_deepseek_adapter.py) | 消息格式、tool_calls 解析、API key 校验、流式 chunk |
| Observability | [test_trace.py](tests/test_trace.py) | TraceRecord、stderr、jsonl、LLM 异常 |

---

## 架构

```
                    ┌─────────────┐
                    │   agent.py  │  CLI 入口
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼───┐  ┌────▼───┐  ┌─────▼──────┐
         │  CLI   │  │Session │  │Orchestrator│
         │ 解析   │  │持久化  │  │  主循环    │
         └────────┘  └────────┘  └─────┬──────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
        ┌─────▼──────┐          ┌─────▼──────┐          ┌─────▼──────┐
        │   Context  │          │  Tool      │          │Observability│
        │  构建/压缩 │          │ Registry   │          │  Trace     │
        └────────────┘          └─────┬──────┘          └────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
              ┌─────▼──┐       ┌─────▼──┐       ┌─────▼──┐
              │Calculator│     │ Search │       │  Todo   │
              └──────────┘     └────────┘       └────────┘
                    ┌─────────────────┐
                    │  DeepSeek API   │
                    │  (OpenAI SDK)   │
                    └─────────────────┘
```

### 核心模块职责

| 模块 | 职责 | 行数 |
|------|------|:----:|
| `orchestrator.py` | 主循环引擎 + streaming + compact | ~340 |
| `tool_registry.py` | Tool 定义 + 注册 + 装饰器 + OpenAI schema 生成 | ~65 |
| `session.py` | Session 文件持久化（Markdown + YAML），tool_call_id 保全 | ~160 |
| `context.py` | Context 构建 + 溢出检测 + 截断压缩 | ~95 |
| `llm/deepseek_adapter.py` | DeepSeek API 封装 + 流式 + reasoning | ~100 |
| `observability.py` | 结构化 trace 记录 + stderr 人可读 + jsonl 完整记录 | ~70 |
| `cli.py` | 参数解析 + system prompt 加载 + session 选择 | ~70 |
| `tools/calculator.py` | AST 安全计算（白名单校验）| ~120 |
| `tools/search.py` | Mock 搜索（可替换 adapter）| ~65 |
| `tools/todo.py` | 待办管理 + 持久化同步 | ~100 |

**总计约 1200 行生产代码，覆盖 3 个工具 + session + context + streaming + trace + 78 个测试。**

---

## 快速开始

### 1. 环境准备

```bash
pip install openai python-dotenv pyyaml pytest
```

### 2. 配置 API Key

在项目根目录创建 `.env` 文件：

```
DEEPSEEK_API_KEY=sk-your-key-here
```

### 3. 启动

```bash
# 交互式选择/新建 session
python agent.py

# 指定 session 名称
python agent.py --session my-notes

# 自定义参数
python agent.py --session dev --max-size 60000 --max-tool-calls 5 --model deepseek-chat
```

### 4. 交互示例

```
Agent ready. Type your message (/compact, /context, Ctrl+C to exit).

> ...（长对话后，context 接近上限）...
  [auto-compact: 95,421 → 42,180 chars]

> 帮我搜索普通兔子的体重大概是多少，然后用计算机算1024只兔子有多重
  ✓ search: 普通兔子的体重大概是多少  (845ms)
  ✓ calculator: 1024 * 2  (0ms)

根据搜索结果，普通成年家兔体重约 1.5~2.5kg，取中值 2kg 计算：

    1024 × 2 = 2048 kg

所以 1024 只兔子大约重 2048 千克（约 2 吨）。

[context: 2,847 / 80,000 chars (4%) | 14 messages]

> 把"整理会议纪要"加到待办
  ✓ todo: add 整理会议纪要  (0ms)
已添加待办 #1: 整理会议纪要

[context: 3,012 / 80,000 chars (4%) | 16 messages]

> /context
[context: 3,012 / 80,000 chars (4%) | 16 messages]

> /compact
[context: 95,421 / 80,000 chars (119%) | 68 messages]
  Context compressed: 68 messages → 35 messages, 95,421 → 42,180 chars
[context: 42,180 / 80,000 chars (53%) | 35 messages]
```

### 5. 运行测试

```bash
# 全部（不含真 API 调用）
pytest tests/ -v

# 含真 API 冒烟测试
pytest tests/ -v --run-slow
```

### 6. CLI 参数

| 参数 | 默认值 | 用途 |
|------|--------|------|
| `--session` / `-s` | (交互式选择) | Session 名称 |
| `--model` | `deepseek-chat` | DeepSeek 模型 |
| `--max-size` | `80000` | Context 字符数上限 |
| `--max-tool-calls` | `10` | 每轮最多工具调用 |

### 7. 交互命令

| 命令 | 用途 |
|------|------|
| `/context` | 查看当前 Context 大小（字符数、消息数、百分比） |
| `/compact` | 手动触发 Context 压缩（LLM 摘要最早 50% 消息） |

> **注意**：Context 达到 `--max-size` 上限时**会自动压缩**，无需手动干预。`/compact` 用于测试或提前释放空间。压缩时 stderr 会显示：
> ```
> [auto-compact: 95,421 → 42,180 chars]
> ```

---

## 项目结构

```
agent.py                          # CLI 入口
system-prompt.md                  # 角色型 system prompt
.env                              # API key（gitignore）
pytest.ini                        # pytest 配置

src/agent_from_zero/
├── orchestrator.py               # 主循环引擎 (streaming + compact + tool loop)
├── tool_registry.py              # 工具注册 + 装饰器
├── session.py                    # Session 持久化 (Markdown + YAML)
├── context.py                    # Context 管理 (overflow + split + summary)
├── observability.py              # Trace 日志 (stderr + jsonl)
├── cli.py                        # CLI 解析 + session 选择
├── llm/
│   ├── base.py                   # LLMResponse / LLMError
│   └── deepseek_adapter.py       # DeepSeek API (streaming + reasoning)
└── tools/
    ├── calculator.py             # 安全计算器 (AST whitelist)
    ├── search.py                 # Mock 搜索 (replaceable adapter)
    └── todo.py                   # 待办管理 (session-persisted)

tests/
├── conftest.py                   # pytest 配置（--run-slow + .env 加载）
├── test_deepseek_adapter.py      # Adapter (chat + stream)
├── test_orchestrator.py          # Orchestrator (loop + tool_calls)
├── test_tool_registry.py         # Tool Registry (register + schema + decorator)
├── test_tools/                   # Calculator / Search / Todo
├── test_session.py               # Session (save + load + isolation)
├── test_context.py               # Context (overflow + split + summary)
├── test_trace.py                 # Observability (record + emit + append)
└── test_integration.py           # Integration + E2E smoke
```
