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

## v2.8.x: Consolidation and CLI Honesty

Historical plan: `docs/version-plans/v2.8-to-v3.0-product-architecture-roadmap.md`.

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

## v2.9.x: Deterministic Evidence and Contract Preparation

Historical plan: `docs/version-plans/v2.8-to-v3.0-product-architecture-roadmap.md`.

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

## v3.5.x: IDE/TUI Product Surface

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.5.0` ✅ | `main` | `src/safecode/api/jsonrpc.py`, `src/safecode/cli_api.py` | LocalAPI JSON-RPC bridge (T-3.5.0-A, experimental); `process_request(line, project_root)` — never raises; `run_server(project_root, *, stdin, stdout)` — stdio newline-delimited loop; `CONTRACT_VERSION="1"`; `_SUPPORTED_METHODS=frozenset({"ask","report","edit","apply"})`; error text never contains caller params; `sac api jsonrpc` CLI command registered (hidden); 64 new tests in `tests/test_ide_bridge_jsonrpc.py`; `PYTHONPATH=src python3 -m pytest tests/test_ide_bridge_jsonrpc.py -q` → 64 pass |
| `v3.5.1` ✅ | `main` | `src/safecode/ide/manifest.py` | VS Code extension skeleton (T-3.5.1-A, repo-side only); `render_manifest()` extended with `jsonrpc_transport` (`launch_command=["sac","api","jsonrpc"]`, `protocol="json-rpc-2.0"`, `transport="stdio"`, `contract_version="1"`, `supported_methods`), `pending_diff_targets`, and `safecode.apiJsonrpc` command; `_JSONRPC_CONTRACT_VERSION="1"` exported; deterministic; IDE bridge remains experimental; tests in `tests/test_ide_bridge_jsonrpc.py` cover manifest |
| `v3.5.2` ✅ | `main` | `src/safecode/tui/interactive.py`, `src/safecode/cli_tui.py` | Interactive TUI (T-3.5.2-A, experimental, no Textual required); `run_interactive(project_root, *, refresh_seconds, history_limit)`: non-TTY → `_print_static()` (deterministic, exits immediately); TTY → `_run_live()` (Rich Live, Ctrl-C exits cleanly); `sac tui interactive` with `--refresh` and `--history-limit`; 24 new tests in `tests/test_tui_interactive_smoke.py`; full regression `PYTHONPATH=src python3 -m pytest -q` → 3148 passed, 2 skipped |

## v3.6.x: Commercial Hardening

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.6.0` ✅ | `main` | `src/safecode/release/publish.py`, `.github/workflows/ci.yml` | T-3.6.0-A release-publish: `sac release publish --dry-run/--sign`; dry-run deterministic (no subprocess, no writes); real publish requires `SAFECODE_PUBLISH=1` + clean matching tag; sign fails closed if no cosign/gpg; 38 new tests in `tests/test_release_publish_dry_run.py`. T-3.6.0-B ci-matrix: CI expanded to Python 3.11/3.12/3.13 × {ubuntu, macos} with `fail-fast: false`; advisory `smoke-windows` lane (`continue-on-error: true`); loop-eval and live-provider remain advisory and gated; 28 new tests in `tests/test_ci_matrix.py`; `PYTHONPATH=src python3 -m pytest tests/test_release_publish_dry_run.py tests/test_ci_matrix.py -q` → 66 pass |
| `v3.6.1` ✅ | `main` | `src/safecode/doctor.py` | T-3.6.1-A doctor-update-check: `_fetch_latest_pypi_version` queries PyPI via HTTPS, no telemetry; offline/404/timeout → `None` (never raises); `Doctor._update_check_diagnostic` returns SKIP (None), PASS (up-to-date), WARN (stale); `Doctor.__init__` accepts injectable `fetch_latest_version` for deterministic tests; `run_diagnostics` includes `update_check` diagnostic; 26 new tests in `tests/test_doctor_update_check.py` (mocked network only); full regression `PYTHONPATH=src python3 -m pytest -q` → 3236 passed, 2 skipped |
| `v3.6.2` ✅ | `main` | `src/safecode/otel/exporter.py` | T-3.6.2-A otel-exporter: optional OTel exporter for runtime events and agent steps; `OtelExporter.from_env()` reads `SAFECODE_OTEL_EXPORTER` env var (disabled by default); missing OTel packages → `RuntimeWarning` + disabled (fail closed); `OtelExporter.export_event()` never raises; endpoint never in error text; no telemetry in tests; OTel remains experimental/optional; 36 new tests in `tests/test_otel_exporter.py`; `PYTHONPATH=src python3 -m pytest tests/test_otel_exporter.py -q` → 36 pass |
| `v3.6.3` ✅ | `main` | `src/safecode/report/session_html.py`, `src/safecode/cli_ops.py` | T-3.6.3-A report-html: `sac report html --session <id>` renders deterministic self-contained HTML from journal data; `render_session_html(session_id, project_root) -> SessionHtmlReport`; no external network assets; secrets redacted via `redact_secrets()`; missing/invalid sessions handled gracefully; `sac report` (no subcommand) unchanged (backward compat); `report_app` Typer group replaces flat `ops_app.command("report")`; 30 new tests in `tests/test_report_html.py`; full regression `PYTHONPATH=src python3 -m pytest -q` → 3302 passed, 2 skipped |
| `v3.6.4` ✅ | `main` | `docs/security/threat-model-v3.6.md` | T-3.6.4-A threat-model-doc: adds `docs/security/threat-model-v3.6.md` with 9 threat personas (local user, malicious repo, malicious project config, malicious MCP server, malicious model output, network/provider risk, audit/approval trust boundaries, sandbox limitations, telemetry/update-check); semi-annual review cadence documented; 14 new tests in `tests/test_threat_model_docs.py`; documentation only, no runtime changes |
| `v3.6.5` ✅ | `main` | `docs/why-safecode.md`, `docs/compare.md`, `docs/troubleshooting.md` | T-3.6.5-A landing-docs: adds three landing docs; claims aligned with `docs/public-contracts.md`; experimental surfaces labeled throughout; all three linked from `README.md`; 20 new tests in `tests/test_landing_docs.py`; documentation only, no runtime changes |
| `v3.6.6` ✅ | `main` | *(metadata only)* | T-3.6.6-A commercial-v1-cut: final commercial v1 milestone; version bumped to 3.6.6 in `pyproject.toml` and `src/safecode/__init__.py`; `.claude/versions.json` updated; `SKILL.md` baseline updated; version matrix rows for v3.6.4–v3.6.6 added; no runtime changes; full regression `PYTHONPATH=src python3 -m pytest -q` → 3336 passed, 2 skipped |

## v3.7.x: Workflow Gap Closure

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.7.0` ✅ | `main` | `src/safecode/cli_fix.py`, `src/safecode/cli_quickstart.py` | T-3.7.0-A sac-fix: `sac fix [--test-command CMD] [--json]`; detects test command via `ProjectTestDetector`, runs it (`shell=False`, 120s timeout), redacts failure output, invokes `AgentOrchestrator.edit()`, leaves pending patch for `sac apply`; no approval gate bypassed; 22 new tests in `tests/test_sac_fix.py`. T-3.7.0-B stack-aware-quickstart: `sac quickstart` detects `pyproject.toml` (python), `package.json` (typescript), `go.mod` (go), `Cargo.toml` (rust) and adapts next-step commands and demo hints; unknown stack preserves existing behavior; 11 new tests added to `tests/test_quickstart.py`; `PYTHONPATH=src python3 -m pytest tests/test_sac_fix.py tests/test_quickstart.py -q` → 35 pass; full regression → 3360 passed, 2 skipped |
| `v3.7.1` ✅ | `main` | `src/safecode/cli.py` (`run_setup_wizard`), `src/safecode/cli_progress.py` | T-3.7.1-A setup-wizard: `sac setup --wizard`; non-TTY exits 0 with static template (no writes); TTY walks provider/model/policy; switching from mock requires explicit confirm; network requires double-confirm; `_stricter_policy` enforced — wizard cannot write weaker policy than user level; cancel=no writes; 14 new tests in `tests/test_setup_wizard.py` + 5 pre-existing kept. T-3.7.1-B progress-indicator: `cli_status(msg)` context manager + `StepCounter(n)` class; TTY shows Rich spinner/step counter; non-TTY emits zero extra bytes; 20 new tests in `tests/test_cli_progress.py`; full regression → 3384 passed, 2 skipped |
| `v3.7.2` ✅ | `main` | `src/safecode/context/selector.py`, `docs/public-contracts.md`, `tests/snapshots/contracts/cli_json_envelope.json` | T-3.7.2-A repo-recency-signal: `ContextSelector` weights recently git-touched files higher via `_RECENCY_BONUS=2` additive to keyword score; `git log -n50 --name-only` cached by HEAD; git failures fall back silently; 22 new tests in `tests/test_context_recency.py`. T-3.7.2-B json-envelope-promote: `CLIJSONResponse` promoted to stable contract in `docs/public-contracts.md` Section 11; snapshot at `tests/snapshots/contracts/cli_json_envelope.json`; 12 new tests in `TestCLIJSONEnvelopeContract`; full regression → 3414 passed, 2 skipped |
| `v3.7.3` ✅ | `main` | `README.md`, `docs/mvp-user-guide.md` | T-3.7.3-A v3.7-docs-cut: documentation-only release; `README.md` Core Commands updated with `sac setup --wizard`, `sac quickstart` stack detection, `sac fix`, `sac fix --test-command`, `--json` flag examples; `docs/mvp-user-guide.md` updated: intro references v3.7.x, quickstart documents stack detection, new "Interactive setup wizard" subsection, new "Fixing failing tests with sac fix" section, new "Machine-readable output" section with stable JSON envelope contract reference (Section 11); no runtime changes; no new tests; full regression → 3414 passed, 2 skipped |

## v3.8.x: MCP Hardening

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.8.0` ✅ | `main` | `src/safecode/mcp/lifecycle.py`, `src/safecode/mcp/runner.py`, `src/safecode/cli_mcp.py` | T-3.8.0-A mcp-stdio-wire: `MCPReadOnlyRunner` gains `stdio_runner` param and `SAFECODE_MCP_STDIO_RUNNER=1` env opt-in; routes `call_readonly` through `StdioReadOnlyAdapter` when server has argv; classification gate runs before stdio call; flag off → byte-identical to v3.7.3; 19 new tests in `tests/test_mcp_stdio_wired.py`; 2 existing v3.3.4 tests updated for wired-opt-in reality. T-3.8.0-B mcp-lifecycle: new `src/safecode/mcp/lifecycle.py` with `MCPLifecycleManager` (start/stop/restart), `MCPLifecycleResult`; PID tracking under `.sac/mcp/`; bounded timeout with SIGTERM+SIGKILL; stop idempotent; each transition emits RuntimeLogger + AuditEvent; `sac mcp start/stop/restart` CLI commands (labeled EXPERIMENTAL); 32 new tests in `tests/test_mcp_lifecycle.py`; `PYTHONPATH=src python3 -m pytest tests/test_mcp_stdio_wired.py tests/test_mcp_lifecycle.py tests/test_mcp_stdio_adversarial.py -q` → 88 pass; full regression → 3465 passed, 2 skipped |
| `v3.8.1` ✅ | `main` | `src/safecode/mcp/config.py`, `src/safecode/mcp/runner.py`, `src/safecode/cli_mcp.py` | T-3.8.1-A mcp-per-server-scopes: `MCPServerConfig.scope` field (`denied`/`read_only`/`write_proposal_required`); parsed from TOML; invalid value → `denied` (fail-closed); unknown server → `denied`; known server without scope → `read_only`; scope gate runs BEFORE classification in `call_readonly` and `propose_write`; `read_only` scope blocks write proposals; `write_proposal_required` allows them; 22 new tests in `tests/test_mcp_per_server_scopes.py`. T-3.8.1-B mcp-doctor: `sac mcp doctor [server]` ([EXPERIMENTAL]); reports binary path, scope, stdio configured, last call status from audit, lifecycle PID; `--json`; pure read, no subprocess; 23 new tests in `tests/test_mcp_doctor.py`; full regression → 3510 passed, 2 skipped |
| `v3.8.2` ✅ | `main` | `src/safecode/mcp/approval_grant.py`, `src/safecode/mcp/runner.py`, `docs/public-contracts.md`, `tests/snapshots/contracts/mcp_read_contract.json` | T-3.8.2-A mcp-write-proposal-e2e: `MCPApprovalStore` (single-use grants outside project root, `SAFECODE_MCP_APPROVAL_DIR`); `execute_granted_write()` on runner; stub JSON-RPC server tests; grant consumed + proposal discarded after execution; audit events `mcp_granted_write_*`; 19 new tests in `tests/test_mcp_write_proposal_e2e.py`. T-3.8.2-B mcp-read-promotion: Section 12 "MCP Read Execution Contract" in `docs/public-contracts.md`; `tests/snapshots/contracts/mcp_read_contract.json`; `TestMCPReadContract` (16 tests); MCP read promoted to stable; write + lifecycle remain experimental; full regression → 3545 passed, 2 skipped |

