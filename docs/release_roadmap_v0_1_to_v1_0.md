# SafeCode Agent Release Roadmap: v0.1 to v1.6.x

这份文档用于把 SafeCode Agent 从 `v0.1` 安全 Patch Runtime，规划到 `v1.6.x` 的 Claude Code-like 本地 Agent Runtime。

核心原则：

- 每个小版本都应该能独立验收。
- 每个版本只增加一类能力，避免一次性扩大风险面。
- 所有写操作继续保留 diff、checkpoint、audit、rollback。
- 高级能力必须建立在权限、状态、日志和回滚之上。
- 当前路线已经根据生产安全审查调整：`v1.5.x` 优先修核心安全边界，`v1.6.x` 再做 MCP 真执行和 subagent 并发。

## 版本总览

| 阶段 | 产品能力 | 主要目标 | 适合学习的知识点 |
|---|---|---|---|
| `v0.1.x` | Safe Patch Runtime | 安全修改文件闭环 | Python CLI、文件 IO、Patch、Diff、JSONL、测试 |
| `v0.2.x` | Permissioned Shell Runtime | 受控执行命令 | `subprocess`、`shlex`、权限策略、命令审计 |
| `v0.3.x` | Long-running State | 长任务状态和项目规则 | Markdown 状态文件、配置、Hooks、项目约定 |
| `v0.4.x` | Skills + Tool Registry | 能力包和工具注册 | 插件化目录、工具元数据、按需加载 |
| `v0.5.x` | Code Index | 大项目上下文检索 | AST、符号索引、全文搜索、上下文选择 |
| `v0.6.x` | MCP Integration | 外部工具生态 | MCP 配置、工具发现、外部写入审批 |
| `v0.7.x` | Sandbox / Containment | 运行时边界 | 文件系统边界、网络策略、受控执行 |
| `v0.8.x` | Subagents | 分工协作 | 任务模型、子任务隔离、结果汇总 |
| `v0.9.x` | Observability + Evaluation | 可观测和可评估 | Trace、指标、回归样例、报告 |
| `v1.0.x` | Stable Local Agent Runtime | 稳定发布版本 | 安装体验、文档、兼容性、安全基线 |
| `v1.1.x` | Product Extension Layer | 产品扩展层 | 本地 API、导出、任务队列、IDE metadata、发布流程 |
| `v1.2.x` | Production Hardening | 生产安全加固 | shell hardening、trusted policy、sandbox enforcement、real LLM、deploy、prod eval |
| `v1.3.x` | Runtime Trust Refinement | 运行时信任边界细化 | context secret filtering、hook trust、LLM network policy、trace/audit integration |
| `v1.4.x` | Runtime Operations | 运行期可运维性 | runtime logs、debug commands、failure diagnostics |
| `v1.5.x` | Core Security Boundary | 核心安全边界整改 | context containment、transactional apply、command policy、hook approval、audit integrity |
| `v1.6.x` | Controlled Tooling and Subagents | 受控工具生态与子任务 | real MCP execution、scoped subagents、merge review、OS-level sandbox |

## Branch 命名约定

用户当前要求分支名不加 `codex/` 前缀，因此后续分支建议使用：

```text
v0.2.0-config-policy
v0.2.1-shell-risk-classifier
v0.2.2-sac-run-readonly
```

规则：

- 分支名以版本号开头。
- 后面接一个短功能名。
- 一个分支尽量对应一个可验收能力。
- 分支内必须配对应说明文档，放在 `docs/version-notes/`。

## v0.1.x: Safe Patch Runtime

目标：完成“模型提出修改，运行时安全应用”的最小闭环。

已规划子版本：

