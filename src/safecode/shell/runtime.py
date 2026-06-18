"""Unified Claude-style conversational shell runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from safecode.agent.conversation import ConversationBuffer
from safecode.agent.loop import AgentLoop
from safecode.agent.session import AgentSessionStore
from safecode.cli_shared import console
from safecode.config import SafeCodeConfig
from safecode.shell.approvals import adopt_legacy_pending_patch
from safecode.shell.approvals import prompt_for_approval
from safecode.shell.commands import dispatch_local_command
from safecode.shell.rendering import (
    phase_for_step,
    resume_hint_text,
    session_list_text,
    turn_summary_text,
    welcome_text,
)
from safecode.shell.session import ShellSessionManager


def _make_loop(
    project_root: Path,
    *,
    session_id: str,
    plan_mode: bool,
    auto_edit: bool,
    full_auto: bool,
    command_delay_ms: int,
) -> AgentLoop:
    return AgentLoop(
        project_root,
        auto_edit=False if plan_mode else auto_edit,
        full_auto=False if plan_mode else full_auto,
        command_delay_ms=command_delay_ms,
        no_clarify=True,
        plan_mode=plan_mode,
        session_id=session_id,
    )


def run_agentic_shell(
    project_root: Path,
    *,
    session_id: str | None = None,
    is_tty: bool = True,
    json_output: bool = False,
    auto_edit: bool = False,
    full_auto: bool = False,
    command_delay_ms: int = 500,
    mode: str = "build",
    new_session: bool = False,
) -> int:
    """Run the single supported conversational shell experience."""
    from safecode.cli_shared_json import CLIJSONResponse, render_json
    from safecode import cli_shell as legacy

    config = SafeCodeConfig.load(project_root)
    sac_dir = project_root / config.sac_dir
    manager = ShellSessionManager(sac_dir)
    manifest = manager.create(mode=mode) if new_session else manager.open(session_id, mode=mode)
    try:
        from safecode.task.store import TaskStore
        manifest = manager.save(manifest.model_copy(update={"task_id": TaskStore(project_root).current_id()}))
    except Exception:
        pass
    conversation = ConversationBuffer.load(manifest.session_id, sac_dir)
    plan_mode = mode == "plan"
    loop: AgentLoop | None = None

    def emit_local(name: str, response: str, **data: Any) -> bool:
        """Render one local command consistently; JSON mode is one-shot."""
        if json_output:
            print(render_json(CLIJSONResponse(
                command=f"shell {name}",
                status="success",
                data={"response": response, "session_id": manifest.session_id, **data},
            )))
            return True
        console.print(response, markup=False)
        return False

    if is_tty and not json_output:
        resumed = conversation.turn_count() > 0
        provider = getattr(config, "provider", "")
        model_name = getattr(config, "model", "")
        console.print(f"[bold]{welcome_text(manifest, resumed=resumed, provider=provider, model=model_name)}[/bold]")
        if resumed:
            console.print(f"[dim]{resume_hint_text(manifest)}[/dim]")
        console.print("[dim]/status  /sessions  /new  /memory why  /mode plan|build  /exit[/dim]")
        legacy._setup_readline()

    turn = conversation.turn_count()
    while True:
        line = legacy._read_line(
            is_tty=is_tty,
            turn=turn,
            prompt_override=legacy._shell_prompt(turn + 1),
        )
        if line is None:
            manifest = manager.save(manifest.model_copy(update={"status": "closed"}))
            break
        goal = line.strip()
        if not goal:
            continue
        agent_goal: str | None = goal
        resume_agent = False

        if goal.startswith("/"):
            command = goal.lower()
            if command in {"/exit", "/quit"}:
                manager.save(manifest.model_copy(update={"status": "closed"}))
                if not json_output:
                    console.print("Exiting shell.")
                break
            if command in {"/clear", "/new"}:
                manifest = manager.create(mode="plan" if plan_mode else "build")
                conversation = ConversationBuffer.load(manifest.session_id, sac_dir)
                loop = None
                if emit_local(command[1:], "Started a new conversation."):
                    break
                continue
            if command == "/sessions":
                if emit_local("sessions", session_list_text(manager.list(limit=10), current_id=manifest.session_id)):
                    break
                continue
            if command.startswith("/resume"):
                parts = goal.split(None, 1)
                selected = parts[1].strip() if len(parts) > 1 else manager.latest_id()
                resumed = manager.load(selected)
                if resumed is None:
                    if emit_local("resume", f"Session not found: {selected or '(none)'}", found=False):
                        break
                    continue
                manifest = manager.save(resumed.model_copy(update={"status": "active", "interrupted": False}))
                conversation = ConversationBuffer.load(manifest.session_id, sac_dir)
                plan_mode = manifest.mode == "plan"
                loop = None
                turn = conversation.turn_count()
                if emit_local("resume", resume_hint_text(manifest), found=True):
                    break
                continue
            if command.startswith("/rename"):
                parts = goal.split(None, 1)
                if len(parts) == 1:
                    if emit_local("rename", "Usage: /rename <title>"):
                        break
                    continue
                manifest = manager.rename(manifest.session_id, parts[1])
                if emit_local("rename", f"Renamed session: {manifest.title}", title=manifest.title):
                    break
                continue
            if command in {"/files", "/tests", "/cost", "/diff"}:
                if command == "/files":
                    text = "\n".join(manifest.files_changed) or "No files changed in this session."
                elif command == "/tests":
                    text = "\n".join(manifest.tests) or "No tests recorded in this session."
                elif command == "/cost":
                    text = (
                        f"Input {manifest.cost_input_tokens}, output {manifest.cost_output_tokens}, "
                        f"cache read {manifest.cost_cache_read_tokens} tokens."
                    )
                else:
                    from safecode.shell.approvals import preview_pending_patch
                    text = preview_pending_patch(project_root, session_id=manifest.session_id) or "No pending diff."
                if emit_local(command[1:], text):
                    break
                continue
            if command == "/status":
                data = legacy._build_shell_status_data(project_root)
                agent_state = AgentSessionStore(
                    project_root,
                    session_id=manifest.session_id,
                ).load()
                if agent_state is not None:
                    data["agent_session"] = {
                        "session_id": agent_state.session_id,
                        "status": agent_state.status,
                        "current_step": agent_state.current_step,
                        "plan_items": len(agent_state.plan),
                        "goal": agent_state.goal,
                        "last_observation": agent_state.last_observation,
                        "pending_action": agent_state.pending_action,
                    }
                if emit_local("status", legacy._render_shell_status(data), status_data=data):
                    break
                continue
            if command == "/timeline":
                goal = f"/timeline {manifest.session_id}"
            if command in {"/approval", "/explain approval"}:
                from safecode.shell.approvals import explain_pending, preview_pending_patch

                state = AgentSessionStore(project_root, session_id=manifest.session_id).load()
                if state is None or not state.pending_action:
                    text = "No pending approval in this conversation."
                else:
                    diff = preview_pending_patch(project_root, session_id=manifest.session_id)
                    text = explain_pending(state.pending_action)
                    if diff:
                        text = f"{text}\n\nPending diff:\n{diff}"
                if emit_local("approval", text):
                    break
                continue
            if command == "/continue":
                migrated_patch = adopt_legacy_pending_patch(project_root, session_id=manifest.session_id)
                scoped_store = AgentSessionStore(project_root, session_id=manifest.session_id)
                state = scoped_store.load()
                if state is None:
                    legacy_state = AgentSessionStore(project_root).load()
                    if legacy_state is not None:
                        state = scoped_store.save(legacy_state.model_copy(update={
                            "session_id": manifest.session_id,
                        }))
                if state is None:
                    if emit_local("continue", "No active agent session.\nNext: Type a request first."):
                        break
                    continue
                if migrated_patch and not json_output:
                    console.print("[dim]Migrated legacy pending patch into this conversation.[/dim]")
                if state.pending_action and state.pending_action.get("requires_approval"):
                    if not is_tty:
                        from safecode.shell.approvals import explain_pending, preview_pending_patch

                        preview = preview_pending_patch(project_root, session_id=manifest.session_id)
                        text = explain_pending(state.pending_action)
                        if preview:
                            text = f"{text}\n\nPending patch is ready:\n{preview}"
                        text = f"{text}\nNext: run sac interactively and use /continue to approve, reject, or explain."
                        manifest = manager.save(manifest.model_copy(update={"status": "waiting_for_approval"}))
                        if emit_local("continue", text, resolved=False):
                            break
                        continue
                    decision = prompt_for_approval(
                        project_root,
                        state.pending_action,
                        console,
                        session_id=manifest.session_id,
                    )
                    resolved = not decision.startswith(("Approval deferred", "This action cannot"))
                    manifest = manager.save(manifest.model_copy(update={
                        "status": "active" if resolved else "waiting_for_approval",
                    }))
                    if emit_local("continue", decision, resolved=resolved):
                        break
                    continue
                if state.status == "completed":
                    if emit_local("continue", "This conversation task is complete. Type a new request to continue."):
                        break
                    continue
                agent_goal = None
                resume_agent = True
            if command == "/compact":
                before = len(conversation.to_messages())
                conversation.compact_now()
                console.print(f"[dim]Conversation compacted: {before} -> {len(conversation.to_messages())} messages.[/dim]")
                continue
            command_name = command.split(None, 1)[0]
            if command_name == "/mode":
                parts = goal.split(None, 1)
                if len(parts) == 1:
                    current_mode = "plan" if plan_mode else "build"
                    if json_output:
                        print(render_json(CLIJSONResponse(
                            command="shell /mode",
                            status="success",
                            data={"message": f"Current mode: {current_mode}", "mode": current_mode},
                        )))
                        break
                    console.print(f"Current mode: {current_mode}")
                    continue
                requested = parts[1].strip().lower()
                if requested not in {"plan", "build"}:
                    console.print("Usage: /mode plan|build")
                    continue
                plan_mode = requested == "plan"
                manifest = manager.save(manifest.model_copy(update={"mode": requested}))
                loop = None
                console.print(f"Switched to {requested} mode.")
                continue

            if not resume_agent:
                def legacy_dispatch(cmd: str, root: Path, task_id: str | None):
                    return legacy._handle_slash_command(cmd, root, task_id, is_tty=is_tty)

                response, should_exit = dispatch_local_command(
                    goal,
                    project_root=project_root,
                    conversation=conversation,
                    legacy_dispatch=legacy_dispatch,
                )
                if json_output:
                    print(render_json(CLIJSONResponse(command="shell slash", status="success", data={"intent": goal.split(None, 1)[0][1:], "response": response})))
                    break
                console.print(response, markup=False)
                if should_exit:
                    break
                continue

        conversation.append_user(goal)
        if manifest.turns == 0 and manifest.title == "New conversation":
            manifest = manager.save(manifest.model_copy(update={"title": manager.title_from_goal(goal)}))
        if loop is None:
            try:
                loop = _make_loop(
                    project_root,
                    session_id=manifest.session_id,
                    plan_mode=plan_mode,
                    auto_edit=auto_edit,
                    full_auto=full_auto,
                    command_delay_ms=command_delay_ms,
                )
            except (PermissionError, RuntimeError, ValueError) as exc:
                message = str(exc)
                conversation.append_assistant(f"Error: {message}")
                if json_output:
                    print(render_json(CLIJSONResponse(command="shell", status="error", error=message)))
                    return 1
                console.print(f"[red]{message}[/red]")
                continue
        phases: list[str] = []
        active_status: Any = None

        def on_step(step: Any) -> None:
            phase = phase_for_step(step)
            if not phases or phases[-1] != phase:
                phases.append(phase)
                if is_tty and not json_output:
                    if active_status is not None:
                        active_status.update(f"[bold blue]{phase}[/bold blue]")
                    console.print(f"[dim]{phase}[/dim]")

        try:
            if is_tty and not json_output:
                from rich.status import Status
                with Status("[bold blue]Thinking[/bold blue]", spinner="dots") as status:
                    active_status = status
                    result = loop.run(agent_goal, max_steps=1 if resume_agent else 8, on_step=on_step, conversation=conversation)
            else:
                result = loop.run(agent_goal, max_steps=1 if resume_agent else 8, on_step=on_step, conversation=conversation)
        except KeyboardInterrupt:
            store = AgentSessionStore(project_root, session_id=manifest.session_id)
            state = store.load()
            if state is not None:
                store.save(state.model_copy(update={
                    "status": "interrupted",
                    "last_error": "Interrupted by user.",
                    "last_observation": "Current step interrupted by user; session preserved.",
                }))
            manifest = manager.save(manifest.model_copy(update={"interrupted": True, "status": "interrupted"}))
            conversation.append_assistant("Current step interrupted by user; session preserved.")
            if is_tty:
                console.print("\n[yellow]Interrupted. Session preserved; enter another request or /exit.[/yellow]")
                continue
            return 130
        except (FileNotFoundError, ValueError) as exc:
            conversation.append_assistant(f"Error: {exc}")
            if json_output:
                print(render_json(CLIJSONResponse(command="shell", status="error", error=str(exc))))
                return 1
            console.print(f"[red]{exc}[/red]")
            continue

        observations = [step.observation for step in result.steps if step.observation]
        reply = observations[-1] if observations else f"Done ({result.stopped_reason})"
        conversation.append_assistant(reply)
        turn = conversation.turn_count()
        files: list[str] = []
        tests: list[str] = []
        for step in result.steps:
            action = step.state.pending_action or {}
            raw_files = action.get("files")
            if isinstance(raw_files, list):
                files.extend(str(path) for path in raw_files)
            if "test" in step.observation.lower() or "pytest" in step.observation.lower():
                tests.append(step.observation[:120].replace("\n", " "))
        files = list(dict.fromkeys(manifest.files_changed + files))
        tests = list(dict.fromkeys(manifest.tests + tests))[-10:]
        session_cost = loop.session_cost() if hasattr(loop, "session_cost") else None
        manifest = manager.save(manifest.model_copy(update={
            "agent_session_id": result.state.session_id,
            "turns": turn,
            "status": "waiting_for_approval" if result.stopped_reason == "approval_required" else "active",
            "interrupted": False,
            "last_response": reply[:4000],
            "files_changed": files,
            "tests": tests,
            "cost_input_tokens": session_cost.prompt_tokens if session_cost else manifest.cost_input_tokens,
            "cost_output_tokens": session_cost.completion_tokens if session_cost else manifest.cost_output_tokens,
            "cost_cache_read_tokens": session_cost.cache_read_tokens if session_cost else manifest.cost_cache_read_tokens,
        }))

        if json_output:
            data: dict[str, Any] = {
                "session_id": manifest.session_id,
                "stopped_reason": result.stopped_reason,
                "steps_count": len(result.steps),
                "turn": turn,
                "phases": phases,
                "mode": manifest.mode,
                "response": reply,
            }
            if session_cost and (session_cost.prompt_tokens or session_cost.completion_tokens):
                data["cost"] = {
                    "input_tokens": session_cost.prompt_tokens,
                    "output_tokens": session_cost.completion_tokens,
                    "cache_read_tokens": session_cost.cache_read_tokens,
                }
            print(render_json(CLIJSONResponse(command="shell", status=result.stopped_reason, data=data)))
            break

        if result.stopped_reason == "approval_required":
            decision = prompt_for_approval(
                project_root,
                result.state.pending_action or {},
                console,
                session_id=manifest.session_id,
            )
            console.print(decision)
            resolved = not decision.startswith(("Approval deferred", "This action cannot"))
            manifest = manager.save(manifest.model_copy(update={
                "status": "active" if resolved else "waiting_for_approval",
            }))
        elif observations:
            if resume_agent:
                console.print("Continued one safe agent step.")
            cost_text = ""
            if session_cost and (session_cost.prompt_tokens or session_cost.completion_tokens):
                cost_text = f"{session_cost.prompt_tokens} in / {session_cost.completion_tokens} out"
            console.print(turn_summary_text(
                response=reply,
                files=files,
                tests=tests,
                stopped_reason=result.stopped_reason,
                cost=cost_text,
            ), markup=False)

    return 0
