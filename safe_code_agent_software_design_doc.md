# SafeCode Agent 软件设计文档

## 1. 项目定位

### 1.1 项目名称

**SafeCode Agent**

SafeCode Agent 是一个用 Python 实现的安全型终端 Coding Agent。它面向个人开发者和学习型项目，短期目标是让 AI 能够读取项目、理解上下文、生成代码修改建议、展示 Diff、经过人工确认后应用修改，并支持 Checkpoint、Rollback、Audit Log、权限控制和后续扩展。

长期目标上，本项目不是“聊天机器人 + 工具调用”，而是一个简化版 Agent Harness / Runtime：模型负责推理和生成提案，运行时负责上下文、工具、文件系统、权限边界、状态、日志、回滚和扩展能力。

本项目不是完整复刻 Claude Code，也不是追求大而全的 Agent 平台。它的目标是做成一个个人可维护、可以演示、可以写进简历、并且能真实辅助本地开发的 Python 终端工具，并逐步演进成一个轻量的本地 Agent 运行时。

### 1.2 一句话描述

SafeCode Agent 是一个安全优先的终端 AI 编程助手和轻量 Agent Harness：LLM 不能直接写文件，只能生成 Patch Proposal；所有写入都经过 Diff Review、人工确认、Checkpoint 和 Audit Log。

### 1.3 核心价值

1. **安全修改代码**：模型只能提出 Patch，不能绕过用户直接写文件。
2. **可解释可审计**：每次读取、修改、命令建议和用户确认都可追踪。
3. **可回滚**：修改前自动保存 Checkpoint，支持恢复。
4. **适合个人维护**：第一版不引入过重框架，优先做稳定闭环。
5. **可持续扩展**：后续可以加入 Shell 权限、Hooks、Memory、代码索引、MCP、Subagents、TUI / IDE 插件。

### 1.4 最终产品标准

SafeCode Agent 的最终产品形态应该对齐现代 Agent Runtime 的核心能力，但按版本逐步实现：

| 方向 | 最终标准 | 当前落点 |
|---|---|---|
| Agent Harness | 模型外部有清晰运行时，负责上下文、工具、权限、状态、日志 | v0.1 的 CLI + Orchestrator + Patch/Checkpoint/Audit |
| 可操作计算机环境 | 能安全读写项目文件、运行受控命令、验证结果 | v0.1 文件 Patch，v0.2 Shell |
| 长任务状态 | 能跨多轮保留 pending task、progress、checkpoint、history | v0.1 `.sac/`，v0.3 progress / memory |
| 工具生态 | 工具可发现、可注册、可按需调用，而不是全部塞进 prompt | v0.4 Skills / Tool Registry，v0.5 MCP |
| 安全 containment | 默认限制能力边界，而不是只靠每次弹窗确认 | v0.1 路径限制和人工确认，v0.2+ sandbox / policy |
| 可审计性 | 每次读取、提案、应用、回滚、命令执行都有结构化记录 | v0.1 JSONL Audit Log |
| 可回滚性 | 写入前有 checkpoint，失败后能恢复 | v0.1 checkpoint / rollback |
| 可观测与评估 | 行为可追踪、可复盘、可回归测试 | v0.9 Trace / Evaluation |
| 稳定发布 | 可安装、可教学、可演示、默认安全 | v1.0.x Stable Local Runtime |

产品验收不以“模型能不能聊天”为核心，而以“能否安全、可解释、可回滚地操作本地项目”为核心。

---

## 2. 设计原则

### 2.1 安全优先

Agent 不应该默认拥有无限制的文件写入和 Shell 执行能力。

规则：

- LLM 不能直接写文件，只能生成结构化 Patch Proposal。
- 所有代码修改必须先展示 Diff。
- 所有文件写入必须经过用户确认。
- 修改前必须创建 Checkpoint。
- 修改后必须写入 Audit Log。
- 读取敏感文件时默认阻止或强确认。
- Shell 命令执行能力不放进 v0.1，避免第一版安全面过大。

### 2.2 人类保持最终决策权

Agent 可以建议、计划、读取上下文、生成 Patch，但最终执行权属于用户。

典型流程：

```text
User Request
→ Context Collection
→ LLM Patch Proposal
→ Patch Parse
→ Diff Preview
→ Human Approval
→ Checkpoint
→ Apply Patch
→ Audit Log
→ Optional Rollback
```

### 2.3 先做闭环，再做复杂能力

第一阶段不追求完整 Agent Loop，而是先完成一个真实可用的代码修改闭环：

```text
sac edit
→ generate patch
→ preview diff
→ sac apply
→ checkpoint
→ write file
→ sac rollback
```

这个闭环跑通后，再逐步加入 Shell、Hooks、Memory、Index、Subagents。

### 2.4 Harness 优先，而不是聊天优先

SafeCode Agent 的设计重点不是让模型自由聊天，而是让模型在一个受控运行时里工作。

运行时需要负责：

- 上下文收集：只读取必要项目文件，默认跳过敏感文件。
- 状态管理：pending patch、checkpoint、history、progress。
- 权限控制：写文件、Shell、网络、工具调用必须有边界。
- 工具调度：未来工具通过 registry / skills / MCP 接入。
- 结果验证：修改后可以运行测试、检查 diff、记录日志。

模型只负责推理、生成回答和生成结构化提案；实际动作由 Harness 校验和执行。

### 2.5 Containment 优先，而不是只靠确认弹窗

用户确认很重要，但不能把安全全部建立在用户每次点确认上。后续版本要逐步加入 containment：

- 文件系统限制在 project root。
- 默认拒绝 `.env`、`.ssh`、私钥、token 等敏感路径。
- Shell 命令按风险等级分类。
- 高风险命令默认阻止或强确认。
- 网络访问、外部工具、MCP 需要单独策略。
- 长任务必须有 progress 和 audit trail，不能只依赖上下文记忆。

---

## 3. 版本路线图

### 3.1 v0.1：安全 Patch 修改闭环

v0.1 是项目最重要的版本。目标不是让 Agent 什么都能做，而是让它在一个本地项目里完成安全、可审计、可回滚的代码修改。

#### 目标

1. 创建可运行的 Python CLI 项目。
2. 支持只读问答 `sac ask`。
3. 支持生成 Patch Proposal 的 `sac edit`。
4. 支持 Diff Preview。
5. 支持人工确认后应用 Patch 的 `sac apply`。
6. 支持修改前 Checkpoint。
7. 支持最近一次修改回滚 `sac rollback --last`。
8. 支持 JSONL Audit Log。
9. 使用 MockLLMClient 跑通完整流程，真实 LLM 作为可选项。

#### v0.1 实施拆分

为了避免第一版范围过大，v0.1 在实现时继续拆成多个小版本：

