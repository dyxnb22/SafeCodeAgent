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
| `v2.1.4` | `v2.1.4-context-debug-command` | `src/safecode/cli.py::context_explain` | `sac context explain "task"` 显示文件被选择的原因 |

## v2.2.x: Tool Ecosystem

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.2.0` | `v2.2.0-tool-schema-registry` | `src/safecode/tools/registry.py` | 内部工具 schema、risk、permission、audit event 显式可查询 |
| `v2.2.1` | `v2.2.1-model-tool-call-adapter` | `src/safecode/agent/tools.py` | LLM tool intent 转换为 runtime tool call 前完成 schema 校验 |
| `v2.2.2` | `v2.2.2-mcp-read-tool-loop` | `src/safecode/mcp/runner.py`、`src/safecode/agent/loop.py` | agent loop 可调用 approved readonly MCP tool 并记录观察 |
| `v2.2.3` | `v2.2.3-mcp-write-review-flow` | `src/safecode/mcp/proposal.py`、`src/safecode/agent/loop.py` | MCP write 进入 proposal/review/apply/audit 生命周期，不直接执行 |
| `v2.2.4` | `v2.2.4-subagent-orchestration` | `src/safecode/subagents/`、`src/safecode/agent/loop.py` | main agent 可派发 readonly subagent 并把结果合并进单一计划 |

## v2.3.x: Developer Experience

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.3.0` | `v2.3.0-interactive-tui` | `src/safecode/tui/` | TUI 展示 plan、diff、approval、command output、history |
| `v2.3.1` | `v2.3.1-config-wizard` | `src/safecode/setup.py`、`src/safecode/cli.py::setup` | `sac setup` 引导 model/network/approval dirs/safety preset |
| `v2.3.2` | `v2.3.2-ide-bridge-mvp` | `src/safecode/ide/` | IDE bridge 可打开 diff 和 selected files |
| `v2.3.3` | `v2.3.3-install-update-polish` | `pyproject.toml`、`src/safecode/doctor.py` | doctor/version/update 指南覆盖常见安装问题 |
| `v2.3.4` | `v2.3.4-onboarding-examples` | `examples/`、`docs/tutorials/` | bug fix、feature edit、docs edit、safe shell task 四个教程跑通 |

## v2.4.x: Real Sandbox Backends

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.4.0` | `v2.4.0-sandbox-backend-contract-v2` | `src/safecode/sandbox/adapter.py` | dry-run/preflight/execute contract 按 backend 分离 |
| `v2.4.1` | `v2.4.1-macos-seatbelt-execution-preview` | `src/safecode/sandbox/seatbelt.py` | opt-in macOS Seatbelt execution path 有窄 allowlist 和 eval |
| `v2.4.2` | `v2.4.2-linux-bubblewrap-execution-preview` | `src/safecode/sandbox/bubblewrap.py` | opt-in Bubblewrap execution path 有 filesystem/network containment eval |
| `v2.4.3` | `v2.4.3-docker-execution-preview` | `src/safecode/sandbox/docker.py` | opt-in Docker execution path 支持隔离命令运行 |
| `v2.4.4` | `v2.4.4-cross-backend-security-evals` | `tests/test_sandbox_*` | backend-specific escape/attack/security eval 全部通过 |

## v2.5.x: Reliability and Evaluation

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.5.0` | `v2.5.0-task-eval-format` | `src/safecode/eval/` | task eval fixture 包含 repo、goal、expected outcome、safety expectations |
| `v2.5.1` | `v2.5.1-agent-replay-runner` | `src/safecode/eval/runner.py` | 保存的 session 可 replay 并比较 action/diff/command/outcome |
| `v2.5.2` | `v2.5.2-failure-taxonomy` | `src/safecode/eval/failures.py` | context miss、patch parse、validation、command block、test failure、model error 可分类 |
| `v2.5.3` | `v2.5.3-quality-dashboard-report` | `src/safecode/report/` | eval 结果渲染为 Markdown/HTML dashboard |
| `v2.5.4` | `v2.5.4-performance-budgets` | `src/safecode/trace/`、`src/safecode/eval/` | 记录 context size、command duration、LLM latency、disk growth |

## v2.6.x: Product Hardening

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v2.6.0` | `v2.6.0-policy-presets` | `src/safecode/config.py` | strict/balanced/experimental safety presets 可切换且不可被项目配置降级 |
| `v2.6.1` | `v2.6.1-migration-system` | `src/safecode/state/migrations.py` | `.sac` state 与用户级 approval/audit store 有版本迁移 |
| `v2.6.2` | `v2.6.2-release-signoff` | `src/safecode/release/` | release checklist 覆盖 tests/docs/tags/security eval |
| `v2.6.3` | `v2.6.3-team-trust-boundaries` | `docs/security/`、`src/safecode/config.py` | project/user/team trust boundary 文档和 enforcement 明确 |
| `v2.6.4` | `v2.6.4-product-security-review` | `docs/security/`、`tests/` | prompts/tools/state/sandbox/install-update 完成产品级安全 review |
