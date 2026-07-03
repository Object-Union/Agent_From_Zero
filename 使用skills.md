# 第一大类：Engineering 工程核心（代码开发主流程）
## 用户手动调用
1. `/ask-matt`：技能调度路由，输入场景自动推荐最合适的技能；
2. `/grill-with-docs`：深度需求拷问 + 自动构建项目领域模型，同步更新 CONTEXT.md、ADR 架构决策记录；
3. `/triage`：工单分级流转，标准化 Issue 处理流程；
4. `/improve-codebase-architecture`：扫描代码架构问题，生成可视化 HTML 报告，引导模块深度封装优化；
5. `/setup-matt-pocock-skills`：项目一次性初始化配置；
6. `/to-issues`：将方案 / PRD 拆分为可独立开发的垂直切片工单；
7. `/to-prd`：把对话上下文自动生成结构化产品需求文档，同步推送至 Issue 平台；
8. `/prototype`：快速搭建可运行原型（终端逻辑 Demo / 多版本 UI 切换原型）。

## 模型自动调用（AI 自动触发）
1. `/diagnosing-bugs`：标准化 Bug 排查闭环：复现 → 最小化复现案例 → 假设根因 → 埋点观测 → 修复 → 回归测试；
2. `/tdd`：严格测试驱动开发，强制红 - 绿 - 重构，单次只开发一个垂直功能切片；
3. `/domain-modeling`：维护项目统一领域术语，校验业务名词、补充边界场景、更新 `CONTEXT.md`；
4. `/codebase-design`：规范「深层模块」设计 —— 少量对外接口承载大量内部逻辑，保证可测试、低耦合。

# 第二大类：Productivity 通用效率工具（非代码专属）
## 用户手动调用
1. `/grill-me`：无文档版需求拷问，穷尽方案所有决策分支，写代码前对齐预期；
2. `/handoff`：压缩对话为交接文档，支持切换 Agent 继续开发；
3. `/teach`：交互式教学，以当前项目为实操环境分步讲解技术概念；
4. `/writing-great-skills`：编写自定义 Skill 的规范参考文档。
## 模型自动调用
5. `/grilling`：`/grill-me//grill-with-docs` 底层复用的拷问逻辑。

# 典型完整开发工作流示例
0. 初始化项目：`/setup-matt-pocock-skills`：项目一次性初始化配置；
1. 需求澄清：`/grill-with-docs` → 对齐需求 + 生成领域术语 `CONTEXT.md`；
2. 产出规划：`/to-prd` 生成需求文档 → `/to-issues` 拆分开发工单；
3. 编码开发：`/tdd` 驱动开发，AI 自动执行测试闭环；
4. 问题修复：出现报错自动触发 `/diagnosing-bugs` 完整排错流程；
5. 长期维护：定期执行 `/improve-codebase-architecture` 重构优化，防止代码腐化；
6. 版本管控：`setup-pre-commit` 自动化代码校验，`git-guardrails` 规避 Git 风险操作。