| 版本 | 分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.1.0` | `v0.1.0-ask-audit` | CLI 骨架、`sac ask`、audit log | `uv run sac ask "这个项目是什么？"` 可运行 |
| `v0.1.1` | `v0.1.1-patch-parser` | Patch 数据模型和解析器 | 能解析 `Update File` patch |
| `v0.1.2` | `v0.1.2-edit-preview` | `sac edit`、diff preview、pending patch | 只写 `.sac/pending_patch.json`，不改业务文件 |
| `v0.1.3` | `v0.1.3-apply-checkpoint` | `sac apply`、checkpoint | apply 前确认并创建 checkpoint |
| `v0.1.4` | `v0.1.4-rollback-history` | `sac rollback --last`、`sac history` | 可恢复最近一次修改，可查看事件 |
| `v0.1.5` | `v0.1.5-fastapi-demo` | FastAPI demo 项目 | 能完整演示 edit/apply/history/rollback |

v0.1 完成后的产品状态：

- Agent 可以读取项目上下文。
- Agent 可以生成可审查的 patch。
- 用户可以在写入前看到 diff。
- 写入前有 checkpoint。
- 写入后有 audit event。
- 用户可以 rollback。

v0.1 不追求：

- 自动 Shell。
- MCP。
- 多 Agent。
- 向量数据库。
- 后台长期任务。

## v0.2.x: Permissioned Shell Runtime

目标：在不破坏安全边界的前提下，让 Agent 能建议和执行受控命令。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.2.0` | `v0.2.0-config-policy` | `.sac/config.yaml`、默认策略、配置读取 | `sac config show` 能展示有效配置 |
| `v0.2.1` | `v0.2.1-shell-risk-classifier` | Shell 风险分类器 | 能识别 `rm`、`sudo`、管道、重定向、`curl | sh` |
| `v0.2.2` | `v0.2.2-sac-run-readonly` | 只读命令执行 | `sac run "git status"` 可执行并审计 |
| `v0.2.3` | `v0.2.3-sac-run-approval` | 中风险命令确认，高风险阻止 | 危险命令不会静默执行 |
| `v0.2.4` | `v0.2.4-shell-audit-history` | Shell 结果进入 history | `sac history` 能看到命令、退出码、耗时 |

核心文件方向：

- `src/safecode/config.py`：读取项目配置和默认策略。
- `src/safecode/shell/risk.py`：判断命令风险等级。
- `src/safecode/shell/runner.py`：受控执行命令。
- `src/safecode/cli.py`：新增 `run`、`config` 命令。

学习重点：

- `subprocess.run`
- `shlex.split`
- allowlist / denylist
- 退出码、stdout、stderr
- 命令审计和风险提示

## v0.3.x: Long-running State + Project Rules

目标：让 Agent 能跨多轮工作，不完全依赖聊天上下文。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.3.0` | `v0.3.0-sac-md-project-rules` | `SAC.md` 项目规则 | Agent 读取并遵守项目规则 |
| `v0.3.1` | `v0.3.1-progress-file` | `.sac/progress.md` | 能记录目标、已完成、下一步、阻塞点 |
| `v0.3.2` | `v0.3.2-hooks-after-apply` | `after_apply` hook | apply 后可运行格式化或测试 |
| `v0.3.3` | `v0.3.3-lightweight-memory` | 低风险项目事实记忆 | 能记住测试命令、启动命令、包管理器 |

核心文件方向：

- `src/safecode/project/rules.py`
- `src/safecode/state/progress.py`
- `src/safecode/hooks/runner.py`
- `src/safecode/memory/store.py`

学习重点：

- Markdown 文件作为状态协议。
- 用户规则和运行时策略的区别。
- Hook 的输入、输出、失败处理。
- 什么信息可以进入 memory，什么不能进入 memory。

## v0.4.x: Skills + Tool Registry

目标：把专业能力做成可组合资源，让 Agent 按需读取，不把所有说明都塞进 prompt。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.4.0` | `v0.4.0-skills-directory` | `skills/` 目录规范 | `sac skills list` 可列出技能 |
| `v0.4.1` | `v0.4.1-tool-registry` | 内部工具注册表 | 工具有名称、描述、风险等级、输入说明 |
| `v0.4.2` | `v0.4.2-skill-loading-demo` | 按需加载 skill | 指定任务时只加载相关 skill |
| `v0.4.3` | `v0.4.3-skill-scripts` | skill 附带脚本/模板 | skill 可以提供可复用脚本和模板 |

核心文件方向：

- `src/safecode/skills/loader.py`
- `src/safecode/tools/registry.py`
- `skills/python-cli/SKILL.md`
- `skills/fastapi/SKILL.md`

学习重点：

- 插件化目录结构。
- 元数据建模。
- prompt 上下文控制。
- 工具能力描述和风险等级。

## v0.5.x: Code Index