| 子版本 | 目标 | 验收重点 |
|---|---|---|
| `v0.1.0` | CLI 骨架 + `sac ask` + audit log | 能运行 `sac --help` 和 `sac ask` |
| `v0.1.1` | Patch 数据模型 + Parser | 能解析 `Update File` Patch |
| `v0.1.2` | `sac edit` + Diff Preview + pending patch | 只生成 `.sac/pending_patch.json`，不写文件 |
| `v0.1.3` | `sac apply` + Checkpoint | apply 前创建 checkpoint，用户确认后写文件 |
| `v0.1.4` | `sac rollback --last` + `sac history` | 能恢复最近一次修改并展示日志 |
| `v0.1.5` | FastAPI Demo | 完整演示 ask/edit/apply/history/rollback |

每个子版本都应该能独立验收，避免一次性实现过多模块。

#### v0.1 命令范围

```bash
sac ask "这个项目是什么结构？"
sac edit "给 FastAPI 项目添加 /health 接口"
sac apply
sac rollback --last
sac history
```

#### v0.1 不做

- 不做自动 Shell 执行。
- 不做 Hooks。
- 不做长期 Memory。
- 不做向量索引。
- 不做 RAG、embedding、向量数据库或代码语义索引。
- 不做 MCP。
- 不做 Subagents。
- 不做 TUI / IDE 插件。

原因：这些能力都很有价值，但会显著扩大安全边界和实现复杂度。v0.1 应该先把“安全改代码”这件事做到稳定。

### 3.2 v0.2：Shell 权限与项目配置

v0.2 在 v0.1 的安全文件修改基础上，加入受控 Shell 命令能力和项目级配置。

#### 目标

1. 支持 `sac run "运行测试"`。
2. 引入 Shell Risk Classifier。
3. 支持 allow once / deny。
4. 支持项目级配置 `.sac/config.yaml`。
5. 支持低风险命令自动执行，中高风险命令确认。
6. 支持命令历史记录。

#### v0.2 命令范围

```bash
sac run "运行测试"
sac run "查看 git 状态"
sac config show
sac config init
```

#### v0.2 重点

- 使用规则引擎识别危险命令。
- 使用 `shlex` 做基础命令解析。
- 识别管道、重定向、`&&`、`;`、`$()` 等高风险 shell 结构。
- 默认阻止读取 secret、私钥、`.env`、系统敏感路径。

### 3.3 v0.3：Hooks、Memory 与长任务状态

v0.3 加入可扩展自动化能力和长期状态，让项目更接近真实 Coding Agent Harness。

#### 目标

1. 支持 `before_apply` / `after_apply` Hooks。
2. 支持 `before_shell` / `after_shell` Hooks。
3. 支持项目级 Memory。
4. 支持 `SAC.md` 项目规则文件。
5. 支持自动记忆低风险项目事实，例如测试命令、启动命令、包管理器。
6. 支持 `.sac/progress.md` 或 `.sac/progress.json`，记录长任务当前目标、已完成事项、下一步和阻塞点。
7. 支持 apply 后建议 git commit message，但默认不自动提交。

#### 示例

```yaml
hooks:
  after_apply:
    - "ruff format ."
    - "pytest -q"
```

### 3.4 v0.4：Skills 与 Tool Registry

v0.4 开始把工具和专业能力做成可发现、可组合的资源，而不是把所有工具说明塞进 prompt。

#### 目标

1. 支持 `skills/` 目录。
2. 每个 skill 包含 `SKILL.md`、可选脚本、模板和示例。
3. 支持 `sac skills list` / `sac skills show`。
4. 支持 Tool Registry，把内部能力注册成可发现工具。
5. 工具说明按需加载，不一次性塞入模型上下文。

### 3.5 v0.5：代码索引与检索增强

v0.5 再考虑大项目上下文不足的问题。注意，这不是 v0.1 的需求。

#### 目标

1. 支持代码结构索引。
2. 可选 Tree-sitter 解析函数、类、入口文件。
3. 可选轻量全文索引。
4. 只有在项目规模变大、上下文不足时才加入 embedding / vector search。
5. 检索结果必须保留来源文件和行号，方便审查。

### 3.6 v0.6：MCP 与外部工具生态

v0.6 接入 MCP 或类似协议，把 GitHub、Notion、浏览器、文档等外部工具纳入统一工具层。

#### 目标

1. 支持 MCP server 配置。
2. 工具按需发现和调用。
3. 外部工具调用写入 audit log。
4. 对外部写操作使用独立权限策略。
5. 不把所有 MCP tool schema 一次性塞进 prompt。

### 3.7 v0.7：Sandbox 与受控执行环境

v0.7 强化 containment，让 Agent 能在更安全的边界内运行命令和工具。

#### 目标

1. 支持 workspace sandbox。
2. 限制 project root 外文件读写。
3. 网络访问默认关闭或按 allowlist 控制。
4. Shell 命令在隔离环境中执行。
5. 高风险命令强确认或默认阻止。

### 3.8 v0.8：Subagents 与长期任务协作

v0.8 再探索多 Agent 和长期自治任务。

#### 目标

1. Lead Agent 负责规划和汇总。
2. Subagent 负责独立子任务，例如代码搜索、测试修复、文档整理。
3. 子任务通过文件化 progress / result 回传。
4. 每个子 agent 有独立上下文和权限边界。
5. 默认不并行写同一文件，避免冲突。

### 3.9 v0.9：Observability 与 Evaluation

v0.9 的目标不是继续增加 Agent 权限，而是让前面已有能力变得可复盘、可比较、可回归测试。

#### 目标

1. 为每次 ask/edit/apply/run 分配 trace id。
2. 将 audit event 和 trace event 关联起来。
3. 建立固定 demo case，用于回归测试。
4. 对失败进行分类，例如 parse、validation、permission、test failure。
5. 支持生成一次任务的本地报告，方便学习和复盘。

#### v0.9 实施拆分

| 子版本 | 目标 | 验收重点 |
|---|---|---|
| `v0.9.0` | Trace event 标准化 | 每次任务都有 trace id |
| `v0.9.1` | Evaluation suite | 固定 demo 可以重复跑 |
| `v0.9.2` | 本地报告 | 能生成 markdown/html 任务报告 |
| `v0.9.3` | 失败分类 | 错误能归类并给出下一步建议 |

### 3.10 v1.0.x：Stable Local Agent Runtime

v1.0.x 的目标是把 SafeCode Agent 从学习型项目收口为一个稳定、可安装、可演示、可继续扩展的本地 Agent Runtime。

#### v1.0.0 Stable Runtime Baseline

目标：

1. CLI 命令稳定。
2. Patch/apply/rollback/history/run/config/skills/index 基本可用。
3. 权限策略默认安全。
4. Audit、checkpoint、trace 结构稳定。
5. Demo 项目可重复跑通。

验收重点：

