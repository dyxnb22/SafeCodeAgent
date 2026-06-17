# SafeCode Agent 后续能力计划

基准版本：v6.17.x dev 增量（v6.9.2-v6.17 已落地）  
更新日期：2026-06-17  
目标定位：terminal-only，对齐 opencode 的终端开发体验；不做 IDE、desktop、远程云 agent。

---

## 当前状态

v6.9.x 已经把 SafeCode 从安全 patch 提案器推进到具备轻量语义能力的 terminal agent：

| 能力 | 文件 | 状态 |
|---|---|---|
| Jedi 语义引用桥 | `src/safecode/index/lsp_bridge.py` | 已实现，需依赖/测试收口 |
| Pyright diagnostics 桥 | `src/safecode/index/lsp_bridge.py` | 已实现 |
| `find_references` native tool | `src/safecode/agent/find_references_tool.py` | 已实现并注册进 agent loop |
| `sac refactor rename` | `src/safecode/cli_refactor.py` | 已实现，需 hardening |
| 对话式 shell 初版 | `src/safecode/agent/conversation.py`, `src/safecode/cli_shell.py` | 已有 dev 增量，需稳定化 |
| 分级审批初版 | `src/safecode/agent/approval_tier.py`, `src/safecode/agent/loop.py` | 已有 dev 增量，需产品化 |
| 结构化 repair 初版 | `src/safecode/agent/repair.py`, `src/safecode/agent/validation.py` | 已有 dev 增量，需接入 diagnostics 闭环 |

当前判断：v6.9.x 的语义/refactor 基础层已经完成 hardening；`sac shell --agentic` 已经进入真正的 conversation-backed native loop；approval tier 已经配置化并接入 auto-edit 路径。

---

## 版本区间总览

| 版本 | 主题 | 优先级 |
|---|---|---|
| v6.9.2 | 语义 rename hardening | 已完成 |
| v6.10.x | 真正的 terminal conversation | 已完成 |
| v6.11.x | 低摩擦权限模型 | 已完成 |
| v6.12.x | Git 感知上下文 + dirty tree safety | 已完成 |
| v6.13.x | Diagnostics + repair loop | 已完成 |
| v6.14.x | Tool registry + MCP 实用化 | 已完成 |
| v6.15.x | 结构化 step journal | 已完成 |
| v6.16.x | 测试生成工作流 | 已完成 |
| v6.17.x | Eval ratchet | 已完成 |
| v6.18.x | 产品面收口与文档/help 对齐 | 已完成 |
| v6.19.x | Plan / Build shell 模式 | 已完成 |
| v6.20.x | terminal-only 多语言 LSP 抽象 | 已完成 |
| v6.21.x | session 管理 + stats/export/import | 已完成 |
| v6.22.x | formatter + post-edit workflow | 已完成 |
| v6.23.x | 用户工具配置生态 | 已完成 |

推荐顺序：

```text
v6.9.2  harden semantic rename
v6.10   conversation shell
v6.11   approval tier
v6.12   git context + dirty tree guard
v6.13   diagnostics repair loop
v6.14   tool registry + MCP
v6.15   step journal
v6.16   test generation
v6.17   eval ratchet
v6.18   product surface alignment
v6.19   plan/build shell mode
v6.20   multi-language lsp diagnostics
v6.21   session management
v6.22   formatter workflow
v6.23   user tool config
```

---

## v6.9.2 — 语义层收口（已完成）

### 目标

把 v6.9.x 从“能跑的 MVP”打磨成后续能力可以依赖的基础设施。

### 要做

1. 依赖和测试稳定
   - 将 `jedi` 加入 optional extra 或 dev dependency。
   - Jedi 相关测试使用 `pytest.importorskip("jedi")`，避免 CI 环境缺依赖时误失败。
   - Pyright 不作为 CI 硬依赖，继续用 mock 覆盖可用、不可用、timeout、JSON 解析路径。

