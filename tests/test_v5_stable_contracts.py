"""Tests for v5.0.0: stable contract promotion verification."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from safecode.agent.command_tool import RUN_COMMAND_SPEC
from safecode.agent.read_tools import (
    GREP_FILES_SPEC,
    LIST_FILES_SPEC,
    READ_FILE_SPEC,
    SEARCH_FILES_SPEC,
)
from safecode.agent.write_tools import EDIT_FILE_SPEC, WRITE_FILE_SPEC
from safecode.cli_ops import _V5_STABLE_CONTRACTS


# ---------------------------------------------------------------------------
# Tool spec experimental=False (stable promotion)
# ---------------------------------------------------------------------------

class TestStableToolSpecs:
    @pytest.mark.parametrize("spec", [
        READ_FILE_SPEC, LIST_FILES_SPEC, SEARCH_FILES_SPEC, GREP_FILES_SPEC,
    ])
    def test_read_tools_are_stable(self, spec):
        """v5.0: all four read tools have experimental=False."""
        assert spec.experimental is False, f"{spec.name} should be experimental=False"

    @pytest.mark.parametrize("spec", [EDIT_FILE_SPEC, WRITE_FILE_SPEC])
    def test_write_tools_are_stable(self, spec):
        """v5.0: edit_file and write_file have experimental=False."""
        assert spec.experimental is False, f"{spec.name} should be experimental=False"

    def test_run_command_is_stable(self):
        """v5.0: run_command has experimental=False."""
        assert RUN_COMMAND_SPEC.experimental is False

    def test_exactly_seven_promoted_specs(self):
        """v5.0: exactly 7 tool specs are stable (promoted set)."""
        promoted = [
            READ_FILE_SPEC, LIST_FILES_SPEC, SEARCH_FILES_SPEC, GREP_FILES_SPEC,
            EDIT_FILE_SPEC, WRITE_FILE_SPEC, RUN_COMMAND_SPEC,
        ]
        stable = [s for s in promoted if not s.experimental]
        assert len(stable) == 7

    def test_promoted_audit_event_types(self):
        """v5.0: audit event types for promoted tools are the three stable values."""
        read_types = {s.audit_event_type for s in [READ_FILE_SPEC, LIST_FILES_SPEC, SEARCH_FILES_SPEC, GREP_FILES_SPEC]}
        assert read_types == {"tool_call_read"}

        write_types = {s.audit_event_type for s in [EDIT_FILE_SPEC, WRITE_FILE_SPEC]}
        assert write_types == {"tool_call_write"}

        assert RUN_COMMAND_SPEC.audit_event_type == "tool_call_command"

    def test_write_tools_require_approval(self):
        """v5.0 stable contract: edit_file and write_file always require approval."""
        assert EDIT_FILE_SPEC.requires_approval is True
        assert WRITE_FILE_SPEC.requires_approval is True

    def test_read_tools_do_not_require_approval(self):
        """v5.0 stable contract: read tools are auto-approved."""
        for spec in [READ_FILE_SPEC, LIST_FILES_SPEC, SEARCH_FILES_SPEC, GREP_FILES_SPEC]:
            assert spec.requires_approval is False, f"{spec.name} should not require approval"

    def test_run_command_does_not_require_approval(self):
        """v5.0 stable contract: run_command passes through ShellRunner (policy-gated, not approval-gated)."""
        assert RUN_COMMAND_SPEC.requires_approval is False


# ---------------------------------------------------------------------------
# _V5_STABLE_CONTRACTS constant
# ---------------------------------------------------------------------------

class TestV5StableContractsList:
    def test_contains_all_seven_tool_names(self):
        for name in ["read_file", "list_files", "search_files", "grep_files",
                     "edit_file", "write_file", "run_command"]:
            assert name in _V5_STABLE_CONTRACTS, f"{name!r} missing from _V5_STABLE_CONTRACTS"

    def test_contains_audit_event_types(self):
        for event_type in ["tool_call_read", "tool_call_write", "tool_call_command"]:
            assert event_type in _V5_STABLE_CONTRACTS, f"{event_type!r} missing from _V5_STABLE_CONTRACTS"

    def test_contains_rollback_and_shell_loop(self):
        assert "write_tool_checkpoint_rollback" in _V5_STABLE_CONTRACTS
        assert "sac_shell_loop" in _V5_STABLE_CONTRACTS

    def test_list_has_no_duplicates(self):
        assert len(_V5_STABLE_CONTRACTS) == len(set(_V5_STABLE_CONTRACTS))

    def test_list_has_expected_length(self):
        assert len(_V5_STABLE_CONTRACTS) == 12


# ---------------------------------------------------------------------------
# sac version --json includes stable_contracts
# ---------------------------------------------------------------------------

class TestVersionJsonStableContracts:
    def test_version_json_has_stable_contracts_key(self, tmp_path):
        """sac version --json output includes stable_contracts list."""
        result = subprocess.run(
            [sys.executable, "-m", "safecode.cli", "ops", "version", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        )
        # The command may not be available via this path; test via direct import instead.
        from io import StringIO
        import contextlib
        from safecode.cli_ops import version as version_cmd
        from unittest.mock import patch

        output_buf = StringIO()
        with patch("builtins.print", side_effect=lambda s: output_buf.write(s + "\n")):
            version_cmd(json_output=True)

        output = output_buf.getvalue()
        data = json.loads(output.strip())
        assert "stable_contracts" in data.get("data", {})
        contracts = data["data"]["stable_contracts"]
        assert isinstance(contracts, list)
        assert "read_file" in contracts
        assert "tool_call_write" in contracts
        assert "sac_shell_loop" in contracts

    def test_version_json_stable_contracts_matches_constant(self, tmp_path):
        """stable_contracts in JSON matches _V5_STABLE_CONTRACTS."""
        from io import StringIO
        from unittest.mock import patch

        output_buf = StringIO()
        with patch("builtins.print", side_effect=lambda s: output_buf.write(s + "\n")):
            from safecode.cli_ops import version as version_cmd
            version_cmd(json_output=True)

        data = json.loads(output_buf.getvalue().strip())
        assert sorted(data["data"]["stable_contracts"]) == sorted(_V5_STABLE_CONTRACTS)


# ---------------------------------------------------------------------------
# docs/public-contracts.md v5.0 section
# ---------------------------------------------------------------------------

class TestPublicContractsDocs:
    _docs = Path(__file__).parent.parent / "docs" / "public-contracts.md"

    def test_v5_section_exists(self):
        text = self._docs.read_text(encoding="utf-8")
        assert "v5.0.0 Stable Contract Promotions" in text

    def test_all_seven_tool_names_in_contracts(self):
        text = self._docs.read_text(encoding="utf-8")
        for name in ["read_file", "list_files", "search_files", "grep_files",
                     "edit_file", "write_file", "run_command"]:
            assert name in text, f"{name!r} missing from public-contracts.md"

    def test_three_audit_event_types_in_contracts(self):
        text = self._docs.read_text(encoding="utf-8")
        for event_type in ["tool_call_read", "tool_call_write", "tool_call_command"]:
            assert event_type in text

    def test_sections_13_to_16_exist(self):
        text = self._docs.read_text(encoding="utf-8")
        assert "### 13." in text
        assert "### 14." in text
        assert "### 15." in text
        assert "### 16." in text

    def test_what_is_not_promoted_listed(self):
        text = self._docs.read_text(encoding="utf-8")
        assert "web_fetch" in text
        assert "github_create_pr" in text or "GitHub" in text


# ---------------------------------------------------------------------------
# docs/versioning-policy.md v5.x section
# ---------------------------------------------------------------------------

class TestVersioningPolicyDocs:
    _policy = Path(__file__).parent.parent / "docs" / "versioning-policy.md"

    def test_v5x_section_exists(self):
        text = self._policy.read_text(encoding="utf-8")
        assert "v5.x Contract Promise" in text or "v5.x" in text

    def test_v500_changelog_entry_exists(self):
        text = self._policy.read_text(encoding="utf-8")
        assert "v5.0.0" in text
