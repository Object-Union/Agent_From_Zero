# Agent From Zero

从零实现的最小可用 AI Agent——不依赖任何现有 agent 框架，核心 Runtime 自行实现。

```
77 tests passed (75 unit/integration + 2 E2E smoke against real DeepSeek API)
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

**Context 有效管理：**

| 要求 | 实现 |
|------|------|
| 记住之前状态 | `Orchestrator._history` 累积所有消息（system / user / assistant / tool） |
| 支持追问（纯对话 + 带工具） | `process_input()` 每次将新输入追加到 history，调 LLM 时送完整 context |
| Context 内容选择 | 完整塞入：系统 prompt + 历史消息 + 思考过程 + 工具调用 trace |
| 最大轮次限制 | `max_size = 80000` 字符，超限触发 truncate |
| 基础压缩 | [context.py](src/agent_from_zero/context.py) — 超过 max_size 时取最早 50% 消息截断 |

**额外要求：**

| 要求 | 实现 |
|------|------|
| 基本异常处理 | LLM 调用失败 → 报用户 + Session 不丢失；工具失败 → 报用户，不自动修正 |
| 工具调用 trace / 执行日志 | [observability.py](src/agent_from_zero/observability.py) — `TraceRecord` + stderr 实时输出 + `.trace.jsonl` 文件 |

### 要求 3：测试用例构建

| 要求 | 实现 |
|------|------|
| 构建测试用例 | [tests/](tests/) — 77 个测试（68 unit + 7 integration + 2 E2E） |

测试切面从高到低：

| 切面 | 文件 | 内容 |
|------|------|------|
| E2E | [test_integration.py](tests/test_integration.py) | 真 DeepSeek API 冒烟（`--run-slow`） |
| CLI 集成 | [test_integration.py](tests/test_integration.py) | agent.py 子进程、模块导入、--help |
| Orchestrator Loop | [test_orchestrator.py](tests/test_orchestrator.py) | 文本回复、链式工具、上限、失败路径 |
| Session + Context | [test_session.py](tests/test_session.py) + [test_context.py](tests/test_context.py) | CRUD、隔离、持久化、截断 |
| Tool Registry + Tools | [test_tool_registry.py](tests/test_tool_registry.py) + [test_tools/](tests/test_tools/) | 注册、schema、calculator/search/todo |
| LLM Adapter | [test_deepseek_adapter.py](tests/test_deepseek_adapter.py) | 消息格式、tool_calls 解析、API key 校验 |
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
         │ 解析   │  │持久化  │   │  主循环    │
         └────────┘  └────────┘  └─────┬──────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
        ┌─────▼──────┐          ┌─────▼──────┐          ┌─────▼──────┐
        │   Context  │          │  Tool      │          │Observability│
        │  构建/压缩  │          │ Registry   │          │  Trace     │
        └────────────┘          └─────┬──────┘          └────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
              ┌─────▼────┐     ┌─────▼──┐       ┌─────▼──┐
              │Calculator│     │ Search │       │  Todo  │
              └──────────┘     └────────┘       └────────┘
                    ┌─────────────────┐
                    │  DeepSeek API   │
                    │  (OpenAI SDK)   │
                    └─────────────────┘
```

### 核心模块职责

| 模块 | 职责 | 行数 |
|------|------|:----:|
| `orchestrator.py` | 主循环引擎：输入 → LLM → tool loop → 输出 | ~130 |
| `tool_registry.py` | Tool 定义 + 注册 + 装饰器 + OpenAI schema 生成 | ~65 |
| `session.py` | Session 文件持久化（Markdown + YAML Frontmatter） | ~125 |
| `context.py` | Context 构建 + 溢出检测 + 截断压缩 | ~70 |
| `llm/deepseek_adapter.py` | DeepSeek API 封装（OpenAI-compatible） | ~55 |
| `observability.py` | 结构化 trace 记录 + stderr/jsonl 输出 | ~60 |
| `cli.py` | 参数解析 + system prompt 加载 + session 选择 | ~70 |
| `tools/calculator.py` | AST 安全计算（白名单校验） | ~110 |
| `tools/search.py` | Mock 搜索（可替换 adapter） | ~55 |
| `tools/todo.py` | 待办管理（add/list/complete） | ~75 |

**总计约 820 行生产代码，覆盖 3 个工具 + session + context + trace + 77 个测试。**

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
Agent ready. Type your message (Ctrl+C to exit).

> What's 156 * 37 + 42?
[TRACE] {"tool_name":"calculator","input_args":{"expression":"156 * 37 + 42"},"output":"5814","duration_ms":0.12,"call_index":1,"timestamp":"..."}

The result is 5,814.

> Add "buy groceries" to my todo list
Added todo #1: buy groceries

> Add "write README" to my todo list
Added todo #2: write README

> Show my todo list
Your todo list:
  1. [ ] buy groceries
  2. [ ] write README
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

---

## 项目结构

```
agent.py                          # CLI 入口
system-prompt.md                  # 角色型 system prompt
.env                              # API key（gitignore）
pytest.ini                        # pytest 配置

src/agent_from_zero/
├── orchestrator.py               # 主循环引擎
├── tool_registry.py              # 工具注册 + 装饰器
├── session.py                    # Session 持久化
├── context.py                    # Context 管理
├── observability.py              # Trace 日志
├── cli.py                        # CLI 解析 + session 选择
├── llm/
│   ├── base.py                   # LLMResponse / LLMError
│   └── deepseek_adapter.py       # DeepSeek API
└── tools/
    ├── calculator.py             # 安全计算器
    ├── search.py                 # Mock 搜索
    └── todo.py                   # 待办管理

tests/
├── conftest.py                   # pytest 配置（--run-slow + .env 加载）
├── test_deepseek_adapter.py      # Adapter 单元测试
├── test_orchestrator.py          # Orchestrator 单元测试
├── test_tool_registry.py         # Tool Registry 单元测试
├── test_tools/                   # 各工具单元测试
├── test_session.py               # Session 单元测试
├── test_context.py               # Context 单元测试
├── test_trace.py                 # Observability 单元测试
└── test_integration.py           # 集成测试 + E2E 冒烟
```