2. 多定义保护
   - `find_references("validate")` 如果发现多个同名定义且没有 `--file`，返回 ambiguous。
   - `sac refactor rename` 遇到 ambiguous 时直接提示用户补 `--file`。
   - 禁止静默选择第一个定义进行 rename。

3. rename 改成 token 级替换
   - 使用 Python `tokenize`，只替换 `NAME` token。
   - 默认不改字符串、注释、docstring。
   - 保留未来选项：`--include-comments`、`--include-strings`。

4. JSON pending patch 顺序修正
   - 先保存 pending patch。
   - 保存成功后再输出 `"status": "pending"`。
   - 保存失败输出 error，不能先报告 pending。

### 验收

- 同名函数不误改。
- 字符串、注释、docstring 不误改。
- 缺 Jedi 时 fallback 测试仍然通过。
- JSON pending 状态真实可靠。

### 实现记录

- `jedi` 已加入 `semantic` optional extra。
- Jedi 相关测试在缺依赖环境中 skip，不让 CI 误失败。
- `find_references` 多定义且无 `--file` 时返回 ambiguity，CLI 转成 error。
- `sac refactor rename` 改为 token 级 NAME 替换，不修改字符串、注释、docstring。
- JSON 模式改为先保存 pending patch，再输出 pending 状态。

---

## v6.10.x — 真正的 Terminal Conversation（已完成）

### 目标

`sac shell` 成为长驻对话式 REPL，而不是每轮独立任务。用户可以自然说“刚才那个函数”“上一步的错误”“继续按刚才方案改”，agent 能延续上下文。

### 要做

1. 稳定 `ConversationBuffer`
   - user、assistant、tool result 都进入 buffer。
   - 持久化到 `.sac/sessions/<session_id>/conversation.jsonl`。
   - 写入前调用 redaction，避免 secret 落盘。
   - 超过轮次或 token 阈值后自动 compact。

2. LLM 调用接入 conversation history
   - `choose_tool_native(..., conversation_history=...)` 成为 shell 默认路径。
   - conversation 中提到过的文件进入 context selector bonus。
   - 已读文件、已跑命令、已失败测试成为下一轮可用上下文。

3. shell UX
   - 默认进入连续对话模式。
   - `/history` 查看当前 conversation 摘要。
   - `/clear` 清空当前 conversation。
   - `/compact` 手动触发压缩。
   - 每轮显示工具调用摘要和 pending/action 状态。

### 验收

```text
第一轮：看一下 src/foo.py 里的 parse_config
第二轮：把刚才那个函数兼容 None
```

agent 能正确定位 `parse_config`，不重复猜文件，也不丢第一轮约束。

### 实现记录

- `AgentLoop.run(..., conversation=...)` 已接入 conversation。
- 当 LLM client 支持 native tools 时，`run()` 优先走 `native_step(conversation=...)`。
- `choose_tool_native()` 的初始调用和 tool-result follow-up 调用都会接收 `conversation_history`。
- `sac shell --agentic` 会把 user、assistant、native tool observation 写入 `ConversationBuffer`。
- 新增 `/compact`，并保留 `/history`、`/clear`、`/undo`。

---

## v6.11.x — 低摩擦权限模型（已完成）

### 目标

接近 opencode 的日常流畅度，同时保持 SafeCode 的 checkpoint、audit、rollback 优势。

### 权限层级

| Tier | 行为 | 示例 |
|---|---|---|
| `auto` | 自动执行 | 单文件小改、注释、测试名修正、低风险文档修改 |
| `confirm` | 展示 diff 等确认 | 多文件逻辑改动、rename、API 改动 |
| `gate` | 强审批 | 删除文件、shell 命令、网络、git push、外部写入 |

### 要做

1. 产品化 `ApprovalTier`
   - `classify_proposal(proposal, config)` 支持配置阈值。
   - 根据文件数、diff 行数、operation、路径敏感度、文件后缀判断风险。

2. 配置项
   - `approval.mode = suggest | auto-edit | full-auto`。
   - `approval.auto_max_files`。
   - `approval.auto_max_changed_lines`。
   - `approval.never_auto_paths`。