- 新 clone 后可以按 README 安装和运行。
- 核心命令能稳定工作。
- 默认不会静默修改 project root 外文件。
- 文档明确说明哪些能力已实现，哪些只是规划。

#### v1.0.1 Packaging and Install Polish

目标：

1. 完善 `pyproject.toml` metadata。
2. 明确 Python 版本支持。
3. 增加安装说明。
4. 增加 `sac doctor` 环境检查。

#### v1.0.2 Documentation and Tutorial Projects

目标：

1. 写从零学习 SafeCode Agent 的教程。
2. 保留 FastAPI demo。
3. 增加 Python CLI demo。
4. 增加“代码入口怎么读”的文档。

#### v1.0.3 Reliability Hardening

目标：

1. 补充异常处理。
2. 补充边界测试。
3. 覆盖 pending patch 损坏、checkpoint 缺失、权限失败等场景。
4. 统一错误提示风格。

#### v1.0.4 Security Baseline and Policy Presets

目标：

1. 提供 `strict`、`normal`、`learning` 策略预设。
2. 整理敏感路径默认列表。
3. 整理高风险命令默认列表。
4. 明确 MCP、Shell、文件写入的默认权限。

#### v1.0.5 Release Demo and Portfolio Package

目标：

1. 准备最终演示脚本。
2. 写项目亮点说明。
3. 写简历/作品集描述。
4. 整理一套可复现 demo 流程。

### 3.11 v1.5：核心安全边界整改

经过生产级安全审查后，v1.5 被调整为当前最高优先级。这个阶段不继续扩展 MCP 真执行和 subagent 并发，而是先修核心安全边界。

#### 目标

1. context 收集拒绝 symlink escape，并对 secret-like 内容做 redaction。
2. patch apply 改成事务式流程，失败时不能留下半写入状态。
3. shell 和 hooks 统一走 command policy engine。
4. hooks 必须有 proposal / approval / result 审计链。
5. audit log 增加 hash chain 和 verify 能力，能发现日志被篡改。

#### v1.5 实施拆分

| 子版本 | 目标 | 验收重点 |
|---|---|---|
| `v1.5.0` | Context containment | symlink escape 和 secret 内容不会进入 LLM context |
| `v1.5.1` | Transactional apply | apply 失败自动 rollback，无半写入 |
| `v1.5.2` | Command policy engine | `git reset --hard`、`python -c`、`pip install` 等能被精细分类 |
| `v1.5.3` | Hook approval audit | hook 执行前后都有审批和审计 |
| `v1.5.4` | Audit integrity | `sac audit verify` 能发现日志篡改 |
| `v1.5.5` | Command policy hardening | 阻止 `git -c alias.*=!`、`git -C`、`--work-tree`、`git clean`、`python -m`、`node -e`、`npm run`、`uv run/tool` 等绕过 |
| `v1.5.6` | Hook approval state | hook 审批必须持久化到 `.sac/approvals/hooks.jsonl`，apply 审批不再隐式批准 hook |
| `v1.5.7` | Audit anchoring | hash chain 增加用户级 anchor，降低整份日志重写后无法发现的问题 |
| `v1.5.8` | Context redaction hardening | symlinked directory、JSON/Bearer/AWS key、file list budget 等边界补齐 |
| `v1.5.9` | Apply metadata and preimage | apply 保留文件 mode，拒绝 non-UTF-8，写入前重查 preimage |
| `v1.5.10` | Review follow-up docs | 将生产安全 review 后的整改范围写回路线图 |
| `v1.5.11` | Hook approval trust | hook approval 移到用户级目录，绑定 user/config/expiry，并且必须启用 `allow_medium_after_apply` |
| `v1.5.12` | Command policy bypass fixes | 补 git pager/editor/diff command、`node --eval`、`python -`、`npx/pip3/pipx/uv pip` 等绕过 |
| `v1.5.13` | Audit and context hardening | anchor 缺失失败、anchor 权限收紧、context 不暴露绝对 project root 和敏感路径片段 |
| `v1.5.14` | Security review docs | 第二轮生产安全 review 后的整改写回路线图 |
| `v1.5.15` | Command policy final bypass fixes | git include.* 旁路、git clean 无条件阻止、Git 环境变量注入清理 |
| `v1.5.16` | Approval parsing hardening | 审批 JSON/expiry 容错，审批绑定 policy 版本 |
| `v1.5.17` | Audit anchor trust boundary | anchor 目录禁止落在 project root（签名/密钥留作后续） |
| `v1.5.18` | Context redaction extension | GitHub/JWT/Bearer/base64 token redaction 扩展 |
| `v1.5.19` | Patch apply symlink race guard | apply 前重验边界与 inode，拒绝 symlink swap（xattr/ownership 仍是已知限制） |
| `v1.5.20` | Security review docs | 补 v1.5.15-1.5.19 文档，明确 v1.6 guardrails |
| `v1.5.21` | Git policy env hardening | git config/ENV 旁路收敛，补 git 远程/状态子命令 |
| `v1.5.22` | Shell network policy | shell 执行前强制 network policy |
| `v1.5.23` | Approval store trust boundary | approval dir 禁止落在 project root |
| `v1.5.24` | Security docs before v1.6 | 补 v1.5.21-1.5.23 文档 + guardrails 更新 |

#### 生产安全 review 后的结论

在 `v1.5.0` 到 `v1.5.4` 后，项目已经有了基本安全边界，但还不应该进入真实 MCP 执行和 subagent 并发。原因是 command policy 仍存在 allowlisted command 参数绕过，hook 审批缺少持久状态，audit hash chain 缺少用户级信任锚点。

因此 `v1.5.5` 到 `v1.5.9` 被追加为进入 `v1.6` 前的必修整改线。

第二轮 review 后继续追加 `v1.5.11` 到 `v1.5.13`。核心结论是：审批不能由项目目录自证，allowlisted command 的危险配置项也必须按参数级别阻止，audit anchor 丢失不能静默降级为成功。

最新一轮安全检查继续追加 `v1.5.15` 到 `v1.5.23`，覆盖 git config/env 旁路、shell network policy、approval store 信任边界，以及 apply 的 symlink/identity race 防护。只有 `v1.5.21` 到 `v1.5.23` 的测试全部通过后，才允许开始 v1.6 的 MCP 真执行与 subagent 扩展。

### 3.12 v1.6：受控 MCP 与 Subagents

v1.6 只有在 v1.5 的核心安全边界完成后才开始。原因是 MCP 真执行和 subagent 并发会显著扩大权限面，如果提前做，会放大安全风险。

#### 目标

1. 实现只读 MCP runner，并记录 audit/runtime log。
2. MCP 写操作必须走 proposal / approval / audit。
3. subagent runner 默认只读，独立上下文和结果文件。
4. Lead agent 汇总结果后生成单一 patch，子 agent 不直接写业务文件。
5. 调研并接入可选 OS-level sandbox adapter。

