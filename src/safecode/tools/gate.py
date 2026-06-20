"""Universal tool call gate — pre-flight check for write/execute/dispatch paths (v2.3.7).

Every CLI and agent-loop path that can write, execute, apply, dispatch, or communicate
with tools must pass this gate *before* performing side effects.  Fails closed:
unknown tool names, missing required args, invalid arg types, and unapproved
approval-required tools are all blocked here.

中文模块说明：通用工具调用门控（ToolCallGate）。
- 所有可能产生写操作、执行、派发或工具通信的路径必须在副作用发生前通过本门；失败即关闭（fail-closed）。
- 本类不执行任何工具、不写文件；仅做校验与审批状态检查，模型输出永远不能替代 `approved=True`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from safecode.tools.adapter import AdapterError, ToolCallAdapter, ToolCallValidationResult
from safecode.tools.registry import ToolRegistry


@dataclass(frozen=True)
class GateResult:
    """Outcome of a ToolCallGate check.

    工具门校验结果；调用方必须检查 ``allowed``，不得仅凭 validation 非空即继续执行。
    """

    allowed: bool
    reason: str
    validation: ToolCallValidationResult | None = None


class GateError(ValueError):
    """Raised by ToolCallGate.must_pass() / must_pass_intent() when the gate blocks.

    门控拒绝时抛出；表示该次工具调用未获授权，须人工审批或修正参数后重试。
    """


class ToolCallGate:
    """Pre-flight gate that wraps ToolCallAdapter.

    Fail-closed contract:
    - Unknown tool name                         → blocked
    - Missing required arg                      → blocked
    - Wrong arg type                            → blocked
    - requires_human_approval=True, approved=False → blocked

    No tool is executed or any file written by this class.

    工具调用预检门：包装 ToolCallAdapter，在副作用前统一校验。
    安全不变量：未知工具名、缺参、类型错误、未审批的高风险工具一律拒绝；
    ``approved`` 须由调用方在获得人类确认后显式传入，Agent 不得自行置 True。
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._adapter = ToolCallAdapter(registry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self, tool_name: str, args: dict[str, Any], *, approved: bool = False
    ) -> GateResult:
        """Full gate check: validates name, required args, arg types, and approval.

        Args:
            tool_name: Registered tool name (e.g. ``"patch.apply"``).
            args:      Dict of arguments as they would be passed to the tool.
            approved:  True if the caller has already obtained human approval for
                       this specific invocation (e.g. after typer.confirm).

        Returns a :class:`GateResult` with ``allowed=False`` to block; callers must
        inspect ``allowed`` before proceeding.

        完整门控：校验工具名、必填参数、参数类型及审批状态。
        返回 ``allowed=False`` 时调用方必须中止，不得降级为 intent 检查或跳过审批。
        """
        try:
            validation = self._adapter.validate(tool_name, args)
        except AdapterError as exc:
            return GateResult(allowed=False, reason=str(exc))

        if validation.requires_approval and not approved:
            # 安全不变量：需人工审批的工具在 approved=False 时必须拒绝，无例外路径。
            return GateResult(
                allowed=False,
                reason=f"Tool {tool_name!r} requires human approval before execution.",
                validation=validation,
            )

        return GateResult(allowed=True, reason="ok", validation=validation)

    def check_intent(
        self, tool_name: str, *, approved: bool = False
    ) -> GateResult:
        """Intent-level gate: validates name and approval state only (no arg validation).

        Use when the full argument dict is not yet available at the call site
        (e.g. the LLM will generate them later, or the CLI accepts a free-form task
        string rather than structured tool args).

        意图级门控：仅校验工具名与审批状态，不校验参数。
        注意：后续实际执行前仍须调用 ``check`` / ``must_pass`` 做完整参数校验，
        不得仅凭 intent 通过即执行写操作。
        """
        try:
            spec = self._adapter.lookup(tool_name)
        except AdapterError as exc:
            return GateResult(allowed=False, reason=str(exc))

        validation = ToolCallValidationResult(
            tool_name=tool_name,
            spec=spec,
            resolved_args={},
            requires_approval=spec.requires_human_approval,
            risk=spec.risk,
            permission_category=spec.permission_category,
            audit_event=spec.audit_event,
        )

        if validation.requires_approval and not approved:
            # intent 路径同样遵守审批不变量，不能因缺参而绕过审批。
            return GateResult(
                allowed=False,
                reason=f"Tool {tool_name!r} requires human approval before execution.",
                validation=validation,
            )

        return GateResult(allowed=True, reason="ok", validation=validation)

    def must_pass(
        self, tool_name: str, args: dict[str, Any], *, approved: bool = False
    ) -> ToolCallValidationResult:
        """Like :meth:`check` but raises :class:`GateError` instead of returning blocked.

        与 ``check`` 相同，但拒绝时抛 GateError，供必须 fail-fast 的调用路径使用。
        """
        result = self.check(tool_name, args, approved=approved)
        if not result.allowed:
            raise GateError(result.reason)
        assert result.validation is not None  # always set when allowed
        return result.validation

    def must_pass_intent(
        self, tool_name: str, *, approved: bool = False
    ) -> ToolCallValidationResult:
        """Like :meth:`check_intent` but raises :class:`GateError` instead of returning blocked.

        与 ``check_intent`` 相同，但拒绝时抛 GateError。
        """
        result = self.check_intent(tool_name, approved=approved)
        if not result.allowed:
            raise GateError(result.reason)
        assert result.validation is not None
        return result.validation
