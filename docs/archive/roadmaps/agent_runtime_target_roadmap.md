# SafeCode Agent Runtime Target Roadmap

这份文档用于约束 SafeCode Agent 的长期方向：最终产品要像一个轻量 Agent Harness / Runtime，而不是停留在“聊天机器人 + 工具调用”。

## 一句话目标

SafeCode Agent 要做成一个安全优先、可审计、可回滚、可扩展的本地 Agent 运行时。

模型负责推理和生成提案；运行时负责上下文、权限、工具、文件系统、状态、日志、checkpoint、rollback 和验证。

```text
Model = brain
Tools / files / shell / MCP = hands
SafeCode Agent Runtime = nervous system + permission boundary + memory + audit trail
```

## 目标能力对照

| 方向 | 目标形态 | 版本落点 | 当前状态 |
|---|---|---|---|
| Agent Harness | CLI + Orchestrator + Context + Patch + Audit + Checkpoint | v0.1 | 正在实现 |
| 安全文件修改 | 模型只能生成 Patch，不能直接写文件 | v0.1 | 已有 edit/apply 雏形 |
| Rollback / History | 每次写入前 checkpoint，操作进入 audit log | v0.1 | rollback/history 待完成 |
| 权限与 Shell | 命令按风险分类，危险命令阻止或强确认 | v0.2 | 未开始 |
| 长任务状态 | progress file、任务状态、下一步、阻塞点 | v0.3 | 未开始 |
| Hooks / Project Rules | `SAC.md`、before/after hooks、项目规则 | v0.3 | 未开始 |
| Skills | 专业能力以目录包形式按需加载 | v0.4 | 未开始 |
| Code Index | 大项目代码结构索引和检索 | v0.5 | 未开始 |
| MCP / Tools | 外部工具按需发现、按策略调用 | v0.6 | 未开始 |
| Sandbox | 文件系统、网络、Shell 的 containment | v0.7 | 未开始 |
| Subagents | lead agent + scoped subagents | v0.8 | 未开始 |
| Observability / Evaluation | trace、回归样例、失败分类、任务报告 | v0.9 | 未开始 |
| Stable Runtime | 安装、文档、安全基线、稳定 API、发布 demo | v1.0.x | 未开始 |
| Product Extension | 本地 API、报告导出、任务队列、IDE manifest、发布清单 | v1.1.x | 未开始 |
| Core Security Boundary | symlink/content redaction、transactional apply、command policy、audit integrity | v1.5.x | 规划中 |
| Controlled Tooling | MCP 真执行、只读 subagent、merge review、OS sandbox adapter | v1.6.x | 规划中 |

## 设计原则

### 1. Harness 先于模型能力

不要把安全和可靠性寄托在“模型会不会自觉”。SafeCode Agent 必须把关键动作收进运行时：

- 文件读取由 ContextCollector 控制。
- 文件写入必须走 PatchValidator 和 PatchApplier。
- 写入前必须 Checkpoint。
- 用户必须看到 Diff。
- 操作必须进入 Audit Log。

### 2. 文件状态先于长期记忆

长任务不能只依赖聊天上下文。后续状态应该写进 `.sac/`：

```text
.sac/
  pending_patch.json
  checkpoints/
  logs/events.jsonl
  progress.md
  memory.json
```

`pending_patch.json` 表示下一步要应用的修改；`progress.md` 表示长任务进展；`events.jsonl` 表示不可变审计记录。

### 3. Containment 先于自动化

越是想让 Agent 自动执行，就越要先限制它能碰到什么：

- 默认只能操作 project root。
- 默认不能读 `.env`、`.ssh`、私钥、token。
- 默认不能联网。
- 默认不能执行高风险 Shell。
- 外部工具写操作必须单独确认。

### 4. 工具按需发现，不全部塞入 prompt

后续工具系统应避免一次性把所有工具 schema 塞进模型上下文。更好的方式是：

```text
skills/
  python-project/
    SKILL.md
    scripts/
    templates/
tools/
  git/
  filesystem/
  shell/
mcp/
  github/
  notion/
```

模型需要某类能力时，再读取对应 skill 或 tool 描述。

### 5. 多 Agent 放到最后

Subagents 很有价值，但只有在以下基础稳定后才做：

- patch/apply/rollback 稳定。
- shell 权限稳定。
- progress file 稳定。
- tool registry 稳定。
- sandbox 边界稳定。

否则多个 agent 并行只会扩大混乱和风险。

## 版本路线

### v0.1: Safe Patch Runtime

目标：完成安全代码修改闭环。

```text
sac ask
sac edit
sac apply
sac rollback --last
sac history
```

验收标准：

- edit 只生成 pending patch，不写业务文件。
- apply 前必须展示 diff 并确认。
- apply 前必须 checkpoint。
- rollback 能恢复最近一次 apply。
- history 能展示 ask/edit/apply/rollback。

### v0.2: Permissioned Shell Runtime

