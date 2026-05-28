# SafeCode Agent Version Implementation Matrix

这份文档说明从 `v0.1.0` 到当前最新规划版本的分支、代码入口和验收命令。

说明：

- `v0.1.x` 是已经拆过的学习阶段。
- `v0.2.x` 到 `v1.4.x` 已经以逐阶段分支推进。
- `v1.5.x` 优先做核心安全边界整改。
- `v1.6.x` 再做 MCP 真执行和 subagent 并发。
- 所有分支名都不使用 `codex/` 前缀。

## v0.1.x

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.1.0` | `v0.1.0-ask-audit` | `src/safecode/cli.py::ask` | `uv run sac ask "这个项目是什么？"` |
| `v0.1.1` | `v0.1.1-patch-parser` | `src/safecode/patch/parser.py` | `PYTHONPATH=src python3 -m pytest tests/test_patch_parser.py -q` |
| `v0.1.2` | `v0.1.2-edit-preview` | `src/safecode/agent/orchestrator.py::edit` | `uv run sac edit "演示一次安全修改"` |
| `v0.1.3` | `v0.1.3-apply-checkpoint` | `src/safecode/agent/orchestrator.py::apply` | `uv run sac apply` |
| `v0.1.4` | `v0.1.4-rollback-history` | `src/safecode/checkpoint/manager.py` | `uv run sac rollback --last && uv run sac history` |
| `v0.1.5` | `v0.1.5-fastapi-demo` | `examples/fastapi-demo` | 在 demo 目录运行 ask/edit/apply/history/rollback |

## v0.2.x: Permissioned Shell Runtime

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.2.0` | `v0.2.0-config-policy` | `src/safecode/config.py` | `uv run sac config show` |
| `v0.2.1` | `v0.2.1-shell-risk-classifier` | `src/safecode/shell/risk.py` | `PYTHONPATH=src python3 -m pytest tests/test_runtime_extensions.py -q` |
| `v0.2.2` | `v0.2.2-sac-run-readonly` | `src/safecode/shell/runner.py` | `uv run sac run "git status --short" --yes` |
| `v0.2.3` | `v0.2.3-sac-run-approval` | `src/safecode/cli.py::run_command` | `uv run sac run "rm -rf /tmp/example"` |
| `v0.2.4` | `v0.2.4-shell-audit-history` | `src/safecode/audit/models.py` | `uv run sac history` |

## v0.3.x: Long-running State

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.3.0` | `v0.3.0-sac-md-project-rules` | `src/safecode/project/rules.py` | `uv run sac rules --init` |
| `v0.3.1` | `v0.3.1-progress-file` | `src/safecode/state/progress.py` | `uv run sac progress set "demo goal" --next "next step"` |
| `v0.3.2` | `v0.3.2-hooks-after-apply` | `src/safecode/hooks/runner.py` | 配置 `[hooks].after_apply` 后运行 `uv run sac apply` |
| `v0.3.3` | `v0.3.3-lightweight-memory` | `src/safecode/memory/store.py` | `uv run sac memory test_command "pytest -q"` |

## v0.4.x: Skills + Tool Registry

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.4.0` | `v0.4.0-skills-directory` | `src/safecode/skills/loader.py` | `uv run sac skills list` |
| `v0.4.1` | `v0.4.1-tool-registry` | `src/safecode/tools/registry.py` | `uv run sac tools list` |
| `v0.4.2` | `v0.4.2-skill-loading-demo` | `src/safecode/skills/loader.py::get` | `uv run sac skills show python-cli` |
| `v0.4.3` | `v0.4.3-skill-scripts` | `skills/*/SKILL.md` | 读取 skill 目录中的脚本/模板 |