#### v1.6.0 read-only MCP runner

`v1.6.0` 首先只允许只读 MCP 调用。MCP server command 必须通过 command policy，调用前必须通过 network policy，调用结果会做 redaction 和大小限制，并写入 audit/runtime log。写工具名会被分类为 write 并直接阻止，MCP 写操作继续推迟到 `v1.6.1+` 的 proposal / approval 流程。

#### v1.6.1 MCP write proposal only

`v1.6.1` 实现了 MCP 写操作 proposal 机制，但**不执行**实际的 MCP 写操作：

- 当 MCP 工具被分类为 write-capable 时，创建 pending proposal 而不是执行。
- Proposal 存储在 `.sac/pending_mcp_call.json`，包含 proposal id、server name、tool name、classification、input hash、created_at、status、risk level 和 reason。
- 输入 payload 在写入磁盘前经过 size-limit 和 redaction 处理，不会包含原始 secret 值。
- 如果已存在 pending proposal，后续 proposal 会被拒绝（fail-closed）。
- Unknown 工具默认被阻止，read-only 工具会提示用户使用现有的 `call-readonly` 路径。
- 提供三个新 CLI 命令：`sac mcp propose-write`、`sac mcp pending`、`sac mcp discard`。
- 新增 audit 事件：`mcp_write_proposed`、`mcp_write_blocked`、`mcp_write_discarded`。

**已知限制**：v1.6.1 只创建 proposal，不执行 MCP 写操作。审批和执行机制留待后续版本。MCP 写操作默认保持禁用。

#### v1.6.2 read-only subagent runner

`v1.6.2` 实现了只读 subagent runner，subagent 只能读取 bounded/redacted 项目上下文并写入结果文件：

- Subagent 任务包含 id、title、instructions、readonly（默认 true）、status、timestamps、result_path 和 error 字段。
- `ReadonlySubagentRunner` 收集 context（使用现有 `ContextCollector`），生成 Markdown 结果文件写入 `.sac/subagents/<task_id>/result.md`。
- 结果文件包含任务标题、指令、上下文摘要和明确声明"未修改任何业务文件"。
- 非 read-only 任务被直接阻止。
- 如果结果文件已存在，拒绝重新运行（fail-closed）。
- 结果内容经过 redaction，不包含原始 secret 值。
- 提供三个 CLI 命令：`sac subagent run-readonly`、`sac subagent list`、`sac subagent show`。
- 新增 audit 事件：`subagent_created`、`subagent_started`、`subagent_completed`、`subagent_blocked`。

**已知限制**：v1.6.2 subagent 不修改业务文件、不执行 shell、不执行 MCP 写操作。subagent merge/review 和并发执行留待 v1.6.3+。

#### v1.6.3 subagent merge review

`v1.6.3` 实现了将多个已完成的只读 subagent 结果合并为单个 pending patch proposal：

- `SubagentMergeReviewer` 读取已完成的 readonly subagent 结果文件，生成针对目标 markdown 文件的 SEARCH/REPLACE patch。
- 目标文件必须存在且包含 `<!-- SAFECODE:SUBAGENT_REVIEW -->` marker，该 marker 会被替换为 marker + 合并后的 review 内容。
- Patch 经过 `PatchValidator` 验证、生成 unified diff preview，保存为 `.sac/pending_patch.json`（如果已存在则 fail-closed）。
- 用户仍需运行 `sac apply` 来确认和应用合并结果。
- 只允许已完成的 readonly 任务参与合并；结果文件必须在 `.sac/subagents/` 内；内容经过 redaction。
- CLI：`sac subagent merge-review TASK_ID... --target SUBAGENT_REVIEW.md`。
- Audit：`subagent_merge_proposed`、`subagent_merge_blocked`。

**已知限制**：v1.6.3 不调用真实 LLM 进行自主合并，不做并发编排，生成的 patch 是确定性的文档级合并。subagent 仍然不修改业务文件。

#### v1.6.4 OS sandbox research

`v1.6.4` 实现了 OS-level sandbox 的调研与计划层，为未来 v1.7+ 的强隔离打下基础：

- `SandboxCapabilityDetector` 检测四种 backend：`none`（逻辑边界）、`macos_seatbelt`（macOS sandbox-exec）、`linux_bubblewrap`（Linux bwrap）、`docker`（跨平台容器）。
- 检测仅使用 `platform.system()` 和 `shutil.which()`，不启动任何进程、容器或沙盒。
- `SandboxPlanner` 根据可用性推荐最佳 backend：Linux bubblewrap > macOS seatbelt > Docker > none。
- 每个 backend 都附带详细的 limitations 和 recommended_for 说明。
- CLI：`sac sandbox status` 以 Rich Table 展示所有 backend 的可用性、推荐 backend、限制说明和当前活跃的逻辑边界。
- Audit：写入 `sandbox_status_checked` 事件，包含 platform、recommended_backend 和 available_backends。

**关键声明**：v1.6.4 不自动启用 OS sandbox。所有 shell、MCP 和 hook 执行仍然经过 CommandPolicy、NetworkPolicy 和 FilesystemBoundary。真正的 OS 级强制沙盒化留待 v1.7+。

#### v1.6.5 tooling security evals

`v1.6.5` 新增系统化工具安全评测套件，不增加任何新的高风险执行能力：

- 新增 `tests/test_tooling_security_evals.py`，包含 37 项安全评测测试。
- 按类别组织：MCP 网络边界、MCP proposal 安全、Subagent 隔离、Merge-review 安全、Sandbox 规划回归、跨模块安全边界（network policy、secret redaction、approval paths、config 安全、command policy）。
- 每个测试带有 v1.6.x 版本标签，明确验证的安全边界。
- 跨模块验证确保 shell/MCP/hooks 共享同一 CommandPolicy 约束，network disabled 不会被绕过，user config 不可被 project config 降级，secret redaction 在 context/MCP proposal/subagent merge 中行为一致。
- 不引入新的运行时代码或 CLI 命令。

**关键声明**：v1.6.5 是纯测试版本，不修改任何业务逻辑。v1.6.x 系列现已有 199 项通过测试，覆盖从 v1.5.x 核心安全边界到 v1.6.x 受控工具生态的完整回归。

### 3.13 v1.7：OS-Level Sandbox Containment

v1.7 在 v1.6.x 的逻辑边界和调研基础上，建立统一的 OS-level sandbox adapter 抽象，为 shell/MCP/hooks 未来统一通过同一接口生成 sandbox execution plan 做准备。

#### v1.7.0 sandbox adapter contract

`v1.7.0` 建立了 sandbox adapter 抽象层，所有 adapter 只生成 dry-run plan，不执行外部进程：

