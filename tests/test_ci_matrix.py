"""Tests for v3.6.0 CI matrix expansion (T-3.6.0-B).

Guards the GitHub Actions workflow YAML shape:
- Python 3.11, 3.12, 3.13 on ubuntu-latest and macos-latest.
- Windows smoke lane (advisory, continue-on-error).
- Loop eval and live-provider lanes remain advisory and gated.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/ci.yml")


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job(name: str) -> dict:
    return _load_workflow()["jobs"][name]


# ── Workflow exists ───────────────────────────────────────────────────────────


class TestWorkflowExists:
    def test_workflow_file_exists(self):
        assert WORKFLOW.is_file()

    def test_workflow_is_valid_yaml(self):
        data = _load_workflow()
        assert isinstance(data, dict)
        assert "jobs" in data


# ── Matrix: Python versions ───────────────────────────────────────────────────


class TestPythonMatrix:
    def _matrix_versions(self) -> list[str]:
        job = _job("test")
        return job["strategy"]["matrix"]["python-version"]

    def test_python_311_in_matrix(self):
        assert "3.11" in self._matrix_versions()

    def test_python_312_in_matrix(self):
        assert "3.12" in self._matrix_versions()

    def test_python_313_in_matrix(self):
        assert "3.13" in self._matrix_versions()

    def test_no_legacy_python_in_matrix(self):
        versions = self._matrix_versions()
        for v in versions:
            major, minor = int(v.split(".")[0]), int(v.split(".")[1])
            assert (major, minor) >= (3, 11), f"legacy Python in matrix: {v}"


# ── Matrix: OS ────────────────────────────────────────────────────────────────


class TestOSMatrix:
    def _matrix_os(self) -> list[str]:
        job = _job("test")
        return job["strategy"]["matrix"]["os"]

    def test_ubuntu_in_matrix(self):
        assert any("ubuntu" in os for os in self._matrix_os())

    def test_macos_in_matrix(self):
        assert any("macos" in os for os in self._matrix_os())

    def test_matrix_has_fail_fast_false(self):
        job = _job("test")
        assert job["strategy"].get("fail-fast") is False


# ── Matrix: runs-on uses matrix variable ─────────────────────────────────────


class TestMatrixRunsOn:
    def test_test_job_uses_matrix_os(self):
        job = _job("test")
        runs_on = job["runs-on"]
        assert "matrix.os" in runs_on

    def test_test_job_uses_matrix_python_version(self):
        job = _job("test")
        setup_step = next(
            s for s in job["steps"] if "setup-python" in s.get("uses", "")
        )
        python_version = setup_step["with"]["python-version"]
        assert "matrix.python-version" in python_version


# ── Windows smoke lane ────────────────────────────────────────────────────────


class TestWindowsSmoke:
    def test_windows_smoke_job_exists(self):
        jobs = _load_workflow()["jobs"]
        assert "smoke-windows" in jobs

    def test_windows_smoke_runs_on_windows(self):
        job = _job("smoke-windows")
        assert "windows" in job["runs-on"]

    def test_windows_smoke_is_advisory(self):
        job = _job("smoke-windows")
        assert job.get("continue-on-error") is True

    def test_windows_smoke_runs_tests(self):
        job = _job("smoke-windows")
        steps_text = str(job["steps"])
        assert "pytest" in steps_text

    def test_windows_smoke_uses_python_311(self):
        job = _job("smoke-windows")
        setup_step = next(
            s for s in job["steps"] if "setup-python" in s.get("uses", "")
        )
        assert setup_step["with"]["python-version"] == "3.11"


# ── Loop eval remains advisory ────────────────────────────────────────────────


class TestLoopEvalAdvisory:
    def test_loop_eval_job_exists(self):
        jobs = _load_workflow()["jobs"]
        assert "loop-eval" in jobs

    def test_loop_eval_is_advisory(self):
        job = _job("loop-eval")
        assert job.get("continue-on-error") is True

    def test_loop_eval_no_credentials(self):
        job = _job("loop-eval")
        env = job.get("env", {})
        for key in env:
            assert "API_KEY" not in key.upper(), f"live key in loop-eval env: {key}"


# ── Live-provider lane remains secret-gated ───────────────────────────────────


class TestLiveProviderGated:
    def test_live_provider_job_exists(self):
        jobs = _load_workflow()["jobs"]
        assert "live-provider" in jobs

    def test_live_provider_is_advisory(self):
        job = _job("live-provider")
        assert job.get("continue-on-error") is True

    def test_live_provider_has_gating_condition(self):
        job = _job("live-provider")
        condition = str(job.get("if", ""))
        assert "ENABLE_LIVE_LLM_TESTS" in condition

    def test_live_provider_injects_secrets_via_env(self):
        job = _job("live-provider")
        env = job.get("env", {})
        assert any("ANTHROPIC" in k or "OPENAI" in k for k in env)

    def test_no_plain_api_keys_in_workflow(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        import re
        # Real keys look like sk-ant-... or sk-... with > 20 chars
        assert not re.search(r'sk-[A-Za-z0-9\-]{20,}', text)


# ── Main test job still runs full regression ──────────────────────────────────


class TestMainJobShape:
    def test_main_job_runs_full_regression(self):
        job = _job("test")
        steps_text = str(job["steps"])
        assert "PYTHONPATH=src python3 -m pytest -q" in steps_text

    def test_main_job_runs_release_smoke(self):
        job = _job("test")
        steps_text = str(job["steps"])
        assert "release smoke" in steps_text

    def test_main_job_no_exact_tag_check(self):
        job = _job("test")
        steps_text = str(job["steps"])
        assert "release check" not in steps_text
        assert "release preflight" not in steps_text

    def test_main_job_generates_changelog(self):
        job = _job("test")
        steps_text = str(job["steps"])
        assert "release changelog" in steps_text


# ── Release job (v5.5.0) ─────────────────────────────────────────────────────


class TestReleaseJob:
    def test_release_job_exists(self):
        jobs = _load_workflow()["jobs"]
        assert "release" in jobs

    def test_release_job_needs_test(self):
        job = _job("release")
        needs = job.get("needs", [])
        needs_list = [needs] if isinstance(needs, str) else list(needs)
        assert "test" in needs_list

    def test_release_job_triggered_on_tag(self):
        job = _job("release")
        condition = str(job.get("if", ""))
        assert "refs/tags/v" in condition

    def test_release_job_restricted_to_major_minor_zero(self):
        job = _job("release")
        condition = str(job.get("if", ""))
        assert ".0" in condition

    def test_release_job_requires_publish_env(self):
        job = _job("release")
        env = job.get("env", {})
        assert env.get("SAFECODE_PUBLISH") == "1"

    def test_release_job_uses_pypi_token_secret(self):
        job = _job("release")
        env = job.get("env", {})
        token_val = env.get("UV_PUBLISH_TOKEN", "")
        assert "PYPI_TOKEN" in token_val

    def test_release_job_runs_preflight(self):
        job = _job("release")
        steps_text = str(job["steps"])
        assert "release preflight" in steps_text

    def test_release_job_runs_publish_no_dry_run(self):
        job = _job("release")
        steps_text = str(job["steps"])
        assert "release publish" in steps_text
        assert "--no-dry-run" in steps_text

    def test_release_job_no_plain_secrets(self):
        import re
        text = WORKFLOW.read_text(encoding="utf-8")
        assert not re.search(r'sk-[A-Za-z0-9\-]{20,}', text)

    def test_release_job_has_id_token_permission(self):
        job = _job("release")
        perms = job.get("permissions", {})
        assert perms.get("id-token") == "write"

    def test_workflow_tag_trigger_configured(self):
        data = _load_workflow()
        # PyYAML parses the 'on' key as boolean True
        trigger = data.get(True, data.get("on", {}))
        push = trigger.get("push", {})
        tags = push.get("tags", [])
        assert any("v" in t for t in tags)