## v3.9.x: Real Distribution and IDE/TUI Maturation

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.9.0` ✅ | `main` | `src/safecode/release/publish.py`, `src/safecode/cli_ops.py`, `docs/install-update.md`, `docs/security/threat-model-v3.6.md` | T-3.9.0-A signing-truthing: Decision B — rename `--sign` semantics to detached cosign/gpg signature; `_planned_steps()` labels the mechanism; `_check_sign_tooling()` error message updated; module docstring clarifies no Sigstore Rekor; `docs/install-update.md` and `docs/security/threat-model-v3.6.md` updated to match; 6 new tests in `TestSigningMechanismDescription`. T-3.9.0-B testpypi-rehearsal: `repository` param on `run_release_publish()` + `PublishResult`; `_REPOSITORY_URLS` maps `pypi`/`test-pypi`; real upload uses `uv publish --publish-url <url>`; both pypi and test-pypi require `SAFECODE_PUBLISH=1`; `--repository` CLI option; `docs/install-update.md` documents TestPyPI rehearsal + pipx install; 28 new tests in `tests/test_release_publish_repository.py`; full regression → 3579 passed, 2 skipped |
| `v3.9.3` ✅ | `main` | `README.md`, `docs/install-update.md`, `docs/version_implementation_matrix.md`, `.claude/skills/current/SKILL.md` | T-3.9.3-A v3.9-docs-cut: README install section updated (local dev, pipx, TestPyPI, offline wheel); Release Flow updated (sync-versions-json step, tag-move, TestPyPI rehearsal, production publish); "IDE and TUI Status" section added; `docs/install-update.md` reflects all v3.9.x additions; version matrix rows v3.9.0–v3.9.3 complete; SKILL.md baseline updated; claims-vs-implementation table in version note; no runtime changes; full regression → 3647 passed, 2 skipped |
| `v3.9.2` ✅ | `main` | `vscode-extension/`, `src/safecode/ide/manifest.py`, `docs/public-contracts.md`, `tests/test_tui_interactive_smoke.py` | T-3.9.2-A vscode-extension-pkg: `vscode-extension/package.json` (6 commands, `_safecodeNotes` with contract version/launch/telemetry/approval), `vscode-extension/src/extension.ts` (spawns `sac api jsonrpc`, modal approval, no telemetry), `tsconfig.json`, `.vscodeignore`; 24 new tests in `tests/test_ide_extension_manifest_contract.py`; **VSIX build deferred** (tsc not in build env; manual smoke procedure documented in version note). T-3.9.2-B tui-textual-decision: Decision B — freeze `sac tui interactive` at v3.5.2 Rich-based behavior; TUI entry in `docs/public-contracts.md` updated to "Frozen experimental at v3.9.2"; 5 new tests in `TestTUIFrozenExperimental`; full regression → 3647 passed, 2 skipped |
| `v3.9.1` ✅ | `main` | `docs/versioning-policy.md`, `docs/install-update.md`, `README.md` | T-3.9.1-A pipx-brew-docs: brew strategy decision = defer (no production PyPI wheel yet; target tap at v3.10.x/v4.0 with live CI); `docs/versioning-policy.md` "Brew Distribution Strategy" section; 18 new tests in `tests/test_install_docs.py` enforcing required install command fragments from fixture list. T-3.99.0-B versioning-policy-doc (landed early): `docs/versioning-policy.md` (new) — patch/minor/major semantics, stable/experimental surfaces, v4.0 churn budget (≤2 new stable contracts, zero breaking v3.0 changes), brew strategy; `README.md` link added; 12 new tests in `tests/test_versioning_policy_doc.py`; full regression → 3617 passed, 2 skipped |

## v3.10.x: Observability, Performance, Blocking Gates

| 版本 | 分支 | 主要入口 | 验收命令 |
|---|---|---|---|
| `v3.10.0` ✅ | `main` | `src/safecode/eval/bench.py`, `src/safecode/metrics/writer.py`, `src/safecode/cli_ops.py`, `src/safecode/agent/orchestrator.py` | T-3.10.0-A sac-eval-bench: `EvalBenchRunner` collects wall time / step count / pending-patch hash per fixture; baseline snapshots under `tests/snapshots/bench/`; ±20% tolerance; mocked-clock injectable for deterministic CI; `sac eval --mode bench` CLI; 27 new tests in `tests/test_eval_bench.py`. T-3.10.0-B live-session-metrics: `MetricsWriter` writes JSONL to `.sac/metrics.jsonl`; disabled by default; `SAFECODE_METRICS=1` opt-in; step start/end + tool intent + patch size (byte count only) + retry; 1 MiB size bound; never raises; minimal wiring in `AgentOrchestrator.edit()`; 26 new tests in `tests/test_metrics_writer.py`; targeted → 53 pass; full regression → 3700 passed, 2 skipped |
| `v3.10.1` ✅ | `main` | `.github/workflows/ci.yml`, `docs/providers.md`, `tests/test_eval_loop_mode_ci_gate.py`, `tests/test_ci_live_lane.py` | T-3.10.1-A loop-eval-blocking: promotion deferred (no clean CI train recorded locally); loop-eval remains advisory (`continue-on-error: true`); 4 new tests in `tests/test_eval_loop_mode_ci_gate.py` encoding truthful current state. T-3.10.1-B live-provider-lane-record: v3.10.x release train history table added to `docs/providers.md`; lane remains advisory; no credential handling changes; 7 new tests in `tests/test_ci_live_lane.py`; targeted → 45 pass; full regression → 3711 passed, 2 skipped |
| `v3.10.2` ✅ | `main` | `docs/context-budgets.md`, `docs/tutorials/typescript-first-hour.md`, `docs/tutorials/go-first-hour.md`, `README.md`, `tests/test_context_budgets_docs.py`, `tests/test_landing_docs.py` | T-3.10.2-A context-budget-docs: `docs/context-budgets.md` documents default 40,000-char budget; p50 fixture numbers from bench snapshots; tied to `ContextBudget`/`ContextBudgetPacker`; 20 new tests. T-3.10.2-B per-stack-tutorial-ts-go: TypeScript and Go "first hour" tutorials with quickstart/ask/edit/apply/rollback/fix/safety sections; cross-references; README links; 18 new tests in `tests/test_landing_docs.py`; targeted → 52 pass; full regression → 3746 passed, 2 skipped |

## v3.11.x: Policy Management and Sandbox Executor Preflight

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v3.11.0` ✅ | `main` | `src/safecode/config.py`, `src/safecode/cli_core.py`, `tests/test_per_directory_trust.py`, `tests/test_ephemeral_trust.py` | T-3.11.0-A per-directory-trust: user-level `trust.roots` apply to explicit roots/subdirectories; project-local trust declarations are blocked and audited. T-3.11.0-B ephemeral-trust: `sac trust grant --until-end-of-session` creates process-local grants only and audits grant/revoke; targeted → 8 passed; full regression → 3754 passed, 2 skipped |
| `v3.11.1` ✅ | `main` | `src/safecode/cli_project.py`, `src/safecode/policy/audit.py`, `tests/test_policy_diff.py` | T-3.11.1-A policy-diff: `sac config diff --against strict\|balanced\|experimental`; deterministic knob-by-knob output; `--json` via `CLIJSONResponse`; preset definitions unchanged; targeted → 5 passed; full regression → 3759 passed, 2 skipped |
| `v3.11.2` ✅ | `main` | `src/safecode/sandbox/executor_preflight.py`, `src/safecode/cli_sandbox_status.py`, `src/safecode/sandbox/execution.py`, `src/safecode/doctor.py`, `docs/install-update.md`, `docs/security/threat-model-v3.6.md`, `tests/test_sandbox_executor_preflight.py` | T-3.11.2-A sandbox-executor-preflight: `sac sandbox executor-preflight <backend>` records passing backend gate state; real Docker/Seatbelt/Bubblewrap require preflight + explicit env opt-in; Noop behavior unchanged. T-3.11.2-B sandbox-promotion-docs: install/threat docs and doctor report policy-gated/preview/opt-in state; targeted → 22 passed; backend-focused regression → 299 passed; full regression → 3767 passed, 2 skipped |