目标：当项目变大时，让 Agent 能先定位代码，再决定读哪些文件。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.5.0` | `v0.5.0-code-index-basic` | 文件和入口索引 | 能输出项目文件树和入口文件 |
| `v0.5.1` | `v0.5.1-symbol-search` | Python 符号索引 | 能查函数、类、方法所在文件和行号 |
| `v0.5.2` | `v0.5.2-context-selection` | 上下文选择器 | ask/edit 前优先选择相关文件 |
| `v0.5.3` | `v0.5.3-index-cache` | 索引缓存 | 重复运行不必全量扫描 |

核心文件方向：

- `src/safecode/index/files.py`
- `src/safecode/index/python_symbols.py`
- `src/safecode/context/selector.py`

学习重点：

- `ast` 标准库。
- 文件索引和缓存失效。
- 行号和源码引用。
- 为什么 v0.5 暂时不需要 RAG。

说明：

- v0.5 可以先用 Python `ast` 和全文搜索。
- embedding、向量数据库、RAG 是可选增强，不是默认架构。

## v0.6.x: MCP Integration

目标：建立 MCP 配置和发现的接口。注意：此阶段不做真实外部工具执行，真实 MCP 执行推迟到 `v1.6.x`，等 `v1.5.x` 的安全边界完成后再做。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.6.0` | `v0.6.0-mcp-config` | MCP server 配置 | 可读取启用的 MCP servers |
| `v0.6.1` | `v0.6.1-mcp-tool-discovery` | 工具发现 | 能列出外部工具，但不一次性塞进 prompt |
| `v0.6.2` | `v0.6.2-mcp-audit-permission` | MCP 权限和审计 | 外部写操作必须确认并写日志 |
| `v0.6.3` | `v0.6.3-mcp-demo-tool` | 只读 demo / placeholder | 明确 MCP 写操作默认拒绝 |

核心文件方向：

- `src/safecode/mcp/config.py`
- `src/safecode/mcp/discovery.py`
- `src/safecode/mcp/runner.py`
- `src/safecode/policy/external_tools.py`

学习重点：

- 工具发现和工具调用的区别。
- 外部读操作和写操作的权限区别。
- 工具 schema 不应全部塞进上下文。
- MCP 不等于 Agent，本项目的 runtime 仍然负责权限和审计。

## v0.7.x: Sandbox / Containment

目标：把安全从“提醒用户确认”升级成“运行时能力边界”。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.7.0` | `v0.7.0-sandbox-policy` | Sandbox 策略模型 | 能声明文件、网络、Shell 权限 |
| `v0.7.1` | `v0.7.1-filesystem-boundary` | 文件系统边界 | project root 外写入默认拒绝 |
| `v0.7.2` | `v0.7.2-network-policy` | 网络策略 | 网络默认关闭或 allowlist |
| `v0.7.3` | `v0.7.3-sandboxed-runner` | 隔离命令执行入口 | 命令在受控 workspace 内运行 |

核心文件方向：

- `src/safecode/sandbox/policy.py`
- `src/safecode/sandbox/filesystem.py`
- `src/safecode/sandbox/network.py`
- `src/safecode/sandbox/runner.py`

学习重点：

- containment 和 confirmation 的区别。
- project root 边界。
- 敏感路径过滤。
- macOS/Linux sandbox 能力差异。

## v0.8.x: Subagents

目标：建立 subagent 任务模型。注意：此阶段不做真正并发和真实子 agent 执行，真实并发 subagent 推迟到 `v1.6.x`。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.8.0` | `v0.8.0-subagent-task-model` | 子任务数据模型 | Lead Agent 能创建子任务 |
| `v0.8.1` | `v0.8.1-subagent-result-files` | 文件化结果回传 | 子任务结果写入 `.sac/subagents/` |
| `v0.8.2` | `v0.8.2-parallel-readonly-subagents` | 只读并行子任务 | 多个子任务可并行搜索/分析 |
| `v0.8.3` | `v0.8.3-subagent-merge-review` | 汇总与冲突检查 | Lead Agent 汇总结果后再生成单一 patch |

核心文件方向：

- `src/safecode/subagents/task.py`
- `src/safecode/subagents/runner.py`
- `src/safecode/subagents/results.py`

学习重点：

- 主 Agent 和子 Agent 的职责边界。
- 为什么子 Agent 默认只读。
- 文件化结果如何避免上下文丢失。
- 并行不等于并行写文件。

