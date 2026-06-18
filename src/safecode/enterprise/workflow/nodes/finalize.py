"""finalize node stub."""

from __future__ import annotations

from safecode.context.redactor import redact_secrets
from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState, Report
from safecode.enterprise.workflow.types import WorkflowStatus

NODE_NAME = "finalize"


async def run(state: EnterpriseRunState) -> NodePatch:
    markdown = redact_secrets(
        f"# Enterprise Workflow Report\n\nRun `{state.run_id}` completed for "
        f"{state.task_type.value}.\n"
    )
    report = Report(
        report_id=f"report-{state.run_id}",
        kind="pr_review_report",
        markdown=markdown,
    )
    return build_patch(
        state,
        NODE_NAME,
        summary="finalized redacted report",
        state_updates={"report": report, "status": WorkflowStatus.succeeded},
    )
