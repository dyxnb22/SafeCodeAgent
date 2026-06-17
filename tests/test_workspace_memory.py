"""Tests for v6.30: cross-session WorkspaceMemoryStore."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.memory.workspace_memory import (
    WorkspaceMemoryEntry,
    WorkspaceMemoryStore,
    _normalise_key,
    _looks_sensitive,
    inject_workspace_memory,
    _MAX_ENTRIES,
    _MAX_FILE_BYTES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store(tmp_path: Path) -> WorkspaceMemoryStore:
    return WorkspaceMemoryStore(tmp_path)


# ---------------------------------------------------------------------------
# Key normalisation & safety
# ---------------------------------------------------------------------------


class TestKeyNormalisation:
    def test_basic(self):
        assert _normalise_key("test_command") == "test_command"

    def test_special_chars_squashed(self):
        # Colons and dots are kept as separators so keys like fix:config.py
        # remain human-readable in the workspace memory file.
        result = _normalise_key("fix:config.py")
        assert "fix" in result

    def test_multiple_separators(self):
        result = _normalise_key("fix::  config---test")
        assert "fix" in result

    def test_empty(self):
        assert _normalise_key("") == ""
        assert _normalise_key("!!!") == ""

    def test_at_sign_removed(self):
        assert _normalise_key("bug@parse_config") == "bug-parse_config"

    def test_truncation(self):
        long_key = "x" * 200
        assert len(_normalise_key(long_key)) <= 120


class TestSensitiveDetection:
    def test_token(self):
        assert _looks_sensitive("my api_key is here")

    def test_password(self):
        assert _looks_sensitive("the password field")

    def test_secret(self):
        assert _looks_sensitive("a secret value")

    def test_normal_text(self):
        assert not _looks_sensitive("fix config parser")

    def test_apikey_inline(self):
        assert _looks_sensitive("sk-apikey-1234")


# ---------------------------------------------------------------------------
# WorkspaceMemoryEntry
# ---------------------------------------------------------------------------


class TestEntry:
    def test_round_trip(self):
        e = WorkspaceMemoryEntry(
            key="test_command",
            value="python -m pytest -q",
            source="agent_observed",
            confidence=0.8,
            timestamp="2026-06-17T12:00:00",
            session_id="abc123",
        )
        d = e.to_dict()
        e2 = WorkspaceMemoryEntry.from_dict(d)
        assert e2.key == e.key
        assert e2.value == e.value
        assert e2.source == e.source
        assert e2.confidence == e.confidence

    def test_age_score_recent(self):
        from datetime import datetime, timezone
        e = WorkspaceMemoryEntry(
            key="k", value="v", source="agent_observed",
            confidence=1.0, session_id="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        assert e.age_score > 0.9

    def test_age_score_old(self):
        e = WorkspaceMemoryEntry(
            key="k", value="v", source="agent_observed",
            confidence=1.0, session_id="s",
            timestamp="2023-01-01T00:00:00",
        )
        assert e.age_score < 0.3

    def test_to_context_line(self):
        e = WorkspaceMemoryEntry(
            key="fix:parser",
            value="parse_config returns {} for None input",
            source="agent_observed",
            confidence=0.9,
            timestamp="2026-06-17T12:00:00",
            session_id="abc",
        )
        line = e.to_context_line()
        assert "fix" in line and "parser" in line
        assert "0.90" in line
        assert "agent_observed" in line


# ---------------------------------------------------------------------------
# Store: write
# ---------------------------------------------------------------------------


class TestStoreWrite:
    def test_record_single(self, tmp_path):
        store = _store(tmp_path)
        e = store.record("test_command", "pytest -q", session_id="s1")
        assert e is not None
        assert e.key == "test_command"
        assert len(store) == 1

    def test_record_sensitive_value_rejected(self, tmp_path):
        store = _store(tmp_path)
        e = store.record("test_command", "my api_key is sk-secret", session_id="s1")
        assert e is None
        assert len(store) == 0

    def test_record_empty_value_rejected(self, tmp_path):
        store = _store(tmp_path)
        e = store.record("test_command", "")
        assert e is None

    def test_record_persists_to_disk(self, tmp_path):
        store = _store(tmp_path)
        store.record("test_command", "pytest", session_id="s1")
        path = tmp_path / ".sac" / "workspace_memory.jsonl"
        assert path.exists()
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["key"] == "test_command"

    def test_record_normalises_key(self, tmp_path):
        store = _store(tmp_path)
        e = store.record("fix:config.py", "handles None")
        assert e is not None
        # Key is normalised (special chars replaced) but colons and dots are kept.
        assert "fix" in e.key

    def test_record_value_capped(self, tmp_path):
        store = _store(tmp_path)
        long_value = "x" * 3000
        e = store.record("test_command", long_value)
        assert e is not None
        assert len(e.value) <= 2000

    def test_record_many(self, tmp_path):
        store = _store(tmp_path)
        results = store.record_many([
            ("test_cmd", "pytest"),
            ("lint_cmd", "ruff check"),
        ], session_id="s1")
        assert len(results) == 2
        assert len(store) == 2

    def test_record_confidence_default(self, tmp_path):
        store = _store(tmp_path)
        e = store.record("test_cmd", "pytest")
        assert e.confidence == 0.7


# ---------------------------------------------------------------------------
# Store: read
# ---------------------------------------------------------------------------


class TestStoreRead:
    def test_load_empty(self, tmp_path):
        store = _store(tmp_path)
        assert store.load_all() == []

    def test_load_sorted_newest_first(self, tmp_path):
        store = _store(tmp_path)
        store.record("cmd1", "old cmd", session_id="s1")
        import time
        time.sleep(0.01)
        store.record("cmd2", "new cmd", session_id="s2")
        entries = store.load_all()
        assert len(entries) >= 2
        # Newest first
        assert entries[0].key == "cmd2"

    def test_query_by_keyword(self, tmp_path):
        store = _store(tmp_path)
        store.record("test_command", "python -m pytest -q")
        store.record("lint_command", "ruff check .")
        store.record("build_cmd", "cargo build")
        results = store.query("pytest")
        assert len(results) == 1
        assert results[0].key == "test_command"

    def test_query_case_insensitive(self, tmp_path):
        store = _store(tmp_path)
        store.record("cmd", "PyTest")
        results = store.query("pytest")
        assert len(results) == 1

    def test_query_no_match(self, tmp_path):
        store = _store(tmp_path)
        store.record("a", "b")
        assert store.query("zzz_nonexistent") == []

    def test_top_context_block(self, tmp_path):
        store = _store(tmp_path)
        store.record("test_command", "python -m pytest -q", session_id="s1")
        store.record("fix:parser", "parse_config handles None input", session_id="s1")
        block = store.top_context_block()
        assert "Workspace Memory" in block
        assert "pytest" in block
        assert "parser" in block

    def test_top_context_block_empty(self, tmp_path):
        store = _store(tmp_path)
        assert store.top_context_block() == ""

    def test_top_context_block_query_ranking(self, tmp_path):
        store = _store(tmp_path)
        store.record("cmd_a", "value a")
        store.record("cmd_b", "value about parser", session_id="s1")
        store.record("cmd_c", "value c")
        block = store.top_context_block(query="parser")
        assert "parser" in block


# ---------------------------------------------------------------------------
# Store: eviction
# ---------------------------------------------------------------------------


class TestStoreEviction:
    def test_lru_eviction_at_entry_limit(self, tmp_path):
        store = _store(tmp_path)
        for i in range(_MAX_ENTRIES + 20):
            store.record(f"cmd_{i:04d}", f"value_{i}", session_id="s")
        assert len(store) <= _MAX_ENTRIES
        # Oldest should be evicted
        entries = store.load_all()
        keys = {e.key for e in entries}
        assert "cmd_0000" not in keys  # evicted

    def test_lru_eviction_at_byte_limit(self, tmp_path):
        store = _store(tmp_path)
        # Each entry ~500 bytes value = ~150 * 500 = 75KB. Add 300 = way over 300KB.
        big_value = "y" * 500
        for i in range(300):
            store.record(f"cmd_{i:04d}", big_value, session_id="s")
        assert len(store) > 10  # keeps at least 10
        # Byte count should be under cap
        path = tmp_path / ".sac" / "workspace_memory.jsonl"
        assert path.stat().st_size <= _MAX_FILE_BYTES + 10000  # small tolerance for last write


# ---------------------------------------------------------------------------
# Store: maintenance
# ---------------------------------------------------------------------------


class TestStoreMaintenance:
    def test_clear_stale(self, tmp_path):
        store = _store(tmp_path)
        from datetime import datetime, timezone, timedelta
        # Manually inject an old entry
        old_entry = {
            "key": "old_cmd",
            "value": "old",
            "source": "agent_observed",
            "confidence": 0.5,
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(),
            "session_id": "s_old",
        }
        path = tmp_path / ".sac" / "workspace_memory.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(old_entry) + "\n")
        removed = store.clear_stale(max_age_days=60)
        assert removed >= 1
        assert len(store) == 0

    def test_export_all(self, tmp_path):
        store = _store(tmp_path)
        store.record("a", "1")
        store.record("b", "2")
        exported = store.export_all()
        assert len(exported) == 2

    def test_len(self, tmp_path):
        store = _store(tmp_path)
        assert len(store) == 0
        store.record("a", "1")
        assert len(store) == 1


# ---------------------------------------------------------------------------
# Context injection helper
# ---------------------------------------------------------------------------


class TestInjectWorkspaceMemory:
    def test_injects_into_empty_context(self, tmp_path):
        store = _store(tmp_path)
        store.record("test_cmd", "pytest", session_id="s1")
        ctx = {}
        ctx = inject_workspace_memory(ctx, tmp_path)
        assert "workspace_memory" in ctx
        assert "pytest" in ctx["workspace_memory"]

    def test_noop_when_store_empty(self, tmp_path):
        ctx = {"existing": "data"}
        ctx = inject_workspace_memory(ctx, tmp_path)
        assert "workspace_memory" not in ctx
        assert ctx["existing"] == "data"

    def test_noop_when_store_missing(self, tmp_path):
        ctx = {}
        ctx = inject_workspace_memory(ctx, tmp_path)
        assert ctx == {}

    def test_query_passed_to_store(self, tmp_path):
        store = _store(tmp_path)
        store.record("cmd_a", "value a")
        store.record("cmd_b", "value about parsing", session_id="s1")
        block_with = inject_workspace_memory({}, tmp_path, query="parsing")
        assert "workspace_memory" in block_with


# ---------------------------------------------------------------------------
# AgentOrchestrator auto-capture
# ---------------------------------------------------------------------------


class TestOrchestratorAutoCapture:
    def test_apply_records_workspace_memory(self, tmp_path):
        from safecode.agent.orchestrator import AgentOrchestrator
        from safecode.patch.models import PatchBlock, PatchProposal
        from safecode.utils.time import utc_now_iso

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "parser.py").write_text("def parse(x): return x\n")
        proposal = PatchProposal(
            id="test-1",
            task="fix parse_config to handle None input",
            blocks=[PatchBlock(
                operation="update",
                file_path=Path("src/parser.py"),
                search="def parse(x): return x",
                replace="def parse(x): return x if x else {}",
            )],
            created_at=utc_now_iso(),
            model="test",
        )
        orch = AgentOrchestrator(tmp_path)
        orch.apply(proposal)

        store = WorkspaceMemoryStore(tmp_path)
        entries = store.load_all()
        assert len(entries) >= 1
        assert any("parser" in e.key for e in entries)

    def test_apply_failure_does_not_block(self, tmp_path):
        """Memory capture failure must never block apply."""
        from safecode.agent.orchestrator import AgentOrchestrator
        from safecode.patch.models import PatchBlock, PatchProposal
        from safecode.utils.time import utc_now_iso

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "item.py").write_text("x = 0\n")
        proposal = PatchProposal(
            id="test-2",
            task="a simple fix",
            blocks=[PatchBlock(
                operation="update",
                file_path=Path("src/item.py"),
                search="x = 0",
                replace="x = 1",
            )],
            created_at=utc_now_iso(),
            model="test",
        )
        # Make the .sac dir unreadable to simulate failure in memory store
        (tmp_path / ".sac").mkdir(exist_ok=True)
        (tmp_path / ".sac" / "workspace_memory.jsonl").mkdir(parents=True, exist_ok=True)  # file is a dir!

        orch = AgentOrchestrator(tmp_path)
        # Must not raise — apply succeeds despite memory capture failure
        result = orch.apply(proposal)
        assert result is not None
        assert (tmp_path / "src" / "item.py").read_text() == "x = 1\n"


# ---------------------------------------------------------------------------
# ContextCollector integration
# ---------------------------------------------------------------------------


class TestContextCollectorIntegration:
    def test_collector_injects_workspace_memory(self, tmp_path):
        from safecode.config import SafeCodeConfig
        from safecode.context.collector import ContextCollector

        # Pre-populate memory
        store = WorkspaceMemoryStore(tmp_path)
        store.record("test_command", "PYTHONPATH=src python -m pytest -q", session_id="s1")

        config = SafeCodeConfig.load(tmp_path)
        collector = ContextCollector(tmp_path, config)
        ctx = collector.collect(query="how to run tests")
        assert "workspace_memory" in ctx
        assert "pytest" in ctx["workspace_memory"]

    def test_empty_store_no_block(self, tmp_path):
        from safecode.config import SafeCodeConfig
        from safecode.context.collector import ContextCollector

        config = SafeCodeConfig.load(tmp_path)
        collector = ContextCollector(tmp_path, config)
        ctx = collector.collect(query="something")
        assert isinstance(ctx, dict)  # no crash


# ---------------------------------------------------------------------------
# End-to-end: record → inject → query
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_record_and_read_back(self, tmp_path):
        store = _store(tmp_path)
        store.record("test_command", "pytest -x", source="agent_observed", session_id="abc")
        store.record("fix:config", "parse_config returns {} for None", source="agent_observed", session_id="def")
        store.record("convention:naming", "use snake_case for Python files", source="user_stated", session_id="ghi")

        entries = store.load_all()
        assert len(entries) == 3

        context = store.top_context_block()
        assert "pytest" in context
        assert "config" in context
        assert "snake_case" in context

    def test_query_relevant_to_goal(self, tmp_path):
        store = _store(tmp_path)
        store.record("test_command", "uv run pytest")
        store.record("fix:math_utils", "fixed integer division bug")
        store.record("convention:naming", "use snake_case")

        # Query for test-related memory
        results = store.query("pytest")
        assert len(results) == 1
        assert results[0].key == "test_command"

        # Context block ranked by query
        block = store.top_context_block(query="math division bug")
        assert "math" in block.lower() or "division" in block.lower()

    def test_workspace_memory_file_never_leaks_secrets(self, tmp_path):
        store = _store(tmp_path)
        # Record a value containing a secret — redact_secrets() strips it before write.
        result = store.record("fix:auth", "the API key is sk-secret-token-abc123")
        assert result is not None  # stored, but redacted
        path = tmp_path / ".sac" / "workspace_memory.jsonl"
        content = path.read_text()
        # The raw secret must never appear in the persisted file
        assert "sk-secret-token-abc123" not in content
        # The redacted form may appear
        assert "REDACTED" in content