## v0.9.x: Observability + Evaluation

目标：让 SafeCode Agent 的行为可以被复盘、比较和回归测试。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v0.9.0` | `v0.9.0-trace-events` | Trace event 标准化 | 每次 ask/edit/apply/run 有 trace id |
| `v0.9.1` | `v0.9.1-evaluation-suite` | 回归评估样例 | 能用固定 demo 验证 patch 是否正确 |
| `v0.9.2` | `v0.9.2-reporting` | 本地报告 | 能生成一次任务的 markdown/html 报告 |
| `v0.9.3` | `v0.9.3-failure-taxonomy` | 失败分类 | 能区分 parse、validation、permission、test failure |

核心文件方向：

- `src/safecode/trace/events.py`
- `src/safecode/eval/cases.py`
- `src/safecode/eval/runner.py`
- `src/safecode/report/render.py`

学习重点：

- 可观测性不是只写日志。
- trace id 如何串起一次任务。
- 回归样例如何防止后续改坏。
- 失败分类如何提升可解释性。

## v1.0.x: Stable Local Agent Runtime

目标：把前面能力收口成一个稳定、可安装、可演示、可继续扩展的本地 Agent Runtime。

### v1.0.0: Stable Runtime Baseline

建议分支名：`v1.0.0-stable-local-runtime`

功能范围：

- CLI 命令稳定。
- Patch/apply/rollback/history/run/config/skills/index 基本可用。
- 权限策略默认安全。
- Audit、checkpoint、trace 结构稳定。
- Demo 项目可重复跑通。

验收标准：

- 新 clone 后按照 README 可以安装并运行。
- `uv run sac ask/edit/apply/rollback/history/run` 可用。
- v0.1 到 v0.9 的核心测试通过。
- 默认不会静默修改 project root 外文件。
- 有清晰的“哪些能力已实现，哪些还没实现”说明。

### v1.0.1: Packaging and Install Polish

建议分支名：`v1.0.1-install-packaging`

功能范围：

- 完善 `pyproject.toml` metadata。
- 明确 Python 版本支持。
- 增加安装说明。
- 增加 `sac doctor` 检查本地环境。

验收标准：

- `uv tool install .` 或等价安装路径文档清楚。
- `sac doctor` 能检查 Python、uv、项目根目录、配置文件。

### v1.0.2: Documentation and Tutorial Projects

建议分支名：`v1.0.2-docs-tutorials`

功能范围：

- 写一套从零学习 SafeCode Agent 的教程。
- 保留 FastAPI demo。
- 增加 Python CLI demo。
- 增加“代码入口怎么读”的文档。

验收标准：

- 新手能按文档理解 CLI 到 Orchestrator 的调用链。
- 每个 demo 都有固定命令和预期输出。

### v1.0.3: Reliability Hardening

建议分支名：`v1.0.3-hardening`

功能范围：

- 补充异常处理。
- 补充边界测试。
- 检查 pending patch 损坏、checkpoint 缺失、权限失败等场景。
- 明确错误提示风格。

验收标准：

- 常见失败不会留下半写入状态。
- 用户能从错误提示知道下一步怎么做。

### v1.0.4: Security Baseline and Policy Presets

建议分支名：`v1.0.4-security-presets`

功能范围：

- 提供 `strict`、`normal`、`learning` 策略预设。
- 整理敏感路径默认列表。
- 整理高风险命令默认列表。
- 明确 MCP、Shell、文件写入的默认权限。

验收标准：

- 默认策略适合普通个人项目。
- `strict` 策略适合重要仓库。
- 文档明确说明每个策略允许什么、拒绝什么。

### v1.0.5: Release Demo and Portfolio Package

建议分支名：`v1.0.5-release-demo`

功能范围：

- 准备最终演示脚本。
- 写项目亮点说明。
- 写简历/作品集描述。
- 录制或整理一套可复现 demo 流程。

验收标准：

- 能用 5 到 10 分钟演示 SafeCode Agent 的核心价值。
- 文档能说明它为什么不是简单聊天机器人，而是轻量 Agent Runtime。

## v1.1.x: Product Extension Layer

目标：在不破坏 v1.0 稳定 runtime 的前提下，补齐产品扩展入口。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v1.1.0` | `v1.1.0-local-api-facade` | 本地 Python API facade | 其他程序可调用 `SafeCodeLocalAPI` |
| `v1.1.1` | `v1.1.1-export-reports` | 报告导出 | `sac export report` 可写 Markdown 文件 |
| `v1.1.2` | `v1.1.2-local-task-queue` | 本地任务队列 | `sac queue add/list/complete-next` 可用 |
| `v1.1.3` | `v1.1.3-ide-manifest` | IDE metadata | `sac ide manifest --write` 可生成 manifest |
| `v1.1.4` | `v1.1.4-release-checklist` | 发布检查清单 | `sac release checklist v1.1.4` 可输出 checklist |
| `v1.1.5` | `v1.1.5-extension-polish` | 扩展层收口 | 文档、命令、测试完成一轮整理 |