## v3.99.x: v4.0 Prep

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v3.99.0` ✅ | `main` | `docs/commercial-v1-readiness-audit-v3.11.x.md`, `docs/versioning-policy.md`, `tests/test_versioning_policy_doc.py` | T-3.99.0-A v4-readiness-audit: re-audits the v3.11.x baseline against v4.0 readiness goals and marks unresolved PyPI, VS Code, loop-eval, live-provider, CI bench, and sandbox real-execution claims as deferred rather than shipped. T-3.99.0-B versioning-policy-doc: clarifies patch/minor/major semantics and pins the v4.0 churn budget (≤2 new stable contracts, zero v3.0 breaking changes). Targeted/full/preflight run as part of release train. |
| `v3.99.1` ✅ | `main` | `docs/public-contracts.md`, `tests/test_public_contract_snapshots.py` | T-3.99.1-A promotion-decision-pass: records CLI JSON envelope and MCP read execution as already-stable promotions; defers IDE JSON-RPC, `sac report html`, and sandbox real-execution opt-in; rejects TUI stable promotion at v4.0. No new stable contract promoted by v3.99.1 itself. Targeted/full/preflight run as part of release train. |

## v4.0.x: Contract Cut and Roadmap Alignment

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.0.0` ✅ | `main` | `docs/public-contracts.md`, `docs/commercial-v1-readiness-audit-v3.11.x.md`, `docs/versioning-policy.md`, `tests/test_public_contract_snapshots.py` | T-4.0.0-A v4-contract-cut: applies v3.99.1 decisions without runtime feature work. CLI JSON envelope and MCP read execution remain already-stable; no new stable contracts are promoted at v4.0.0; zero breaking changes to v3.0 public contracts; IDE JSON-RPC, TUI, `sac report html`, and sandbox real-execution opt-in remain deferred/rejected as documented. Targeted/full/preflight run as part of release train. |
| `v4.0.1` ✅ | `main` | `README.md`, `.claude/versions.json`, `docs/version_implementation_matrix.md`, `docs/product-commercialization-roadmap.md`, `docs/version-plans/v4.1-to-v4.8-shell-first-roadmap.md` | post-v4-roadmap-metadata-alignment: aligns active planning pointers around the v4.1-to-v4.8 shell-first roadmap, preserves the v3.7-to-v4.0 roadmap as previous, points readiness to the v3.11.x audit, and synchronizes package/runtime/lock metadata to v4.0.1. No runtime behavior changes and no stable contract changes. Targeted governance/contract tests passed. |

## v4.1.x: Unified Task State

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.1.0` ✅ | `main` | `src/safecode/task/state.py`, `src/safecode/task/store.py`, `src/safecode/cli_task.py`, `tests/test_task_state.py`, `tests/test_cli_task.py` | T-4.1.0-A task-state-sidecar: new `TaskState` Pydantic model (payload_version=1, status enum, iterations, last_command); `TaskStore` with atomic writes via tmp+os.replace; `.sac/tasks/<id>.json`, `INDEX`, `CURRENT` files; refuses to overwrite payload_version>1 (fail closed); missing files never crash read paths. T-4.1.0-B task-cli-core: `sac task new|list|show|switch|close|delete`; all support `--json` via CLIJSONResponse; `new` requires non-empty goal, auto-generates kebab-case+short-hash id, sets CURRENT; `delete` requires `--yes`; `show` redacts secrets; `list` deterministic. 58 targeted tests passed; full suite 3842 passed, 2 skipped; contract snapshots green; preflight passed post-commit. |
| `v4.1.1` ✅ | `main` | `src/safecode/cli_status.py`, `src/safecode/task/wiring.py`, `src/safecode/cli_core.py`, `src/safecode/cli_fix.py`, `src/safecode/audit/logger.py`, `tests/test_cli_status.py`, `tests/test_audit_task_metadata.py` | T-4.1.1-A sac-status-cmd: `sac status [--json]`; pure `next_step(state, pending_patch_exists)` with truth-table coverage (6 states); TTY/non-TTY deterministic; never writes audit events. T-4.1.1-B wire-edit-apply-rollback-into-task: `sac edit|apply|rollback|fix|run` attach to CURRENT task (auto-create if none/closed); task sidecar mutated on each command; `AuditLogger.write()` extended with optional `task_id` keyword (metadata only; field set unchanged); 26 targeted tests; full suite 3868 passed, 2 skipped; contract snapshots green; preflight passed. |
| `v4.1.2` ✅ | `main` | `src/safecode/audit/logger.py`, `src/safecode/cli_core.py`, `tests/test_history.py`, `tests/test_history_task_filter.py`, `docs/version-notes/v4.1.2-task-history-filter-and-docs.md` | T-4.1.2-A history-task-filter: `sac history --task <id>` filters output to events with exact `metadata.task_id` match (EXPERIMENTAL); `AuditLogger.read_by_task_id(task_id, limit=200)` added (exact match, empty task_id returns [], corrupted lines skipped); field set unchanged. T-4.1.2-B v4.1-docs-cut: README core commands updated with `sac task`, `sac status`, `sac history --task`; `docs/mvp-user-guide.md` updated with task-first v4.1 flow; all v4.1 surfaces marked EXPERIMENTAL; stable contract snapshots unchanged. 17 targeted history tests; full suite 3885 passed, 2 skipped; contract snapshots green. |

## Current Project Status After v4.16.2

Completed post-v4.14 usability roadmaps:
- `docs/version-plans/post-v4.14-usability-roadmap.md` (v4.14.1–v4.16.2, 8 versions COMPLETED).
- v4.14.1 diagnostic clarity, v4.14.2 --model parity, v4.15.0 sac init, v4.15.1 session-scoped model, v4.15.2 keychain/env credentials, v4.16.0 bare-sac-shell + 7-cmd help, v4.16.1 config migration, v4.16.2 error-message rewrite + sac why.

Completed provider-profile UX cut: `docs/version-notes/v4.14.0-provider-profile-ux.md`.

Completed resume-MVP plan: `docs/version-plans/v4.10-to-v4.12-resume-mvp-roadmap.md`.
Completed AI shell plan: `docs/version-plans/v4.9-ai-shell-mvp-roadmap.md`.
Completed shell-first plan: `docs/version-plans/v4.1-to-v4.8-shell-first-roadmap.md`.

Next active plan: `docs/version-plans/post-v4.16-shell-ux-roadmap.md` (streaming, shell polish, live connectivity, fuzzy matching, per-patch undo, agent-loop transparency).

Readiness baseline: `docs/archive/audits/commercial-v1-readiness-audit-v3.11.x.md`.
Architecture reference: `docs/product-commercialization-roadmap.md`.

v4.16 result: First-run usability train complete — bare sac enters shell, 7 daily
commands, session-scoped model switching, keychain credentials, config migration,
and error messages all ship as EXPERIMENTAL. Zero new stable contracts.
Project-local config still cannot store
credentials or silently widen user-level network policy.

## v4.9.x: AI Shell MVP

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.9.0` ✅ | `main` | `src/safecode/cli_shell.py`, `src/safecode/shell_session/state.py`, `src/safecode/shell_session/store.py`, `src/safecode/cli.py`, `tests/test_cli_shell.py` | T-4.9.0-A shell-session-and-repl: experimental `sac shell` REPL with TTY and non-TTY modes; slash commands `/status`, `/task`, `/overview`, `/apply`, `/commit`, `/debug`, `/help`, `/exit`; session state persisted to `.sac/shell/`; corrupt/future-version files handled fail-safe; each turn bound to CURRENT task and audit; mutation paths require explicit confirmation, never auto-apply. 24 tests. |
| `v4.9.1` ✅ | `main` | `src/safecode/shell_session/router.py`, `tests/test_shell_router.py` | T-4.9.1-A natural-language-router: intent classifier routes user input to ask/edit/fix/run/status/apply/commit/debug/overview/exit; ambiguous intent defaults to read-only ask; write-class actions require explicit confirmation; profile-based test/lint/typecheck/build routing preserved; mock provider for deterministic tests. 44 tests. |
| `v4.9.2` ✅ | `main` | `src/safecode/shell_session/overview.py`, `tests/test_shell_overview.py` | T-4.9.2-A project-overview-context: `build_project_overview()` aggregates stack, git, profile commands, entrypoints, test dirs, high-signal files, pinned memory, current task, and recent failures without RAG; context bounded by `_MAX_OVERVIEW_BYTES`; skipped signals listed in output; secrets redacted; paths stay within project root; Python/TypeScript/Go/Rust fixture tests. 23 tests. |
| `v4.9.3` ✅ | `main` | `docs/tutorials/ai-shell-first-hour.md`, `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `docs/public-contracts.md`, `docs/versioning-policy.md`, `src/safecode/cli_smoke.py`, `tests/test_smoke_ai_shell.py`, `tests/test_ai_shell_docs_claims.py` | T-4.9.3-A ai-shell-docs-and-smoke: shell-first tutorial added; README, MVP guide, troubleshooting, public-contracts, versioning-policy updated; v4.9 surfaces explicitly EXPERIMENTAL; zero new stable contracts; no v5 scheduled; `sac smoke ai-shell` added with 6 deterministic scenarios under mock provider; docs claims guard and smoke tests. Full suite clean. |

## v4.10.x: DeepSeek Provider + Reliability

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.10.0` ✅ | `main` | `src/safecode/llm/deepseek.py`, `src/safecode/llm/factory.py`, `src/safecode/llm/openai_client.py`, `src/safecode/config.py`, `tests/test_llm_deepseek_preset.py`, `docs/version-notes/v4.10.0-deepseek-provider-preset.md` | T-4.10.0-A deepseek-provider-preset: `deepseek.py` preset table (`base_url`, `default_model: deepseek-v4-pro`, `api_key_env: DEEPSEEK_API_KEY`); factory routes `deepseek` provider to `OpenAICompatibleLLMClient` using preset defaults without overwriting explicit config; client gains `api_key_env` resolution (provider-env → OPENAI_API_KEY → SAFECODE_LLM_API_KEY) and `/v1/chat/completions` endpoint normalization with double-append prevention. All new surfaces EXPERIMENTAL; mock default unchanged. Targeted tests pass; full suite clean. |
| `v4.10.1` ✅ | `main` | `src/safecode/cli.py`, `src/safecode/llm/deepseek.py`, `tests/test_setup_wizard.py`, `docs/version-notes/v4.10.1-deepseek-setup-wizard.md` | T-4.10.1-A deepseek-setup-wizard: `sac setup --wizard` gains `deepseek` preset option in `run_setup_wizard`; wizard reads `DEEPSEEK_PRESET`, reminds the user to set `DEEPSEEK_API_KEY`, writes provider/model/base URL only through existing setup flow, and never prompts for or writes secrets. Existing openai/openai-compatible wizard paths unaffected. All new surfaces EXPERIMENTAL. Targeted tests pass; full suite clean. |
| `v4.10.2` ✅ | `main` | `src/safecode/doctor.py`, `tests/test_provider_doctor.py`, `docs/version-notes/v4.10.2-provider-doctor-diagnostics.md` | T-4.10.2-A provider-doctor-diagnostics: `Doctor._provider_diagnostics()` checks API key env var present, `base_url` parseable without provider I/O, model name non-empty, and static network policy permits base URL; makes no live provider network request; PyPI update check is separately gated by `SAFECODE_DOCTOR_UPDATE_CHECK=0`; diagnostics report PASS/SKIP/FAIL with actionable hints. All new surfaces EXPERIMENTAL. Targeted tests pass; full suite clean. |
| `v4.10.3` ✅ | `main` | `src/safecode/llm/openai_client.py`, `src/safecode/llm/retry.py`, `src/safecode/config.py`, `tests/test_llm_retry.py`, `tests/test_llm_retry_extended.py`, `docs/version-notes/v4.10.3-provider-retry-reliability.md` | T-4.10.3-A provider-retry-reliability: `OpenAICompatibleLLMClient` gains rate-limit-aware retry on HTTP 429/5xx, bounded Retry-After handling, configurable request timeout fields, and structured progress callback; no retry on ordinary 4xx; secrets never logged during retry. All new surfaces EXPERIMENTAL. Targeted tests pass; full suite clean. |
| `v4.10.4` ✅ | `main` | `src/safecode/cli_smoke.py`, `tests/test_smoke_live_provider.py`, `docs/version-notes/v4.10.4-live-provider-smoke.md` | T-4.10.4-A live-provider-smoke: `sac smoke live-provider` opt-in scenario gated by `SAFECODE_LIVE_SMOKE=1`; refuses mock provider and blocked network policy; makes a real provider network call only after the explicit gate, verifies minimal chat completion, records round-trip latency, and remains hidden from `sac --help`. Existing mock-only smoke scenarios unaffected. All new surfaces EXPERIMENTAL. Targeted tests pass; full suite clean. |

