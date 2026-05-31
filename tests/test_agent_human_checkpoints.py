"""Human checkpoint prompt tests for v1.9.4."""

from __future__ import annotations

from typer.testing import CliRunner

from safecode.agent.approvals import HumanCheckpointPresenter
from safecode.audit.logger import AuditLogger
from safecode.cli import app

runner = CliRunner()


class TestHumanCheckpointPresenter:
    def test_checkpoint_writes_standard_audit_event(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        checkpoint = HumanCheckpointPresenter(tmp_path).checkpoint(
            checkpoint_type="patch_apply",
            title="Patch Apply Checkpoint",
            prompt="Apply this patch?",
            risk_level="write",
            summary="Apply one patch.",
            subject="patch-123",
            metadata={"patch_id": "patch-123"},
        )

        assert checkpoint.subject_hash
        events = AuditLogger(tmp_path).read_recent(limit=5)
        event = [e for e in events if e.type == "human_checkpoint_presented"][0]
        assert event.status == "blocked"
        assert event.metadata["checkpoint_type"] == "patch_apply"
        assert event.metadata["risk_level"] == "write"
        assert event.metadata["patch_id"] == "patch-123"

    def test_subject_hash_does_not_store_raw_subject_in_metadata(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        HumanCheckpointPresenter(tmp_path).checkpoint(
            checkpoint_type="shell_run",
            title="Shell",
            prompt="Run?",
            risk_level="medium",
            summary="Run command.",
            subject="secret command value",
        )

        events = AuditLogger(tmp_path).read_recent(limit=5)
        event = [e for e in events if e.type == "human_checkpoint_presented"][0]
        assert "secret command value" not in str(event.metadata)


class TestHumanCheckpointCLI:
    def test_shell_medium_prompt_writes_checkpoint_event(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["run", "python -V"], input="n\n")

        assert result.exit_code == 0
        assert "Shell Command Checkpoint" in result.stdout
        events = AuditLogger(tmp_path).read_recent(limit=10)
        checkpoints = [e for e in events if e.type == "human_checkpoint_presented"]
        assert checkpoints
        assert checkpoints[0].metadata["checkpoint_type"] == "shell_run"

    def test_sandbox_approve_writes_checkpoint_event(self, tmp_path, monkeypatch):
        approvals = tmp_path.parent / f"approvals-{tmp_path.name}"
        anchors = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(approvals))
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchors))
        monkeypatch.chdir(tmp_path)

        propose = runner.invoke(app, ["sandbox", "propose", "echo", "hello"])
        approve = runner.invoke(app, ["sandbox", "approve"])

        assert propose.exit_code == 0
        assert approve.exit_code == 0
        assert "Sandbox Execution Checkpoint" in approve.stdout
        events = AuditLogger(tmp_path).read_recent(limit=10)
        checkpoints = [e for e in events if e.type == "human_checkpoint_presented"]
        assert checkpoints
        assert checkpoints[-1].metadata["checkpoint_type"] == "sandbox_execute"
