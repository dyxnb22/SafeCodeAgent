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
| `v1.5.15` | `v1.5.15-command-policy-final-bypass-fixes` | `src/safecode/policy/commands.py`、`src/safecode/shell/runner.py` | git include/clean 旁路被阻止，Git env 注入被清理 |
| `v1.5.16` | `v1.5.16-approval-parsing-hardening` | `src/safecode/hooks/approvals.py` | 审批 JSON/expiry 解析失败不崩溃，审批绑定 policy 版本 |
| `v1.5.17` | `v1.5.17-audit-anchor-trust-boundary` | `src/safecode/audit/anchor.py`、`src/safecode/audit/logger.py` | anchor 不能落在 project root，缺失 anchor 直接失败 |
| `v1.5.18` | `v1.5.18-context-redaction-extension` | `src/safecode/context/redactor.py`、`src/safecode/context/collector.py` | GitHub/JWT/Bearer/base64 secret redaction 扩展 |
| `v1.5.19` | `v1.5.19-patch-apply-symlink-race-guard` | `src/safecode/patch/applier.py`、`src/safecode/sandbox/filesystem.py` | apply 前重验边界与 inode，拒绝 symlink swap |
| `v1.5.20` | `v1.5.20-security-review-docs` | `docs/*`、`safe_code_agent_software_design_doc.md` | v1.5.15-1.5.19 补充 + v1.6 guardrails |
| `v1.5.21` | `v1.5.21-git-policy-env-hardening` | `src/safecode/policy/commands.py`、`src/safecode/shell/runner.py` | git config/ENV 旁路收敛，补 git 远程/状态子命令 |
| `v1.5.22` | `v1.5.22-shell-network-policy` | `src/safecode/shell/runner.py`、`src/safecode/sandbox/network.py` | shell 执行前强制 network policy |
| `v1.5.23` | `v1.5.23-approval-store-trust-boundary` | `src/safecode/hooks/approvals.py` | approval dir 禁止落在 project root |
| `v1.5.24` | `v1.5.24-security-docs-before-v1.6` | `docs/*`、`README.md`、`safe_code_agent_software_design_doc.md` | v1.5.21-1.5.23 文档 + guardrails 更新 |

## v1.6.x: Controlled Tooling and Subagents

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.6.0` | `v1.6.0-mcp-runner-readonly` | `src/safecode/mcp/runner.py`、`src/safecode/cli.py::mcp_call_readonly` | MCP 只读工具调用有 audit/runtime log；写工具、network disabled、过大输出被阻止 |
| `v1.6.1` | `v1.6.1-mcp-write-proposal-only` | `src/safecode/mcp/proposal.py`、`src/safecode/mcp/runner.py::propose_write`、`src/safecode/cli.py::mcp_propose_write` | MCP 写工具创建 `.sac/pending_mcp_call.json` proposal（不执行）；`sac mcp propose-write`/`sac mcp pending`/`sac mcp discard` 可用 |
| `v1.6.2` | `v1.6.2-subagent-readonly-runner` | `src/safecode/subagents/task.py`、`src/safecode/subagents/runner.py`、`src/safecode/cli.py::subagent_run_readonly` | 只读 subagent 写 `.sac/subagents/<id>/result.md`；`sac subagent run-readonly`/`sac subagent list`/`sac subagent show` 可用 |
| `v1.6.3` | `v1.6.3-subagent-merge-review` | `src/safecode/subagents/merge.py`、`src/safecode/cli.py::subagent_merge_review` | 合并 subagent 结果为 pending patch；`sac subagent merge-review ID... --target SUBAGENT_REVIEW.md` 可用 |
| `v1.6.4` | `v1.6.4-os-sandbox-research` | `src/safecode/sandbox/capabilities.py`、`src/safecode/sandbox/planner.py`、`src/safecode/cli.py::sandbox_status` | 检测 macOS/Linux/Docker sandbox 可用性；`sac sandbox status` 可用 |
| `v1.6.5` | `v1.6.5-tooling-security-evals` | `tests/test_tooling_security_evals.py` | 37 项安全评测覆盖 MCP/subagent/sandbox/跨模块边界 |

## v1.7.x: OS-Level Sandbox Containment

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.7.0` | `v1.7.0-sandbox-adapter-contract` | `src/safecode/sandbox/adapter.py`、`src/safecode/sandbox/factory.py`、`src/safecode/cli.py::sandbox_plan` | 生成 sandbox dry-run plan；`sac sandbox plan pwd` 显示计划不执行 |
| `v1.7.1` | `v1.7.1-macos-seatbelt-profile-plan` | `src/safecode/sandbox/seatbelt.py`、`src/safecode/sandbox/adapter.py::MacOSSeatbeltAdapter` | 生成 macOS .sb profile preview；`sac sandbox plan pwd` 显示 profile |
| `v1.7.2` | `v1.7.2-linux-bubblewrap-args-plan` | `src/safecode/sandbox/bubblewrap.py`、`src/safecode/sandbox/adapter.py::LinuxBubblewrapAdapter` | 生成 bwrap argv preview；`sac sandbox plan pwd` 在 Linux backend 下显示 bwrap 参数 |
| `v1.7.3` | `v1.7.3-docker-container-plan` | `src/safecode/sandbox/docker.py`、`src/safecode/sandbox/adapter.py::DockerSandboxAdapter` | 生成 docker run argv preview；`sac sandbox plan pwd` 在 Docker backend 下显示 docker 参数 |
| `v1.7.4` | `v1.7.4-sandbox-plan-security-evals` | `tests/test_sandbox_plan_security_evals.py` | 43 项跨 backend 安全评测覆盖 no-execution/network/filesystem/sensitive/audit/isolation |
| `v1.7.5` | `v1.7.5-sandbox-execution-gate` | `src/safecode/sandbox/execution.py`、`src/safecode/cli.py::sandbox_propose` | 审批门：`sac sandbox propose`/`pending`/`discard`/`execute` 可用；execute 拒绝真实执行 |
| `v1.7.6` | `v1.7.6-sandbox-approval-state` | `src/safecode/sandbox/approvals.py`、`src/safecode/sandbox/execution.py::SandboxExecutionGate` | 用户级审批：`sac sandbox approve`/`approvals`/`revoke` 可用；execute 区分 unapproved/approved-but-disabled |
| `v1.7.7` | `v1.7.7-sandbox-approval-security-evals` | `tests/test_sandbox_approval_security_evals.py` | 40 项审批安全评测覆盖 storage/binding/gate/CLI/audit/regression |
| `v1.7.8` | `v1.7.8-sandbox-execution-preflight` | `src/safecode/sandbox/preflight.py`、`src/safecode/cli.py::sandbox_preflight` | 统一 preflight 检查：`sac sandbox preflight` 显示所有检查项结果 |
| `v1.7.9` | `v1.7.9-sandbox-execution-preflight-evals` | `tests/test_sandbox_preflight_security_evals.py` | 30 项 preflight 安全评测覆盖 integrity/approval/cmd/network/filesystem/backend/audit/CLI |