## v4.11.x: Agentic-Lite Task Loop

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.11.0` ✅ | `main` | `src/safecode/agent/step_model.py`, `src/safecode/agent/loop.py`, `src/safecode/agent/__init__.py`, `tests/test_agent_loop_typed_steps.py`, `docs/version-notes/v4.11.0-typed-agent-step-projection.md` | T-4.11.0-A typed-agent-step-projection: experimental `TypedAgentStep` / `TypedAgentStepResult` projection added to the existing `AgentLoop`; legacy return types unchanged; mutating kinds remain approval-required; invalid model output, stale approval, patch hash, dirty-tree, commit file-set, and rollback checkpoint bindings covered. No `AgentTaskRunner` introduced. Focused tests and full suite pass per local evidence. |
| `v4.11.1` ✅ | `main` | `src/safecode/state/journal.py`, `src/safecode/agent/loop.py`, `src/safecode/cli_status.py`, `docs/mvp-user-guide.md`, `tests/test_agent_journal_typed_events.py`, `docs/version-notes/v4.11.1-typed-agent-journal-events.md` | T-4.11.1-A typed-agent-journal-events: existing `AgentJournalStore` gains additive `typed_step` / `typed_result` records, redaction, tolerant latest-plan / last-result readers, and `sac status --json` agent-plan context. Journal remains `.sac/agent_journals/<session_id>.jsonl`; audit remains separate. Focused tests and full suite pass per local evidence. |
| `v4.11.2` ✅ | `main` | `src/safecode/cli_shell.py`, `src/safecode/cli_agent.py`, `docs/tutorials/agent-run-first-hour.md`, `tests/test_cli_agent_run.py`, `tests/test_cli_shell.py`, `docs/version-notes/v4.11.2-agentic-shell-entrypoints.md` | T-4.11.2-A agentic-shell-entrypoints: experimental `sac shell --agentic` reuses `AgentLoop.run()`; `sac agent run` gains `--auto-approve-read-only`, `--no-validate`, JSON typed-step output, and default `--max-steps 8`; non-TTY approvals fail closed and read-only auto-approval cannot approve edit/apply/run/fix/commit/rollback. Focused tests and full suite pass per local evidence. |
| `v4.11.3` ✅ | `main` | `src/safecode/agent/validation.py`, `src/safecode/agent/loop.py`, `src/safecode/cli_agent.py`, `docs/tutorials/agent-run-first-hour.md`, `tests/test_validation_loop.py`, `docs/version-notes/v4.11.3-validation-loop.md` | T-4.11.3-A validation-loop: experimental `ValidationLoop` runs project-profile `test` after successful apply-kind typed steps, then optional `lint`, `typecheck`, `build` in deterministic order; failures produce redacted tail hash, typed validation/fix journal events, task iterations, and repair proposals through `AgentOrchestrator.edit()` without auto-apply. `--no-validate` disables the loop for one invocation with warning behavior. Focused tests pass; full suite clean. |
| `v4.11.4` ✅ | `main` | `src/safecode/cli_resume.py`, `src/safecode/agent/loop.py`, `docs/mvp-user-guide.md`, `tests/test_resume_agentic.py`, `docs/version-notes/v4.11.4-agentic-resume.md` | T-4.11.4-A agentic-resume: `sac resume` reads existing `.sac/agent_journals/<session_id>.jsonl` when present, prints last plan, last typed result, and suggested next safe step; `AgentLoop.resume_from(session_id)` reconstructs passive state from journal/session store; `sac resume --continue-agent` re-enters `AgentLoop.run()` without bypassing approvals. Missing/corrupt journals degrade to v4.4 summary; closed tasks refused. Focused tests pass; full suite clean. |
| `v4.11.5` ✅ | `main` | `src/safecode/cli_smoke.py`, `docs/troubleshooting.md`, `tests/test_smoke_agentic.py`, `docs/version-notes/v4.11.5-agentic-workflow-smoke.md` | T-4.11.5-A agentic-workflow-smoke: experimental `sac smoke agentic [--json]` adds six deterministic mock-only scenarios covering plan-only, edit rejection, apply plus validation pass, validation repair pass, validation `loop_no_progress`, and interrupted apply resume recovery. JSON reports scenario names, pass/fail, step kinds, final status, and failure reason; smoke writes typed journal/audit events in temp project roots only and never calls real providers. Focused tests pass; full suite clean. |

## v4.12.x: Demo Project + Resume-MVP Cut

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.12.0` ✅ | `main` | `examples/fastapi-todo/`, `pyproject.toml`, `tests/test_example_fastapi_todo.py`, `docs/version-notes/v4.12.0-fastapi-todo-demo-project.md` | T-4.12.0-A fastapi-todo-demo-project: adds runnable FastAPI todo example outside the SafeCode package path with `GET /todos`, `POST /todos`, in-memory store, `.sac/project_profile.json`, README, examples extra, and four baseline tests. Future demo task is naturally adding `DELETE /todos/{id}` with a passing test. Focused tests and full suite pass per local evidence. |
| `v4.12.1` ✅ | `main` | `src/safecode/demo/agent_loop_demo.py`, `src/safecode/cli_test_demo.py`, `examples/fastapi-todo/demo/`, `docs/tutorials/from-task-to-tested-commit.md`, `tests/test_demo_agent_loop.py`, `docs/version-notes/v4.12.1-agent-loop-demo-transcript.md` | T-4.12.1-A agent-loop-transcript-demo: hidden EXPERIMENTAL `sac demo agent-loop` prints a deterministic mock-provider transcript with task, plan, patch proposal, review/apply boundaries, validation, and commit prompt. Demo script runs in a temp working copy and never mutates the source example, calls live providers, pushes, or commits. Focused tests and full suite pass per local evidence. |
| `v4.12.2` ✅ | `main` | `README.md`, `docs/mvp-user-guide.md`, `docs/tutorials/agent-run-first-hour.md`, `docs/public-contracts.md`, `tests/test_docs_demo_section.py`, `docs/version-notes/v4.12.2-readme-demo-front-door.md` | T-4.12.2-A readme-demo-front-door: README opens with "Demo: from task to tested commit", links the FastAPI example, transcript, and tutorial; MVP guide and agent first-hour tutorial point to the mock demo. Docs guards assert no auto-apply, auto-commit, live-provider requirement, IDE requirement, or push/PR claim. Focused tests and full suite pass per local evidence. |
| `v4.12.3` ✅ | `main` | `pyproject.toml`, `src/safecode/__init__.py`, `.claude/versions.json`, `.claude/skills/current/SKILL.md`, `docs/version-notes/v4.12.3-resume-mvp.md`, `docs/version_implementation_matrix.md`, `docs/project-final-status-and-roadmap.md`, `docs/security/threat-model-v3.6.md`, `docs/public-contracts.md` | T-4.12.3-A resume-mvp-cut: bumps package/runtime metadata to 4.12.3, marks v4.12.x complete, records release notes and matrix rows, updates current status and threat model, and keeps all v4.10-v4.12 surfaces EXPERIMENTAL with no new stable contracts. Release metadata, focused demo/docs/example, full suite, and deterministic smoke commands run locally. |
| `v4.12.4` ✅ | `main` | `.gitignore`, `examples/fastapi-todo/.sac/project_profile.json`, `docs/version-notes/v4.12.4-fastapi-todo-profile.md` | T-4.12.4-A fastapi-todo-profile-tracking: keeps repository `.sac/` runtime state ignored while explicitly tracking the FastAPI todo demo profile required by `tests/test_example_fastapi_todo.py`; no runtime behavior change and no stable contract change. Package/runtime metadata remains 4.12.3 pending a release-tag decision. |

## v4.14.x-v4.16.x: Provider Profile and First-run Usability

