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

### 3.9 更后续能力

- Textual TUI。
- VSCode / JetBrains 插件。
- Langfuse / OpenTelemetry 观测。
- 云端任务队列。
- 团队协作和 PR 工作流。

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
12. apply 中途失败时必须记录 error 事件；后续版本再实现事务式自动回滚。

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
