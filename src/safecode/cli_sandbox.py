"""Sandbox CLI — thin Typer registry (v2.8.6 module split).

Command implementations live in focused submodules:
- cli_sandbox_status.py   — status, plan
- cli_sandbox_proposal.py — propose, pending, discard, execute, approve, approvals, revoke, preflight
- cli_sandbox_executions.py — executions sub-app, last-execution, execution
"""

import typer

from safecode.cli_sandbox_executions import (
    executions_app,
    sandbox_execution_show,
    sandbox_last_execution,
)
from safecode.cli_sandbox_proposal import (
    sandbox_approve,
    sandbox_approvals,
    sandbox_discard,
    sandbox_execute,
    sandbox_pending,
    sandbox_preflight,
    sandbox_propose,
    sandbox_revoke,
)
from safecode.cli_sandbox_status import sandbox_executor_preflight, sandbox_plan, sandbox_status

sandbox_app = typer.Typer(help="Check OS sandbox capabilities and recommendations.")

sandbox_app.command("status")(sandbox_status)
sandbox_app.command("plan")(sandbox_plan)
sandbox_app.command("propose")(sandbox_propose)
sandbox_app.command("pending")(sandbox_pending)
sandbox_app.command("discard")(sandbox_discard)
sandbox_app.command("execute")(sandbox_execute)
sandbox_app.command("approve")(sandbox_approve)
sandbox_app.command("approvals")(sandbox_approvals)
sandbox_app.command("revoke")(sandbox_revoke)
sandbox_app.command("preflight")(sandbox_preflight)
sandbox_app.command("executor-preflight")(sandbox_executor_preflight)
sandbox_app.add_typer(executions_app, name="executions")
sandbox_app.command("last-execution")(sandbox_last_execution)
sandbox_app.command("execution")(sandbox_execution_show)