Active plan: `docs/version-plans/post-v4.14-usability-roadmap.md` (COMPLETED).
Next: `docs/version-plans/post-v4.16-shell-ux-roadmap.md`.

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.14.0` ✅ | `main` | `src/safecode/llm/provider_profiles.py`, `src/safecode/cli_provider.py`, `src/safecode/cli_model.py`, `src/safecode/config.py`, `src/safecode/doctor.py`, `src/safecode/cli_smoke.py`, `README.md`, `docs/providers.md`, `docs/mvp-user-guide.md`, `tests/test_provider_profiles.py`, `tests/test_cli_model_config.py`, `tests/test_provider_doctor.py`, `tests/test_smoke_live_provider.py` | T-4.14.0-A provider-profile-ux: trusted user-level provider profiles with DeepSeek defaults; `sac provider add/list/status/use/rm`; `sac model flash/pro/deepseek:pro`; root and shell one-shot `--model`; provider-aware shell status; doctor/live-smoke checks that understand user-config API keys. No stable contract promotion. |
| `v4.14.1` ✅ | `main` | `src/safecode/doctor.py`, `src/safecode/cli_provider.py`, `src/safecode/cli_quickstart.py`, `tests/test_doctor_top_line_verdict.py`, `tests/test_provider_status_verdict.py` | First-run diagnostic clarity: top-line READY/NEEDS SETUP verdicts on `sac doctor` and `sac provider status`; every failed row carries `Next:`; `sac quickstart` refuses live-provider demo when not ready. |
| `v4.14.2` ✅ | `main` | `src/safecode/cli_core.py`, `src/safecode/cli_fix.py`, `src/safecode/cli_agent.py`, `tests/test_cli_model_subcommand_parity.py` | One-shot `--model` parity: `sac ask/edit/fix/run/agent run` accept `--model`; subcommand-level wins over root; shell already supported. |
| `v4.15.0` ✅ | `main` | `src/safecode/cli_init.py`, `src/safecode/cli.py`, `README.md`, `tests/test_cli_init.py` | `sac init` front door: interactive TTY wizard (provider, key source, model, policy); setup hidden but callable; non-TTY prints static template. |
| `v4.15.1` ✅ | `main` | `src/safecode/cli_model.py`, `tests/test_cli_model_session_scope.py` | Session-scoped model switching: `sac model <alias>` session-only by default; `--save` persists; `sac model status` shows session vs persisted; legacy env `SAFECODE_LEGACY_MODEL_PERSIST=1` deprecated. |
| `v4.15.2` ✅ | `main` | `src/safecode/security/keychain.py`, `src/safecode/cli_provider.py`, `src/safecode/doctor.py`, `tests/test_provider_keychain_backend.py` | Keychain/env-only credentials: `--api-key` requires `--store user-config|keychain`; keyring backend (macOS Keychain/Linux Secret Service); doctor reports `credential_storage`; provider rm cleans keychain. |
| `v4.16.0` ✅ | `main` | `src/safecode/cli.py`, `tests/test_cli_help_surface_v4_8.py`, `tests/test_cli_default_is_shell.py` | Bare `sac` enters shell; 7-command daily help surface (init, ask, edit, apply, fix, commit, doctor); `sac help --all` shows full surface; 13 commands hidden but callable. |
| `v4.16.1` ✅ | `main` | `src/safecode/cli_project.py`, `src/safecode/doctor.py`, `tests/test_config_migrate.py` | Config migration: `sac config migrate` converts legacy `[llm]` to `[providers.<name>]` with `.bak` backup; doctor warns on legacy section. |
| `v4.16.2` ✅ | `main` | `src/safecode/core/failure_category.py`, `src/safecode/cli.py`, `tests/test_failure_taxonomy_next_command.py` | Error-message rewrite: `FailureCategory.next_command` property; `sac why` prints last failure category + next command (<=3 lines). |

## v4.17.x-v4.18.x: Shell & Interaction UX

Completed. Plan: `docs/version-plans/post-v4.16-shell-ux-roadmap.md` (COMPLETED as of v4.18.1).

| Version | Status | Key Files | Summary |
|---|---|---|---|
| `v4.17.0` ✅ | `main` | `src/safecode/cli_shell.py`, `src/safecode/llm/openai_client.py`, `src/safecode/cli_stream.py` | Streaming output: `sac ask --stream` and `sac shell` default to token-by-token via Rich Live; non-TTY batch unchanged; token-level redaction. |
| `v4.17.1` ✅ | `main` | `src/safecode/cli_shell.py`, `src/safecode/shell_session/` | Shell polish: Rich Markdown rendering, syntax-highlighted diffs, readline completer for slash commands, `/clear` command, readline history persistence. |
| `v4.17.2` ✅ | `main` | `src/safecode/doctor.py`, `src/safecode/cli_provider.py` | Live connectivity: `sac doctor --live` and `sac provider status --live` ping the provider endpoint; opt-in only. |
| `v4.17.3` ✅ | `main` | `src/safecode/cli_model.py`, `src/safecode/llm/provider_profiles.py` | Levenshtein fuzzy matching for model/provider names; suggest closest match when distance ≤ 2. |
| `v4.18.0` ✅ | `main` | `src/safecode/cli_core.py`, `src/safecode/cli_shell.py`, `src/safecode/checkpoint/`, `tests/test_per_patch_undo.py` | Per-patch undo and shell diff rendering: finer-grained checkpoints per patch file; Rich diff in shell `/apply`; `--checkpoint <id>` and `--list` flags on rollback. |
| `v4.18.1` ✅ | `main` | `src/safecode/agent/loop.py`, `src/safecode/cli_shell.py`, `tests/test_agent_loop_transparency.py` | Agent-loop transparency: Rich Status spinner with on_step callback in agentic mode showing current step/intent. |
| `v4.18.2` ✅ | `main` | `src/safecode/cli_core.py`, `src/safecode/checkpoint/`, `tests/test_per_patch_undo.py` | Safety regression fix: `--checkpoint <id>` rollback path was missing `ToolCallGate` check present in `--last`; corrected and covered by 5 new tests (gate enforcement, committed-checkpoint refusal, force-uncommit bypass, audit event emission, task sidecar creation). Full suite 4862 passed, 4 skipped. |

## v4.19.x: Local Observability Polish

Completed. Plan: `docs/version-plans/v4.19.x-local-observability-polish-roadmap.md`.

| Version | Status | Key Files | Summary |
|---|---|---|---|
| `v4.19.0` ✅ | `dev/v4.19` | `src/safecode/cli_task.py`, `tests/test_task_stats.py`, `docs/version-notes/v4.19.0-task-stats.md` | Experimental read-only `sac task stats [--task <id>] [--json]`: deterministic histograms over TaskIteration event/status/failure_category; budget defaults via TaskBudgetStore; pinned file count via MemoryFacade; all fields redacted; closed tasks readable; 16 tests. |
| `v4.19.1` ✅ | `dev/v4.19` | `src/safecode/memory/sizing.py`, `src/safecode/cli_memory.py`, `tests/test_memory_size.py`, `docs/version-notes/v4.19.1-memory-size.md` | Experimental read-only `sac memory size [--json]`: pure Path.stat() walk of .sac/ with named scopes (audit/checkpoints/memory/runtime_logs/tasks/other), temp-file and symlink skipping, Rich Table human output; 12 tests. |
| `v4.19.2` ✅ | `dev/v4.19` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `docs/version_implementation_matrix.md`, `tests/test_mvp_docs.py`, `.claude/skills/current/SKILL.md`, `.claude/versions.json`, `docs/project-final-status-and-roadmap.md`, `docs/version-notes/v4.19.2-observability-docs.md` | v4.19 docs cut: README observability section; MVP guide "Inspecting Local State" section; troubleshooting "Reading local state" entry; matrix v4.19.x rows; docs guard extensions; SKILL.md/versions.json/final-status updated to v4.19.2. |

## v4.20.x: Native Tool Protocol — Read Side

Completed. Plan: `docs/version-plans/v4.20-to-v5.0-product-roadmap.md` (v4.20.x section).

| Version | Status | Key Files | Summary |
|---|---|---|---|
| `v4.20.0` ✅ | `dev/v4.19` | `src/safecode/agent/native_tools.py`, `src/safecode/agent/native_dispatcher.py`, `src/safecode/agent/schemas.py`, `src/safecode/context/budget.py`, `src/safecode/context/collector.py`, `src/safecode/index/files.py`, `tests/test_native_tool_protocol.py`, `docs/version-notes/v4.20.0-native-tool-protocol.md` | Native tool wire format (NativeToolSpec/Call/Result + NativeToolDispatcher). AgentNativeToolCallResponse added to schema union. B4 fix: TOKEN_CHAR_RATIO 4→3.5, _CODE_TOKEN_CHAR_RATIO=3.2. B5 fix: _list_files() returns truncated flag; collect() emits file_tree_meta. B17 fix: pack() skips string/list sources when budget exhausted. 28 tests. |
| `v4.20.1` ✅ | `dev/v4.19` | `src/safecode/agent/read_tools.py`, `tests/test_read_tools.py`, `docs/version-notes/v4.20.1-read-tools.md` | Four read-only native tools: read_file (400-line cap, redacted, sensitive/binary blocked), list_files (500-entry cap, SKIP_DIRS respected, recursive option), search_files (literal substring, 100-result cap, include_glob), grep_files (regex via re, case_insensitive option). All auto-approved, audited as tool_call_read, path-validated. register_read_tools() wires all four. 24 tests. |
| `v4.20.2` ✅ | `dev/v4.19` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `docs/version_implementation_matrix.md`, `tests/test_mvp_docs.py`, `.claude/skills/current/SKILL.md`, `.claude/versions.json`, `docs/version-notes/v4.20.2-read-tools-docs.md` | v4.20 docs cut: README native tool calling section; MVP guide "Exploring a Codebase with Native Tools"; troubleshooting for root-escape, sensitive-path, truncation, and file-tree-cap entries; matrix v4.20.x rows; docs guard tests. |

## v4.21.x: Native Tool Protocol — Write Side

Completed. Plan: `docs/version-plans/v4.20-to-v5.0-product-roadmap.md` (v4.21.x section).

| Version | Status | Key Files | Summary |
|---|---|---|---|
| `v4.21.0` ✅ | `dev/v4.19` | `src/safecode/agent/write_tools.py`, `src/safecode/patch/applier.py`, `src/safecode/agent/loop.py`, `tests/test_write_tools.py`, `docs/version-notes/v4.21.0-edit-and-write-tools.md` | edit_file (unique old_string, checkpoint, diff preview, approval gate) and write_file (create/overwrite, SKIP_DIRS guard, checkpoint, approval gate). B6: patch/applier supports create/delete operations. B7: PatchApplyError(PatchValidationError) wraps PermissionError/OSError. B8: AgentLoop.run() max_steps 5→20. 23 tests. |
| `v4.21.1` ✅ | `dev/v4.19` | `src/safecode/agent/command_tool.py`, `tests/test_run_command_tool.py`, `docs/version-notes/v4.21.1-run-command-tool.md` | run_command native tool via ShellRunner/policy stack; high-risk blocked; cwd validated within project root; timeout_seconds parameter; auto-approved via existing policy. 10 tests. |
| `v4.21.2` ✅ | `dev/v4.19` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `docs/version_implementation_matrix.md`, `tests/test_mvp_docs.py`, `.claude/skills/current/SKILL.md`, `.claude/versions.json`, `docs/version-notes/v4.21.2-write-tools-docs.md` | v4.21 docs cut: README write/command tools section; MVP guide "Making Edits with Native Tools" section; troubleshooting old_string errors, disk-full, rollback, high-risk run_command; matrix rows; doc guard tests. |

## v4.22.x: Multi-Tool Turns + Agentic Shell

Completed. Plan: `docs/version-plans/v4.20-to-v5.0-product-roadmap.md` (v4.22.x section).

| Version | Status | Key Files | Summary |
|---|---|---|---|
| `v4.22.0` ✅ | `dev/v4.19` | `src/safecode/agent/multi_tool_turn.py`, `src/safecode/agent/loop.py`, `tests/test_multi_tool_turn.py`, `docs/version-notes/v4.22.0-multi-tool-turn.md` | MultiToolTurnRunner: dispatch_calls() (20-tool-per-turn cap, redaction) and run_turn() (iterative llm_next_fn loop). B9 fix: stuck-loop guard tracks has_current_task; outside task scope emits RuntimeWarning but does NOT abort. 17 tests. |
| `v4.22.1` ✅ | `dev/v4.19` | `src/safecode/cli_shell.py`, `tests/test_shell_session_quality.py`, `docs/version-notes/v4.22.1-shell-session-quality.md` | B10 fix: /clear calls AgentSessionStore.clear(). B11 fix: _read_line() prints [exiting shell] on EOF. Prompt: sac[N]>. New /undo, /history, /tools commands. 13 tests. |
| `v4.22.2` ✅ | `dev/v4.19` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `docs/version_implementation_matrix.md`, `tests/test_mvp_docs.py`, `.claude/skills/current/SKILL.md`, `.claude/versions.json`, `docs/version-notes/v4.22.2-multi-tool-docs.md` | v4.22 docs cut: README multi-tool/shell section; MVP guide "From Question to Patch in One Turn"; troubleshooting per-turn cap, /clear B10, /undo, B11 EOF; matrix rows; doc guard tests. |

## v4.23.x: Anthropic / Claude as First-Class Provider

Completed. Plan: `docs/version-plans/v4.20-to-v5.0-product-roadmap.md` (v4.23.x section).

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.23.0` ✅ | `dev/v4.19` | `src/safecode/llm/stream.py`, `src/safecode/llm/anthropic_client.py`, `src/safecode/doctor.py`, `tests/test_anthropic_native_tool_use.py`, `docs/version-notes/v4.23.0-anthropic-native-tool-use.md` | B2 fix: _extract_text()/_extract_native_result() validate content list non-empty before access; return RecoverableContractFailure on missing/empty content. B3 fix: StreamTimeoutError(StreamError) added; stream timeout 30s per-chunk; socket.timeout → StreamTimeoutError. B16 fix: Doctor._live_anthropic_ping() authenticated GET /v1/models; shown in sac doctor --live when provider=anthropic. AnthropicLLMClient.choose_tool_native(): sends NativeToolSpec list as Anthropic tools parameter; maps tool_use blocks to AgentNativeToolCallResponse; text fallback → AgentStopForUserResponse. 25 tests. Full suite 5043 passed. |
| `v4.23.1` ✅ | `dev/v4.19` | `src/safecode/llm/openai_client.py`, `src/safecode/llm/retry.py`, `tests/test_openai_native_tool_use.py`, `docs/version-notes/v4.23.1-openai-native-tool-use.md` | B1 fix: _chat() bounds-checks choices[] before indexing; empty/missing choices → "" → RecoverableContractFailure from validate_provider_json. B12 fix: _sanitize_retry_reason() strips https?:// URLs → [URL] and applies redact_secrets(); applied to all retry_call log_fn calls. OpenAICompatibleLLMClient.choose_tool_native(): sends tools (function calling format); maps tool_calls to AgentNativeToolCallResponse; DeepSeek inherits via compat path. 14 tests. Full suite 5057 passed. |
| `v4.23.2` ✅ | `dev/v4.19` | `README.md`, `docs/mvp-user-guide.md`, `docs/security/threat-model-v3.6.md`, `docs/version_implementation_matrix.md`, `tests/test_mvp_docs.py`, `.claude/skills/current/SKILL.md`, `.claude/versions.json`, `docs/version-notes/v4.23.2-provider-docs.md` | v4.23 docs cut: README provider table with anthropic first-class; MVP guide "First-run with Claude" section; threat model v4.23 native tool-use surface addendum; matrix rows; doc guard tests. |