## v1.8.x: Local Policy-Gated Sandbox Execution

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.8.0` | `v1.8.0-sandbox-execution-mvp` | `src/safecode/sandbox/execution.py::execute_pending`、`src/safecode/sandbox/adapter.py::NoopSandboxAdapter`、`src/safecode/cli.py::sandbox_execute` | Noop adapter 在 preflight 全通过时执行 ShellRunner；macOS/Linux/Docker 保持 dry-run；30 项安全评测 |
| `v1.8.1` | `v1.8.1-single-use-sandbox-approval` | `src/safecode/sandbox/approvals.py::SandboxExecutionApprovalStore.consume`、`src/safecode/sandbox/execution.py::execute_pending` | approval 单次消费；执行成功后不可重用；blocked preflight 不消费；7 项新安全评测 |
| `v1.8.2` | `v1.8.2-atomic-sandbox-approval-consumption` | `src/safecode/sandbox/approvals.py::claim_for_execution`、`src/safecode/sandbox/execution.py::execute_pending` | 原子 claim 关闭 TOCTOU 并发窗口；lock file + os.replace；stale lock 检测；13 项新安全评测 |
| `v1.8.3` | `v1.8.3-sandbox-execution-result-lifecycle` | `src/safecode/sandbox/execution.py::SandboxExecutionResultStore`、`src/safecode/cli.py::sandbox_executions` | 执行结果记录持久化 + 截断/脱敏；pending 在 execution/claim-failure 后清理；新增 CLI `sac sandbox executions`/`last-execution`；16 项新安全评测 |
| `v1.8.4` | `v1.8.4-sandbox-execution-audit-usability` | `src/safecode/sandbox/execution.py::_filter_record_data`、`src/safecode/cli.py::sandbox_executions` | 结果记录 schema 版本标记；前向兼容未知字段；CLI 按 status/backend/proposal_id 过滤；`sac sandbox status` 展示 execution 摘要；10 项新安全评测 |
| `v1.8.5` | `v1.8.5-sandbox-execution-detail-query` | `src/safecode/sandbox/execution.py::filter_by`、`src/safecode/cli.py::sandbox_execution_show` | filter_by 支持 limit/sort_order；CLI `sac sandbox execution show <id>` 详情视图；`sac sandbox executions --limit/--sort`；10 项新安全评测 |
| `v1.8.6` | `v1.8.6-sandbox-execution-result-maintenance` | `src/safecode/sandbox/execution.py::stats`、`src/safecode/sandbox/execution.py::prune`、`src/safecode/cli.py::sandbox_executions_stats` | stats() 聚合统计 + 磁盘占用；plan_prune() 预览 / prune() 安全删除；symlink/path-safety 防护；prune 绑定扫描到的源文件，避免 mismatched `proposal_id` 误删；CLI `sac sandbox executions stats`/`prune --keep-latest --dry-run/--yes`；14 项新安全评测 |
| `v1.8.7` | `v1.8.7-sandbox-execution-maintenance-audit` | `src/safecode/cli.py::sandbox_executions_prune` | confirmed prune 写入 `sandbox_execution_results_pruned` audit event；dry-run 不写 destructive event；元数据只含计数、过滤条件和截断 proposal ids；2 项新安全评测 |
| `v1.8.8` | `v1.8.8-sandbox-result-atomic-save` | `src/safecode/sandbox/execution.py::SandboxExecutionResultStore.save` | result record 使用同目录临时文件 + `os.replace` 原子写入；已有同名 symlink 被替换而不被跟随；replace 失败清理临时文件；2 项新安全评测 |
| `v1.8.9` | `v1.8.9-sandbox-proposal-atomic-save` | `src/safecode/sandbox/execution.py::SandboxExecutionProposalStore._write` | pending sandbox proposal 使用同目录临时文件 + `os.replace` 原子写入；broken symlink 被替换而不被跟随；replace 失败清理临时文件；2 项新安全评测 |
| `v1.8.10` | `v1.8.10-sandbox-approval-atomic-save` | `src/safecode/sandbox/approvals.py::SandboxExecutionApprovalStore._atomic_write_json` | approval approve/consume/claim 统一使用同目录随机临时文件 + `os.replace`；同名 symlink 被替换而不被跟随；replace 失败清理临时文件；2 项新安全评测 |

## v1.9.x: Interactive Agent Loop

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v1.9.0` | `v1.9.0-session-state` | `src/safecode/agent/session.py`、`src/safecode/cli.py::agent_status` | `.sac/session.json` 记录 goal/plan/current_step/pending_action/last_observation，可显示当前 session |
| `v1.9.1` | `v1.9.1-agent-step-command` | `src/safecode/agent/loop.py`、`src/safecode/cli.py::agent_step` | `sac agent step "goal"` 只执行一个 plan/tool-decision step，不直接越过安全门 |
| `v1.9.2` | `v1.9.2-agent-run-loop` | `src/safecode/agent/loop.py`、`src/safecode/cli.py::agent_run` | `sac agent run "goal" --max-steps 5` 可多步推进，遇到写入/执行审批时停下 |
| `v1.9.3` | `v1.9.3-tool-intent-router` | `src/safecode/agent/tools.py` | typed tool intents 覆盖 read/patch/shell/sandbox/MCP/subagent/report，未知 intent fail closed |
| `v1.9.4` | `v1.9.4-human-checkpoint-prompts` | `src/safecode/agent/approvals.py`、`src/safecode/cli.py` | patch apply、shell run、MCP write、sandbox execute 使用统一审批提示和 audit metadata |
| `v1.9.5` | `v1.9.5-agent-recovery` | `src/safecode/agent/session.py`、`src/safecode/logs/runtime.py` | `sac agent resume/abort/explain-last-failure` 可恢复或解释失败状态 |