- `SandboxExecutionRequest` / `SandboxExecutionPlan` 数据模型定义统一的输入输出接口。
- `SandboxAdapter` Protocol + 四个具体实现：`NoopSandboxAdapter`、`MacOSSeatbeltAdapter`、`LinuxBubblewrapAdapter`、`DockerSandboxAdapter`。
- 所有 adapter 的 `supports_execution()` 返回 `False`，`build_plan()` 不调用 subprocess。
- `SandboxAdapterFactory` 根据 `SandboxPlanner` 推荐 backend 选择 adapter，fallback 到 noop。
- CLI：`sac sandbox plan COMMAND...` 以 Rich Table 展示 backend、command、network/filesystem/writable paths/env keys/dry_run，并显示 warnings 和 limitations。
- Command 必须经过 `CommandPolicy` 检查；高风险或非 allowlisted 命令被阻止并写入 `sandbox_plan_blocked` audit event。
- 通过的 plan 写入 `sandbox_plan_created` audit event。
- env value 不出现在 plan/audit/CLI 输出中，只显示 env keys。

**关键声明**：v1.7.0 不执行任何外部进程。所有 adapter 仅生成 sandbox execution plan。后续版本会先补齐 profile/argument/container plan，真实 OS-level sandbox 执行留待更后续版本。

#### v1.7.1 macOS Seatbelt profile plan

`v1.7.1` 为 macOS 后端补上了 Seatbelt profile 文本生成能力，但仍然不执行 sandbox-exec：

- `SeatbeltProfileBuilder` 根据 `SandboxExecutionRequest` 和项目安全策略生成保守的 `.sb` profile 文本。
- Profile 规则：默认 deny、允许基础进程操作（process-exec/fork/signal/sysctl-read）、允许读取 project_root 和系统路径、`readonly_filesystem=True` 时不生成写权限、敏感路径（`.env`, `.ssh`, `.aws`, `credentials`, `token` 等）被显式 deny。
- `network_enabled=False` 时 profile 不含网络允许规则。
- env value 不出现在 profile、warnings 或 plan 字符串中。
- `MacOSSeatbeltAdapter.build_plan()` 填充 `profile_preview`、`profile_backend`、`profile_warnings` 字段。
- CLI：`sac sandbox plan` 在 macOS backend 下以 Rich Syntax 展示 profile preview，附带 profile warnings 和"sandbox-exec was NOT executed"提示。
- 其他 adapter（Noop/Linux/Docker）不填充 profile_preview。

**关键声明**：v1.7.1 只生成 profile preview，不调用 sandbox-exec。真实 macOS sandbox 执行留待后续版本。

#### v1.7.2 Linux Bubblewrap args plan

`v1.7.2` 为 Linux 后端补上了 Bubblewrap 参数生成能力，但仍然不执行 bwrap：

- `BubblewrapArgsBuilder` 根据 `SandboxExecutionRequest` 和项目安全策略生成保守的 bwrap argv。
- argv 规则：`bwrap --die-with-parent --new-session`、`--unshare-pid/ipc/uts`、network disabled 时 `--unshare-net`、`--ro-bind <project_root>` 和系统路径、`--tmpfs /tmp`、writable paths 通过 `FilesystemBoundary` 后用 `--bind` 绑定。
- 不绑定整个 `/home`、`/tmp`、`/var`、`/private`、`/root`；敏感路径不出现在 writable bind 中。
- `LinuxBubblewrapAdapter.build_plan()` 填充 `args_preview`、`args_backend`、`args_warnings` 字段。
- CLI：`sac sandbox plan` 以 Rich Table 展示 bwrap argv preview。
- 其他 adapter（Noop/MacOS/Docker）不填充 args_preview。

**关键声明**：v1.7.2 只生成 bwrap argv preview，不调用 bwrap。真实 Linux bubblewrap 执行留待后续版本。

#### v1.6 guardrails

- MCP 写操作默认禁用。
- Shell/MCP/hooks 必须走 command policy。
- Network policy 必须覆盖 shell 与 MCP。
- approval store 与 audit anchor 必须在 project root 之外。
- audit anchor 必须存在且可验证。
- context 收集保持 bounded + redacted。
- subagent 初期必须只读。

#### 已知限制（v1.6 前）

- audit anchors 尚未做签名或 keychain 绑定。
- filesystem hardlink/bind-mount 风险未完全解决。
- patch apply 不保留 xattrs/ownership。

### 3.13 更后续能力

- Textual TUI。
- VSCode / JetBrains 插件。
- 云端任务队列。
- 团队协作和 PR 工作流。

这些可以作为 v1.7+ 的方向。当前主线应该优先完成 v1.5 的核心安全边界，再进入 v1.6 的受控工具生态。

---

## 4. v0.1 总体架构

### 4.1 架构图

```text
┌────────────────────────────────────┐
│              CLI Layer              │
│    ask / edit / apply / rollback    │
└──────────────────┬─────────────────┘
                   │
┌──────────────────▼─────────────────┐
│          Agent Orchestrator         │
│ context → llm → patch → review      │
└───────┬───────────────┬────────────┘
        │               │
┌───────▼───────┐ ┌─────▼────────────┐
│ Context Engine│ │     LLM Client    │
│ files/git     │ │ mock/openai later │
└───────┬───────┘ └─────┬────────────┘
        │               │
┌───────▼───────────────▼────────────┐
│           Patch Manager             │
│ parse / validate / diff / apply     │
└───────┬───────────────┬────────────┘
        │               │
┌───────▼───────┐ ┌─────▼────────────┐
│ Checkpoint    │ │    Audit Logger   │
│ backup/restore│ │    events.jsonl   │
└───────────────┘ └──────────────────┘
```

### 4.2 v0.1 核心模块

| 模块 | 作用 |
|---|---|
| CLI Layer | Typer 命令入口 |
| Agent Orchestrator | 串联 ask / edit / apply 流程 |
| Context Engine | 收集目录结构、README、依赖文件、Git 状态 |
| LLM Client | v0.1 默认 MockLLMClient，后续接 OpenAI-compatible API |
| Patch Manager | 解析 Patch、校验 SEARCH 唯一匹配、生成 Diff、应用修改 |
| Checkpoint Manager | 保存修改前文件，支持回滚 |
| Audit Logger | 写入 JSONL 操作日志 |
| Config Manager | 读取基本配置，v0.1 可先轻量实现 |

---

## 5. 技术栈

### 5.1 v0.1 技术栈

```text
Language: Python 3.11+
CLI: Typer
Terminal UI: Rich
Config: Pydantic Settings
Schema: Pydantic
Patch: custom SEARCH/REPLACE parser + difflib
Storage: JSONL + local .sac directory
Testing: pytest
Packaging: uv
```

### 5.2 v0.2+ 可加入