## v4.24.x: Web + GitHub Integration

Completed. Plan: `docs/version-plans/v4.20-to-v5.0-product-roadmap.md` (v4.24.x section).

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.24.0` ✅ | `dev/v4.19` | `src/safecode/agent/web_fetch_tool.py`, `tests/test_web_fetch_tool.py`, `docs/version-notes/v4.24.0-web-fetch-tool.md` | web_fetch: HTTP GET text/HTML only; _MaxRedirectHandler (max 3); _strip_html() removes script/style; requires network: true (blocked by default); only http/https; binary content type → blocked; output capped at max_bytes (50 KB default); URL never in error messages; redact_secrets(). 16 tests. Full suite 5076 passed. |
| `v4.24.1` ✅ | `dev/v4.19` | `src/safecode/agent/github_read_tools.py`, `tests/test_github_read_tools.py`, `docs/version-notes/v4.24.1-github-read-tools.md` | github_read_issue/github_read_pr via gh CLI JSON output; github_read_file via gh api + base64 decode; _validate_gh_name() blocks shell metacharacters; shell=False always; path traversal blocked in read_file; requires network: true; redact_secrets(). 19 tests. |
| `v4.24.2` ✅ | `dev/v4.19` | `src/safecode/agent/github_write_tools.py`, `tests/test_github_write_tools.py`, `README.md`, `docs/mvp-user-guide.md`, `docs/version_implementation_matrix.md`, `tests/test_mvp_docs.py`, `.claude/skills/current/SKILL.md`, `.claude/versions.json`, `docs/version-notes/v4.24.2-github-write-and-docs.md` | github_create_pr (approval-gated, gh pr create) and github_push_branch (approval-gated, git push; force requires explicit flag); _validate_branch(); shell=False; docs cut: README GitHub tools section, MVP guide "From local edits to open PR"; matrix rows; doc guard tests. 21 tests. |

## v4.25.x: Reliability Hardening

Completed. Plan: `docs/version-plans/v4.20-to-v5.0-product-roadmap.md` (v4.25.x section).

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.25.0` ✅ | `dev/v4.19` | `src/safecode/checkpoint/models.py`, `src/safecode/checkpoint/manager.py`, `tests/test_checkpoint.py`, `docs/version-notes/v4.25.0-checkpoint-integrity.md` | B13 fix: CheckpointIntegrityError(RuntimeError) with path/checkpoint_id/expected/actual; _sha256_of_file(); CheckpointFileOperation.backup_sha256 (optional, backward compat); create() stores sha256 after copy2; _restore_checkpoint() pre-flight integrity check — raises CheckpointIntegrityError without touching targets if mismatch; sha256=None skips verification. 5 new tests (7 total). Full suite 5121 passed. |
| `v4.25.1` ✅ | `dev/v4.19` | `src/safecode/doctor.py`, `src/safecode/cli_init.py`, `tests/test_doctor_sac_dir.py`, `tests/test_cli_init_b15.py`, `docs/version-notes/v4.25.1-doctor-and-init-hardening.md` | B14 fix: Doctor._sac_dir_diagnostics() adds sac_dir_writable (probe touch, PASS/FAIL) and disk_space (WARN <100 MB, SKIP on error); appended to run_diagnostics(). B15 fix: cli_init._init_live_connectivity_check() pings API after setup for non-mock providers; yellow warning + sac doctor --live hint on FAIL; never raises. 15 new tests. Full suite 5139 passed. |
| `v4.25.2` ✅ | `dev/v4.19` | `docs/troubleshooting.md`, `docs/version_implementation_matrix.md`, `tests/test_mvp_docs.py`, `.claude/skills/current/SKILL.md`, `.claude/versions.json`, `docs/version-notes/v4.25.2-hardening-docs.md` | v4.25 docs cut: troubleshooting sections for checkpoint integrity error, .sac/ not writable, low disk space, provider not reachable after init; matrix rows; doc guard tests. |

## v5.0.0: First Stable Contract

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v5.0.0` ✅ | `dev/v4.19` | `src/safecode/agent/read_tools.py`, `src/safecode/agent/write_tools.py`, `src/safecode/agent/command_tool.py`, `src/safecode/cli_ops.py`, `docs/public-contracts.md`, `docs/versioning-policy.md`, `docs/security/threat-model-v3.6.md`, `tests/test_v5_stable_contracts.py`, `tests/test_mvp_docs.py`, `.claude/skills/current/SKILL.md`, `.claude/versions.json`, `docs/version-notes/v5.0.0-first-stable-contract.md` | Seven tool specs promoted to experimental=False (read_file, list_files, search_files, grep_files, edit_file, write_file, run_command). sac version --json gains stable_contracts list (12 entries). public-contracts.md sections 13-16 added. versioning-policy.md v5.x contract promise added. threat-model v5.0 stable contract security properties. Zero breaking changes to 12 v4.0 stable contracts. |

## v5.1.x: Agentic Loop Foundation

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v5.1.0` ✅ | `dev/v4.19` | `src/safecode/agent/loop.py`, `src/safecode/llm/anthropic_client.py`, `src/safecode/llm/cost.py`, `src/safecode/checkpoint/models.py`, `src/safecode/cli_shell.py`, `tests/test_auto_edit_mode.py`, `tests/test_llm_cost_accounting.py`, `tests/test_cli_shell.py` | P1: AgentLoop gains `native_step()` wired to MultiToolTurnRunner; `_build_dispatcher()` creates NativeToolDispatcher with read/write/command tools; falls back to step() when LLM has no choose_tool_native. P2: AnthropicLLMClient `_messages()` and `_messages_with_tools()` send block-format system prompt and first user turn with `cache_control: {"type": "ephemeral"}`; `_record_usage()` surfaces cache_read_tokens and cache_creation_tokens; TokenUsage gains two new fields. CheckpointMetadata gains `session_id` field (additive, backward compat). Auto-edit mode: `--auto-edit` flag for `sac shell --agentic`; `AgentLoop(auto_edit=True)` registers write tools with `approved=True`; file count guard at 10 writes/session; session summary printed on exit. 5191 passed, 4 skipped. |
| `v5.1.1` ✅ | `dev/v4.19` | `src/safecode/agent/command_tool.py`, `src/safecode/agent/loop.py`, `src/safecode/cli_shell.py`, `tests/test_full_auto_mode.py`, `tests/test_cli_shell.py` | Full-auto mode: `--full-auto` flag for `sac shell` (implies --agentic); `AgentLoop(full_auto=True)` registers write tools with `approved=True` and command tool with preview+delay; `--command-delay-ms` (0–2000, default 500) grace period before run_command executes; Ctrl-C during delay returns status=blocked; high-risk commands still blocked via ShellRunner policy; `run_command` prints "→ run_command <cmd>" preview and "✓ exit N (Xs)" after; cannot be persisted (session-scoped). 5203 passed, 4 skipped. |
| `v5.1.2` ✅ | `dev/v4.19` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `docs/security/threat-model-v3.6.md`, `tests/test_mvp_docs.py` | Trust modes docs cut: README "Trust Modes (v5.1)" section with mode comparison table; MVP guide "Trust Modes" section with auto-edit walkthrough, full-auto CI example, and session rollback; troubleshooting "Trust Mode Issues" section covering undo-all, file count guard, full-auto unexpected command, Ctrl-C abort, and command-delay-ms; threat model v5.1.0 addendum (trust-mode surface table, mitigations, what does NOT change); 5 doc guard tests. 5208 passed, 4 skipped. |