3. shell 行为
   - `sac shell --auto-edit` 自动 apply `auto` tier。
   - `sac shell --full-auto` 自动 apply 合规写入和合规命令。
   - 自动 apply 仍必须 checkpoint + audit。
   - `/undo` 可回滚最近自动修改。

### 验收

- 小文档改动自动落盘。
- 3 文件重构展示 diff 并等待确认。
- 删除文件、配置修改、shell 命令仍然 gate。
- `/undo` 能回滚最近自动修改。

### 实现记录

- 新增 `ApprovalConfig`，包含 `mode`、`auto_max_files`、`auto_max_changed_lines`、`never_auto_paths`。
- `classify_proposal(proposal, config)` 支持配置化阈值。
- 项目配置只能收紧 approval 阈值，不能放宽用户侧限制。
- `AgentLoop` 的 auto-edit 路径使用配置化 approval tier。
- 默认 never-auto 覆盖 `.env`、`.sac/`、`pyproject.toml`、`uv.lock`。

---

## v6.12.x — Git 感知上下文 + Dirty Tree Safety（已完成）

### 目标

agent 知道当前工作区状态、用户已有改动、最近提交和本轮 agent 改动，避免静默覆盖用户工作。

### 要做

1. context 注入
   - `git status --short`。
   - `git diff --stat`。
   - 任务相关文件的 recent commits。
   - 当前未提交 diff 的 compact summary。

2. dirty tree guard
   - 区分用户已有改动和 agent 本轮改动。
   - apply 前检测目标文件是否有 unrelated changes。
   - 默认不覆盖用户未授权改动。
   - 提供显式 override，例如 `--allow-dirty-targets`。

3. shell 命令
   - `/status`。
   - `/diff`。
   - `/checkpoints`。
   - `/undo`。

### 验收

```text
用户手动改了 a.py
agent 也想改 a.py
```

agent 必须提示冲突，不允许静默覆盖。

### 实现记录

- Git context 已通过 `GitContextProvider` 注入 context collector，包含 status、diff stat、recent commits 和 dirty summary。
- `AgentOrchestrator.apply()` 在 patch validator 之后增加 dirty target guard。
- apply 前会检查 patch 目标文件是否已经在 git dirty set 中；命中时抛出 `PatchValidationError`，不继续写入。
- dirty tree guard 覆盖到 orchestrator 层，因此 CLI、shell、JSON pending apply 共享同一安全边界。

---

## v6.13.x — Diagnostics + Repair Loop（已完成）

### 目标

从“能提出修改”升级到“能根据测试和类型错误进行 bounded repair”。

### 要做

1. Pyright diagnostics 接入 repair
   - 调用 `PyrightBridge.get_diagnostics()`。
   - 将 `file`、`line`、`message`、`rule` 注入 repair prompt。
   - 根据 diagnostics 自动召回错误文件附近上下文。

2. validation strategy
   - Python：pytest + pyright。
   - JS/TS：npm test + tsc。
   - Go：go test。
   - Rust：cargo test。

3. bounded repair
   - 最多 N 次 repair。
   - 每次失败分类。
   - 失败 tail 去重，避免循环。
   - repair patch 仍走 pending/approval/apply。

### 验收

- agent 改完后测试失败，能基于失败输出生成 repair patch。
- pyright 报错能精准召回对应文件和行。
- 最多尝试 N 次，不无限循环。

### 实现记录

- `build_repair_prompt()` 支持接收 bounded diagnostics block。
- validation repair 失败路径会调用 `PyrightBridge.get_diagnostics(project_root)`，将前 10 条类型诊断注入 repair prompt。
- diagnostics 输出经过长度上限控制，避免污染 prompt。
- repair patch 仍沿用原有 pending、approval、validation、apply 流程。

---

## v6.14.x — Tool Registry + MCP 实用化（已完成）

### 目标

让 terminal agent 的工具层更像 opencode：丰富、可发现、可审计、可控。