```text
Shell Parse: shlex
Config File: YAML
Memory: SQLite
Code Parser: tree-sitter
Vector Index: sqlite-vec / Chroma / LanceDB
TUI: Textual
MCP: Python MCP SDK
Observability: OpenTelemetry / Langfuse
```

---

## 6. CLI 设计

### 6.1 v0.1 命令

#### `sac ask`

只读问答，不修改文件，不执行 Shell。

```bash
sac ask "这个项目是什么结构？"
```

行为：

1. 收集项目基础上下文。
2. 调用 LLM Client。
3. 输出回答。
4. 写入 audit log。

#### `sac edit`

生成 Patch Proposal，但不写文件。

```bash
sac edit "给 FastAPI 项目添加 /health 接口"
```

行为：

1. 收集项目上下文。
2. 调用 LLM 生成 Patch Proposal。
3. 解析 Patch。
4. 校验目标文件存在。
5. 校验 SEARCH 片段唯一匹配。
6. 展示 Diff Preview。
7. 保存 pending patch 到 `.sac/pending_patch.json`。

#### `sac apply`

应用最近一次 pending patch。

```bash
sac apply
```

行为：

1. 读取 `.sac/pending_patch.json`。
2. 再次校验 SEARCH 是否唯一匹配。
3. 展示 Diff 并请求确认。
4. 创建 Checkpoint。
5. 写入文件。
6. 记录 patch applied 事件。
7. 清理 pending patch。

#### `sac rollback --last`

回滚最近一次 apply。

```bash
sac rollback --last
```

行为：

1. 找到最近 checkpoint。
2. 展示将恢复、删除或重建的文件。
3. 请求用户确认。
4. 恢复文件状态。
5. 记录 rollback 事件。

#### `sac history`

查看最近操作。

```bash
sac history
```

行为：

1. 读取 `.sac/logs/events.jsonl`。
2. 展示最近 patch、apply、rollback、ask 事件。

---

## 7. Patch 系统设计

### 7.1 Patch 格式

v0.1 使用自定义 SEARCH/REPLACE Patch，原因是容易让 LLM 生成，也容易校验和回滚。

```text
*** Begin Patch
*** Update File: app/main.py
@@
SEARCH:
from fastapi import FastAPI

app = FastAPI()
REPLACE:
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}
*** End Patch
```

### 7.2 Patch 操作类型

v0.1 至少支持：

```text
*** Update File: path/to/file.py
*** Add File: path/to/file.py
*** Delete File: path/to/file.py
```

实施约束：

- `v0.1.1` 先实现 `Update File`。
- `v0.1.2` 加入 `Add File`。
- `Delete File` 风险较高，v0.1 只在数据结构中预留，不进入第一轮实现。
- 一个 Patch Proposal 可以包含多个文件 block，但第一轮实现可以先限制为 1 个 block，后续再放开。
- 同一个文件包含多个 SEARCH/REPLACE block 时，需要按顺序应用，并在 apply 前整体校验。

### 7.3 Patch 应用规则

1. Patch 必须以 `*** Begin Patch` 开始，以 `*** End Patch` 结束。
2. `Update File` 必须包含 SEARCH 和 REPLACE。
3. SEARCH 内容必须在目标文件中唯一匹配。
4. 匹配 0 次时拒绝 apply。
5. 匹配多次时拒绝 apply，并提示重新生成更精确 Patch。
6. `Add File` 不能覆盖已有文件，除非用户明确确认。
7. `Delete File` v0.1 暂不执行，只返回“当前版本不支持删除文件”。
8. SEARCH 不能为空字符串；空 SEARCH 容易导致不可控插入。
9. Patch 路径必须限制在 project root 内，不能通过 `../` 越界。
10. apply 前必须创建 checkpoint。
11. apply 后必须写 audit log。
12. apply 中途失败时必须记录 error 事件；`v1.5.1` 实现事务式自动回滚。

### 7.4 审批流程

`sac edit` 和 `sac apply` 必须明确分离：

```text
sac edit
→ 生成 Patch Proposal
→ 校验格式
→ 展示 Diff Preview
→ 保存 .sac/pending_patch.json
→ 不写任何业务文件

sac apply
→ 读取 .sac/pending_patch.json
→ 再次校验 SEARCH 唯一匹配
→ 展示 Diff Preview
→ 询问用户 y/N
→ 默认 N
→ 用户输入 y 后才创建 checkpoint 并写文件
```

v0.1 不实现 `sac apply --yes`，避免绕过学习和审查流程。

### 7.5 Patch 数据结构

```python
from pathlib import Path
from pydantic import BaseModel


class PatchBlock(BaseModel):
    operation: str  # update / add / delete
    file_path: Path
    search: str | None = None
    replace: str | None = None
    content: str | None = None


class PatchProposal(BaseModel):
    id: str
    task: str
    blocks: list[PatchBlock]
    created_at: str
    model: str
    status: str  # pending / applied / rejected / failed
```

### 7.6 Pending Patch 存储

```text
.sac/
  pending_patch.json
```

`sac edit` 只生成和保存 pending patch，不修改项目文件。`sac apply` 才真正写入。

---

## 8. Checkpoint / Rollback 设计

### 8.1 Checkpoint 创建时机

每次 `sac apply` 写文件前创建 Checkpoint。

### 8.2 存储结构

```text
.sac/
  checkpoints/
    2026-05-21T12-30-00Z_patch_001/
      metadata.json
      files/
        app/main.py
```

### 8.3 Metadata

```json
{
  "checkpoint_id": "2026-05-21T12-30-00Z_patch_001",
  "task": "add health endpoint",
  "patch_id": "patch_001",
  "created_at": "2026-05-21T12:30:00Z",
  "file_operations": [
    {
      "path": "app/main.py",
      "operation": "update",
      "existed_before": true,
      "backup_path": "files/app/main.py"
    },
    {
      "path": "app/health.py",
      "operation": "add",
      "existed_before": false,
      "backup_path": null
    }
  ]
}
```

### 8.4 Rollback 规则

1. 如果文件原来存在，rollback 时恢复备份。
2. 如果文件是 apply 新增的，rollback 时删除该文件。
3. 如果文件被删除，rollback 时从备份恢复。
4. rollback 前展示将影响的文件列表。
5. rollback 本身也要写入 audit log。

---

## 9. Audit Log 设计

### 9.1 日志位置

```text
.sac/logs/events.jsonl
```

### 9.2 日志事件

v0.1 记录：

```text
ask_started
ask_completed
patch_proposed
patch_parse_failed
patch_validation_failed
patch_applied
checkpoint_created
rollback_started
rollback_completed
error
```

### 9.3 示例