## v2.0.x: Usable Local Coding Agent MVP

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.0.0` | `v2.0.0-real-llm-agent-contract` | `src/safecode/agent/schemas.py`、`src/safecode/llm/*` | LLM 输出 answer/plan/tool_intent/patch/stop_for_user 结构化并可校验 |
| `v2.0.1` | `v2.0.1-context-budget-manager` | `src/safecode/context/selector.py`、`src/safecode/context/collector.py` | context 打包有 token/byte budget、来源列表、截断说明 |
| `v2.0.2` | `v2.0.2-task-journal` | `src/safecode/state/`、`src/safecode/report/` | 每个 agent session 生成 plan/action/diff/command/failure/final summary journal |
| `v2.0.3` | `v2.0.3-test-detect-and-run` | `src/safecode/project/`、`src/safecode/shell/runner.py` | 自动识别 pytest/uv/npm 等测试命令，并通过 policy gate 提议执行 |
| `v2.0.4` | `v2.0.4-demo-workflow-suite` | `examples/`、`tests/` | FastAPI/CLI/docs/failing-test repair 四类 demo workflow 可回归运行 |
| `v2.0.5` | `v2.0.5-mvp-docs` | `README.md`、`docs/*` | install、model config、first task、safety、rollback 文档可按步骤跑通 |

## v2.1.x: Repository Intelligence

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.1.0` | `v2.1.0-code-map` | `src/safecode/index/` | repo map 输出 files/symbols/imports/tests/entrypoints |
| `v2.1.1` | `v2.1.1-test-build-detector` | `src/safecode/project/test_detector.py` | 检测 pytest、uv、npm、pnpm、gradle、maven、go、cargo 常见命令 |
| `v2.1.2` | `v2.1.2-runtime-consolidation` | `src/safecode/cli*.py`、`src/safecode/agent/loop.py`、`src/safecode/context/collector.py` | CLI 分组拆分、agent loop 接入 LLM plan/tool、context 接入 repo map/selector/budget，版本与占位模块同步 |
| `v2.1.3` | `v2.1.3-diff-planner` | `src/safecode/agent/planner.py` | patch 前预测 touched files，最终 patch scope 与计划不一致时提示 |
| `v2.1.4` | `v2.1.4-context-debug-command` | `src/safecode/cli_context.py::context_explain` | `PYTHONPATH=src python3 -m pytest tests/test_context_explain.py -v` / `uv run sac context explain "task"` |

## v2.2.x: Tool Ecosystem

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.2.0` | `v2.2.0-tool-schema-registry` | `src/safecode/tools/registry.py` | `PYTHONPATH=src python3 -m pytest tests/test_tool_schema_registry.py -q` / `uv run sac tools list` / `uv run sac tools inspect patch.propose` |
| `v2.2.1` | `v2.2.1-model-tool-call-adapter` | `src/safecode/tools/adapter.py`、`src/safecode/agent/tools.py` | `ToolCallAdapter` 在路由前校验 tool name/required args/arg types；`ToolIntentRouter` 接入 registry 元数据；`PYTHONPATH=src python3 -m pytest tests/test_tool_call_adapter.py -q` |
| `v2.2.2` | `v2.2.2-mcp-read-tool-loop` | `src/safecode/mcp/loop_executor.py`、`src/safecode/agent/loop.py`、`src/safecode/agent/tools.py` | read-only MCP tool intents route to `mcp.call_readonly` without approval; executed in loop with journal+audit; `PYTHONPATH=src python3 -m pytest tests/test_mcp_read_tool_loop.py -q` |
| `v2.2.3` | `v2.2.3-mcp-approved-write-execution` | `src/safecode/mcp/proposal.py`、`src/safecode/mcp/loop_executor.py`、`src/safecode/mcp/runner.py`、`src/safecode/agent/loop.py` | Approved MCP write proposals execute via `MCPApprovedWriteExecutor`; unapproved/rejected proposals blocked; journal mcp_call with `approved_write=True`; `PYTHONPATH=src python3 -m pytest tests/test_mcp_approved_write.py -q` |
| `v2.2.4` | `v2.2.4-subagent-orchestration` | `src/safecode/subagents/executor.py`、`src/safecode/tools/registry.py`、`src/safecode/agent/loop.py`、`src/safecode/state/journal.py` | `SubagentDispatchExecutor` runs bounded read-only investigations via `ReadonlySubagentRunner`; `subagent.dispatch` tool spec; `AgentLoop` routes subagent intents to executor and journals `subagent_dispatch` events; writes confined to `.sac/subagents/`; fails closed; `PYTHONPATH=src python3 -m pytest tests/test_subagent_orchestration.py -q` |
| `v2.2.5` | `v2.2.5-subagent-result-merge-policy` | `src/safecode/subagents/merge_policy.py` | `SubagentFinding` and `MergedSubagentContext` frozen dataclasses; `merge_subagent_findings()` with order-preserving dedup, successful-only content merge, blocked/error provenance, and deterministic max_observations/max_files caps; never raises on empty input; `AgentLoop` journal payload compatible with `SubagentFinding` fields; `PYTHONPATH=src python3 -m pytest tests/test_subagent_orchestration.py -q` |
| `v2.2.6` | `v2.2.6-subagent-findings-context` | `src/safecode/subagents/journal_adapter.py`、`src/safecode/agent/loop.py` | `findings_from_journal_events()` converts `subagent_dispatch` journal events to `SubagentFinding`; `merge_journal_subagent_findings()` produces `MergedSubagentContext`; `AgentLoop._enrich_with_subagent_findings()` injects merged findings into `choose_tool` context as `"subagent_findings"`; malformed payloads skipped (fail closed); blocked subagents contribute only errors/provenance; execution behavior unchanged; `PYTHONPATH=src python3 -m pytest tests/test_subagent_orchestration.py -q` |

## v2.3.x: Developer Experience

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.3.0` | `v2.3.0-interactive-tui` | `src/safecode/tui/`、`src/safecode/cli_tui.py` | `sac tui dashboard` 用 Rich 展示 session、plan、pending action/approval、pending diff、journal history；read-only；`PYTHONPATH=src python3 -m pytest tests/test_tui_dashboard.py -q` |
| `v2.3.1` | `v2.3.1-config-wizard` | `src/safecode/setup.py`、`src/safecode/cli.py::setup` | `sac setup` 写入 `.sac/config.toml` 和 `.sac/setup.env`，覆盖 model/network/approval dirs/safety preset，默认不覆盖已有配置；`PYTHONPATH=src python3 -m pytest tests/test_setup_wizard.py -q` |
| `v2.3.2` | `v2.3.2-ide-bridge-mvp` | `src/safecode/ide/`、`src/safecode/cli_ops.py::ide_app` | `sac ide open-diff` 输出 materialized pending diff URI/path；`sac ide open-files` 输出 selected files URI/path；manifest 暴露 IDE bridge commands；`PYTHONPATH=src python3 -m pytest tests/test_ide_bridge.py -q` |
| `v2.3.3` | `v2.3.3-install-update-polish` | `pyproject.toml`、`src/safecode/__init__.py`、`src/safecode/doctor.py` | package version 同步；`sac version` 输出版本和 update hint；`sac doctor` 覆盖 config、`.sac/`、approval env；`docs/install-update.md`；`PYTHONPATH=src python3 -m pytest tests/test_install_update_polish.py -q` |
| `v2.3.4` | `v2.3.4-onboarding-examples` | `examples/`、`docs/tutorials/`、`src/safecode/demo/workflows.py` | bug fix、feature edit、docs edit、safe shell task 四个教程；`safe-shell-status` demo workflow 可 materialize；`PYTHONPATH=src python3 -m pytest tests/test_onboarding_examples.py -q` |
| `v2.3.5` | `v2.3.5-honest-surface` | `src/safecode/cli_sandbox.py`、`src/safecode/cli_mcp.py`、`src/safecode/cli_subagent.py`、`docs/` | CLI/docs 明确当前边界：Noop 是唯一执行 backend；macOS/Linux/Docker 为 plan-only/dry-run；MCP 是 subprocess JSON shim；subagent 是 read-only context/result collector；`PYTHONPATH=src python3 -m pytest tests/test_cli_output_honesty.py -q` |
| `v2.3.6` | `v2.3.6-agent-loop-patch-path` | `src/safecode/agent/loop.py`、`src/safecode/agent/tools.py`、`src/safecode/llm/mock.py`、`src/safecode/patch/` | `sac agent run "goal"` 对 write-class plan item 生成 `.sac/pending_patch.json` 并停在 approval；legacy `sac edit/apply` 不破坏；`PYTHONPATH=src python3 -m pytest tests/test_agent_loop_patch.py -q` |
| `v2.3.7` | `v2.3.7-universal-gate-and-migrations` | `src/safecode/tools/`、`src/safecode/cli_*.py`、`src/safecode/state/migrations.py` | 所有 CLI 写入/执行/工具通信路径先经过 ToolCallAdapter/ToolCallGate；持久化 state records 带 `_schema_version` 并支持 migrate-on-load；`PYTHONPATH=src python3 -m pytest tests/test_tool_call_gate.py tests/test_state_migrations.py -q` |

## v2.4.x: Real Sandbox Backends

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.4.0` | `v2.4.0-docker-execution-preview` | `src/safecode/sandbox/docker.py` | opt-in Docker execution path first, because it is most uniform across macOS/Linux/CI; fixed allowlisted image, network forced off, backend-specific eval |
| `v2.4.1` | `v2.4.1-macos-seatbelt-execution-preview` | `src/safecode/sandbox/seatbelt.py` | opt-in macOS Seatbelt execution path with narrow allowlist and on-host eval |
| `v2.4.2` | `v2.4.2-linux-bubblewrap-execution-preview` | `src/safecode/sandbox/bubblewrap.py` | opt-in Bubblewrap execution path with filesystem/network containment eval |
| `v2.4.3` ✅ | `v2.4.3-cross-backend-security-evals` | `tests/test_sandbox_cross_backend_security_evals.py` | 82 cross-backend security evals pass: shell=False, hash-before-binary, network-off-default, no --privileged, env-not-leaked, filesystem-boundary, sensitive-path-rejected, approval-claimed-first, result-lifecycle, env-not-in-audit |

## v2.5.x: Reliability and Evaluation

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.5.0` ✅ | `v2.5.0-task-eval-format` | `src/safecode/eval/fixtures.py`, `src/safecode/eval/loader.py` | 71 tests pass: TaskEvalFixture (RepoFixture, ExpectedOutcome, SafetyExpectations), FixtureLoadError, load_fixture/load_fixture_from_dict/load_fixtures_from_dir, schema versioning, stable JSON round-trip |
| `v2.5.1` ✅ | `v2.5.1-agent-replay-runner` | `src/safecode/eval/runner.py` | 68 tests pass: TaskReplayRunner (inline/local workspace, setup_commands, validation_commands, diff/file/output/exit-code constraints, forbidden_changed_files, safety forbidden_file_writes/forbidden_commands, audit_events_status, network_intent, timeout) |
| `v2.5.2` ✅ | `v2.5.2-failure-taxonomy` | `src/safecode/eval/failures.py` | 50 tests pass: FailureCategory enum (11 values), ClassifiedFailure (frozen dataclass, as_dict), classify_replay_result (passes→[], error→setup, structured signals for forbidden_file_write/command_blocked, keyword-pattern for forbidden_file_changed/validation/timeout/setup/unknown), ReplayResult.classified_failures backward-compatible field, runner integration end-to-end |
| `v2.5.3` ✅ | `v2.5.3-quality-dashboard-report` | `src/safecode/report/dashboard.py` | 112 tests pass: DashboardRenderer (render_markdown, render_html), ReportSummary, build_summary; covers empty/passing/failing/mixed results, failure category aggregation, per-fixture status, classified failures with category/reason/detail, audit_events_status, network_intent, forbidden command/file-write violations, HTML escaping, pipe escaping in Markdown tables, determinism, backward-compat with v2.5.2 ReplayResult |
| `v2.5.4` ✅ | `v2.5.4-performance-budgets` | `src/safecode/trace/budget.py`, `src/safecode/eval/runner.py` | `PerformanceBudget` (frozen dataclass): context_size_bytes, total_command_duration_ms, llm_latency_ms, disk_growth_bytes; `ReplayResult.performance_budget` backward-compatible field; 40 tests pass |

## v2.6.x: Product Hardening

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.6.0` ✅ | `v2.6.0-policy-presets` | `src/safecode/config.py` | `POLICY_PRESETS`, `normalize_policy_name()`, `apply_policy_preset()` added; POLICY_ORDER updated for all five names; `PYTHONPATH=src python3 -m pytest tests/test_policy_presets.py tests/test_security_hardening.py::test_project_config_cannot_lower_user_security -q` → 75 tests pass |
| `v2.6.1` ✅ | `v2.6.1-migration-hardening` | `src/safecode/config.py`, `src/safecode/setup.py` | `KNOWN_POLICY_NAMES`, `is_known_policy_name()` added; `_stricter_policy()` hardened (unknown right never overrides known left); `load()` warns+skips unknown `SAFECODE_POLICY`; `write_setup()` accepts all 5 names; `PYTHONPATH=src python3 -m pytest tests/test_migration_hardening.py tests/test_policy_presets.py tests/test_setup_wizard.py -q` → 39+75+5 tests pass |
| `v2.6.2` ✅ | `v2.6.2-release-version-consistency` | `src/safecode/release/version_guard.py` | `check_version_consistency()` guards pyproject/runtime drift |
| `v2.6.3` ✅ | `v2.6.3-release-checklist-polish` | `src/safecode/release/check.py` | `sac release check` reports version and working-tree state |
| `v2.6.4` ✅ | `v2.6.4-policy-docs-hardening` | `README.md`, `docs/install-update.md` | policy preset docs clarify canonical names, aliases, and unknown-policy behavior |
| `v2.6.5` ✅ | `v2.6.5-release-smoke-test` | `src/safecode/release/smoke.py` | `sac release smoke` validates import, CLI version, version consistency, policy names, and docs |
| `v2.6.6` ✅ | `v2.6.6-tag-version-consistency` | `src/safecode/release/version_guard.py` | exact git tag must match package version |
| `v2.6.7` ✅ | `v2.6.7-release-check-next-steps` | `src/safecode/release/check.py` | release check next-step output avoids duplicate commit/tag advice |
| `v2.6.8` ✅ | `v2.6.8-release-metadata-index` | `src/safecode/release/metadata.py` | `sac release meta` audits version notes, tags, and SKILL baseline |
| `v2.6.9` ✅ | `v2.6.9-release-docs-guard` | `src/safecode/release/docs_guard.py` | docs guard verifies version note, SKILL baseline, and release command docs |
| `v2.6.10` ✅ | `v2.6.10-release-version-bump-helper` | `src/safecode/release/bump.py` | `sac release bump` updates canonical version files without committing/tagging |
| `v2.6.11` ✅ | `v2.6.11-release-preflight` | `src/safecode/release/preflight.py` | `sac release preflight` aggregates release check, smoke, metadata, and docs |
| `v2.6.12` ✅ | `v2.6.12-version-note-index-validation` | `src/safecode/release/metadata.py` | version-note heading and duplicate-note validation |
| `v2.6.13` ✅ | `v2.6.13-release-workflow-docs` | `README.md`, `docs/install-update.md` | release flow documents bump/test/commit/tag/gate order |
| `v2.6.14` ✅ | `v2.6.14-release-command-ux-polish` | `src/safecode/release/ux.py` | release commands share PASS/FAIL status and next-step output |
| `v2.6.15` ✅ | `v2.6.15-release-changelog-generator` | `src/safecode/release/changelog.py` | `sac release changelog` renders Markdown from version notes |
| `v2.6.16` ✅ | `v2.6.16-release-checklist-upgrade` | `src/safecode/release/checklist.py` | release checklist mirrors bump/test/commit/tag/preflight flow |
| `v2.6.17` ✅ | `v2.6.17-ci-workflow-draft` | `.github/workflows/ci.yml` | CI draft runs pytest plus non-exact-tag release smoke/meta/changelog |
| `v2.6.18` ✅ | `v2.6.18-doctor-release-diagnostics` | `src/safecode/doctor.py` | `sac doctor` reports release version/tag/docs/preflight status |
| `v2.6.19` ✅ | `v2.6.19-policy-audit-command` | `src/safecode/policy/audit.py` | `sac config policy-audit` audits policy names, aliases, unknown values, and invariants |
| `v2.6.20` ✅ | `v2.6.20-security-review-documentation` | `docs/security/product-security-review-v2.6.md` | product security review covers config, sandbox, hooks, release gates, and trust boundaries |
| `v2.6.21` ✅ | `v2.6.21-final-signoff` | `src/safecode/release/signoff.py` | final signoff verifies exact tag, release check, and preflight |

## v2.7.x: Audit Consolidation

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.7.0` ✅ | `v2.7.0-audit-consolidation-baseline` | `src/safecode/config.py`, `src/safecode/doctor.py`, `src/safecode/hooks/approvals.py`, `src/safecode/release/bump.py`, `src/safecode/release/changelog.py`, `src/safecode/cli_sandbox.py` | policy presets apply on load; doctor --release opt-in; Noop backend labeled policy-gated; hook approval version schema-scoped; bump skips test files; changelog --recent N; `PYTHONPATH=src python3 -m pytest -q` → 1871 tests pass |
| `v2.7.1` ✅ | `v2.7.1-hook-approval-project-binding` | `src/safecode/hooks/approvals.py` | `config_hash()` includes project root hash; approvals cannot carry across project roots; `test_approval_does_not_carry_across_projects` added; `PYTHONPATH=src python3 -m pytest -q` → 1872 tests pass |
| `v2.7.2` ✅ | `v2.7.2-versions-json-sync` | `src/safecode/release/versions_sync.py` | `sync_versions_json()` appends missing git tags and updates `current_implemented_tag`; `sac release sync-versions-json [--dry-run]` CLI; stale detection test; `PYTHONPATH=src python3 -m pytest -q` → 1881 tests pass |
| `v2.7.3` ✅ | `v2.7.3-subagent-finding-redaction-logging` | `src/safecode/agent/loop.py` | subagent findings redacted via `redact_secrets()` before context injection; broad except replaced with `RuntimeWarning` log; 6 new redaction tests; `PYTHONPATH=src python3 -m pytest -q` → 1887 tests pass |
| `v2.7.4` ✅ | `v2.7.4-release-surface-honesty-lite` | `src/safecode/cli_ops.py`, `docs/install-update.md` | signoff/checklist/check/smoke/meta help text labelled [internal]/[advanced]; docs main flow clarified to bump→pytest→tag→preflight; 18 new CLI surface tests; `PYTHONPATH=src python3 -m pytest -q` → 1905 tests pass |
| `v2.7.5` ✅ | `v2.7.5-quickstart-command` | `src/safecode/cli_quickstart.py`, `src/safecode/cli.py` | new `sac quickstart` command: checks/creates .sac/config.toml, displays provider/policy, recommends demo workflow, --demo materializes seed project, prints next-step commands; never claims edit/apply ran; 8 new tests; `PYTHONPATH=src python3 -m pytest -q` passes |
| `v2.7.6` ✅ | `v2.7.6-cli-help-surface-trim` | `src/safecode/cli.py`, `src/safecode/cli_ops.py` | queue/memory/progress/rules/tui/ide/export hidden from `sac --help` (still callable); core commands (setup/quickstart/ask/edit/apply/rollback/run/doctor/version) remain visible; 23 new tests; `PYTHONPATH=src python3 -m pytest -q` passes |
| `v2.7.7` ✅ | `v2.7.7-agent-loop-stub-eval-mode` | `src/safecode/eval/loop_runner.py`, `src/safecode/agent/loop.py`, `src/safecode/agent/orchestrator.py`, `src/safecode/cli_ops.py` | ScriptedLLMClient with explicit scripted sequences (not keyword matching); LLMContractViolation fail-closed; docs-edit and python-function-fix fixtures; `sac eval --mode loop`; 13 new tests; `PYTHONPATH=src python3 -m pytest -q` → 1949 tests pass |
| `v2.7.8` ✅ | `v2.7.8-versions-governance-preflight` | `src/safecode/release/versions_governance.py`, `src/safecode/release/preflight.py` | check_versions_governance: versions.json staleness + SKILL.md baseline tag contradiction detection; integrated into release preflight; next-step hint for sync-versions-json; injectable git_tags for fixture-based tests; 11 new tests; `PYTHONPATH=src python3 -m pytest -q` → 1960 tests pass |
| `v2.7.9` ✅ | `v2.7.9-release-surface-collapse-lite` | `src/safecode/release/signoff.py`, `src/safecode/release/checklist.py`, `docs/install-update.md` | signoff runtime output labelled deprecated; checklist runtime output labelled planning helper/not a release gate; docs main flow adds sync-versions-json; 10 new tests; `PYTHONPATH=src python3 -m pytest -q` → 1970 tests pass |

## v2.8.x: Consolidation and CLI Honesty (planned)

Active plan: `docs/version-plans/v2.8-to-v3.0-product-architecture-roadmap.md`.

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.8.0` ✅ | `v2.8.0-diagnostic-core` | `src/safecode/core/diagnostic.py` | `Diagnostic` / `DiagnosticGroup` / `DiagnosticStatus` (PASS/FAIL/WARN/SKIP) + `aggregate_status`/`all_passed`; 32 new tests in `tests/test_core_diagnostic.py`; no user-facing CLI change |
| `v2.8.1` ✅ | `v2.8.1-diagnostic-migration-doctor-release` | `src/safecode/doctor.py`, `src/safecode/release/check.py`, `src/safecode/release/smoke.py`, `src/safecode/release/preflight.py`, `src/safecode/release/signoff.py`, `src/safecode/policy/audit.py` | `to_diagnostics()` / `run_diagnostics()` / `collect_smoke_diagnostics()` produce typed diagnostics; legacy `DoctorCheck`/`SmokeTestCase`/`ReleaseCheckResult` shapes preserved; CLI output unchanged; 18 new tests in `tests/test_diagnostic_migration.py` |
| `v2.8.2` | `v2.8.2-sandbox-backend-strategy-split` | `src/safecode/sandbox/`, `src/safecode/cli_sandbox.py` | backend detection/recommendation separated from proposal/execution logic; sandbox tests pass |
| `v2.8.3` | `v2.8.3-agent-loop-typed-actions` | `src/safecode/agent/loop.py` | pending agent actions become typed objects; CLI owns rendering |
| `v2.8.4` | `v2.8.4-mcp-shim-schema-prep` | `src/safecode/mcp/` | typed MCP metadata prep with keyword fallback unchanged when schema is absent |
| `v2.8.5` ✅ | `v2.8.5-release-surface-collapse-full` | `src/safecode/cli_ops.py`, `docs/install-update.md` | `sac release --help` shows only preflight/bump/changelog; checklist/check/smoke/meta/signoff hidden but callable; signoff emits RuntimeWarning; 25 new tests |
| `v2.8.6` ✅ | `v2.8.6-cli-sandbox-module-split` | `src/safecode/cli_sandbox_status.py`, `src/safecode/cli_sandbox_proposal.py`, `src/safecode/cli_sandbox_executions.py` | sandbox CLI split: status/plan → cli_sandbox_status; propose/pending/discard/execute/approve/approvals/revoke/preflight → cli_sandbox_proposal; executions sub-app/last-execution/execution → cli_sandbox_executions; thin registry in cli_sandbox.py; 2148 tests pass |
| `v2.8.7` ✅ | `v2.8.7-subagent-finding-redaction-at-journal-boundary` | `src/safecode/subagents/journal_adapter.py`, `src/safecode/agent/loop.py` | producer-side redaction in `_event_to_finding()` (summary, observations, errors); consumer-side `RuntimeWarning` on producer gap; `sync_versions_json` sorts merged_tags by semver; 10 new tests; 2158 tests pass |
| `v2.8.8` ✅ | `v2.8.8-shell-exit-code-honesty` | `src/safecode/cli_core.py`, `docs/install-update.md` | `sac run` returns 125 for approval-required and 126 for policy-blocked; `SAFECODE_RUN_LEGACY_EXIT_CODE=1` opt-out; 13 new tests |
| `v2.8.9` ✅ | `v2.8.9-audit-and-hook-event-dedup` | `src/safecode/hooks/runner.py` | `hook_skipped_by_policy` no longer produces duplicate `hook_approval_required`; distinct event type; backward-compatible verification; 13 new tests |
| `v2.8.10` ✅ | `v2.8.10-final-v28-baseline-sync` | `pyproject.toml`, `src/safecode/__init__.py`, `uv.lock`, `.claude/versions.json`, `.claude/skills/current/SKILL.md` | metadata-only final v2.8 baseline after out-of-order v2.8.6/v2.8.7 cleanup; package/runtime/current tag synchronized to v2.8.10 |

## v2.9.x: Deterministic Evidence and Contract Preparation (planned)

Active plan: `docs/version-plans/v2.8-to-v3.0-product-architecture-roadmap.md`.

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.9.0` ✅ | `v2.9.0-agent-loop-fixture-expansion` | `src/safecode/eval/loop_runner.py` | Six scripted fixtures; `LoopFailureCategory`/`ClassifiedLoopFailure` typed failure categories; `RecoverableContractFailure` stub for bounded retry; 31 new tests in `tests/test_agent_loop_fixture_expansion.py`; `sac eval --mode loop` exits 0 |
| `v2.9.1` ✅ | `v2.9.1-agent-loop-error-recovery` | `src/safecode/agent/schemas.py`, `src/safecode/agent/loop.py`, `src/safecode/state/journal.py` | `RecoverableContractFailure` in schemas; `AgentLoop.step()` bounded retry (one); `loop_retry` journal event; `record_loop_retry()`; 18 new tests in `tests/test_agent_loop_error_recovery.py` |
| `v2.9.2` ✅ | `v2.9.2-eval-replay-baseline-snapshot` | `src/safecode/eval/loop_runner.py`, `tests/snapshots/loop/` (6 JSON files) | `LoopStepTrace`/`LoopEvalTrace` frozen dataclasses; `build_loop_eval_trace()` derives deterministic trace from fixture definition; 6 snapshot JSON files; 30 new tests in `tests/test_eval_replay_baseline_snapshot.py` |
| `v2.9.3` ✅ | `v2.9.3-eval-loop-mode-ci-gate` | `.github/workflows/ci.yml`, `tests/test_eval_loop_mode_ci_gate.py` | CI has advisory `loop-eval` job running `sac eval --mode loop`; no provider credentials; 13 new tests |
| `v2.9.4` ✅ | `v2.9.4-mcp-tools-list-schema-shim` | `src/safecode/mcp/schema.py`, `src/safecode/mcp/runner.py`, `src/safecode/mcp/loop_executor.py` | `MCPSchemaStore.tools_list()` and `classify_all()`; `MCPReadOnlyRunner` and `MCPReadToolExecutor` accept optional `schemas` list; `classify_with_schema` wired into classification gate; 24 new tests in `tests/test_mcp_tools_list_schema_shim.py` |
| `v2.9.5` ✅ | `v2.9.5-mcp-call-schema-arg-validation` | `src/safecode/mcp/schema.py`, `src/safecode/mcp/runner.py` | `MCPSchemaArg` frozen dataclass; `arg_schemas` field on `MCPToolSchema`; `validate_call_args()`; runner blocks missing-required and extra args when schema has `arg_schemas`; 29 new tests in `tests/test_mcp_call_schema_arg_validation.py` |
| `v2.9.6` ✅ | `v2.9.6-subagent-journal-payload-versioning` | `src/safecode/subagents/payload.py`, `src/safecode/subagents/journal_adapter.py`, `src/safecode/state/journal.py` | `SubagentDispatchPayload` versioned Pydantic model; tolerant loading with `payload_version` default; `RuntimeWarning` for invalid/future payloads; `record_subagent_dispatch` adds `payload_version=1`; 30 new tests including adversarial in `tests/test_subagent_journal_payload_versioning.py` (v2.9.7 folded in) |
| `v2.9.8` ✅ | `v2.9.8-tool-spec-registry-versioning` | `src/safecode/tools/registry.py`, `tests/snapshots/registry/tool_registry_v1.json` | `REGISTRY_SCHEMA_VERSION="1"`; `ToolSpec.version="1.0.0"` default; 14 new tests (6 version + 8 snapshot); narrow snapshot covers name/version/permission/risk/approval/arg-schema; no prose frozen |
| `v2.9.9` ✅ | `v2.9.9-public-contract-snapshot-tests` | `tests/snapshots/contracts/`, `tests/test_public_contract_snapshots.py` | 5 contract snapshots (config, pending patch, audit event, sandbox lifecycle, eval trace); reuses v2.9.8 tool registry snapshot; 51 new tests; no prose frozen; experimental surfaces excluded |

## v3.0.0: Stable Local Safety Runtime (planned)

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.0.0` ✅ | `v3.0.0-public-contract-stabilization` | `docs/public-contracts.md`, `README.md` | 8 stable contracts documented (config precedence, pending patch, audit hash-chain, sandbox lifecycle, tool registry, eval trace, CLI workflows, release command policy); 6 experimental surfaces explicitly labeled; all v2.9.9 snapshot tests pass |

## v3.1.x: Autopilot + JSON Output

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.1.0` ✅ | `main` | `src/safecode/cli_shared_json.py`, `src/safecode/cli_core.py`, `src/safecode/cli_ops.py`, `src/safecode/cli_agent.py` | `--json` flag on ask/edit/apply/run/doctor/version/release preflight/agent run; `CLIJSONResponse`/`render_json()` in `cli_shared_json.py`; `get_last_failure_context()` in journal; `--retry-from-last-failure` on edit; 35 new tests in `tests/test_cli_json_output.py` + `tests/test_agent_autopilot.py`; `PYTHONPATH=src python3 -m pytest tests/test_cli_json_output.py tests/test_agent_autopilot.py -q` → 35 pass; full regression 2429 pass |
| `v3.1.1` ✅ | `main` | `src/safecode/agent/session.py`, `src/safecode/cli_agent.py` | `AgentSessionStore.load_by_id()`; `agent_resume` gains optional `session_id` arg with ID verification and contract_failed guard; 17 new tests in `tests/test_agent_resume.py` + `tests/test_edit_retry.py`; `PYTHONPATH=src python3 -m pytest tests/test_agent_resume.py tests/test_edit_retry.py -q` → 17 pass; full regression 2446 pass |

## v3.2.x: LLM Retry + Cost Accounting

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.2.0` ✅ | `main` | `src/safecode/llm/retry.py`, `src/safecode/llm/cost.py`, `src/safecode/llm/openai_client.py`, `src/safecode/doctor.py` | `retry_call()` with jitter for 429/503/URLError; `TokenUsage`/`SessionCostAccumulator` writing `.sac/sessions/<id>/cost.json`; wired into OpenAI client; `last_session_cost` diagnostic in `sac doctor`; 27 new tests in `tests/test_llm_retry.py` + `tests/test_llm_cost_accounting.py`; full regression 2473 pass |
| `v3.2.1` ✅ | `main` | `src/safecode/llm/stream.py`, `src/safecode/llm/openai_client.py`, `src/safecode/llm/mock.py` | `StreamChunk`/`StreamResult`/`StreamError`/`aggregate_chunks()`/`parse_sse_line()`/`parse_sse_stream()`/`SupportsStreaming` protocol; `stream_chat()` on `OpenAICompatibleLLMClient` with injectable `_lines_fn`; `stream_chat()` on `MockLLMClient`; 31 new tests in `tests/test_llm_streaming.py`; full regression 2504 pass |
| `v3.2.2` ✅ | `main` | `src/safecode/agent/schemas.py`, `src/safecode/llm/openai_client.py` | `validate_provider_json()` returns `AgentContractResponse | RecoverableContractFailure`; `_chat_agent_json` wired to use it; `choose_tool()` returns `RecoverableContractFailure` on soft failures; `plan()` raises ValueError on soft failures; 38 new tests in `tests/test_llm_structured_output.py`; full regression 2542 pass |
| `v3.2.3` ✅ | `main` | `src/safecode/llm/anthropic_client.py`, `src/safecode/llm/factory.py` | `AnthropicLLMClient` implements full 4-method contract + `stream_chat()`; factory adds `anthropic` provider key; reuses retry/cost/streaming/validation infrastructure; `_parse_anthropic_sse` for Anthropic SSE events; 30 new tests in `tests/test_llm_anthropic_client.py`; full regression 2572 pass |
| `v3.2.4` ✅ | `main` | `src/safecode/config.py`, `src/safecode/llm/factory.py` | `LLMConfig` gains `fallback_provider/model/base_url`; `FanOutLLMClient` routes `RuntimeError` to fallback, preserves policy/contract gates; `_log_fanout` redacts prompts; 24 new tests in `tests/test_llm_provider_fanout.py`; full regression 2596 pass |
| `v3.2.5` ✅ | `main` | `.github/workflows/ci.yml`, `tests/live/`, `tests/test_ci_live_lane.py` | Advisory `live-provider` CI job gated by `ENABLE_LIVE_LLM_TESTS` repo var; `tests/live/conftest.py` skips without `SAFECODE_LIVE_TESTS=1`; 21 new tests in `tests/test_ci_live_lane.py`; 2 live tests skipped in baseline; full regression 2617 pass, 2 skipped |
| `v3.2.6` ✅ | `main` | `docs/providers.md`, `docs/public-contracts.md`, `tests/snapshots/contracts/provider_contract_schema.json`, `tests/test_provider_contract_snapshot.py`, `README.md` | Provider layer promoted to stable documented contract; `docs/providers.md` full reference; section 9 added to `public-contracts.md`; machine-readable snapshot with all contract invariants; 66 new tests in `tests/test_provider_contract_snapshot.py`; no runtime changes; full regression 2683 pass, 2 skipped |

## v3.3.x: MCP stdio Transport (experimental)

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.3.0` ✅ | `main` | `src/safecode/mcp/transport_stdio.py` | `call_stdio(argv, method, params, ...)` — one-shot stdio JSON-RPC; argv-only/no shell; timeout kill; max-output-bytes limit; fail-closed on malformed JSON/id-mismatch/timeout/no-output; stderr truncated; params not in error text; returns `StdioTransportResult`; not wired into runner; MCP remains experimental; 45 new tests in `tests/test_mcp_transport_stdio.py`; `PYTHONPATH=src python3 -m pytest tests/test_mcp_transport_stdio.py -q` → 45 pass |
| `v3.3.1` ✅ | `main` | `src/safecode/mcp/config.py` | stdio server config argv validation (experimental); `MCPServerConfig.argv: tuple[str,...] \| None`; `StdioArgvError`; `validate_stdio_argv(raw) -> tuple[str,...]` — rejects shell strings, empty list, non-list, non-string items, never puts content in error text; `resolve_stdio_argv(servers, name) -> list[str]` — fails closed on missing server/missing argv/empty argv/invalid types; `MCPConfigStore.list_servers()` parses and validates `argv` from TOML; `call_stdio` not invoked; no tools/list or tools/call; existing MCP behavior unchanged; 37 new tests in `tests/test_mcp_stdio_config.py`; `PYTHONPATH=src python3 -m pytest tests/test_mcp_stdio_config.py -q` → 37 pass |
| `v3.3.2` ✅ | `main` | `src/safecode/mcp/discovery.py` | experimental one-shot stdio tools/list discovery; `StdioDiscoveryResult(frozen dataclass)`: `success`, `schemas`, `error`, `skipped_count`, `server_name`; `discover_stdio_tools(server_name, argv, *, timeout_seconds, max_output_bytes) -> StdioDiscoveryResult` — calls `call_stdio("tools/list")`, fails closed on transport error/non-dict result/missing tools key/non-list tools; malformed individual entries skipped with `skipped_count`; classification always `"unknown"`; error text never contains argv content; `_parse_tool_entry` helper; no tools/call; no runner wiring; existing `MCPDiscovery` unchanged; 60 new tests in `tests/test_mcp_stdio_discovery.py`; `PYTHONPATH=src python3 -m pytest tests/test_mcp_stdio_discovery.py -q` → 60 pass |
| `v3.3.3` ✅ | `main` | `src/safecode/mcp/schema.py` | pure schema merge helper (experimental); `merge_discovered_schemas(static, discovered) -> tuple[MCPToolSchema, ...]` — matches by (server, tool); static classification always wins; discovered fills description/args only when static is absent (empty); arg_schemas always from static; discovered-only tools appended; static order preserved; duplicate discovered entries use first occurrence; cross-server entries never merged; pure: no I/O, no subprocess; existing `MCPSchemaStore` API and static behavior unchanged; 45 new tests in `tests/test_mcp_schema_merge.py`; `PYTHONPATH=src python3 -m pytest tests/test_mcp_schema_merge.py -q` → 45 pass |
| `v3.3.4` ✅ | `main` | `src/safecode/mcp/stdio_runner.py` | experimental read-only stdio runner adapter (new module); `StdioReadOnlyAdapter(server_name, argv, schemas, *, timeout_seconds, max_output_bytes)` — disabled by default, not wired into MCPReadOnlyRunner; classification gate: read→executes via call_stdio("tools/call"), write/unknown→blocked(exit_code=126); `StdioCallResult(frozen dataclass)`: server, tool, classification, output, error, exit_code, success, blocked; `_extract_output`: MCP content-block format + JSON fallback; call_args never in error text; RuntimeWarning on block/failure; never raises; 51 new tests in `tests/test_mcp_stdio_runner.py`; `PYTHONPATH=src python3 -m pytest tests/test_mcp_stdio_runner.py -q` → 51 pass |
| `v3.3.5` ✅ | `main` | `src/safecode/cli_mcp.py` | experimental CLI stdio inspect/discover surface; `sac mcp stdio-status <server>` — reads MCPConfigStore, reports whether stdio argv is configured, clearly labeled EXPERIMENTAL, no subprocess launched, `--json` support via `CLIJSONResponse`/`render_json`; `sac mcp stdio-discover <server>` — resolves argv via `resolve_stdio_argv`, calls `discover_stdio_tools`, shows tool table labeled EXPERIMENTAL, no tools/call issued, `--timeout`, `--json` support; both commands fail closed on missing server or missing argv; error text never contains argv content; existing MCP commands unchanged; 56 new tests in `tests/test_mcp_cli_stdio.py`; `PYTHONPATH=src python3 -m pytest tests/test_mcp_cli_stdio.py -q` → 56 pass |
| `v3.3.7` ✅ | `main` | *(metadata only)* | full-regression signoff for v3.3.0–v3.3.6 MCP stdio series; no runtime changes; no new tests; `PYTHONPATH=src python3 -m pytest -q` → 3014 passed, 2 skipped, 50 warnings; all warnings are expected by-design emissions |
| `v3.3.6` ✅ | `main` | `tests/test_mcp_stdio_adversarial.py` | adversarial hardening of v3.3.1-v3.3.5 MCP stdio surface; no new features; no promotion to stable; 37 new adversarial tests across 8 classes: (1) server-supplied "classification" field in JSON response never overrides "unknown" classification; (2) CLI `stdio-discover` has no path to `StdioReadOnlyAdapter` — verified via mock assertion and import absence; (3) `--timeout` flag verified to propagate to `discover_stdio_tools` via mock-call inspection; (4) `StdioReadOnlyAdapter` gates on static classification after `merge_discovered_schemas` — static "write" wins, discovered-only "unknown" blocked; (5) shell string argv in TOML config raises `StdioArgvError` at parse time, error text never contains argv content; (6) oversized server response fails closed, error text does not expose server content; (7) error text from all failure paths verified to never contain caller-supplied values, secrets, or server response data; (8) shell metacharacter tool names blocked by classification gate before any subprocess call; `PYTHONPATH=src python3 -m pytest tests/test_mcp_stdio_adversarial.py -q` → 37 pass |

## v3.4.x: Subagent Orchestration and Synthesis

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.4.0` ✅ | `main` | `src/safecode/subagents/pool.py` | Bounded concurrent subagent pool (T-3.4.0-A); `SubagentPool(project_root, max_workers=2)` runs requests with `ThreadPoolExecutor`; default max 2 (env `SAFECODE_SUBAGENT_MAX`); invalid env values warn + fall back safely; results sorted by `task_id`; worker exceptions isolated; 22 new tests in `tests/test_subagent_pool.py`; `PYTHONPATH=src python3 -m pytest tests/test_subagent_pool.py tests/test_subagent_orchestration.py -q` → 128 pass |
| `v3.4.1` ✅ | `main` | `src/safecode/subagents/pool.py` | Parent-side cancellation (T-3.4.1-A); `CancellationToken` (threading.Event-backed, idempotent); `SubagentPool.cancel()` + external token support; cancelled tasks → `blocked=True` with empty task_id; no orphan files; completes within 5s; deterministic ordering preserved; 12 new tests in `tests/test_subagent_cancellation.py`; `PYTHONPATH=src python3 -m pytest tests/test_subagent_cancellation.py tests/test_subagent_pool.py tests/test_subagent_orchestration.py -q` → 140 pass |
| `v3.4.2` ✅ | `main` | `src/safecode/subagents/synthesis.py` | Parent-side synthesis (T-3.4.2-A); `synthesize_findings(findings, llm_client=None, *, max_findings=10) -> SubagentSynthesisResult`; calls LLM if available else fallback; output redacted via `redact_secrets`; never mutates input; `source_task_ids` sorted; `_enrich_with_subagent_findings` in loop calls synthesis before consumption; synthesis failure → `RuntimeWarning` + merged findings preserved; 28 new tests in `tests/test_subagent_synthesis.py`; `PYTHONPATH=src python3 -m pytest tests/test_subagent_synthesis.py tests/test_subagent_redaction.py tests/test_subagent_orchestration.py -q` → 140 pass |
| `v3.4.3` ✅ | `main` | `src/safecode/subagents/payload.py` | Subagent payload v2 promoted to supported (T-3.4.3-A); `CURRENT_PAYLOAD_VERSION=2`; `SUPPORTED_PAYLOAD_VERSIONS=frozenset({1,2})`; v2 fields: `synthesis_summary`, `synthesis_key_findings`, `synthesis_risks`, `synthesis_source_task_ids`, `cancelled_task_ids`; Pydantic default stays 1 for old-journal backward compat; new journals written at v2; v1 still loads tolerantly; unsupported future versions warn + fail closed; malformed warnings don't leak secrets; `docs/public-contracts.md` updated; 12 new tests in extended `tests/test_subagent_journal_payload_versioning.py`; full regression `PYTHONPATH=src python3 -m pytest -q` → 3084 passed, 2 skipped |