## v5.2.x: Display Polish

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v5.2.1` ✅ | `dev/v4.19` | `src/safecode/agent/write_tools.py`, `src/safecode/agent/command_tool.py`, `src/safecode/cli_shell.py`, `tests/test_edit_display_polish.py` | Compact diff header: `_compact_diff()` adds `[+N / -M lines] path` as first line; counts added/removed lines from unified diff. Command output collapsing: `_collapse_output()` truncates at 40 lines (first 5 + last 5 + hidden count); `NativeToolResult.metadata` gains `output_collapsed` and `full_output_lines`. Shell prompt with task status: `_shell_prompt(turn, cost_str, task_str)` — `run_shell()` reads task state and formats `task:{status[:4]} · {N}i` into prompt; `_read_line()` accepts `prompt_override`. 15 tests; 5238 passed, 4 skipped. |
| `v5.2.2` ✅ | `dev/v4.19` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `tests/test_mvp_docs.py` | Display docs cut: README "Shell Display (v5.2)" section with prompt format, /cost, compact diff, and output collapsing. MVP guide "Understanding What the Agent Did" section with prompt anatomy, /cost breakdown, diff header, and output collapse example. Troubleshooting "Display Issues" section covering /cost not showing price (mock vs no data), full command output (audit log / JSON mode), and session edit summary. 4 doc guard tests; 5242 passed, 4 skipped. |
| `v5.2.0` ✅ | `dev/v4.19` | `src/safecode/agent/session.py`, `src/safecode/agent/loop.py`, `src/safecode/llm/factory.py`, `src/safecode/cli_shell.py`, `tests/test_session_cost.py`, `tests/test_cli_shell.py`, `tests/test_full_auto_mode.py` | Per-session cost tracking: `AgentSessionState` gains `cost_tokens_in`, `cost_tokens_out`, `cost_cache_read` (additive). `AgentLoop` generates stable `_cost_session_id`; `create_llm_client()` wires `sac_dir` to `OpenAICompatibleLLMClient`/`AnthropicLLMClient` for cost accumulation; `AgentLoop.session_cost()` reads accumulated cost. `_format_cost()` helper formats tokens/USD. `/cost` slash command reads all session cost files. Session end summary includes cost estimate. Agentic shell `--json` output includes `cost` field. `_shell_prompt()` signature updated to accept optional cost string. 5223 passed, 4 skipped. |

## v4.2.x: Project Command Profile

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.2.0` ✅ | `main` | `src/safecode/project/profile.py`, `src/safecode/cli_profile.py`, `tests/test_project_profile.py`, `tests/test_cli_profile.py` | T-4.2.0-A project-profile-detector: `ProjectProfile` Pydantic model (payload_version=1, test/lint/typecheck/build: ProfileCommand\|None, user_overrides: frozenset[str]); `ProfileCommand` (command: tuple[str,...], stack, source: detected\|user\|none, missing_dependency); atomic persist to .sac/project_profile.json; detects Python (pytest/ruff/mypy), Node (npm/pnpm/yarn scripts), Go (go test/vet/build), Rust (cargo test/clippy/check/build); missing tool → missing_dependency=True; user overrides survive detect. T-4.2.0-B sac-profile-cli: `sac profile detect\|show\|set\|clear`; `set` parses with shlex.split and rejects ; \| & $ \` and newline; `show --json` deterministic; profile registered in cli.py; matrix heading fixed from v4.0.1 to v4.1.2. 87 targeted tests; full suite 3972 passed, 2 skipped; contract snapshots green. |
| `v4.2.1` ✅ | `main` | `src/safecode/cli_core.py`, `src/safecode/cli_fix.py`, `tests/test_sac_run_suite.py`, `tests/test_sac_fix.py` | T-4.2.1-A sac-run-suite: `sac run --suite test\|lint\|typecheck\|build`; reads .sac/project_profile.json; missing profile → "run sac profile detect" guidance; missing kind → actionable message; auto-approved (--yes=True) since user explicitly selected; high-risk still blocked; audit/task wiring/exit codes unchanged from sac run. T-4.2.1-B fix-uses-profile: `sac fix` precedence: --test-command > profile test > ProjectTestDetector; profile never auto-set by fix. 43 new tests; full suite 3991 passed, 2 skipped; contract snapshots green. |
| `v4.2.2` ✅ | `main` | `src/safecode/doctor.py`, `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `tests/test_doctor_missing_deps.py` | T-4.2.2-A doctor-missing-deps: `Doctor._project_tooling_diagnostics()` added; no profile → single SKIP "run sac profile detect"; with profile → one diagnostic per kind (test/lint/typecheck/build): PASS (detected+binary present), SKIP (not detected or missing_dependency=True); missing tool → SKIP not FAIL; SKIP includes binary name and sac profile set hint; diagnostic substrate contract preserved. T-4.2.2-B v4.2-docs-cut: README "Profile commands (v4.2)" section; mvp-user-guide.md updated to v4.2.x + profile flow section; troubleshooting.md missing-tool section; all v4.2 surfaces EXPERIMENTAL. 30 new tests; full suite 4005 passed, 2 skipped; contract snapshots green. |

## v4.3.x: Reliable Test-Fix Loop

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.3.0` ✅ | `main` | `src/safecode/cli_fix.py`, `src/safecode/task/state.py`, `src/safecode/task/wiring.py`, `tests/test_fix_iteration_record.py`, `tests/test_fix_watch_mode.py` | T-4.3.0-A fix-loop-iteration-record: task sidecar fix iterations now carry experimental loop metadata (`mode`, `suite`, `exit_code`, `tail_hash`, `pending_patch_path`, `status`, `created_at`) while preserving existing v4.1 fields; hashes use a bounded redacted failure tail and do not store raw long output. T-4.3.0-B fix-watch-mode: `sac fix --watch [--max-iterations N=3] [--rerun-suite test]` runs one approval-gated loop step, proposes a pending patch on failure, prints next step `sac apply` then rerun, marks passing reruns applied, and never auto-applies. Targeted slice 124 passed; full/preflight validation run as part of release train. |
| `v4.3.1` ✅ | `main` | `src/safecode/cli_fix.py`, `src/safecode/shell/runner.py`, `src/safecode/task/state.py`, `tests/test_fix_loop_no_progress.py`, `tests/test_fix_watch_mode.py`, `tests/test_sac_fix.py` | T-4.3.1-A no-progress-stop: `sac fix --watch` stops before proposing another patch when two consecutive failing fix iterations have the same bounded redacted `tail_hash`; task sidecar and JSON carry experimental `failure_category: loop_no_progress`. T-4.3.1-B fix-timeout-and-broader-tests: `sac fix --timeout-seconds N` defaults to 120 and timeout exits 124 with `failure_category: command_timeout`; `--rerun-suite test\|all` added; `all` runs profile suites in order test/lint/typecheck/build via `ShellRunner`/policy, skips missing suites, and stops safely for blocked suite commands. Targeted slice 143 passed; full/preflight validation run as part of release train. |
| `v4.3.2` ✅ | `main` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `tests/test_mvp_docs.py`, `docs/version-notes/v4.3.2-fix-watch-docs.md` | T-4.3.2-A v4.3-docs-cut: README Core Commands documents `sac fix --watch`, `--max-iterations`, `--timeout-seconds`, and `--rerun-suite`; MVP guide documents the approval-gated loop `sac fix --watch` → review → `sac apply` → `sac fix --watch`; troubleshooting covers `loop_no_progress`, `command_timeout`, max iterations reached, blocked suite command, and missing profile suite. All v4.3 surfaces marked EXPERIMENTAL; `sac fix --watch` never auto-applies; no stable contract promotion. |

## v4.4.x: Resume / Recovery / Budgets

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.4.0` ✅ | `main` | `src/safecode/cli_resume.py`, `src/safecode/task/recovery.py`, `src/safecode/cli_core.py`, `src/safecode/cli_fix.py`, `tests/test_sac_resume.py`, `tests/test_interrupt_durable.py`, `docs/version-notes/v4.4.0-resume-and-interrupt.md` | T-4.4.0-A sac-resume: top-level experimental `sac resume [<task_id>]` supports explicit/CURRENT/newest interrupted-open selection, refuses closed tasks, reopens interrupted tasks to open, sets CURRENT, and prints redacted passive resume summaries with next safe step. T-4.4.0-B sigint-durable-interrupt: `sac edit`, `sac fix`, `sac fix --watch`, and `sac run` catch KeyboardInterrupt only, mark task status `interrupted`, append an interrupted iteration marker, record journal/audit interruption metadata where available, print `resume with: sac resume`, exit 130, and leave pending patch files untouched. Targeted slice 149 passed; full/preflight validation run as part of release train. |
| `v4.4.1` ✅ | `main` | `src/safecode/task/budget.py`, `src/safecode/cli_task.py`, `src/safecode/agent/loop.py`, `tests/test_task_budget.py`, `tests/test_loop_stuck_guard.py`, `tests/test_agent_loop_error_recovery.py`, `docs/version-notes/v4.4.1-budgets-and-stuck-loop.md` | T-4.4.1-A task-budget-config: per-task experimental budgets default to steps=8, time_seconds=600, retries=2, tokens=60000; `sac task budget show\|set` supports CURRENT or `--task`, JSON output, and positive integer validation; `AgentLoop.run()` enforces step budget and records `failure_category: budget_exceeded`. T-4.4.1-B stuck-loop-guard: `AgentLoop` aborts after three identical consecutive tool intent identities `(type, target, tool_name, description)`, journals `failure_category: loop_stuck`, records a task marker when available, and does not count recoverable contract retries as emitted tool intents. Targeted slice 124 passed; full/preflight validation run as part of release train. |
| `v4.4.2` ✅ | `main` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `tests/test_mvp_docs.py`, `docs/version-notes/v4.4.2-resume-recovery-budget-docs.md` | T-4.4.2-A v4.4-docs-cut: README Core Commands documents `sac resume`, `sac task budget show`, and `sac task budget set`; MVP guide documents resume after Ctrl-C, interrupted task recovery, task budget usage, and stuck-loop guard behavior; troubleshooting covers interrupted tasks, `budget_exceeded`, `loop_stuck`, and resume refusing closed tasks. All v4.4 surfaces remain EXPERIMENTAL; no stable contract promotion. |