```json
{"type":"patch_proposed","patch_id":"patch_001","files":["app/main.py"],"timestamp":"..."}
{"type":"checkpoint_created","checkpoint_id":"...","patch_id":"patch_001","timestamp":"..."}
{"type":"patch_applied","patch_id":"patch_001","checkpoint_id":"...","timestamp":"..."}
{"type":"rollback_completed","checkpoint_id":"...","timestamp":"..."}
```

### 9.4 统一事件 Schema

为了让 `sac history` 容易实现，v0.1 的每条 JSONL 事件都使用统一基础字段：

```json
{
  "type": "patch_applied",
  "timestamp": "2026-05-21T12:30:00Z",
  "status": "success",
  "patch_id": "patch_001",
  "checkpoint_id": "2026-05-21T12-30-00Z_patch_001",
  "files": ["app/main.py"],
  "message": null,
  "error": null
}
```

字段说明：

- `type`：事件类型，例如 `ask_completed`、`patch_applied`。
- `timestamp`：UTC ISO 时间。
- `status`：`success` / `failed` / `skipped`。
- `patch_id`、`checkpoint_id`：没有时可以为 `null`。
- `files`：受影响文件列表，没有时为空数组。
- `message`：给用户看的简短说明。
- `error`：失败时记录错误摘要，不能记录 secret。

---

## 10. Context Engine 设计

### 10.1 v0.1 收集内容

```text
当前工作目录
目录树，限制深度和文件数
README.md
requirements.txt
pyproject.toml
package.json
Dockerfile
.gitignore
git status
git diff --stat
```

### 10.2 限制

- 目录树最多 200 个文件。
- 单个文件最多读取 300 行。
- README 最多读取 200 行。
- git diff stat 只读摘要。
- 默认不读取 `.env`、私钥、token、credential 文件。
- v0.1 是 bounded context collector，不是 RAG。
- v0.1 不做 embedding、向量库、代码索引、rerank。
- 如果上下文不足，应提示用户指定文件，而不是自动扩大读取范围。

### 10.3 项目类型识别

```text
requirements.txt + fastapi → FastAPI project
pyproject.toml + fastapi → FastAPI project
package.json + next → Next.js project
pom.xml → Java Maven project
build.gradle → Java Gradle project
Dockerfile → Containerized project
```

---

## 11. LLM 输出协议

### 11.1 输出类型

v0.1 不让模型自由混合自然语言和 Patch，而是要求输出明确类型。

```python
class AgentAnswer(BaseModel):
    type: str  # answer
    content: str


class AgentPatchResponse(BaseModel):
    type: str  # patch
    patch_text: str
    explanation: str | None = None


class AgentError(BaseModel):
    type: str  # error
    message: str
```

### 11.2 v0.1 MockLLMClient

v0.1 先实现 MockLLMClient，保证工程闭环独立于真实模型。

用途：

- `sac ask` 返回固定项目解释。
- `sac edit` 返回固定 Patch。
- 单元测试可稳定运行。

真实 LLM 接入放在 v0.1 后半段或 v0.2，不阻塞核心架构。

### 11.3 Prompt 核心规则

```text
You are SafeCode Agent, a terminal coding assistant.
You must not directly write files.
When editing code, output only the required Patch format.
Do not output full files unless creating a new file.
SEARCH must be exact and unique.
Never request secret files unless the user explicitly asks.
```

---

## 12. v0.2 权限与 Shell 设计

### 12.1 权限模式

v0.2 引入：

| 模式 | 说明 |
|---|---|
| `read_only` | 只允许读取 |
| `ask` | 默认模式，写文件和 Shell 命令需要确认 |
| `auto_safe` | 低风险自动执行，中高风险确认 |
| `strict` | 所有工具调用都要确认 |

不建议实现 `bypass` 模式。

### 12.2 Shell 风险等级

| 等级 | 示例 | 处理方式 |
|---|---|---|
| Low | `ls`, `pwd`, `git status`, `pytest --version` | 可自动执行或轻确认 |
| Medium | `pip install`, `npm install`, `mv`, `cp` | 需要确认 |
| High | `rm`, `sudo`, `chmod`, `git reset --hard` | 强确认 |
| Blocked | `rm -rf /`, `cat ~/.ssh/id_rsa`, `curl ... | sh` | 默认阻止 |

### 12.3 Shell 解析要求

不能只靠简单字符串包含判断。v0.2 至少要识别：

- 管道：`|`
- 重定向：`>`、`>>`
- 命令连接：`&&`、`||`、`;`
- subshell：`$()`
- sudo
- `rm -rf`
- `curl/wget | sh/bash`
- 访问 `.env`、`.ssh`、`id_rsa`、token、credential
- 路径是否越出 project root

---

## 13. v0.3 Hooks 与 Memory 设计

### 13.1 Hooks

v0.3 支持事件：

```text
before_apply
after_apply
before_shell
after_shell
on_error
```

Hook 返回 JSON：

```json
{
  "decision": "allow",
  "message": "ok"
}
```

可选 decision：

```text
allow
warn
deny
```

### 13.2 Project Memory

Memory 存储低风险项目事实：

```text
项目测试命令是 pytest -q
项目启动命令是 uvicorn app.main:app --reload
项目包管理器是 uv
```

Memory 不允许被外部文档直接写入。写入前要判断：

1. 是否来自用户明确指令？
2. 是否只是 Agent 推测？
3. 是否涉及敏感信息？
4. 是否可能污染未来行为？

### 13.3 SAC.md

项目规则文件：

```text
SAC.md
```

示例：

```markdown
# Project Rules

- Use pytest for tests.
- Use uv as package manager.
- Do not modify migrations unless explicitly requested.
- Run `pytest -q` after backend changes.
```

---

## 14. 推荐目录结构

```text
safecode-agent/
  pyproject.toml
  README.md
  src/
    safecode/
      __init__.py
      cli.py
      config.py
      llm/
        base.py
        mock.py
        openai_compatible.py
      agent/
        orchestrator.py
        prompts.py
        schemas.py
      context/
        collector.py
        project_detector.py
      patch/
        parser.py
        manager.py
        diff.py
        models.py
      checkpoint/
        manager.py
        models.py
      audit/
        logger.py
        models.py
      permissions/
        risk.py
        policy.py
      hooks/
        manager.py
        runner.py
      memory/
        sqlite_store.py
        progress.py
      skills/
        registry.py
        loader.py
      tools/
        registry.py
        schemas.py
      sandbox/
        runner.py
        policy.py
      utils/
        paths.py
        time.py
  tests/
    test_patch_parser.py
    test_patch_apply.py
    test_checkpoint.py
    test_audit_log.py
  examples/
    fastapi-demo/
```

v0.1 可以先创建核心目录：`agent`、`context`、`llm`、`patch`、`checkpoint`、`audit`、`utils`。

`permissions`、`hooks`、`memory`、`skills`、`tools`、`sandbox` 不建议在 v0.1 急着实现，可以等对应版本到来时再创建。这样目录结构能表达长期目标，但不会让第一版学习成本失控。