## v0.5.x: Code Index

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.5.0` | `v0.5.0-code-index-basic` | `src/safecode/index/files.py` | `uv run sac index files` |
| `v0.5.1` | `v0.5.1-symbol-search` | `src/safecode/index/python_symbols.py` | `uv run sac index symbols` |
| `v0.5.2` | `v0.5.2-context-selection` | `src/safecode/context/selector.py` | 在 Python 中调用 `ContextSelector(...).select(...)` |
| `v0.5.3` | `v0.5.3-index-cache` | `src/safecode/index/*` | 当前为轻量实时索引，缓存留作后续增强 |

## v0.6.x: MCP Integration

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.6.0` | `v0.6.0-mcp-config` | `src/safecode/mcp/config.py` | 创建 `.sac/mcp.toml` 后运行命令 |
| `v0.6.1` | `v0.6.1-mcp-tool-discovery` | `src/safecode/mcp/discovery.py` | `uv run sac mcp tools` |
| `v0.6.2` | `v0.6.2-mcp-audit-permission` | `src/safecode/audit/models.py` | 外部工具写操作未来统一走 audit |
| `v0.6.3` | `v0.6.3-mcp-demo-tool` | `src/safecode/mcp/discovery.py` | 当前提供只读 discovery placeholder |

## v0.7.x: Sandbox / Containment

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.7.0` | `v0.7.0-sandbox-policy` | `src/safecode/config.py::SandboxPolicy` | `uv run sac config show` |
| `v0.7.1` | `v0.7.1-filesystem-boundary` | `src/safecode/sandbox/filesystem.py` | `PYTHONPATH=src python3 -m pytest tests/test_runtime_extensions.py -q` |
| `v0.7.2` | `v0.7.2-network-policy` | `src/safecode/sandbox/network.py` | 默认网络策略拒绝外部访问 |
| `v0.7.3` | `v0.7.3-sandboxed-runner` | `src/safecode/shell/runner.py` | `uv run sac run "git status" --yes` |

## v0.8.x: Subagents

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.8.0` | `v0.8.0-subagent-task-model` | `src/safecode/subagents/task.py` | `uv run sac subagent create "inspect" "read files"` |
| `v0.8.1` | `v0.8.1-subagent-result-files` | `src/safecode/subagents/task.py::write_result` | 文件结果写入 `.sac/subagents/` |
| `v0.8.2` | `v0.8.2-parallel-readonly-subagents` | `src/safecode/subagents/task.py` | 当前默认 readonly task |
| `v0.8.3` | `v0.8.3-subagent-merge-review` | `src/safecode/subagents/task.py` | 后续汇总后生成单一 patch |

## v0.9.x: Observability + Evaluation

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v0.9.0` | `v0.9.0-trace-events` | `src/safecode/trace/events.py` | 在 Python 中调用 `TraceLogger.write(...)` |
| `v0.9.1` | `v0.9.1-evaluation-suite` | `src/safecode/eval/runner.py` | `uv run sac eval` |
| `v0.9.2` | `v0.9.2-reporting` | `src/safecode/report/render.py` | `uv run sac report` |
| `v0.9.3` | `v0.9.3-failure-taxonomy` | 错误分类目前体现在 validator/shell exit code | 后续可扩展独立 taxonomy 模块 |

## v1.0.x: Stable Local Agent Runtime

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.0.0` | `v1.0.0-stable-local-runtime` | `src/safecode/cli.py` | `uv run sac --help` |
| `v1.0.1` | `v1.0.1-install-packaging` | `pyproject.toml`、`src/safecode/doctor.py` | `uv run sac doctor` |
| `v1.0.2` | `v1.0.2-docs-tutorials` | `docs/*` | 阅读版本矩阵和 roadmap |
| `v1.0.3` | `v1.0.3-hardening` | `tests/test_runtime_extensions.py` | `PYTHONPATH=src python3 -m pytest -q` |
| `v1.0.4` | `v1.0.4-security-presets` | `src/safecode/config.py` | `uv run sac config show` |
| `v1.0.5` | `v1.0.5-release-demo` | `examples/fastapi-demo`、`src/safecode/release` | `uv run sac release checklist v1.0.5` |

## v1.1.x: Product Extension Layer

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.1.0` | `v1.1.0-local-api-facade` | `src/safecode/api.py` | 在 Python 中调用 `SafeCodeLocalAPI(Path.cwd()).ask(...)` |
| `v1.1.1` | `v1.1.1-export-reports` | `src/safecode/export/bundle.py` | `uv run sac export report` |
| `v1.1.2` | `v1.1.2-local-task-queue` | `src/safecode/queue/store.py` | `uv run sac queue add "demo"` |
| `v1.1.3` | `v1.1.3-ide-manifest` | `src/safecode/ide/manifest.py` | `uv run sac ide manifest --write` |
| `v1.1.4` | `v1.1.4-release-checklist` | `src/safecode/release/checklist.py` | `uv run sac release checklist v1.1.4` |
| `v1.1.5` | `v1.1.5-extension-polish` | 全部扩展层 | `PYTHONPATH=src python3 -m pytest -q` |

## v1.2.x: Production Hardening

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.2.0` | `v1.2.0-security-hardening` | `src/safecode/shell/runner.py` | `uv run sac run "rm -rf /tmp/example" --yes` 不执行 |
| `v1.2.1` | `v1.2.1-trusted-policy` | `src/safecode/config.py` | `PYTHONPATH=src python3 -m pytest tests/test_security_hardening.py -q` |
| `v1.2.2` | `v1.2.2-sandbox-enforcement` | `src/safecode/patch/validator.py`、`src/safecode/sandbox/*` | 路径逃逸和 MCP 写操作测试通过 |
| `v1.2.3` | `v1.2.3-real-llm-provider` | `src/safecode/llm/factory.py`、`src/safecode/llm/openai_client.py` | 默认 mock 测试通过，真实 LLM 需 API key |
| `v1.2.4` | `v1.2.4-deploy-package` | `README.md`、`Dockerfile`、`.github/workflows/ci.yml` | `uv run sac doctor` |
| `v1.2.5` | `v1.2.5-prod-eval-suite` | `tests/test_security_hardening.py` | `PYTHONPATH=src python3 -m pytest -q` |

## v1.3.x: Runtime Trust Refinement

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.3.0` | `v1.3.0-context-secret-hardening` | `src/safecode/context/collector.py` | secret-like 文件不进入 context |
| `v1.3.1` | `v1.3.1-hook-policy-hardening` | `src/safecode/hooks/runner.py` | medium-risk hooks 默认不执行 |
| `v1.3.2` | `v1.3.2-llm-network-policy` | `src/safecode/llm/factory.py` | real LLM 需要 trusted network policy |
| `v1.3.3` | `v1.3.3-trace-audit-integration` | `src/safecode/agent/orchestrator.py` | audit event 带 trace id |
| `v1.3.4` | `v1.3.4-docs-trust-boundaries` | `README.md`、`docs/*` | `PYTHONPATH=src python3 -m pytest -q` |

## v1.4.x: Runtime Operations

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.4.0` | `v1.4.0-runtime-logging` | `src/safecode/logs/runtime.py`、`src/safecode/cli.py` | `uv run sac logs show --level error --traceback` |

## v1.5.x: Core Security Boundary

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.5.0` | `v1.5.0-context-containment` | `src/safecode/context/collector.py`、`src/safecode/sandbox/filesystem.py` | symlink escape / secret content 不进入 context |
| `v1.5.1` | `v1.5.1-transactional-apply` | `src/safecode/patch/applier.py`、`src/safecode/checkpoint/manager.py` | apply 失败自动 rollback，无半写入 |
| `v1.5.2` | `v1.5.2-command-policy-engine` | `src/safecode/shell/*`、`src/safecode/hooks/runner.py` | arg-level 风险判断测试通过 |
| `v1.5.3` | `v1.5.3-hook-approval-audit` | `src/safecode/hooks/*`、`src/safecode/audit/*` | hook proposal/approval/result 可审计 |
| `v1.5.4` | `v1.5.4-audit-integrity` | `src/safecode/audit/logger.py` | `sac audit verify` 能发现日志篡改 |
| `v1.5.5` | `v1.5.5-command-policy-hardening` | `src/safecode/policy/commands.py` | `git -c alias.*=!`、`git -C`、`python -m`、`node -e` 等被阻止 |
| `v1.5.6` | `v1.5.6-hook-approval-state` | `src/safecode/hooks/approvals.py`、`src/safecode/hooks/runner.py`、`src/safecode/cli.py::hooks_approve` | `uv run sac hooks approve "git status"` 后 hook 才能使用对应审批 |
| `v1.5.7` | `v1.5.7-audit-anchoring` | `src/safecode/audit/anchor.py`、`src/safecode/audit/logger.py` | 整份 audit log 被重写后 anchor mismatch |
| `v1.5.8` | `v1.5.8-context-redaction-hardening` | `src/safecode/context/collector.py`、`src/safecode/context/redactor.py` | symlinked directory、Bearer/AWS/JSON secret、file-list cap 有测试 |
| `v1.5.9` | `v1.5.9-apply-metadata-preimage` | `src/safecode/patch/applier.py` | mode preserved、non-UTF-8 rejected、preimage rechecked |
| `v1.5.10` | `v1.5.10-review-followup-docs` | `docs/*`、`safe_code_agent_software_design_doc.md` | Copilot security review 后的 v1.5 follow-up 路线写清楚 |
| `v1.5.11` | `v1.5.11-hook-approval-trust` | `src/safecode/hooks/approvals.py`、`src/safecode/hooks/runner.py` | 用户级 approval + config/user/expiry binding + allow switch |
| `v1.5.12` | `v1.5.12-command-policy-bypass-fixes` | `src/safecode/policy/commands.py` | git pager/editor/diff command、node --eval、python stdin、npx/pip3/pipx/uv pip 被阻止 |
| `v1.5.13` | `v1.5.13-audit-context-hardening` | `src/safecode/audit/*`、`src/safecode/context/collector.py` | anchor missing fail、0600 anchor、project_root redaction、sensitive path segment skip |
| `v1.5.14` | `v1.5.14-security-review-docs` | `docs/*`、`safe_code_agent_software_design_doc.md` | 第二轮安全 review 后续整改写入文档 |

## v1.6.x: Controlled Tooling and Subagents

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.6.0` | `v1.6.0-mcp-runner-readonly` | `src/safecode/mcp/*` | MCP 只读工具调用有 audit/runtime log |
| `v1.6.1` | `v1.6.1-mcp-write-approval` | `src/safecode/mcp/*`、`src/safecode/policy/*` | MCP 写操作必须审批 |
| `v1.6.2` | `v1.6.2-subagent-readonly-runner` | `src/safecode/subagents/*` | 子任务只读执行并写结果文件 |
| `v1.6.3` | `v1.6.3-subagent-merge-review` | `src/safecode/subagents/*`、`src/safecode/patch/*` | Lead agent 合并后生成单一 patch |
| `v1.6.4` | `v1.6.4-os-sandbox-research` | `docs/*`、`src/safecode/sandbox/*` | sandbox adapter 能力和限制写清楚 |
| `v1.6.5` | `v1.6.5-tooling-security-evals` | `tests/*` | MCP/subagent 权限和冲突测试通过 |
