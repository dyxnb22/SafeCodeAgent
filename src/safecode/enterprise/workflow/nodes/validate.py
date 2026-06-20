"""validate 工作流节点（九步流水线第 7 步）。

- **流水线位置**：第 7 步 / 9 — 对提案运行测试、扫描器或策略一致性检查。
- **输入**：``proposals``、任务证据及（remediation）补丁提案引用。
- **输出**：``validation``（``ValidationResult``）与 ``validation_failed`` 标志。
- **安全治理**：工具驱动、确定性校验；校验失败时节点状态为 ``soft_failure``，
  阻断 ``approval_gate`` 放行；secure_planning 路径显式跳过扫描器并记录原因。
"""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState, ValidationResult
from safecode.enterprise.workflow.tasks import remediation, secure_planning

NODE_NAME = "validate"


async def run(state: EnterpriseRunState) -> NodePatch:
    """执行任务相关的预应用或默认校验，记录通过/失败结果。"""
    if secure_planning.is_secure_planning_task(state):
        validation = ValidationResult(
            passed=True,
            summary="validation skipped for secure_planning workflow",
            details={"skipped": "secure_planning does not run scanners"},
        )
        return build_patch(
            state,
            NODE_NAME,
            summary=validation.summary,
            state_updates={"validation": validation, "validation_failed": False},
        )
    if remediation.is_remediation_task(state):
        validation = remediation.run_pre_apply_validation(state)
        return build_patch(
            state,
            NODE_NAME,
            summary=validation.summary,
            state_updates={
                "validation": validation,
                "validation_failed": not validation.passed,
            },
            status="soft_failure" if not validation.passed else "ok",
        )
    failed = state.request.extra.get("validation_failed") == "1"
    validation = ValidationResult(
        passed=not failed,
        summary="validation failed" if failed else "validation passed",
    )
    return build_patch(
        state,
        NODE_NAME,
        summary=validation.summary,
        state_updates={"validation": validation, "validation_failed": failed},
        status="soft_failure" if failed else "ok",
    )