目标：加入受控 Shell。

验收标准：

- `sac run` 支持低风险命令。
- Shell Risk Classifier 能识别管道、重定向、sudo、rm、curl pipe shell。
- 高风险命令强确认或阻止。
- 命令结果写 audit log。

### v0.3: Long-running State + Project Rules

目标：让 Agent 能跨上下文继续工作。

验收标准：

- `.sac/progress.md` 记录目标、已完成、下一步、阻塞点。
- `SAC.md` 记录项目规则。
- after_apply hook 可以运行格式化或测试。
- Memory 只能记录低风险事实。

### v0.4: Skills + Tool Registry

目标：把专业能力做成可组合包。

验收标准：

- `skills/` 可以列出和读取。
- Skill 包含 `SKILL.md`、脚本、模板、示例。
- Tool Registry 能描述内部工具能力。
- 工具说明按需加载。

### v0.5: Code Index

目标：解决大项目上下文不足。

验收标准：

- 能索引文件、类、函数、入口点。
- 能按关键词或符号定位代码。
- 检索结果带文件路径和行号。
- embedding / vector search 只作为可选增强。

### v0.6: MCP Integration

目标：接外部工具生态。

验收标准：

- MCP server 可配置。
- 外部工具按需发现。
- 外部写操作独立审批。
- 工具调用写入 audit log。

### v0.7: Sandbox / Containment

目标：把能力边界从“提醒用户小心”升级成“运行时限制”。

验收标准：

- Shell 在受控 workspace 内运行。
- 网络默认关闭或 allowlist。
- project root 外写入默认拒绝。
- 敏感路径默认拒绝。

### v0.8: Subagents

目标：支持复杂任务的分工。

验收标准：

- Lead Agent 负责任务拆分和汇总。
- Subagent 有独立上下文和权限。
- 子任务通过文件化结果回传。
- 默认避免多个 agent 同时写同一文件。

### v0.9: Observability + Evaluation

目标：让 SafeCode Agent 的行为可以复盘、比较和回归测试。

验收标准：

- 每次 ask/edit/apply/run 有 trace id。
- audit event 和 trace event 可以串起一次任务。
- 有固定 demo case 可以做回归评估。
- 能生成一次任务的 markdown/html 报告。
- 失败能分类为 parse、validation、permission、test failure 等。

### v1.0.x: Stable Local Agent Runtime

目标：把前面能力收口成一个稳定、可安装、可演示、可继续扩展的本地 Agent Runtime。

验收标准：

- 新 clone 后可以按 README 安装和运行。
- `sac ask/edit/apply/rollback/history/run/config/skills/index` 基本稳定。
- 默认安全策略不会静默修改 project root 外文件。
- checkpoint、audit、trace 数据结构稳定。
- 有教程、demo、错误处理和安全策略说明。

`v1.0.x` 拆分：

```text
v1.0.0 stable-local-runtime
v1.0.1 install-packaging
v1.0.2 docs-tutorials
v1.0.3 reliability-hardening
v1.0.4 security-presets
v1.0.5 release-demo
```

### v1.1.x: Product Extension Layer

目标：在 v1.0 稳定 runtime 之上，补齐本地产品扩展入口。

验收标准：

- 有稳定的本地 Python API facade。
- 报告可以导出到 Markdown 文件。
- 有轻量本地任务队列。
- 可以生成 IDE adapter metadata。
- 可以生成发布检查清单。

## 当前优先级

当前不要急着做高级能力。最优先完成和巩固：

```text
v1.5.0 context-containment
v1.5.1 transactional-apply
v1.5.2 command-policy-engine
v1.5.3 hook-approval-audit
v1.5.4 audit-integrity
v1.5.5 command-policy-hardening
v1.5.6 hook-approval-state
v1.5.7 audit-anchoring
v1.5.8 context-redaction-hardening
v1.5.9 apply-metadata-preimage
v1.5.11 hook-approval-trust
v1.5.12 command-policy-bypass-fixes
v1.5.13 audit-context-hardening
v1.5.15 command-policy-final-bypass-fixes
v1.5.16 approval-parsing-hardening
v1.5.17 audit-anchor-trust-boundary
v1.5.18 context-redaction-extension
v1.5.19 patch-apply-symlink-race-guard
v1.5.21 git-policy-env-hardening
v1.5.22 shell-network-policy
v1.5.23 approval-store-trust-boundary
```

`MCP 真执行` 和 `subagent 并发` 推迟到 `v1.6.x`。只有上述 `v1.5.21` 到 `v1.5.23` 的测试全部通过后，才允许开始 v1.6。

### v1.6 guardrails

- MCP 写操作默认禁用。
- Shell/MCP/hooks 必须走 command policy。
- Network policy 必须覆盖 shell 与 MCP。
- approval store 与 audit anchor 必须在 project root 之外。
- context 收集保持 bounded + redacted。
- subagent 初期必须只读。
