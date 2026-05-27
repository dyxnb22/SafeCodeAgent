# SafeCode Agent v0.1 Implementation Plan

这份文档是 `safe_code_agent_software_design_doc.md` 的实施版补充。

主设计文档负责说明项目愿景和总体架构；本文件只负责 v0.1 怎么一步一步落地。后续开发时，每次只实现一个小版本，先审计划和 diff，再写代码。

## v0.1 总目标

v0.1 只做安全 Patch 修改闭环：

```text
sac ask
-> sac edit
-> save pending patch
-> sac apply
-> checkpoint
-> write file
-> audit log
-> sac rollback --last
-> sac history
```

v0.1 不做：

- 真实 LLM 接入。
- Shell 命令执行。
- RAG、embedding、向量数据库。
- Hooks。
- 长期 Memory。
- MCP。
- Subagents。
- TUI / IDE 插件。

## v0.1.0: CLI 骨架 + ask + audit log

目标：项目能作为 Python CLI 跑起来，并完成只读问答。

涉及模块：

```text
src/safecode/cli.py
src/safecode/context/collector.py
src/safecode/llm/mock.py
src/safecode/audit/logger.py
src/safecode/audit/models.py
tests/test_audit_log.py
```

要实现：

- `sac --help` 正常显示。
- `sac ask "..."` 能调用 `ContextCollector`。
- `MockLLMClient.ask()` 返回固定回答。
- 每次 ask 写入 `.sac/logs/events.jsonl`。
- audit event 使用统一 schema。

验收命令：

```bash
uv run sac --help
uv run sac ask "这个项目是什么？"
uv run pytest tests/test_audit_log.py
```

学习重点：

- Typer 命令如何调用业务层。
- `Path` 如何创建 `.sac/logs`。
- JSONL 为什么适合 append-only audit log。

## v0.1.1: Patch 模型 + Parser

目标：把 SEARCH/REPLACE 文本解析成结构化对象。

涉及模块：

```text
src/safecode/patch/models.py
src/safecode/patch/parser.py
tests/test_patch_parser.py
```

第一轮只支持：

```text
*** Begin Patch
*** Update File: path/to/file.py
@@
SEARCH:
old text
REPLACE:
new text
*** End Patch
```

要实现：

- 校验 Begin / End。
- 解析 `Update File`。
- 解析 `SEARCH:` 和 `REPLACE:`。
- SEARCH 不能为空。
- 格式错误时抛出清晰异常。

暂不实现：

- Delete File。
- 一个文件多个 block。
- Markdown fence 容错。

验收命令：

```bash
uv run pytest tests/test_patch_parser.py
```

学习重点：

- 文本解析不要急着写复杂正则。
- 先处理最小格式，再逐步兼容边界情况。

## v0.1.2: edit + Diff Preview + pending patch

目标：`sac edit` 只生成待应用 patch，不写业务文件。

涉及模块：

```text
src/safecode/cli.py
src/safecode/agent/orchestrator.py
src/safecode/llm/mock.py
src/safecode/patch/validator.py
src/safecode/patch/diff.py
src/safecode/audit/logger.py
tests/test_patch_validator.py
```

要实现：

- `MockLLMClient.propose_patch()` 返回固定 Patch。
- `PatchValidator` 校验目标文件存在。
- `Update File` 的 SEARCH 必须唯一匹配。
- 用 `difflib.unified_diff()` 展示预览。
- 保存 `.sac/pending_patch.json`。
- 写入 `patch_proposed` 或 `patch_validation_failed` 事件。

验收命令：

```bash
uv run sac edit "演示一次安全修改"
uv run pytest tests/test_patch_validator.py
```

学习重点：

- 为什么 edit 阶段不能写文件。
- 为什么 SEARCH 必须唯一匹配。
- diff 是给人审的，不是给机器看的。

## v0.1.3: apply + checkpoint

目标：用户确认后才真正写文件，并在写入前保存 checkpoint。

涉及模块：

```text
src/safecode/cli.py
src/safecode/patch/applier.py
src/safecode/checkpoint/manager.py
src/safecode/checkpoint/models.py
src/safecode/audit/logger.py
tests/test_patch_apply.py
tests/test_checkpoint.py
```

要实现：

- `sac apply` 读取 `.sac/pending_patch.json`。
- apply 前再次执行 SEARCH 唯一匹配校验。
- 展示 Diff Preview。
- 询问用户 `Apply this patch? [y/N]`。
- 默认不应用。
- 用户输入 `y` 后创建 checkpoint。
- 写入文件。
- 清理 pending patch。
- 写入 `checkpoint_created` 和 `patch_applied` 事件。

暂不实现：

- `sac apply --yes`。
- 事务式批量 apply。
- Delete File。

验收命令：

```bash
uv run sac apply
uv run pytest tests/test_patch_apply.py tests/test_checkpoint.py
```

学习重点：

- 写文件前为什么要 checkpoint。
- 为什么 apply 前要重新校验，而不是相信 edit 阶段的结果。
- 失败时如何记录错误，避免静默失败。

## v0.1.4: rollback + history

目标：能恢复最近一次 apply，并查看操作历史。

涉及模块：

```text
src/safecode/cli.py
src/safecode/checkpoint/manager.py
src/safecode/audit/logger.py
tests/test_checkpoint.py
tests/test_audit_log.py
```

要实现：

- `sac rollback --last` 找到最新 checkpoint。
- rollback 前展示将恢复或删除的文件。
- 用户确认后执行恢复。
- update 文件恢复备份内容。
- add 文件 rollback 时删除新增文件。
- rollback 写入 audit log。
- `sac history` 读取最近 JSONL 事件并用 Rich 表格展示。

验收命令：

```bash
uv run sac rollback --last
uv run sac history
uv run pytest tests/test_checkpoint.py tests/test_audit_log.py
```

学习重点：

- rollback 不是简单 git reset。
- checkpoint metadata 必须记录每个文件 apply 前的状态。
- history 只读 audit log，不重新推断历史。

## v0.1.5: FastAPI Demo

目标：做一个能展示完整闭环的小 demo。

涉及目录：

```text
examples/fastapi-demo/
```

演示流程：

```bash
cd examples/fastapi-demo
sac ask "这个项目的入口文件在哪里？"
sac edit "给这个 FastAPI 项目添加 /health 接口"
sac apply
sac history
sac rollback --last
```

验收重点：

- edit 阶段只生成 pending patch。
- apply 阶段必须人工确认。
- apply 前有 checkpoint。
- history 能看到完整事件。
- rollback 后文件恢复原状。

## 后续开发规则

为了配合学习审批流，后续实现每个小版本时遵守：

1. 先读当前代码。
2. 先给本次修改计划和涉及文件。
3. 用户确认后再改代码。
4. 每次只实现一个小版本。
5. 改完后给出文件级变更说明。
6. 能跑的测试必须跑。
7. 不把真实 LLM、Shell、RAG 提前塞进 v0.1。
