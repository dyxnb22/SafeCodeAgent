"""Tool dispatcher and _execute_* step helpers for AgentLoop (v6.29).

Extracted from loop.py as _DispatcherMixin. Covers:
- _build_dispatcher              (NativeToolDispatcher factory with plan/build mode)
- _enrich_with_subagent_findings (inject merged subagent context + synthesis)
- _execute_mcp_readonly_step     (read-only MCP tool call)
- _execute_subagent_dispatch_step (read-only subagent investigation)
- _execute_patch_proposal_step   (pending patch proposal; auto-apply in auto_edit/full_auto)
- _find_approved_write_proposal  (look up approved MCP write proposal by tool_name)
- _execute_mcp_approved_write_step (consume + run an approved MCP write)
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from safecode.agent.loop_types import AgentStepResult
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.orchestrator import AgentOrchestrator
from safecode.agent.pending_action import PatchPendingAction
from safecode.agent.session import AgentSessionState
from safecode.agent.tools import RoutedToolIntent
from safecode.context.redactor import redact_secrets
from safecode.core.failure_category import FailureCategory
from safecode.logs.runtime import RuntimeLogger
from safecode.mcp.loop_executor import MCPApprovedWriteExecutor, MCPReadToolExecutor
from safecode.mcp.proposal import MCPWriteProposal, MCPWriteProposalStore
from safecode.subagents.executor import SubagentDispatchExecutor
from safecode.subagents.journal_adapter import findings_from_journal_events
from safecode.subagents.merge_policy import merge_subagent_findings
from safecode.subagents.synthesis import synthesize_findings

if TYPE_CHECKING:
    from safecode.agent.loop import AgentLoop


class _DispatcherMixin:
    """Tool dispatcher and execute-step methods — mixed into AgentLoop."""

    # ------------------------------------------------------------------
    # Dispatcher factory
    # ------------------------------------------------------------------

    def _build_dispatcher(self: "AgentLoop") -> NativeToolDispatcher:
        """Create a NativeToolDispatcher with native tools registered.

        When auto_edit=True or full_auto=True, write tools are registered with
        approved=True so they execute immediately without blocking.
        In full_auto mode, run_command is registered with a delay for Ctrl-C abort.
        Policy gates (high-risk blocking) still apply via ShellRunner.
        In plan_mode, only read/search/reference tools are registered.
        """
        from safecode.agent.read_tools import register_read_tools
        from safecode.agent.write_tools import register_write_tools
        from safecode.agent.command_tool import register_command_tool
        from safecode.mcp.native_bridge import register_mcp_tools
        from safecode.agent.find_references_tool import register_find_references_tool

        dispatcher = NativeToolDispatcher()
        register_read_tools(dispatcher, self.project_root)
        if self.plan_mode:
            register_mcp_tools(dispatcher, self.project_root)
            register_find_references_tool(dispatcher, self.project_root)
            return dispatcher
        write_approved = self.auto_edit or self.full_auto
        register_write_tools(dispatcher, self.project_root, approved=write_approved)
        cmd_delay = self.command_delay_ms if self.full_auto else -1
        register_command_tool(dispatcher, self.project_root, full_auto_delay_ms=cmd_delay)
        register_mcp_tools(dispatcher, self.project_root)
        register_find_references_tool(dispatcher, self.project_root)
        return dispatcher

    # ------------------------------------------------------------------
    # Subagent context enrichment
    # ------------------------------------------------------------------

    def _enrich_with_subagent_findings(
        self: "AgentLoop", session_id: str, context: dict
    ) -> dict:
        """Inject merged subagent findings and synthesis into planning context.

        Secrets are redacted before injection. Fails closed: any error leaves
        context unchanged and emits a warning without interrupting the loop.
        """
        try:
            events = self.journal.read(session_id)
            findings = findings_from_journal_events(events)
            merged = merge_subagent_findings(findings)
            if merged.source_task_ids or merged.blocked_task_ids or merged.errors:
                redacted_summary = redact_secrets(merged.summary)
                redacted_observations = [redact_secrets(o) for o in merged.observations]
                redacted_errors = [redact_secrets(e) for e in merged.errors]
                if (
                    redacted_summary != merged.summary
                    or redacted_observations != list(merged.observations)
                    or redacted_errors != list(merged.errors)
                ):
                    warnings.warn(
                        "consumer-side redaction changed merged subagent text; "
                        "producer-side redaction may have missed a secret",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                context["subagent_findings"] = {
                    "summary": redacted_summary,
                    "observations": redacted_observations,
                    "files_inspected": merged.files_inspected,
                    "source_task_ids": merged.source_task_ids,
                    "blocked_task_ids": merged.blocked_task_ids,
                    "errors": redacted_errors,
                }
                try:
                    synthesis = synthesize_findings(findings, self.llm_client)
                    context["subagent_synthesis"] = {
                        "summary": synthesis.summary,
                        "key_findings": synthesis.key_findings,
                        "risks": synthesis.risks,
                        "source_task_ids": synthesis.source_task_ids,
                        "used_fallback": synthesis.used_fallback,
                    }
                except Exception as syn_exc:
                    warnings.warn(
                        f"subagent synthesis failed (merged findings preserved): {type(syn_exc).__name__}",
                        RuntimeWarning,
                        stacklevel=2,
                    )
        except Exception as exc:
            warnings.warn(
                f"subagent enrichment failed (context unchanged): {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
        return context

    # ------------------------------------------------------------------
    # MCP read-only step
    # ------------------------------------------------------------------

    def _execute_mcp_readonly_step(
        self: "AgentLoop",
        plan_item: str,
        state: AgentSessionState,
        routed: RoutedToolIntent,
    ) -> AgentStepResult:
        """Execute a validated read-only MCP tool call and record the observation."""
        intent = routed.intent
        tool_name = intent.tool_name or ""
        input_json = intent.input_json or {}

        mcp_result = MCPReadToolExecutor(self.project_root).execute(tool_name, input_json)

        step_label = f"Step {state.current_step + 1}: {plan_item}"
        observation = f"{step_label} → MCP [{tool_name}]: {mcp_result.observation}"
        pending_action: dict[str, object] = {
            "type": "mcp",
            "route": routed.route,
            "tool_name": tool_name,
            "executable_now": "true",
            "reason": routed.reason,
            "mcp_success": str(mcp_result.success).lower(),
            "mcp_blocked": str(mcp_result.blocked).lower(),
            "mcp_exit_code": str(mcp_result.exit_code),
        }
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "active",
                "last_error": None if mcp_result.success else mcp_result.observation,
            }
        )
        saved = self.store.save(updated)
        call_summary: dict[str, object] = {
            "tool_name": tool_name,
            "server": mcp_result.server,
            "tool": mcp_result.tool,
            "success": mcp_result.success,
            "blocked": mcp_result.blocked,
            "exit_code": mcp_result.exit_code,
            **mcp_result.metadata,
        }
        self.journal.record_mcp_call(
            saved.session_id, saved.current_step, observation, call_summary,
        )
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=False,
            session_id=saved.session_id,
        )
        return AgentStepResult(state=saved, observation=observation)

    # ------------------------------------------------------------------
    # Subagent dispatch step
    # ------------------------------------------------------------------

    def _execute_subagent_dispatch_step(
        self: "AgentLoop",
        plan_item: str,
        state: AgentSessionState,
        routed: RoutedToolIntent,
    ) -> AgentStepResult:
        """Dispatch a read-only subagent investigation and record the structured result."""
        intent = routed.intent
        input_json = intent.input_json or {}
        task = input_json["task"] if "task" in input_json else (intent.description or "")
        scope = input_json.get("scope")
        max_steps = input_json.get("max_steps")

        sub_result = SubagentDispatchExecutor(self.project_root).execute(task, scope, max_steps)

        step_label = f"Step {state.current_step + 1}: {plan_item}"
        observation = f"{step_label} → Subagent [{sub_result.task_id}]: {sub_result.summary}"
        pending_action: dict[str, object] = {
            "type": "subagent",
            "route": routed.route,
            "task_id": sub_result.task_id,
            "executable_now": "true",
            "reason": routed.reason,
            "subagent_success": str(sub_result.success).lower(),
            "subagent_blocked": str(sub_result.blocked).lower(),
        }
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "active",
                "last_error": None if sub_result.success else sub_result.summary,
            }
        )
        saved = self.store.save(updated)
        dispatch_summary: dict[str, object] = {
            "task_id": sub_result.task_id,
            "task": task,
            "scope": scope,
            "max_steps": max_steps,
            "summary": sub_result.summary,
            "observations": list(sub_result.observations),
            "files_inspected": list(sub_result.files_inspected),
            "blocked_actions": list(sub_result.blocked_actions),
            "errors": list(sub_result.errors),
            "success": sub_result.success,
            "blocked": sub_result.blocked,
        }
        self.journal.record_subagent_dispatch(
            saved.session_id, saved.current_step, observation, dispatch_summary,
        )
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=False,
            session_id=saved.session_id,
        )
        return AgentStepResult(state=saved, observation=observation)

    # ------------------------------------------------------------------
    # Patch proposal step
    # ------------------------------------------------------------------

    def _execute_patch_proposal_step(
        self: "AgentLoop",
        plan_item: str,
        state: AgentSessionState,
        routed: RoutedToolIntent,
    ) -> AgentStepResult:
        """Generate a pending patch proposal via AgentOrchestrator and stop for approval.

        Fail closed: if a pending patch already exists, stop for approval without
        overwriting. If proposal generation fails, record the error without modifying
        any business/source files.
        """
        pending_patch_path = self.project_root / ".sac" / "pending_patch.json"

        if pending_patch_path.exists():
            observation = (
                "A pending patch already exists and requires review before a new one "
                "can be created. Run 'sac apply' to review and apply it, or "
                "'sac rollback' to discard it."
            )
            existing_patch_action = PatchPendingAction(
                route=routed.route,
                requires_approval=True,
                reason="pending_patch_already_exists",
                pending_patch_path=str(pending_patch_path),
                target=str(routed.intent.target or ""),
            )
            pending_action: dict[str, object] = existing_patch_action.to_dict()
            updated = state.model_copy(
                update={
                    "pending_action": pending_action,
                    "last_observation": observation,
                    "status": "waiting_for_user",
                    "last_error": observation,
                }
            )
            saved = self.store.save(updated)
            self.journal.record_action(
                saved.session_id, saved.current_step, observation, pending_action,
            )
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=pending_action,
                observation=observation,
                stopped_for_approval=True,
                session_id=saved.session_id,
            )
            return AgentStepResult(state=saved, observation=observation, stopped_for_approval=True)

        try:
            edit_result = AgentOrchestrator(self.project_root, llm_client=self.llm_client).edit(state.goal)
        except Exception as exc:
            observation = f"Patch proposal failed: {exc}"
            failed_patch_action = PatchPendingAction(
                route=routed.route,
                requires_approval=True,
                reason="patch_proposal_failed",
                target=str(routed.intent.target or ""),
            )
            err_action: dict[str, object] = failed_patch_action.to_dict()
            updated = state.model_copy(
                update={
                    "pending_action": err_action,
                    "last_observation": observation,
                    "status": "active",
                    "last_error": observation,
                }
            )
            saved = self.store.save(updated)
            self.journal.record_failure(
                saved.session_id, observation,
                {"error": str(exc), "failure_category": "patch_parse_failed"},
            )
            RuntimeLogger(self.project_root, self.config).error(
                "agent.loop", observation, exc=exc,
                failure_category=FailureCategory.PATCH_PARSE_FAILED.value,
            )
            self._classify_and_record(
                step_index=saved.current_step,
                pending_action=err_action,
                observation=observation,
                stopped_for_approval=False,
                failure_category="patch_parse_failed",
                session_id=saved.session_id,
            )
            return AgentStepResult(state=saved, observation=observation, stopped_for_approval=False)

        patch_files = [block.file_path.as_posix() for block in edit_result.proposal.blocks]

        # v6.8.0: classify tier and auto-apply when safe.
        from safecode.agent.approval_tier import ApprovalTier, classify_proposal
        tier = classify_proposal(edit_result.proposal, self.config)

        # v6.26: full_auto also auto-applies CONFIRM tier (not just AUTO).
        # GATE tier always stops for approval regardless of mode.
        auto_apply_condition = (
            (tier == ApprovalTier.AUTO and (self.auto_edit or self.full_auto))
            or (tier == ApprovalTier.CONFIRM and self.full_auto)
        )
        if auto_apply_condition:
            try:
                orch = AgentOrchestrator(self.project_root, llm_client=self.llm_client)
                apply_result = orch.apply(edit_result.proposal)
                tier_label = tier.value
                observation = (
                    f"Auto-applied patch (tier={tier_label}, full_auto={self.full_auto}): "
                    f"{', '.join(patch_files)}. "
                    f"Checkpoint {apply_result.checkpoint.checkpoint_id} created. "
                    "Run 'sac rollback --last' to undo."
                )
                auto_action: dict[str, object] = {
                    "type": "patch",
                    "route": routed.route,
                    "requires_approval": False,
                    "reason": "auto_applied",
                    "patch_id": edit_result.proposal.id,
                    "files": patch_files,
                    "tier": tier.value,
                }
                updated = state.model_copy(
                    update={
                        "current_step": state.current_step + 1,
                        "pending_action": auto_action,
                        "last_observation": observation,
                        "status": "active",
                        "last_error": None,
                    }
                )
                saved = self.store.save(updated)
                self.journal.record_patch_proposal(
                    saved.session_id, saved.current_step, observation,
                    {"patch_id": edit_result.proposal.id, "files": patch_files, "tier": tier.value},
                )
                self._classify_and_record(
                    step_index=saved.current_step,
                    pending_action=auto_action,
                    observation=observation,
                    stopped_for_approval=False,
                    session_id=saved.session_id,
                )
                return AgentStepResult(state=saved, observation=observation, stopped_for_approval=False)
            except Exception as exc:
                # Auto-apply failed; fall through to normal confirm flow.
                RuntimeLogger(self.project_root, self.config).error(
                    "agent.loop", f"Auto-apply failed, falling back to confirm: {exc}", exc=exc
                )
                tier = ApprovalTier.CONFIRM

        # CONFIRM or GATE — stop for user approval (gate carries extra warning).
        gate_note = " [GATE: high-sensitivity change]" if tier == ApprovalTier.GATE else ""
        approved_patch_action = PatchPendingAction(
            route=routed.route,
            requires_approval=True,
            reason=f"patch_proposal_awaiting_approval{gate_note}",
            patch_id=edit_result.proposal.id,
            pending_patch_path=str(edit_result.pending_patch_path),
            files=tuple(patch_files),
        )
        pending_action = approved_patch_action.to_dict()
        pending_action["tier"] = tier.value
        observation = (
            f"Patch proposal created: {edit_result.pending_patch_path.name} "
            f"(patch_id={edit_result.proposal.id}, tier={tier.value}){gate_note}. "
            "Review with 'sac apply' — target files are not modified until you approve."
        )
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "waiting_for_user",
                "last_error": None,
            }
        )
        saved = self.store.save(updated)
        self.journal.record_patch_proposal(
            saved.session_id, saved.current_step, observation,
            {
                "patch_id": edit_result.proposal.id,
                "pending_patch_path": str(edit_result.pending_patch_path),
                "files": patch_files,
                "tier": tier.value,
                "scope_status": (
                    edit_result.scope_result.status
                    if edit_result.scope_result is not None
                    else "no_prediction"
                ),
            },
        )
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=True,
            session_id=saved.session_id,
        )
        return AgentStepResult(state=saved, observation=observation, stopped_for_approval=True)

    # ------------------------------------------------------------------
    # MCP approved-write step
    # ------------------------------------------------------------------

    def _find_approved_write_proposal(
        self: "AgentLoop", tool_name: str
    ) -> MCPWriteProposal | None:
        """Return an approved write proposal matching tool_name, or None."""
        if "." not in tool_name:
            return None
        server, tool = tool_name.split(".", 1)
        if not server or not tool:
            return None
        proposal_store = MCPWriteProposalStore(self.project_root)
        proposal = proposal_store.load_pending()
        if proposal is None:
            return None
        if proposal.status != "approved":
            return None
        if proposal.server != server or proposal.tool != tool:
            return None
        return proposal

    def _execute_mcp_approved_write_step(
        self: "AgentLoop",
        plan_item: str,
        state: AgentSessionState,
        routed: RoutedToolIntent,
        proposal_id: str,
    ) -> AgentStepResult:
        """Execute an explicitly approved MCP write tool call and record the observation."""
        intent = routed.intent
        tool_name = intent.tool_name or ""
        input_json = intent.input_json or {}

        mcp_result = MCPApprovedWriteExecutor(self.project_root).execute(
            tool_name, input_json, proposal_id=proposal_id
        )

        step_label = f"Step {state.current_step + 1}: {plan_item}"
        observation = f"{step_label} → MCP write [{tool_name}]: {mcp_result.observation}"
        pending_action: dict[str, object] = {
            "type": "mcp",
            "route": "mcp.execute_approved_write",
            "tool_name": tool_name,
            "executable_now": "true",
            "reason": "approved_write_executed",
            "mcp_success": str(mcp_result.success).lower(),
            "mcp_blocked": str(mcp_result.blocked).lower(),
            "mcp_exit_code": str(mcp_result.exit_code),
        }
        updated = state.model_copy(
            update={
                "current_step": state.current_step + 1,
                "pending_action": pending_action,
                "last_observation": observation,
                "status": "active",
                "last_error": None if mcp_result.success else mcp_result.observation,
            }
        )
        saved = self.store.save(updated)
        call_summary: dict[str, object] = {
            "tool_name": tool_name,
            "server": mcp_result.server,
            "tool": mcp_result.tool,
            "success": mcp_result.success,
            "blocked": mcp_result.blocked,
            "exit_code": mcp_result.exit_code,
            "approved_write": True,
            **mcp_result.metadata,
        }
        self.journal.record_mcp_call(
            saved.session_id, saved.current_step, observation, call_summary,
        )
        self._classify_and_record(
            step_index=saved.current_step,
            pending_action=pending_action,
            observation=observation,
            stopped_for_approval=False,
            session_id=saved.session_id,
        )
        return AgentStepResult(state=saved, observation=observation)