### 要做

1. 统一 tool metadata
   - name。
   - risk level。
   - approval tier。
   - output cap。
   - redaction policy。
   - audit event。

2. `sac tools list`
   - 展示 read/write/command/refactor/MCP tools。
   - 展示是否 auto-approved。
   - 展示权限类别。
   - 展示工具来源和实验状态。

3. MCP 稳定化
   - stdio lifecycle 稳定。
   - tool schema discovery。
   - read-only 默认可用。
   - write 走 proposal + approval。
   - 工具失败不会卡死 agent loop。

### 验收

agent 可以自然调用 search、read、git、test、find_references、MCP read 工具；工具失败被结构化记录，不污染后续上下文。

### 实现记录

- `sac tools list --json` 输出结构化 built-in tool registry。
- `sac tools list --include-mcp` 会通过 native dispatcher 注册已配置 MCP tools，并 fail-soft 展示可发现工具。
- JSON 输出包含 `tools` 和 `mcp_tools` 两个区块，方便终端脚本和 eval 使用。
- 非 JSON 输出保留表格视图，并在需要时展示 MCP 工具来源。

---

## v6.15.x — 结构化 Step Journal（已完成）

### 目标

长任务中断后，恢复时不重复劳动，不忘记失败过的方案。

### 要做

1. 新增 `.sac/tasks/<id>/step_journal.jsonl`。

2. 每步记录：
   - action type。
   - tool name。
   - files read。
   - files changed。
   - outcome。
   - summary。
   - timestamp。

3. resume 时注入：
   - 已尝试方案。
   - 已失败原因。
   - 已修改文件。
   - 当前 pending patch 状态。

4. 安全边界
   - journal 写入前 redaction。
   - journal cap，防止无限增长。
   - 损坏 journal fail-soft，不阻断任务。

### 验收

8 步任务中断后 resume，agent 不重复第 1-5 步，也不会忘记失败过的方案。

### 实现记录

- 新增 `StepJournalStore`，写入 `.sac/tasks/<session_id>/step_journal.jsonl`。
- 每步记录 action type、tool name、files changed、outcome、summary、timestamp。
- journal 写入前进行 redaction，并按 cap 保留最近记录。
- 损坏 journal fail-soft，不阻断 agent loop。

---

## v6.16.x — 测试生成工作流（已完成）

### 目标

agent 不只修 bug，也能主动补测试，尤其是 bugfix 后的 regression test。

### 要做

1. `sac test-gen <target>`
   - 定位函数、类或文件。
   - 读取目标实现。
   - 搜索已有测试。
   - 生成 pending patch。

2. shell 内建议
   - 改逻辑后提示是否补测试。
   - bugfix 后优先生成 regression test。
   - 不重复已有测试名和覆盖点。

3. 验证
   - 生成测试后建议运行最小测试集。
   - 失败时进入 repair loop。

### 验收

`sac test-gen src/foo.py::parse_config` 生成不少于 3 个边界测试，并且不重复已有测试。

### 实现记录

- 新增 `sac test-gen generate <target>`，支持文件、`file.py::symbol` 和唯一符号名定位。
- 命令会读取目标实现、检索已有测试片段，并生成 pending patch。
- 默认输出到 `tests/test_<target_stem>.py`，也支持 `--output` 指定路径。
- JSON 模式返回 pending patch 元信息，方便 shell 或脚本后续接 `sac apply`。

---

## v6.17.x — Eval Ratchet（已完成）

### 目标

对齐 opencode 不能靠感觉，要有版本间可比较的指标。

### Fixture 分类

| 类型 | 目标 |
|---|---|
| single-file bugfix | 基础修复 |
| multi-file refactor | 上下文能力 |
| symbol rename | 语义能力 |
| signature change | 调用点理解 |
| failing test repair | repair loop |
| dirty tree safety | 不覆盖用户改动 |
| long conversation | 多轮记忆 |
| permission boundary | 权限边界 |

### 指标

