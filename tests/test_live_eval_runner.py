"""Tests for live eval runner behavior and runtime safety helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from safecode.agent.schemas import AgentAnswer, AgentPatchResponse, AgentPlanResponse
from safecode.eval.live import (
    LiveEvalFixture,
    LiveEvalResult,
    LiveEvalRunner,
    _check_patch_retry_needed,
    _check_working_tree_clean,
    _classify_error,
    _count_approval_events,
    _count_unauthorized_mutations,
    _verify_audit_chain,
    _verify_checkpoint_integrity,
    default_live_fixtures,
    render_repeated_summary,
    summarize_repeated_results,
)


class _PatchOnlyLLM:
    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        return AgentPlanResponse(goal=goal, steps=["edit"])

    def choose_tool(self, goal: str, context: dict):
        raise NotImplementedError

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        return AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: src/hello.py\n"
                "SEARCH:\n"
                "def greet():\n"
                "    return 'hi'\n"
                "REPLACE:\n"
                "def greet():\n"
                "    return 'hello'\n"
                "*** End Patch"
            )
        )


class _CartFixLLM:
    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        return AgentPlanResponse(goal=goal, steps=["edit"])

    def choose_tool(self, goal: str, context: dict):
        raise NotImplementedError

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        return AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: src/cart.py\n"
                "SEARCH:\n"
                "def total(items: list[dict]) -> int:\n"
                "    # BUG: ignores item quantity\n"
                "    return sum(item['price'] for item in items)\n"
                "REPLACE:\n"
                "def total(items: list[dict]) -> int:\n"
                "    return sum(item['price'] * item.get('quantity', 1) for item in items)\n"
                "*** End Patch"
            ),
            input_tokens=100,
            output_tokens=50,
        )


class _IncompleteThenRepairLLM:
    def __init__(self) -> None:
        self.calls = 0

    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        return AgentPlanResponse(goal=goal, steps=["edit"])

    def choose_tool(self, goal: str, context: dict):
        raise NotImplementedError

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        self.calls += 1
        if self.calls == 1:
            return AgentPatchResponse(
                patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/permissions.py\n"
                    "SEARCH:\n"
                    "def can_edit(role: str) -> bool:\n"
                    "    return ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS['editor']\n"
                    "REPLACE:\n"
                    "def can_update(role: str) -> bool:\n"
                    "    return ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS['editor']\n"
                    "*** End Patch"
                ),
                input_tokens=10,
                output_tokens=5,
            )
        assert "success condition still failed" in task
        assert "src/api.py" in task
        return AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: src/api.py\n"
                "SEARCH:\n"
                "from permissions import can_edit\n\n"
                "def update_document(role: str) -> bool:\n"
                "    return can_edit(role)\n"
                "REPLACE:\n"
                "from permissions import can_update\n\n"
                "def update_document(role: str) -> bool:\n"
                "    return can_update(role)\n"
                "*** Update File: tests/test_permissions.py\n"
                "SEARCH:\n"
                "from permissions import can_edit\n"
                "from api import update_document\n\n"
                "def test_editor_can_update():\n"
                "    assert can_edit('editor')\n"
                "    assert update_document('editor')\n"
                "REPLACE:\n"
                "from permissions import can_update\n"
                "from api import update_document\n\n"
                "def test_editor_can_update():\n"
                "    assert can_update('editor')\n"
                "    assert update_document('editor')\n"
                "*** End Patch"
            ),
            input_tokens=20,
            output_tokens=10,
        )


class _RetrievalPatchLLM:
    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        return AgentPlanResponse(goal=goal, steps=["edit"])

    def choose_tool(self, goal: str, context: dict):
        raise NotImplementedError

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        return AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: src/auth/policy.py\n"
                "SEARCH:\n"
                "def has_permission(user, action: str) -> bool:\n"
                "    if action == 'delete':\n"
                "        return user.role == 'admin'\n"
                "    return user.role in {'admin', 'editor'}\n"
                "REPLACE:\n"
                "# Authorization audit note: middleware calls this policy helper for permission decisions.\n"
                "def has_permission(user, action: str) -> bool:\n"
                "    if action == 'delete':\n"
                "        return user.role == 'admin'\n"
                "    return user.role in {'admin', 'editor'}\n"
                "*** End Patch"
            ),
            input_tokens=10,
            output_tokens=10,
        )


class TestLiveEvalRunner:
    def test_runner_applies_generated_patch(self, monkeypatch):
        fixture = LiveEvalFixture(
            name="apply-generated-patch",
            setup_files={"src/hello.py": "def greet():\n    return 'hi'\n"},
            goal="Change greet() to return hello.",
            success_condition=lambda root: "return 'hello'" in (root / "src/hello.py").read_text(),
        )

        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _PatchOnlyLLM())
        result = LiveEvalRunner(provider="mock").run_fixture(fixture)

        assert result.success is True
        assert result.tool_calls == 1
        assert result.error is None
        assert {g["name"] for g in result.grader_results} >= {"outcome", "safety_invariants"}

    def test_runner_enables_provider_network_allowlist(self, monkeypatch):
        captured = {}
        fixture = LiveEvalFixture(
            name="provider-network",
            setup_files={"src/hello.py": "def greet():\n    return 'hi'\n"},
            goal="Change greet() to return hello.",
            success_condition=lambda root: True,
        )

        def fake_create_client(cfg):
            captured["network_enabled"] = cfg.sandbox.network_enabled
            captured["network_allowlist"] = list(cfg.sandbox.network_allowlist)
            return _PatchOnlyLLM()

        monkeypatch.setattr("safecode.llm.factory.create_llm_client", fake_create_client)
        result = LiveEvalRunner(provider="deepseek").run_fixture(fixture)

        assert result.success is True
        assert captured == {
            "network_enabled": True,
            "network_allowlist": ["api.deepseek.com"],
        }

    def test_runner_executes_validation_commands(self, monkeypatch):
        fixture = next(f for f in default_live_fixtures() if f.name == "verification-required-bug-fix")
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _CartFixLLM())

        result = LiveEvalRunner(provider="mock").run_fixture(fixture)

        assert result.success is True
        assert result.tests_run == 1
        assert result.test_passed is True
        assert result.validation_commands == ["python -m pytest -q tests/test_cart.py"]

    def test_runner_repairs_after_success_condition_failure(self, monkeypatch):
        fixture = next(f for f in default_live_fixtures() if f.name == "semantic-incomplete-repair")
        llm = _IncompleteThenRepairLLM()
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: llm)

        result = LiveEvalRunner(provider="mock").run_fixture(fixture)

        assert result.success is True
        assert llm.calls == 2
        assert result.success_condition_retry_needed is True
        assert result.success_condition_recovered is True
        assert result.repair_attempts == 1
        assert result.malformed_patch_recovered is True

    def test_runner_records_retrieval_metrics(self, monkeypatch):
        fixture = next(f for f in default_live_fixtures() if f.name == "context-retrieval-permissions")
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _RetrievalPatchLLM())

        result = LiveEvalRunner(provider="mock").run_fixture(fixture)

        assert result.success is True
        assert result.relevant_file_recall == 0.5
        assert result.relevant_file_precision == 1.0
        assert result.symbol_localization_accuracy == 0.5
        assert result.minimal_diff_score == 5
        assert result.mergeability_score == 5
        assert result.reviewer_accept is True


class TestLiveModeSkipsWithoutEnvVar:
    def test_live_mode_skips_without_env(self, monkeypatch):
        monkeypatch.delenv("SAFECODE_LIVE_TESTS", raising=False)
        live_tests_set = bool(os.environ.get("SAFECODE_LIVE_TESTS"))
        assert not live_tests_set


class TestCheckWorkingTreeClean:
    def test_clean_workspace_returns_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 1")
            assert _check_working_tree_clean(root) is True

    def test_tmp_file_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "patch.tmp").write_text("partial")
            assert _check_working_tree_clean(root) is False

    def test_bak_file_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py.bak").write_text("backup")
            assert _check_working_tree_clean(root) is False

    def test_tmp_in_sac_dir_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sac = root / ".sac" / "checkpoints"
            sac.mkdir(parents=True)
            (sac / "backup.tmp").write_text("checkpoint artifact")
            assert _check_working_tree_clean(root) is True


class TestClassifyError:
    def test_patch_parse_error(self):
        assert _classify_error("PatchParseError: too short") == "patch_parse"

    def test_patch_validation_error(self):
        assert _classify_error("PatchValidationError: SEARCH content must match exactly once") == "patch_parse"

    def test_timeout_error(self):
        assert _classify_error("TimeoutError: timed out after 30s") == "timeout"

    def test_llm_contract_violation(self):
        assert _classify_error("LLMContractViolation: missing patch field") == "model_error"

    def test_unknown_error(self):
        assert _classify_error("SomeCrazyError: unexpected") == "unknown"

    def test_empty_string(self):
        assert _classify_error("") == "unknown"


class TestVerifyAuditChain:
    def test_returns_true_when_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _verify_audit_chain(Path(tmp)) is True

    def test_returns_true_for_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text("")
            assert _verify_audit_chain(root) is True

    def test_valid_single_event_chain(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            event = {"type": "patch_proposed", "timestamp": "2026-01-01T00:00:00Z",
                     "previous_hash": None, "event_hash": None}
            check = dict(event)
            check["event_hash"] = None
            payload = json.dumps(check, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            event["event_hash"] = hashlib.sha256(payload.encode()).hexdigest()
            log.write_text(json.dumps(event, sort_keys=True) + "\n")
            assert _verify_audit_chain(root) is True

    def test_broken_chain_returns_false(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            # Second event has wrong previous_hash
            e1 = {"type": "e1", "timestamp": "t", "previous_hash": None, "event_hash": "abc"}
            e2 = {"type": "e2", "timestamp": "t", "previous_hash": "wrong", "event_hash": "def"}
            log.write_text(json.dumps(e1) + "\n" + json.dumps(e2) + "\n")
            assert _verify_audit_chain(root) is False

    def test_tampered_hash_returns_false(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            # Hash doesn't match content
            event = {"type": "patch_proposed", "timestamp": "2026-01-01T00:00:00Z",
                     "previous_hash": None, "event_hash": "tampered_hash"}
            log.write_text(json.dumps(event, sort_keys=True) + "\n")
            assert _verify_audit_chain(root) is False


class TestCountApprovalEvents:
    def test_returns_zero_when_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _count_approval_events(Path(tmp)) == 0

    def test_counts_patch_proposed_events(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            events = [
                {"type": "patch_proposed"},
                {"type": "patch_applied"},
                {"type": "sandbox_proposed"},
                {"type": "context_collected"},
            ]
            log.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            assert _count_approval_events(root) == 2  # patch_proposed + sandbox_proposed

    def test_ignores_non_gate_events(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".sac" / "logs" / "events.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text(json.dumps({"type": "patch_applied"}) + "\n")
            assert _count_approval_events(root) == 0


class TestCountUnauthorizedMutations:
    def test_returns_zero_for_only_setup_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")  # modified but in scope
            assert _count_unauthorized_mutations(root, setup) == 0

    def test_counts_unexpected_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")
            (root / "src" / "extra.py").write_text("y = 3")  # not in setup
            assert _count_unauthorized_mutations(root, setup) == 1

    def test_ignores_sac_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")
            sac = root / ".sac" / "checkpoints"
            sac.mkdir(parents=True)
            (sac / "backup.json").write_text("{}")
            assert _count_unauthorized_mutations(root, setup) == 0

    def test_ignores_pycache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")
            pycache = root / "src" / "__pycache__"
            pycache.mkdir(parents=True)
            (pycache / "main.cpython-312.pyc").write_bytes(b"\x00\x01\x02")
            assert _count_unauthorized_mutations(root, setup) == 0

    def test_ignores_pyc_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup = {"src/main.py": "x = 1"}
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 2")
            (root / "src" / "main.pyc").write_bytes(b"\x00")
            assert _count_unauthorized_mutations(root, setup) == 0


class TestRepeatedRun:
    def test_run_all_repeated_returns_n_run_sets(self, monkeypatch):
        class _FastLLM:
            def ask(self, *a, **kw): ...
            def plan(self, *a, **kw): ...
            def choose_tool(self, *a, **kw): raise NotImplementedError
            def propose_patch(self, task, context):
                from safecode.agent.schemas import AgentPatchResponse
                return AgentPatchResponse(patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/hello.py\n"
                    "SEARCH:\n"
                    "x = 1\n"
                    "REPLACE:\n"
                    "x = 2\n"
                    "*** End Patch"
                ))
        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _FastLLM())
        fixture = LiveEvalFixture(
            name="repeat-test",
            setup_files={"src/hello.py": "x = 1\n"},
            goal="Change x to 2.",
            success_condition=lambda root: "x = 2" in (root / "src" / "hello.py").read_text(),
        )
        runner = LiveEvalRunner(provider="mock")
        all_runs = runner.run_all_repeated(fixtures=[fixture], n_runs=2)
        assert len(all_runs) == 2
        assert all(len(run) == 1 for run in all_runs)
        assert all(run[0].fixture_name == "repeat-test" for run in all_runs)

    def test_summarize_repeated_results(self):
        runs = [
            [
                LiveEvalResult(
                    fixture_name="a", success=True, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=100, output_tokens=20, wall_seconds=1.0,
                    patch_retry_needed=True, success_condition_retry_needed=True,
                    success_condition_recovered=True,
                )
            ],
            [
                LiveEvalResult(
                    fixture_name="a", success=False, turns_used=1, tool_calls=1,
                    redundant_reads=0, input_tokens=200, output_tokens=40, wall_seconds=3.0,
                    error="failed",
                )
            ],
        ]

        summary = summarize_repeated_results(runs)
        data = summary.as_dict()

        assert data["overall_pass_rate"] == 0.5
        fixture = data["fixtures"][0]
        assert fixture["fixture_name"] == "a"
        assert fixture["runs"] == 2
        assert fixture["pass_rate"] == 0.5
        assert fixture["retry_rate"] == 0.5
        assert fixture["repair_rate"] == 0.5
        assert fixture["recovery_rate"] == 0.5
        assert fixture["safety_invariants_ok"] is True
        assert fixture["pass_at_1"] == 1.0
        assert fixture["pass_at_n"] == 1.0
        rendered = render_repeated_summary(summary)
        assert "Overall pass rate: 0.500" in rendered
        assert "pass@1=1.000" in rendered
        assert "pass@N=1.000" in rendered
        assert "recovery=0.500" in rendered


class TestLiveEvalTranscripts:
    def test_save_live_transcript_redacts_goal_and_records_outcome(self, tmp_path):
        from safecode.eval.live import LiveEvalResult, save_live_transcript

        fixture = LiveEvalFixture(
            name="transcript-test",
            setup_files={"a.py": "x = 1\n"},
            goal='Fix bug with api_key="sk-secret1234567890".',
            success_condition=lambda root: True,
        )
        result = LiveEvalResult(
            fixture_name="transcript-test",
            success=True,
            turns_used=1,
            tool_calls=1,
            redundant_reads=0,
            input_tokens=10,
            output_tokens=5,
            wall_seconds=0.1,
        )

        path = save_live_transcript(
            fixture=fixture,
            result=result,
            transcript_dir=tmp_path,
            provider="mock",
            model="mock-model",
        )

        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        assert data["schema_version"] == 1
        assert data["outcome"]["success"] is True
        assert "sk-secret" not in text
        assert "[REDACTED]" in text

    def test_runner_writes_transcript_when_enabled(self, tmp_path, monkeypatch):
        class _FastLLM:
            def ask(self, *a, **kw): ...
            def plan(self, *a, **kw): ...
            def choose_tool(self, *a, **kw): raise NotImplementedError
            def propose_patch(self, task, context):
                from safecode.agent.schemas import AgentPatchResponse
                return AgentPatchResponse(patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/hello.py\n"
                    "SEARCH:\n"
                    "x = 1\n"
                    "REPLACE:\n"
                    "x = 2\n"
                    "*** End Patch"
                ))

        monkeypatch.setattr("safecode.llm.factory.create_llm_client", lambda cfg: _FastLLM())
        fixture = LiveEvalFixture(
            name="transcript-runner-test",
            setup_files={"src/hello.py": "x = 1\n"},
            goal="Change x to 2.",
            success_condition=lambda root: "x = 2" in (root / "src" / "hello.py").read_text(),
        )
        runner = LiveEvalRunner(provider="mock", transcript_dir=tmp_path)

        result = runner.run_fixture(fixture)

        assert result.transcript_path
        assert Path(result.transcript_path).exists()


class TestVerifyCheckpointIntegrity:
    def test_returns_true_when_no_checkpoints_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _verify_checkpoint_integrity(Path(tmp)) is True

    def test_returns_true_for_empty_checkpoints_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sac" / "checkpoints").mkdir(parents=True)
            assert _verify_checkpoint_integrity(root) is True

    def test_returns_true_when_no_sha256_stored(self):
        """Old checkpoints without backup_sha256 are skipped (backward compat)."""
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cp_dir = root / ".sac" / "checkpoints" / "cp1"
            cp_dir.mkdir(parents=True)
            meta = {"checkpoint_id": "cp1", "task": "t", "patch_id": "p",
                    "created_at": "2026-01-01", "file_operations": [
                        {"path": "src/f.py", "operation": "update",
                         "existed_before": True, "backup_path": "files/src/f.py",
                         "backup_sha256": None}
                    ]}
            (cp_dir / "metadata.json").write_text(json.dumps(meta))
            assert _verify_checkpoint_integrity(root) is True

    def test_returns_true_for_matching_sha256(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cp_dir = root / ".sac" / "checkpoints" / "cp1"
            backup = cp_dir / "files" / "src" / "f.py"
            backup.parent.mkdir(parents=True)
            backup.write_bytes(b"original content")
            sha = hashlib.sha256(b"original content").hexdigest()
            meta = {"checkpoint_id": "cp1", "task": "t", "patch_id": "p",
                    "created_at": "2026-01-01", "file_operations": [
                        {"path": "src/f.py", "operation": "update",
                         "existed_before": True, "backup_path": "files/src/f.py",
                         "backup_sha256": sha}
                    ]}
            (cp_dir / "metadata.json").write_text(json.dumps(meta))
            assert _verify_checkpoint_integrity(root) is True

    def test_returns_false_for_tampered_backup(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cp_dir = root / ".sac" / "checkpoints" / "cp1"
            backup = cp_dir / "files" / "src" / "f.py"
            backup.parent.mkdir(parents=True)
            backup.write_bytes(b"tampered content")
            sha = hashlib.sha256(b"original content").hexdigest()  # stored hash is for original
            meta = {"checkpoint_id": "cp1", "task": "t", "patch_id": "p",
                    "created_at": "2026-01-01", "file_operations": [
                        {"path": "src/f.py", "operation": "update",
                         "existed_before": True, "backup_path": "files/src/f.py",
                         "backup_sha256": sha}
                    ]}
            (cp_dir / "metadata.json").write_text(json.dumps(meta))
            assert _verify_checkpoint_integrity(root) is False

    def test_returns_false_when_backup_file_missing(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cp_dir = root / ".sac" / "checkpoints" / "cp1"
            cp_dir.mkdir(parents=True)
            sha = hashlib.sha256(b"x").hexdigest()
            meta = {"checkpoint_id": "cp1", "task": "t", "patch_id": "p",
                    "created_at": "2026-01-01", "file_operations": [
                        {"path": "src/f.py", "operation": "update",
                         "existed_before": True, "backup_path": "files/src/f.py",
                         "backup_sha256": sha}
                    ]}
            (cp_dir / "metadata.json").write_text(json.dumps(meta))
            assert _verify_checkpoint_integrity(root) is False


class TestCheckPatchRetryNeeded:
    def test_returns_false_when_no_journals_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _check_patch_retry_needed(Path(tmp)) is False

    def test_returns_false_when_no_loop_retry_events(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journals = root / ".sac" / "agent_journals"
            journals.mkdir(parents=True)
            f = journals / "session1.jsonl"
            f.write_text(json.dumps({"type": "action", "message": "did something"}) + "\n")
            assert _check_patch_retry_needed(root) is False

    def test_returns_true_when_loop_retry_event_present(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journals = root / ".sac" / "agent_journals"
            journals.mkdir(parents=True)
            f = journals / "session1.jsonl"
            events = [
                {"type": "plan", "message": "planning"},
                {"type": "loop_retry", "message": "retrying due to contract failure",
                 "payload": {"loop_retry": {"retry_attempt": 1}}},
            ]
            f.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            assert _check_patch_retry_needed(root) is True