v1.1.x 不改变核心安全模型，只提供外部集成和产品化辅助。

## v1.2.x: Production Hardening

目标：把学习型 runtime 推近生产可用边界，优先补安全、部署和生产测试。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v1.2.0` | `v1.2.0-security-hardening` | 去掉默认 `shell=True`，高风险命令即使 `--yes` 也拒绝 | 高风险命令不执行 |
| `v1.2.1` | `v1.2.1-trusted-policy` | 区分 user-level 和 project-level config | 项目配置不能降低用户策略 |
| `v1.2.2` | `v1.2.2-sandbox-enforcement` | patch、shell、MCP 接入统一边界 | 路径逃逸和 MCP 写操作被拒绝 |
| `v1.2.3` | `v1.2.3-real-llm-provider` | OpenAI-compatible provider | 真实 LLM 输出仍走 parser/validator |
| `v1.2.4` | `v1.2.4-deploy-package` | README、Dockerfile、CI、安装说明 | `uv tool install .` 和 Docker 路径清楚 |
| `v1.2.5` | `v1.2.5-prod-eval-suite` | 生产安全回归测试 | dangerous shell、path escape、hook injection、checkpoint missing、MCP write 均有测试 |

## v1.3.x: Runtime Trust Refinement

目标：继续收紧 runtime 里容易被忽略的信任边界，让产品更接近安全可用。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v1.3.0` | `v1.3.0-context-secret-hardening` | 上下文收集跳过 secret-like 文件 | `.env.local`、`*token*` 不进入 context |
| `v1.3.1` | `v1.3.1-hook-policy-hardening` | hooks 默认不自动批准中风险命令 | project hook 不能静默跑 `python -c` |
| `v1.3.2` | `v1.3.2-llm-network-policy` | 真实 LLM 受网络策略控制 | project config 不能强行启用真实 LLM |
| `v1.3.3` | `v1.3.3-trace-audit-integration` | audit event 关联 trace id | ask/edit/apply/rollback 可追踪 |
| `v1.3.4` | `v1.3.4-docs-trust-boundaries` | 文档说明信任边界 | README 和版本矩阵更新 |

## v1.4.x: Runtime Operations

