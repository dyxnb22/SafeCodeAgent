"""Tests for v2.7.2 versions-json-sync — sac release sync-versions-json."""

import json
import subprocess
from pathlib import Path

import pytest

from safecode.release.versions_sync import check_versions_json_stale, sync_versions_json


def _make_git_repo_with_tags(tmp_path: Path, tags: list[str]) -> Path:
    """Create a minimal git repo with the given annotated tags."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path), check=True, capture_output=True,
    )
    (tmp_path / "README.md").write_text("test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path), check=True, capture_output=True,
    )
    for tag in tags:
        subprocess.run(
            ["git", "tag", "-a", tag, "-m", tag],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
    return tmp_path


def _write_versions_json(tmp_path: Path, current: str, latest_tags: list[str]) -> Path:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    data = {
        "project": "TestProject",
        "current_implemented_tag": current,
        "latest_tags": latest_tags,
    }
    path = claude_dir / "versions.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


class TestSyncVersionsJson:
    def test_sync_updates_stale_current_tag(self, tmp_path):
        repo = _make_git_repo_with_tags(tmp_path, ["v1.0.0", "v1.1.0", "v1.2.0"])
        _write_versions_json(repo, "v1.0.0", ["v1.0.0"])

        result = sync_versions_json(project_root=repo)

        assert result.ok is True
        assert result.new_current == "v1.2.0"
        assert result.changed is True
        payload = json.loads((repo / ".claude" / "versions.json").read_text())
        assert payload["current_implemented_tag"] == "v1.2.0"
        # New tags are appended to the existing list
        assert "v1.1.0" in payload["latest_tags"]
        assert "v1.2.0" in payload["latest_tags"]
        assert payload["latest_tags"][-1] == "v1.2.0"

    def test_sync_appends_only_missing_tags(self, tmp_path):
        repo = _make_git_repo_with_tags(tmp_path, ["v1.0.0", "v1.1.0", "v1.2.0"])
        _write_versions_json(repo, "v1.1.0", ["v1.0.0", "v1.1.0"])

        result = sync_versions_json(project_root=repo)

        assert result.ok is True
        assert result.changed is True
        payload = json.loads((repo / ".claude" / "versions.json").read_text())
        # v1.2.0 was appended; v1.0.0 and v1.1.0 remain in original order
        assert payload["latest_tags"] == ["v1.0.0", "v1.1.0", "v1.2.0"]

    def test_sync_no_change_when_already_current(self, tmp_path):
        repo = _make_git_repo_with_tags(tmp_path, ["v1.0.0", "v1.1.0"])
        _write_versions_json(repo, "v1.1.0", ["v1.0.0", "v1.1.0"])

        result = sync_versions_json(project_root=repo)

        assert result.ok is True
        assert result.changed is False

    def test_dry_run_does_not_write(self, tmp_path):
        repo = _make_git_repo_with_tags(tmp_path, ["v1.0.0", "v2.0.0"])
        path = _write_versions_json(repo, "v1.0.0", ["v1.0.0"])
        before = path.read_text()

        result = sync_versions_json(project_root=repo, dry_run=True)

        assert result.ok is True
        assert result.changed is True
        assert path.read_text() == before

    def test_missing_versions_json_returns_error(self, tmp_path):
        repo = _make_git_repo_with_tags(tmp_path, ["v1.0.0"])

        result = sync_versions_json(project_root=repo)

        assert result.ok is False
        assert "versions.json" in result.message

    def test_no_tags_returns_error(self, tmp_path):
        repo = tmp_path
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(repo), check=True, capture_output=True,
        )
        _write_versions_json(repo, "v0.0.0", [])

        result = sync_versions_json(project_root=repo)

        assert result.ok is False
        assert "tag" in result.message.lower()

    def test_stale_versions_json_is_detected(self, tmp_path):
        repo = _make_git_repo_with_tags(tmp_path, ["v1.0.0", "v1.1.0"])
        _write_versions_json(repo, "v1.0.0", ["v1.0.0"])

        result = check_versions_json_stale(project_root=repo)

        assert result.ok is True
        assert result.changed is True

    def test_current_repo_versions_json_current_tag_is_latest(self):
        """The actual repo's current_implemented_tag must equal the latest git tag."""
        result = check_versions_json_stale(project_root=Path("."))
        assert result.ok is True, result.message
        # Only the current_implemented_tag staleness matters for CI governance.
        # latest_tags may be a curated subset; we only require the last entry is current.
        from pathlib import Path as _Path
        import json as _json
        payload = _json.loads((_Path(".claude") / "versions.json").read_text())
        assert payload["current_implemented_tag"] == result.new_current, (
            f"current_implemented_tag {payload['current_implemented_tag']!r} != "
            f"latest git tag {result.new_current!r}"
        )
        assert payload["latest_tags"][-1] == result.new_current, (
            f"latest_tags[-1] {payload['latest_tags'][-1]!r} != "
            f"latest git tag {result.new_current!r}"
        )


class TestSyncVersionsJsonCli:
    def test_cli_command_exists_and_runs(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["release", "sync-versions-json", "--help"])
        assert result.exit_code == 0
        assert "sync" in result.output.lower() or "versions" in result.output.lower()
