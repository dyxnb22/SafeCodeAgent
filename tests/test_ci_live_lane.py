"""Tests for v3.2.5 live-provider CI lane.

Verifies structural properties of the CI workflow and the live test gate.
No real network calls are made.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

_CI_YAML = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
_LIVE_DIR = Path(__file__).parent / "live"
_LIVE_CONFTEST = _LIVE_DIR / "conftest.py"
_LIVE_TEST = _LIVE_DIR / "test_live_providers.py"


def _load_ci() -> dict:
    return yaml.safe_load(_CI_YAML.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CI workflow structure
# ---------------------------------------------------------------------------


class TestCIWorkflowStructure:
    def test_ci_file_exists(self) -> None:
        assert _CI_YAML.exists(), "CI workflow file must exist"

    def test_live_provider_job_exists(self) -> None:
        ci = _load_ci()
        assert "live-provider" in ci["jobs"], "live-provider job must be in CI"

    def test_live_provider_job_is_advisory(self) -> None:
        ci = _load_ci()
        job = ci["jobs"]["live-provider"]
        assert job.get("continue-on-error") is True, "live-provider job must be continue-on-error"

    def test_live_provider_job_has_gating_condition(self) -> None:
        ci = _load_ci()
        job = ci["jobs"]["live-provider"]
        condition = str(job.get("if", ""))
        # Must reference ENABLE_LIVE_LLM_TESTS variable (not a secret check)
        assert "ENABLE_LIVE_LLM_TESTS" in condition, (
            "live-provider job must be gated by ENABLE_LIVE_LLM_TESTS"
        )

    def test_live_provider_job_uses_env_for_secrets(self) -> None:
        ci = _load_ci()
        job = ci["jobs"]["live-provider"]
        env = job.get("env", {})
        # Secrets are consumed via env vars, not exposed in step conditions
        env_str = str(env)
        assert "ANTHROPIC_API_KEY" in env_str or "OPENAI_API_KEY" in env_str

    def test_live_provider_job_sets_safecode_live_tests(self) -> None:
        ci = _load_ci()
        job = ci["jobs"]["live-provider"]
        env = job.get("env", {})
        assert env.get("SAFECODE_LIVE_TESTS") == "1"

    def test_live_provider_job_runs_live_tests_dir(self) -> None:
        ci = _load_ci()
        job = ci["jobs"]["live-provider"]
        steps = job.get("steps", [])
        run_cmds = [s.get("run", "") for s in steps if "run" in s]
        assert any("tests/live" in cmd for cmd in run_cmds), (
            "live-provider job must run tests in tests/live/"
        )

    def test_main_test_job_does_not_run_live_tests(self) -> None:
        ci = _load_ci()
        job = ci["jobs"]["test"]
        steps = job.get("steps", [])
        run_cmds = [s.get("run", "") for s in steps if "run" in s]
        # Main test job must not explicitly run tests/live/
        assert not any("tests/live" in cmd for cmd in run_cmds), (
            "Main test job must not run live tests"
        )

    def test_default_ci_path_runs_local_only(self) -> None:
        ci = _load_ci()
        job = ci["jobs"]["test"]
        steps = job.get("steps", [])
        run_cmds = [s.get("run", "") for s in steps if "run" in s]
        # Should run pytest without SAFECODE_LIVE_TESTS
        regression_cmds = [cmd for cmd in run_cmds if "pytest" in cmd]
        assert regression_cmds, "Main job must run pytest"
        for cmd in regression_cmds:
            assert "SAFECODE_LIVE_TESTS" not in cmd, (
                "Main job pytest must not set SAFECODE_LIVE_TESTS"
            )

    def test_no_real_api_keys_in_workflow_file(self) -> None:
        content = _CI_YAML.read_text(encoding="utf-8")
        # No hardcoded API key patterns (starts with sk-, claude-, anthropic-)
        suspicious = ["sk-ant-", "sk-proj-", "claude-key-", "anthropic-key-"]
        for pattern in suspicious:
            assert pattern not in content, (
                f"CI file must not contain hardcoded key pattern: {pattern!r}"
            )


# ---------------------------------------------------------------------------
# Live test directory structure
# ---------------------------------------------------------------------------


class TestLiveTestDirectory:
    def test_live_dir_exists(self) -> None:
        assert _LIVE_DIR.is_dir(), "tests/live/ directory must exist"

    def test_live_conftest_exists(self) -> None:
        assert _LIVE_CONFTEST.exists(), "tests/live/conftest.py must exist"

    def test_live_test_file_exists(self) -> None:
        assert _LIVE_TEST.exists(), "tests/live/test_live_providers.py must exist"

    def test_live_conftest_references_env_var(self) -> None:
        content = _LIVE_CONFTEST.read_text(encoding="utf-8")
        assert "SAFECODE_LIVE_TESTS" in content

    def test_live_conftest_skips_without_env(self) -> None:
        content = _LIVE_CONFTEST.read_text(encoding="utf-8")
        assert "pytest.skip" in content

    def test_live_test_file_no_hardcoded_credentials(self) -> None:
        content = _LIVE_TEST.read_text(encoding="utf-8")
        suspicious = ["sk-ant-", "sk-proj-", "AKIA", "token=", "password="]
        for pattern in suspicious:
            assert pattern not in content, (
                f"Live test file must not contain hardcoded credential pattern: {pattern!r}"
            )


# ---------------------------------------------------------------------------
# Live test gate: normal pytest does not trigger live providers
# ---------------------------------------------------------------------------


class TestLiveGateDefault:
    def test_live_tests_skipped_without_env_var(self) -> None:
        """The live conftest skips tests unless SAFECODE_LIVE_TESTS=1."""
        # Ensure env var is not set in this process
        env_val = os.environ.get("SAFECODE_LIVE_TESTS", "")
        if env_val:
            pytest.skip("SAFECODE_LIVE_TESTS is set in this process; gate test not meaningful")

        # The conftest uses pytest.skip() in pytest_runtest_setup.
        # We verify the guard code is present rather than actually running the live tests.
        content = _LIVE_CONFTEST.read_text(encoding="utf-8")
        assert "pytest_runtest_setup" in content or "pytest_collection_modifyitems" in content

    def test_no_live_import_in_normal_tests(self) -> None:
        """Normal test files must not import from tests/live/."""
        tests_dir = Path(__file__).parent
        for test_file in tests_dir.glob("test_*.py"):
            if test_file.name == "test_ci_live_lane.py":
                continue
            content = test_file.read_text(encoding="utf-8")
            assert "from tests.live" not in content
            assert "import tests.live" not in content

    def test_live_test_uses_require_env_pattern(self) -> None:
        """Each live test class must guard with _require_env() or equivalent."""
        content = _LIVE_TEST.read_text(encoding="utf-8")
        assert "_require_env" in content or "pytest.skip" in content


# ---------------------------------------------------------------------------
# Repository-wide: no secrets in any test or doc file
# ---------------------------------------------------------------------------


class TestNoSecretsInRepository:
    def test_no_hardcoded_keys_in_test_files(self) -> None:
        tests_dir = Path(__file__).parent
        suspicious_patterns = ["Bearer sk-", " sk-ant-api03", " sk-proj-abc"]
        # Exclude this meta-test file since it documents the patterns being checked.
        this_file = Path(__file__).name
        for test_file in tests_dir.rglob("*.py"):
            if test_file.name == this_file:
                continue
            content = test_file.read_text(encoding="utf-8")
            for pattern in suspicious_patterns:
                assert pattern not in content, (
                    f"Test file {test_file.name} contains suspicious credential pattern: {pattern!r}"
                )

    def test_no_hardcoded_keys_in_docs(self) -> None:
        docs_dir = Path(__file__).parent.parent / "docs"
        suspicious_patterns = ["sk-ant-api", "sk-proj-", "Bearer sk-"]
        for doc_file in docs_dir.rglob("*.md"):
            content = doc_file.read_text(encoding="utf-8")
            for pattern in suspicious_patterns:
                assert pattern not in content, (
                    f"Doc file {doc_file.name} contains suspicious credential pattern: {pattern!r}"
                )