```text
pass_rate
tool_calls
tokens
cost
repair_iterations
confirm_count
unsafe_action_blocked
dirty_tree_preserved
```

### 验收

- 每个版本有 eval snapshot。
- 能比较 v6.10 到 v6.17 的真实提升。
- eval 结果能暴露回归，而不是只作为 demo 材料。

### 实现记录

- `scripts/eval_compare.py` 增加 snapshot compare 模式。
- 可以直接比较两个 eval snapshot 文件，输出 pass/regression/fixed/unchanged 统计。
- 原有 live provider compare 模式保留，snapshot 模式作为更轻量的 ratchet 检查入口。
- 新增测试覆盖 regression、fixed、unchanged、wrong-arity 参数路径。

---

## 与 opencode 的 terminal-only 差距

| 维度 | SafeCode 当前方向 | opencode 强项 | 后续版本 |
|---|---|---|---|
| 连续交互 | conversation shell 稳定化 | 长驻 REPL，连续上下文 | v6.10 |
| 低摩擦执行 | approval tier | 默认顺滑工具执行 | v6.11 |
| 代码理解 | Jedi/Pyright 轻量语义层 | LSP/多语言语义能力 | v6.9.2, v6.13 |
| Git 工作流 | git context + dirty tree guard | 日常开发上下文强 | v6.12 |
| 工具生态 | tool registry + MCP | 工具丰富且可发现 | v6.14 |
| 长任务恢复 | step journal | 长会话体验 | v6.15 |
| 质量闭环 | validation + eval ratchet | 实战体验 | v6.13, v6.17 |
| 安全链 | checkpoint/audit/rollback | SafeCode 优势 | 持续保持 |

结论：SafeCode 不需要复制 opencode 的 IDE/desktop 外壳。正确方向是成为 terminal-only、安全优先、可审计、有 rollback 的 opencode 替代品。

---

## v6.18.x — 产品面收口与文档/help 对齐（已完成）

### 目标

让文档、help surface、实际能力一致。尤其是 shell 已支持 `--auto-edit` / `--full-auto` 后，README 和 comparison 不能继续声称“永不 auto-apply”。

### 要做

- 更新 README 的 shell、trust mode、context、MCP、comparison 描述。
- 更新 `docs/compare.md` 的能力摘要，不再停留在 v3.x。
- `sac help --all` 展示 v6.9-v6.17 新入口：`refactor`、`test-gen`、`tools`、`mcp`、`context`、`agent`。
- 保留 daily command surface 克制，不把所有实验命令塞进默认 `sac --help`。

### 验收

- 文档不再与 `sac shell --help` 冲突。
- `sac help --all` 能发现主要高级能力。

### 实现记录

- README 的 shell/trust mode 描述已更新到 `--auto-edit`、`--full-auto`、`--mode plan`。
- `docs/compare.md` 的能力摘要更新到 v6.23 dev。
- `sac help --all` 增加 `tools`、`mcp`、`refactor`、`test-gen`、`lsp`、`session`、`format`。

---

## v6.19.x — Plan / Build Shell 模式（已完成）

### 目标

对齐 opencode 的 Plan/Build 心智模型：Plan 只读分析，不写文件、不跑命令；Build 可按当前 approval/trust 策略执行。

### 要做

- `sac shell --mode plan|build`。
- `/mode` 查看当前模式，`/mode plan` 和 `/mode build` 在 agentic shell 内切换。
- Plan 模式只注册 read/search/find-references 类工具。
- Build 模式使用现有 approval tier、auto-edit、full-auto。

### 验收

- Plan 模式下模型无法调用 write/run_command native tools。
- Build 模式保持现有行为。

### 实现记录

- `AgentLoop(plan_mode=True)` 只注册 read/search/reference 类 native tools。
- `sac shell --agentic --mode plan|build` 已接入。
- agentic shell 支持 `/mode`、`/mode plan`、`/mode build`。
- Plan 模式会强制关闭 `auto_edit` 和 `full_auto`。

---