目标：让出错后的定位和修复更容易，补齐面向真实使用的运行日志。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v1.4.0` | `v1.4.0-runtime-logging` | 结构化 runtime log 和 `sac logs show` | CLI 失败会写 `.sac/logs/runtime.jsonl` |

## v1.5.x: Core Security Boundary

目标：按照生产安全审查结果，优先整改核心安全边界。这个阶段不扩 MCP 真执行、不扩 subagent 并发，避免在基础安全没稳时扩大风险面。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v1.5.0` | `v1.5.0-context-containment` | context symlink 拒绝、内容 redaction、文件大小和总上下文上限 | symlink 指向 project root 外或 secret 内容不会进入 LLM context |
| `v1.5.1` | `v1.5.1-transactional-apply` | temp write + atomic replace；apply 失败自动 rollback | 多文件 apply 中途失败不会留下半写入状态 |
| `v1.5.2` | `v1.5.2-command-policy-engine` | shell/hooks 统一 command policy；allowlist；arg-level 风险判断 | `git reset --hard`、`python -c`、`pip install` 等按策略阻止或审批 |
| `v1.5.3` | `v1.5.3-hook-approval-audit` | hook proposal / approval / result 全进 audit；hook 默认不静默执行 | hook 执行前有审批状态，结果可审计 |
| `v1.5.4` | `v1.5.4-audit-integrity` | audit hash chain 和 `sac audit verify` | 篡改 JSONL 后 verify 能发现 |
| `v1.5.5` | `v1.5.5-command-policy-hardening` | 阻止 `git -c alias.*=!`、`git -C`、`--work-tree`、`git clean`、`python -m`、`node -e`、`npm run`、`uv run/tool` 等绕过 | allowlisted command 不能通过危险参数逃出安全边界 |
| `v1.5.6` | `v1.5.6-hook-approval-state` | hook 审批写入 `.sac/approvals/hooks.jsonl`，运行时按命令 hash 匹配 | apply 审批不再隐式代表 hook 审批 |
| `v1.5.7` | `v1.5.7-audit-anchoring` | audit hash chain 增加用户级 external anchor | 整份项目日志被重写后 `sac audit verify` 能发现 anchor mismatch |
| `v1.5.8` | `v1.5.8-context-redaction-hardening` | 剪掉 symlinked directory，扩展 JSON/Bearer/AWS key redaction，file list 进入总预算 | context 更难泄漏敏感内容和敏感路径 |
| `v1.5.9` | `v1.5.9-apply-metadata-preimage` | apply 保留文件 mode、拒绝 non-UTF-8 text patch、写前重查 preimage、记录 rollback failure | 降低 TOCTOU、权限丢失和二进制误改风险 |
| `v1.5.10` | `v1.5.10-review-followup-docs` | 把生产安全 review 后的整改项写回路线图和矩阵 | 后续进入 v1.6 前有清晰的安全完成线 |
| `v1.5.11` | `v1.5.11-hook-approval-trust` | hook approval 移到用户级，绑定 user/config/expiry，并要求 `allow_medium_after_apply=true` | 项目不能通过预置 `.sac` approval 自动运行 hook |
| `v1.5.12` | `v1.5.12-command-policy-bypass-fixes` | 补 `core.pager`、`core.editor`、`pager.*`、`diff.*.command`、`node --eval`、`python -`、`npx/pip3/pipx/uv pip` 等绕过 | allowlisted command 的参数绕过面继续收窄 |
| `v1.5.13` | `v1.5.13-audit-context-hardening` | anchor 缺失失败、anchor 权限收紧、context 移除绝对 project root、路径片段按敏感规则过滤 | 减少 audit 降级和 context 路径泄漏 |
| `v1.5.14` | `v1.5.14-security-review-docs` | 把第二轮生产安全 review 后的整改写回文档 | v1.6 前安全门槛保持可追踪 |

暂缓到后续：

- MCP 真实工具执行。
- subagent 并发执行。
- OS-level sandbox。

## v1.6.x: Controlled Tooling and Subagents

目标：在 `v1.5.x` 核心安全边界完成后，再扩展真实 MCP 和 subagent 能力。

| 版本 | 建议分支名 | 功能 | 验收 |
|---|---|---|---|
| `v1.6.0` | `v1.6.0-mcp-runner-readonly` | 真实 MCP client runner，只允许只读工具 | MCP read-only 调用有 audit 和 runtime log |
| `v1.6.1` | `v1.6.1-mcp-write-approval` | MCP 写操作审批和权限策略 | 外部写操作必须 proposal + approval + audit |
| `v1.6.2` | `v1.6.2-subagent-readonly-runner` | 只读 subagent runner，独立上下文和结果文件 | 子任务只能读，结果写 `.sac/subagents/` |
| `v1.6.3` | `v1.6.3-subagent-merge-review` | Lead agent 汇总结果后生成单一 patch | 子任务不直接写业务文件 |
| `v1.6.4` | `v1.6.4-os-sandbox-research` | macOS/Linux sandbox 调研和可选 adapter | 文档说明不同系统上的 sandbox 能力和限制 |
| `v1.6.5` | `v1.6.5-tooling-security-evals` | MCP/subagent 安全回归测试 | 工具调用、权限拒绝、冲突场景有测试 |

## v1.7 之后暂不展开

`v1.1+` 可以考虑：

- TUI。
- IDE 插件。
- 云端任务队列。
- 团队协作。
- 更完整的多 Agent 调度。

但在 `v1.1.x` 之前，这些都不是主线。当前路线要优先保证本地 runtime 的安全、稳定、可解释和可教学。