## v4.5.x: Local Git Delivery

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.5.0` ✅ | `main` | `src/safecode/git/local.py`, `src/safecode/cli_commit.py`, `src/safecode/cli_core.py`, `tests/test_sac_commit.py`, `tests/test_dirty_worktree_guard.py`, `docs/version-notes/v4.5.0-local-commit-and-dirty-tree-guard.md` | T-4.5.0-A sac-commit: experimental `sac commit` derives the current task file set from applied checkpoint/audit metadata, stages only those files, creates deterministic task messages, refuses non-git repos or unknown task files, and keeps all git subprocesses argv-only with `shell=False` and no push/remote path. T-4.5.0-B dirty-tree-guard: `sac apply` and `sac commit` refuse unrelated tracked/staged changes, ignore untracked files outside touched directories, block untracked files inside touched directories, and support explicit `--allow-unrelated-changes`. Targeted slice green; full/preflight validation run as part of release train. |
| `v4.5.1` ✅ | `main` | `src/safecode/git/local.py`, `src/safecode/cli_commit.py`, `src/safecode/cli_core.py`, `tests/test_sac_branch_new.py`, `tests/test_rollback_after_commit.py`, `docs/version-notes/v4.5.1-branch-and-rollback-commit-guard.md` | T-4.5.1-A sac-branch-new: `sac branch new <name>` validates names, refuses existing branches and dirty unrelated changes, uses `git check-ref-format --branch`, never force-creates, and never resets. T-4.5.1-B rollback-after-commit-warn: `sac rollback --last` refuses when the latest apply appears committed, prints a `git revert <sha>` hint, allows explicit `--force-uncommit`, and audits the commit sha while preserving uncommitted rollback behavior. Targeted slice green; full/preflight validation run as part of release train. |
| `v4.5.2` ✅ | `main` | `src/safecode/cli_commit.py`, `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `tests/test_sac_diff_task.py`, `tests/test_mvp_docs.py`, `docs/version-notes/v4.5.2-task-diff-and-local-git-docs.md` | T-4.5.2-A sac-diff-task: `sac diff --task [<task_id>] [--json]` is read-only, resolves CURRENT when omitted, returns deterministic file ordering, shows applied task diffs plus pending patch previews where available, redacts content, and returns deterministic empty results for missing tasks. T-4.5.2-B v4.5-docs-cut: README, MVP guide, troubleshooting, matrix, and version note document `sac commit`, `sac branch new`, `sac diff --task`, dirty-tree guard, rollback-after-commit warning, branch refusal, and unknown task-file handling. Targeted slice green; full/preflight validation run as part of release train. |

## v4.6.x: Project Memory and Rules

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.6.0` ✅ | `main` | `src/safecode/memory/facade.py`, `src/safecode/cli_memory.py`, `src/safecode/memory/store.py`, `src/safecode/cli.py`, `tests/test_memory_facade.py`, `tests/test_cli_memory.py`, `docs/version-notes/v4.6.0-memory-facade-and-cli.md` | T-4.6.0-A memory-unification: experimental `MemoryFacade` reads legacy memory/progress/rules, writes only to the new `.sac/memory/` and per-task memory layout, caps recent failures/edits at 200, redacts CLI reads, rejects obvious secret writes, and normalizes pinned files under the project root. T-4.6.0-B sac-memory-cli: experimental hidden-but-help-accessible `sac memory show|pin|unpin|add-note|clear` supports JSON via `CLIJSONResponse`; `clear` requires confirmation or `--yes`; pinned paths are sorted, unique, deterministic, and root-escape-safe. Targeted slice 146 passed; full suite 4097 passed, 2 skipped; release preflight passed. |
| `v4.6.1` ✅ | `main` | `src/safecode/context/selector.py`, `src/safecode/context/collector.py`, `src/safecode/cli_fix.py`, `tests/test_context_pinned_files.py`, `tests/test_fix_recent_failures_memory.py`, `docs/version-notes/v4.6.1-pinned-context-and-fix-memory.md` | T-4.6.1-A pinned-files-in-context: safe pinned files from `MemoryFacade` are considered alongside keyword-ranked context, capped by a selector quota, missing pins expose deterministic `pinned_missing` metadata, and ignored/sensitive/binary/root-escaping pins remain excluded. T-4.6.1-B recent-failures-into-fix: `sac fix` and `sac fix --watch` append redacted bounded failures to recent-failures memory, cap at 200, and include the newest three as prompt context. Targeted slice green; full/preflight validation run as part of release train. |
| `v4.6.2` ✅ | `main` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `tests/test_mvp_docs.py`, `docs/version-notes/v4.6.2-memory-docs.md` | T-4.6.2-A v4.6-docs-cut: README documents experimental `sac memory show|pin|unpin|add-note|clear`; MVP guide documents the unified memory layout, project/task notes, pinned files and context quota, and recent failures helping `sac fix`; troubleshooting covers missing pins, outside-root pins, secret rejection, and stale recent-failure memory. Docs guard tests verify every documented v4.6 memory command exists. |

## v4.7.x: Debug Bundle and Failure Taxonomy

| 版本 | 分支 | 主要入口 | 验收命令 / 结果 |
|---|---|---|---|
| `v4.7.0` ✅ | `main` | `src/safecode/core/failure_category.py`, `src/safecode/cli_debug.py`, `src/safecode/logs/runtime.py`, `tests/test_failure_taxonomy.py`, `tests/test_debug_last_failure.py`, `docs/version-notes/v4.7.0-failure-taxonomy-and-debug-last-failure.md` | T-4.7.0-A runtime-failure-taxonomy: experimental runtime-wide failure categories plus suggested-command table; runtime log events gain optional `failure_category` while older logs still parse; mapped existing CLI/orchestrator/shell/sandbox/MCP/loop failure paths without changing stable contracts. T-4.7.0-B sac-debug-last-failure: experimental read-only `sac debug last-failure [--task <id>] [--json]` summarizes redacted local runtime/task/memory/audit failure evidence and never executes project commands. Targeted slice 106 passed; full suite 4121 passed, 2 skipped. |
| `v4.7.1` ✅ | `main` | `src/safecode/debug/bundle.py`, `src/safecode/cli_debug.py`, `src/safecode/cli_ops.py`, `src/safecode/audit/logger.py`, `tests/test_debug_bundle.py`, `tests/test_audit_query.py`, `docs/version-notes/v4.7.1-debug-bundle-and-audit-query.md` | T-4.7.1-A sac-debug-bundle: experimental `sac debug bundle` writes a redacted tar.gz with manifest, version/config/doctor/runtime/audit/task/profile/memory metadata, excludes project source, refuses overwrite without `--force`, verifies audit integrity, and enforces a 5 MiB cap. T-4.7.1-B sac-audit-query: experimental read-only `sac audit query` verifies audit integrity before deterministic type/since/task/limit filtering and never writes audit events. Targeted slice 114 passed; full suite 4135 passed, 2 skipped. |
| `v4.7.2` ✅ | `main` | `README.md`, `docs/mvp-user-guide.md`, `docs/troubleshooting.md`, `tests/test_mvp_docs.py`, `docs/version-notes/v4.7.2-debug-docs.md` | T-4.7.2-A v4.7-docs-cut: README documents experimental debug/audit commands; MVP guide documents the debug workflow; troubleshooting documents every failure category with meaning, likely cause, and code-table suggested command; docs guards verify table agreement and command existence. Targeted docs/public-contract slice 125 passed; full suite 4138 passed, 2 skipped. |
| `v4.8.0` ✅ | `main` | `src/safecode/cli_smoke.py`, `src/safecode/cli.py`, `src/safecode/cli_core.py`, `src/safecode/cli_ops.py`, `src/safecode/cli_commit.py`, `tests/test_smoke_shell_first.py`, `tests/test_cli_help_surface_v4_8.py`, `docs/version-notes/v4.8.0-smoke-shell-first-and-cli-trim.md` | T-4.8.0-A smoke-shell-first: new `sac smoke shell-first` with 8 deterministic workflow scenarios (docs-edit-task, failing-test-repair-with-fix-watch, command-profile-detection, dirty-tree-refusal, rollback-after-commit-warn, resume-after-sigint, debug-bundle-redaction, pinned-files-in-context) under mock provider only; hidden but callable; JSON output via CLIJSONResponse. T-4.8.0-B cli-surface-trim: root `sac --help` trimmed to exactly 17 visible daily-loop commands; `memory` promoted from hidden to visible; all trimmed commands remain callable. Full suite 4230 passed, 2 skipped. |
| `v4.8.1` ✅ | `main` | `docs/tutorials/python-first-hour.md`, `docs/tutorials/typescript-first-hour.md`, `docs/tutorials/go-first-hour.md`, `tests/test_docs_claims_guard.py`, `docs/version-notes/v4.8.1-v4-tutorials-and-doc-guards.md` | T-4.8.1-A tutorials-v4-rewrite: new Python tutorial and rewritten TypeScript/Go tutorials built around the v4.x task-first daily loop; all three are honest (no auto-apply, no auto-commit, no push, no live provider required, no IDE required) and mark all v4.x surfaces EXPERIMENTAL. T-4.8.1-B docs-claims-guard-extend: 46 new tests verifying tutorial existence, daily-loop coverage per tutorial, honesty guards, CLI command existence, stack-specific content, failure taxonomy command existence, and visible command documentation coverage. Full suite 4276 passed, 2 skipped. |
| `v4.8.2` ✅ | `main` | `README.md`, `docs/mvp-user-guide.md`, `docs/public-contracts.md`, `docs/versioning-policy.md`, `docs/security/threat-model-v3.6.md`, `docs/version-notes/v4.8.2-final-v4-shell-first-docs-cut.md` | T-4.8.2-A v4.8-final-docs-cut: README adds Python tutorial link and task-first daily loop summary with 17-command surface and v4.x train closure note; MVP guide updated to v4.8.x with Task-First Daily Loop section; public-contracts adds v4.x series summary (zero new stable contracts v4.0–v4.8); versioning-policy adds v4.x train closure section and v4.8.2 changelog entry; threat-model adds v4.x shell-first addendum table for all new surfaces. Full suite 4276 passed, 2 skipped. |