## v6.20.x — Terminal-only 多语言 LSP 抽象（已完成）

### 目标

不做 IDE LSP UI，但让 terminal agent 有统一的语言服务入口：可探测、可诊断、可注入 repair/context。

### 要做

- 新增 `LanguageServiceManager`。
- Python 复用 PyrightBridge。
- TypeScript/JavaScript 探测 `tsc --noEmit`。
- Go 探测 `go test ./...` 或 `gopls` 可用性。
- Rust 探测 `cargo check --message-format=json`。
- 新增 `sac lsp status` 和 `sac lsp diagnostics --json`。

### 验收

- 无对应工具时 fail-soft。
- 有工具时输出统一 diagnostics 结构。

### 实现记录

- 新增 `LanguageServiceManager`，统一返回 service status 和 diagnostics。
- Python 复用 `PyrightBridge`。
- TypeScript/JavaScript、Go、Rust 通过本地 CLI fail-soft 采集 diagnostics。
- 新增 `sac lsp status` 和 `sac lsp diagnostics --json`。

---

## v6.21.x — Session 管理 + Stats / Export / Import（已完成）

### 目标

把已有 shell session、task sidecar、conversation、journal 变成用户可操作的 terminal surface。

### 要做

- 新增 `sac session list`。
- 新增 `sac session stats`。
- 新增 `sac session export <id> --sanitize`。
- 新增 `sac session import <file>`。
- JSON 输出可用于 eval 和脚本。

### 验收

- 用户能列出最近 session。
- export 不泄露 secret。
- import 损坏文件 fail-soft。

### 实现记录

- 新增 `sac session list --json`。
- 新增 `sac session stats --json`。
- 新增 `sac session export <id> --sanitize`。
- 新增 `sac session import <file>`。
- export 使用 redaction，并补充 `sk-...` token redaction。

---

## v6.22.x — Formatter + Post-edit Workflow（已完成）

### 目标

补齐日常开发的“改完格式化，再跑最小验证”的体验。

### 要做

- 新增 formatter detector：`ruff format`、`black`、`prettier`、`gofmt`、`cargo fmt`。
- 新增 `sac format [--check] [--json]`。
- validation loop 在配置开启时可先跑 formatter，再跑 test/typecheck。
- formatter 命令仍走 policy gate / ShellRunner。

### 验收

- 未安装 formatter 时 fail-soft。
- 安装 formatter 时命令通过 ShellRunner 运行并记录结果。

### 实现记录

- 新增 `detect_formatters()` 和 `run_formatters()`。
- 支持配置式 `[formatter] commands = [...]`。
- 自动探测 `ruff format`、`black`、`prettier`、`gofmt`、`cargo fmt`。
- 新增 `sac format run --check --json`。
- validation loop 在 `formatter.enabled=true` 时会先跑 formatter，再跑 validation suite。

---

## v6.23.x — 用户工具配置生态（已完成）

### 目标

让 terminal-only 用户能通过配置声明项目工具，而不是只能等内置工具或 MCP。

### 要做

- 支持 `.sac/tools.toml`。
- 工具字段：name、description、command、risk、permission、approval、experimental。
- `sac tools list --include-user --json` 展示用户工具。
- 首版只做可发现和审计 metadata，不默认自动执行任意用户工具。

### 验收

- tools.toml 配置错误 fail-soft。
- 用户工具能进入 registry 输出。

### 实现记录

- 新增 `.sac/tools.toml` loader。
- 支持 `[[tools]]` 声明 name、description、command、risk、permission、approval。
- `sac tools list --include-user --json` 输出 `user_tools` 和 `user_tool_errors`。
- 首版只做可发现和审计 metadata，不默认自动执行任意用户工具。

---

## 非目标

- 不做 IDE 插件产品化。
- 不做 desktop app。
- 不做远程云 agent。
- 不做团队 memory 同步。
- 不做截图/电脑操作。
- 不做自动 merge / CD。
- 不做持续学习；历史经验进入长期记忆必须人工批准。