---

## 15. v0.1 开发计划

### Step 1：项目骨架

目标：项目能安装、能运行 CLI、能跑测试。

任务：

- [ ] 创建 `pyproject.toml`。
- [ ] 创建 `src/safecode` 包。
- [ ] 引入 Typer、Rich、Pydantic、pytest。
- [ ] 实现 `sac --help`。
- [ ] 配置 pytest。

验收：

```bash
uv run sac --help
uv run pytest
```

### Step 2：Context Engine + Ask

目标：能读取项目基础上下文，并进行只读回答。

任务：

- [ ] 实现目录树收集。
- [ ] 读取 README / pyproject / requirements / package.json。
- [ ] 跳过敏感文件。
- [ ] 实现 MockLLMClient。
- [ ] 实现 `sac ask`。
- [ ] 写 audit log。

验收：

```bash
uv run sac ask "这个项目是什么？"
```

### Step 3：Patch Parser

目标：能稳定解析 SEARCH/REPLACE Patch。

任务：

- [ ] 定义 `PatchProposal` / `PatchBlock`。
- [ ] 实现 `*** Begin Patch` / `*** End Patch` 解析。
- [ ] 支持 `Update File`。
- [ ] 支持 SEARCH / REPLACE。
- [ ] 校验格式错误。
- [ ] 写 parser 单元测试。

验收：

```bash
uv run pytest tests/test_patch_parser.py
```

### Step 4：Diff Preview + Edit

目标：`sac edit` 能生成 pending patch，并展示 diff。

任务：

- [ ] MockLLMClient 返回固定 Patch。
- [ ] 实现 SEARCH 唯一匹配校验。
- [ ] 使用 difflib 生成 unified diff。
- [ ] 保存 `.sac/pending_patch.json`。
- [ ] 展示 Rich diff。

验收：

```bash
uv run sac edit "添加 health endpoint"
```

### Step 5：Apply + Checkpoint

目标：用户确认后写入文件，并能记录修改前状态。

任务：

- [ ] 读取 pending patch。
- [ ] apply 前再次校验。
- [ ] 创建 checkpoint。
- [ ] 应用文件修改。
- [ ] 记录 audit log。
- [ ] 清理 pending patch。

验收：

```bash
uv run sac apply
```

### Step 6：Rollback + History

目标：能回滚最近一次 apply，并查看操作历史。

任务：

- [ ] 实现 checkpoint metadata。
- [ ] 实现 `sac rollback --last`。
- [ ] 支持恢复 update 文件。
- [ ] 支持删除 apply 新增的文件。
- [ ] 实现 `sac history`。
- [ ] 写 checkpoint 测试。

验收：

```bash
uv run sac rollback --last
uv run sac history
```

### Step 7：FastAPI Demo

目标：有一个可展示的完整演示。

任务：

- [ ] 创建 `examples/fastapi-demo`。
- [ ] demo 中有一个简单 FastAPI app。
- [ ] 用 `sac edit` 添加 `/health`。
- [ ] 用 `sac apply` 应用修改。
- [ ] 用 `sac rollback --last` 回滚。
- [ ] README 写明演示步骤。

---

## 16. v0.1 Demo Scenario

最终演示应该能这样跑：

```bash
cd examples/fastapi-demo
sac ask "这个项目的入口文件在哪里？"
sac edit "给这个 FastAPI 项目添加 /health 接口"
sac apply
pytest -q
sac history
sac rollback --last
```

演示重点：

1. Agent 会读取项目上下文。
2. Agent 只生成 Patch，不直接写文件。
3. 用户能看到 Diff。
4. apply 前创建 Checkpoint。
5. 修改后有 Audit Log。
6. rollback 能恢复原状。

---

## 17. 风险与应对

### 17.1 Patch 匹配失败

问题：LLM 生成的 SEARCH 不精确，导致找不到或多处匹配。

应对：

- SEARCH 必须唯一匹配。
- 匹配失败时拒绝 apply。
- 提示用户重新生成 Patch。
- 后续加入 AST-aware patch。

### 17.2 Patch 格式不稳定

问题：真实 LLM 可能输出解释文字、Markdown 包裹或格式错误。

应对：

- v0.1 先用 MockLLMClient 稳定闭环。
- 真实 LLM 接入时使用严格 Prompt。
- Parser 对常见 Markdown fence 做兼容。
- 格式错误时不给写文件。

### 17.3 Rollback 不完整

问题：只备份已有文件会导致新增/删除文件无法正确恢复。

应对：

- checkpoint metadata 记录 `file_operations`。
- 新增文件 rollback 时删除。
- 删除文件 rollback 时恢复。
- update 文件 rollback 时覆盖回备份。

### 17.4 Scope 膨胀

问题：过早加入 Shell、Hooks、Memory、Index，会导致 v0.1 做不完。

应对：

- v0.1 只做 Patch 修改闭环。
- v0.2 再做 Shell。
- v0.3 再做 Hooks 和 Memory。

---

## 18. 简历描述草稿

英文：

```text
SafeCode Agent — Secure Python Terminal Coding Agent
- Built a terminal-native coding agent in Python with a safe SEARCH/REPLACE patch workflow, human diff review, automatic checkpoints, rollback, and JSONL audit logging.
- Designed a constrained code editing pipeline where LLMs can only propose structured patches, while file writes require explicit user approval.
- Implemented project context collection, patch parsing, diff preview, checkpoint metadata, and rollback handling for updated, added, and deleted files.
- Extended the design toward permissioned shell execution, hooks, project memory, and future code indexing.
```

中文：

```text
SafeCode Agent：安全型 Python 终端 Coding Agent
- 基于 Python 构建终端原生 Coding Agent，支持项目上下文读取、Patch 生成、Diff Review、人工确认、Checkpoint、Rollback 和 JSONL 审计日志。
- 设计受限代码修改管线，LLM 只能生成结构化 SEARCH/REPLACE Patch，文件写入必须经过用户确认。
- 实现 Patch 解析、唯一匹配校验、Diff Preview、修改前备份和新增/删除/更新文件的回滚机制。
- 后续扩展 Shell 权限控制、Hooks、项目 Memory、代码索引和 MCP 集成能力。
```

---

## 19. 给 Codex 的第一条实现任务

```text
请根据 safe_code_agent_software_design_doc.md 的 v0.1 设计创建 SafeCode Agent 的 Python 项目骨架，使用 Typer + Rich + Pydantic + pytest。先实现 sac ask、sac edit、sac apply、sac rollback --last、sac history 的基础闭环。v0.1 不接真实 LLM，使用 MockLLMClient 返回固定 Patch，保证 Patch Parser、Diff Preview、Checkpoint、Apply、Rollback 和 Audit Log 可运行，并补充对应单元测试。
```
