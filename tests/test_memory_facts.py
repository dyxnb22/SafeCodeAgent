"""Tests for project convention facts store (v6.2.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.memory.facts import (
    ProjectFact,
    ProjectFactStore,
    _classify_command,
    _detect_guarded_dirs,
    _looks_sensitive,
)


# ---------------------------------------------------------------------------
# ProjectFact dataclass
# ---------------------------------------------------------------------------


class TestProjectFactDataclass:
    def test_round_trip(self) -> None:
        f = ProjectFact(
            fact_id="abc123",
            key="test_command",
            value="pytest -q",
            source="auto",
            status="pending",
            created_at="2026-06-16T10:00:00+00:00",
        )
        d = f.to_dict()
        rebuilt = ProjectFact.from_dict(d)
        assert rebuilt == f

    def test_from_dict_missing_fields(self) -> None:
        f = ProjectFact.from_dict({})
        assert f.fact_id == ""
        assert f.status == "pending"
        assert f.approved_at is None

    def test_summary_line(self) -> None:
        f = ProjectFact(fact_id="abc12345", key="test_command", value="pytest -q",
                        source="auto", status="pending", created_at="")
        line = f.summary_line()
        assert "abc12345" in line
        assert "test_command" in line
        assert "pytest -q" in line


# ---------------------------------------------------------------------------
# ProjectFactStore
# ---------------------------------------------------------------------------


class TestProjectFactStore:
    def test_propose_creates_pending_fact(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        fact = store.propose("test_command", "pytest -q")
        assert fact is not None
        assert fact.status == "pending"
        assert fact.key == "test_command"
        assert fact.value == "pytest -q"
        assert fact.source == "auto"

    def test_propose_duplicate_returns_none(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        store.propose("test_command", "pytest -q")
        duplicate = store.propose("test_command", "pytest -q")
        assert duplicate is None

    def test_propose_sensitive_value_returns_none(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        assert store.propose("convention", "api_key=supersecret") is None

    def test_propose_sensitive_key_returns_none(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        assert store.propose("token", "some_value") is None

    def test_propose_value_truncated(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        long_val = "x" * 400
        fact = store.propose("convention", long_val)
        assert fact is not None
        assert len(fact.value) <= 300

    def test_list_facts_empty(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        assert store.list_facts() == []

    def test_list_facts_all(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        store.propose("test_command", "pytest")
        store.propose("lint_command", "ruff check .")
        facts = store.list_facts()
        assert len(facts) == 2

    def test_list_facts_filter_pending(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        f = store.propose("test_command", "pytest")
        assert f is not None
        store.approve(f.fact_id)
        store.propose("lint_command", "ruff")
        pending = store.list_facts(status="pending")
        assert len(pending) == 1
        assert pending[0].key == "lint_command"

    def test_list_facts_filter_approved(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        f = store.propose("test_command", "pytest")
        assert f is not None
        store.approve(f.fact_id)
        approved = store.list_facts(status="approved")
        assert len(approved) == 1
        assert approved[0].status == "approved"
        assert approved[0].approved_at is not None

    def test_approve_pending_fact(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        f = store.propose("convention", "use snake_case")
        assert f is not None
        approved = store.approve(f.fact_id)
        assert approved.status == "approved"
        assert approved.approved_at is not None

    def test_approve_prefix_match(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        f = store.propose("convention", "keep tests green")
        assert f is not None
        approved = store.approve(f.fact_id[:6])  # prefix
        assert approved.status == "approved"

    def test_approve_nonexistent_raises(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        with pytest.raises(ValueError, match="not found"):
            store.approve("doesnotexist")

    def test_approve_already_approved_raises(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        f = store.propose("convention", "x")
        assert f is not None
        store.approve(f.fact_id)
        with pytest.raises(ValueError, match="not pending"):
            store.approve(f.fact_id)

    def test_reject_pending_fact(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        f = store.propose("convention", "bad idea")
        assert f is not None
        rejected = store.reject(f.fact_id)
        assert rejected.status == "rejected"

    def test_reject_nonexistent_raises(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        with pytest.raises(ValueError, match="not found"):
            store.reject("doesnotexist")

    def test_get_by_full_id(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        f = store.propose("test_command", "go test ./...")
        assert f is not None
        retrieved = store.get(f.fact_id)
        assert retrieved is not None
        assert retrieved.fact_id == f.fact_id

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        assert store.get("nope") is None

    def test_approved_context_empty_when_no_approved(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        store.propose("test_command", "pytest")
        assert store.approved_context() == ""

    def test_approved_context_contains_approved_facts(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        f1 = store.propose("test_command", "pytest -q")
        f2 = store.propose("lint_command", "ruff check .")
        assert f1 and f2
        store.approve(f1.fact_id)
        store.approve(f2.fact_id)
        ctx = store.approved_context()
        assert "pytest -q" in ctx
        assert "ruff check ." in ctx
        assert "Approved Project Conventions" in ctx

    def test_approved_context_respects_max_chars(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        for i in range(20):
            f = store.propose("convention", f"convention rule number {i:03d} with extra text padding here")
            if f:
                store.approve(f.fact_id)
        ctx = store.approved_context(max_chars=200)
        assert len(ctx) <= 300

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        store1 = ProjectFactStore(tmp_path / ".sac")
        f = store1.propose("test_command", "pytest")
        assert f is not None
        store2 = ProjectFactStore(tmp_path / ".sac")
        facts = store2.list_facts()
        assert len(facts) == 1
        assert facts[0].fact_id == f.fact_id

    def test_corrupt_file_returns_empty(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        path = sac_dir / "memory" / "facts.json"
        path.parent.mkdir(parents=True)
        path.write_text("NOT JSON", encoding="utf-8")
        store = ProjectFactStore(sac_dir)
        assert store.list_facts() == []

    def test_parent_dir_created(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        assert not (tmp_path / ".sac" / "memory").exists()
        store.propose("convention", "something")
        assert (tmp_path / ".sac" / "memory" / "facts.json").exists()


# ---------------------------------------------------------------------------
# Auto-detection helpers
# ---------------------------------------------------------------------------


class TestClassifyCommand:
    def test_pytest(self) -> None:
        assert _classify_command("pytest -q") == "test_command"
    def test_npm_test(self) -> None:
        assert _classify_command("npm test") == "test_command"
    def test_go_test(self) -> None:
        assert _classify_command("go test ./...") == "test_command"
    def test_ruff(self) -> None:
        assert _classify_command("ruff check .") == "lint_command"
    def test_eslint(self) -> None:
        assert _classify_command("eslint src/") == "lint_command"
    def test_mypy(self) -> None:
        assert _classify_command("mypy src/") == "typecheck_command"
    def test_tsc(self) -> None:
        assert _classify_command("tsc --noEmit") == "typecheck_command"
    def test_npm_build(self) -> None:
        assert _classify_command("npm run build") == "build_command"
    def test_unknown_returns_none(self) -> None:
        assert _classify_command("git status") is None


class TestDetectGuardedDirs:
    def test_generated_dir(self) -> None:
        files = ["src/generated/models.py", "src/auth.py"]
        assert "generated" in _detect_guarded_dirs(files)

    def test_pycache_ignored(self) -> None:
        files = ["src/__pycache__/foo.cpython.pyc"]
        assert "__pycache__" in _detect_guarded_dirs(files)

    def test_no_special_dirs(self) -> None:
        files = ["src/auth.py", "tests/test_auth.py"]
        assert _detect_guarded_dirs(files) == []


class TestLooksSensitive:
    def test_token_detected(self) -> None:
        assert _looks_sensitive("token=abc")
    def test_secret_detected(self) -> None:
        assert _looks_sensitive("my secret value")
    def test_normal_text_not_sensitive(self) -> None:
        assert not _looks_sensitive("pytest -q")


# ---------------------------------------------------------------------------
# propose_from_session_summary
# ---------------------------------------------------------------------------


class TestProposeFromSessionSummary:
    def test_proposes_test_command(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        proposed = store.propose_from_session_summary(
            commands_run=["pytest -q", "git status"],
            touched_files=["src/auth.py"],
        )
        keys = [f.key for f in proposed]
        assert "test_command" in keys

    def test_skips_duplicate_on_second_session(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        store.propose_from_session_summary(commands_run=["pytest -q"], touched_files=[])
        proposed2 = store.propose_from_session_summary(commands_run=["pytest -q"], touched_files=[])
        assert proposed2 == []  # duplicate skipped

    def test_proposes_guarded_dir(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        proposed = store.propose_from_session_summary(
            commands_run=[],
            touched_files=["src/generated/models.py"],
        )
        keys = [f.key for f in proposed]
        assert "guarded_dir" in keys

    def test_no_proposals_for_empty_session(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        assert store.propose_from_session_summary(commands_run=[], touched_files=[]) == []


# ---------------------------------------------------------------------------
# AgentLoop integration: facts proposed after run()
# ---------------------------------------------------------------------------


class TestAgentLoopFactsIntegration:
    def test_facts_proposed_after_run(self, tmp_path: Path) -> None:
        from safecode.agent.loop import AgentLoop
        from safecode.llm.mock import MockLLMClient

        loop = AgentLoop(tmp_path, llm_client=MockLLMClient())
        loop.run(goal="fix the calculator bug", max_steps=3)

        store = ProjectFactStore(tmp_path / ".sac")
        # facts file should exist (even if no commands auto-detected, file may be created)
        # We just verify no crash occurred
        facts = store.list_facts()
        assert isinstance(facts, list)

    def test_approved_facts_prepended_to_goal(self, tmp_path: Path) -> None:
        from safecode.agent.loop import AgentLoop
        from safecode.llm.mock import MockLLMClient

        # Pre-approve a fact
        store = ProjectFactStore(tmp_path / ".sac")
        f = store.propose("test_command", "pytest -q", source="user")
        assert f is not None
        store.approve(f.fact_id)

        loop = AgentLoop(tmp_path, llm_client=MockLLMClient())
        prefixed = loop._prepend_session_memory("my goal")
        assert prefixed is not None
        assert "pytest -q" in prefixed
        assert "my goal" in prefixed

    def test_facts_injection_failure_does_not_crash(self, tmp_path: Path) -> None:
        from safecode.agent.loop import AgentLoop
        from safecode.llm.mock import MockLLMClient

        # Corrupt the facts file
        sac_dir = tmp_path / ".sac"
        facts_path = sac_dir / "memory" / "facts.json"
        facts_path.parent.mkdir(parents=True)
        facts_path.write_text("INVALID", encoding="utf-8")

        loop = AgentLoop(tmp_path, llm_client=MockLLMClient())
        result = loop._prepend_session_memory("my goal")
        # Should still return something (facts error is swallowed)
        assert result == "my goal" or result is None or "my goal" in (result or "")
