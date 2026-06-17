"""Tests for structured step journal."""

from __future__ import annotations

from pathlib import Path

from safecode.state.step_journal import StepJournalEntry, StepJournalStore


def test_step_journal_appends_and_reads(tmp_path: Path) -> None:
    store = StepJournalStore(tmp_path)
    store.append(
        StepJournalEntry(
            step_id="s1:1",
            session_id="s1",
            step_index=1,
            action_type="edit",
            tool_name="patch.propose",
            files_changed=["src/foo.py"],
            outcome="waiting_for_user",
            summary="change src/foo.py",
        )
    )

    entries = store.read("s1")

    assert len(entries) == 1
    assert entries[0].files_changed == ["src/foo.py"]
    assert (tmp_path / ".sac" / "tasks" / "s1" / "step_journal.jsonl").exists()


def test_step_journal_caps_entries(tmp_path: Path) -> None:
    store = StepJournalStore(tmp_path, cap=2)
    for idx in range(4):
        store.append(
            StepJournalEntry(
                step_id=f"s1:{idx}",
                session_id="s1",
                step_index=idx,
                action_type="ask",
            )
        )

    entries = store.read("s1")

    assert [entry.step_index for entry in entries] == [2, 3]


def test_agent_loop_records_step_journal(tmp_path: Path) -> None:
    from safecode.agent.loop import AgentLoop

    loop = AgentLoop(tmp_path, no_clarify=True)
    state = loop.store.start("goal", plan=["step"])
    loop._classify_and_record(
        step_index=1,
        pending_action={
            "type": "patch",
            "route": "patch.propose",
            "files": ["src/foo.py"],
        },
        observation="Patch proposal created",
        stopped_for_approval=True,
        session_id=state.session_id,
    )

    entries = StepJournalStore(tmp_path).read(state.session_id)

    assert entries
    assert entries[-1].action_type == "edit"
    assert entries[-1].files_changed == ["src/foo.py"]
