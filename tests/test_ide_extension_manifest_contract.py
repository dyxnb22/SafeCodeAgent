"""Tests for v3.9.2 T-3.9.2-A: VS Code extension manifest contract parity.

Verifies that vscode-extension/package.json and src/safecode/ide/manifest.py
declare the same commands, the same JSON-RPC launch command, the same contract
version, and the same supported methods. No Node tooling required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_VSCODE_PKG = Path(__file__).parent.parent / "vscode-extension" / "package.json"
_MANIFEST_PY = Path(__file__).parent.parent / "src" / "safecode" / "ide" / "manifest.py"

_JSONRPC_CONTRACT_VERSION = "1"
_LAUNCH_COMMAND = ["sac", "api", "jsonrpc"]
_SUPPORTED_METHODS = {"ask", "report", "edit", "apply"}

# Commands that must exist in vscode-extension/package.json contributes.commands
_REQUIRED_VSCODE_COMMANDS = {
    "safecode.ask",
    "safecode.edit",
    "safecode.apply",
    "safecode.rollback",
    "safecode.openDiff",
    "safecode.apiJsonrpc",
}

# Commands documented in src/safecode/ide/manifest.py
_REQUIRED_MANIFEST_COMMANDS = {
    "safecode.ask",
    "safecode.edit",
    "safecode.apply",
    "safecode.rollback",
    "safecode.openDiff",
    "safecode.apiJsonrpc",
}


def _load_pkg() -> dict:
    return json.loads(_VSCODE_PKG.read_text(encoding="utf-8"))


def _load_manifest_text() -> str:
    return _MANIFEST_PY.read_text(encoding="utf-8")


def _load_manifest_data() -> dict:
    from safecode.ide.manifest import render_manifest
    return json.loads(render_manifest())


# ── package.json existence and shape ─────────────────────────────────────────


class TestVSCodePackageJson:
    def test_package_json_exists(self):
        assert _VSCODE_PKG.exists(), "vscode-extension/package.json not found"

    def test_package_json_valid_json(self):
        pkg = _load_pkg()
        assert isinstance(pkg, dict)

    def test_name_field(self):
        pkg = _load_pkg()
        assert "name" in pkg
        assert "safecode" in pkg["name"].lower()

    def test_version_present(self):
        pkg = _load_pkg()
        assert "version" in pkg

    def test_engines_vscode_present(self):
        pkg = _load_pkg()
        assert "engines" in pkg
        assert "vscode" in pkg["engines"]

    def test_main_entrypoint_present(self):
        pkg = _load_pkg()
        assert "main" in pkg

    def test_contributes_commands_present(self):
        pkg = _load_pkg()
        assert "contributes" in pkg
        assert "commands" in pkg["contributes"]
        assert len(pkg["contributes"]["commands"]) > 0


# ── Command parity ────────────────────────────────────────────────────────────


class TestCommandParity:
    def test_vscode_commands_include_required(self):
        pkg = _load_pkg()
        cmd_ids = {c["command"] for c in pkg["contributes"]["commands"]}
        for required in _REQUIRED_VSCODE_COMMANDS:
            assert required in cmd_ids, f"Missing command in package.json: {required}"

    def test_manifest_py_commands_include_required(self):
        data = _load_manifest_data()
        cmd_ids = {c["id"] for c in data["commands"]}
        for required in _REQUIRED_MANIFEST_COMMANDS:
            assert required in cmd_ids, f"Missing command in ide/manifest.py: {required}"

    def test_ask_command_in_both(self):
        pkg = _load_pkg()
        pkg_ids = {c["command"] for c in pkg["contributes"]["commands"]}
        manifest = _load_manifest_data()
        manifest_ids = {c["id"] for c in manifest["commands"]}
        assert "safecode.ask" in pkg_ids
        assert "safecode.ask" in manifest_ids

    def test_apply_command_in_both(self):
        pkg = _load_pkg()
        pkg_ids = {c["command"] for c in pkg["contributes"]["commands"]}
        manifest = _load_manifest_data()
        manifest_ids = {c["id"] for c in manifest["commands"]}
        assert "safecode.apply" in pkg_ids
        assert "safecode.apply" in manifest_ids


# ── JSON-RPC transport parity ─────────────────────────────────────────────────


class TestJSONRPCTransportParity:
    def test_manifest_launch_command(self):
        data = _load_manifest_data()
        launch = data["jsonrpc_transport"]["launch_command"]
        assert launch == _LAUNCH_COMMAND

    def test_manifest_contract_version(self):
        data = _load_manifest_data()
        assert data["jsonrpc_transport"]["contract_version"] == _JSONRPC_CONTRACT_VERSION

    def test_manifest_supported_methods(self):
        data = _load_manifest_data()
        methods = set(data["jsonrpc_transport"]["supported_methods"])
        assert methods >= _SUPPORTED_METHODS

    def test_package_json_notes_launch_command(self):
        pkg = _load_pkg()
        notes = pkg.get("_safecodeNotes", {})
        assert "launchCommand" in notes
        assert notes["launchCommand"] == _LAUNCH_COMMAND

    def test_package_json_notes_contract_version(self):
        pkg = _load_pkg()
        notes = pkg.get("_safecodeNotes", {})
        assert notes.get("jsonrpcContractVersion") == _JSONRPC_CONTRACT_VERSION


# ── Safety and telemetry invariants ──────────────────────────────────────────


class TestSafetyInvariants:
    def test_no_telemetry_claim_in_package(self):
        pkg = _load_pkg()
        notes = pkg.get("_safecodeNotes", {})
        telemetry = notes.get("telemetry", "")
        assert "none" in telemetry.lower() or telemetry == "" or "no" in telemetry.lower()

    def test_approval_gate_documented_in_package(self):
        pkg = _load_pkg()
        notes = pkg.get("_safecodeNotes", {})
        approval = notes.get("approvalGate", "")
        assert approval != "", "approvalGate should be documented in package.json _safecodeNotes"

    def test_extension_ts_has_approval_modal(self):
        ext_ts = (
            Path(__file__).parent.parent / "vscode-extension" / "src" / "extension.ts"
        ).read_text(encoding="utf-8")
        assert "modal" in ext_ts.lower() or "confirm" in ext_ts.lower()

    def test_extension_ts_no_telemetry_imports(self):
        ext_ts = (
            Path(__file__).parent.parent / "vscode-extension" / "src" / "extension.ts"
        ).read_text(encoding="utf-8")
        # Must not import any telemetry module
        assert 'import * as telemetry' not in ext_ts
        assert "require('telemetry')" not in ext_ts
        assert 'from "telemetry"' not in ext_ts
        assert "@vscode/extension-telemetry" not in ext_ts

    def test_manifest_experimental_label(self):
        data = _load_manifest_data()
        transport_note = data["jsonrpc_transport"].get("note", "")
        assert "EXPERIMENTAL" in transport_note or "experimental" in transport_note.lower()


# ── VSIX build status ─────────────────────────────────────────────────────────


class TestVSIXBuildStatus:
    def test_build_script_present_in_package(self):
        """package.json must have a 'build' script defined."""
        pkg = _load_pkg()
        assert "scripts" in pkg
        assert "build" in pkg["scripts"]

    def test_package_script_present(self):
        """package.json must have a 'package' script for VSIX generation."""
        pkg = _load_pkg()
        assert "package" in pkg["scripts"]

    def test_typescript_src_exists(self):
        ext_ts = Path(__file__).parent.parent / "vscode-extension" / "src" / "extension.ts"
        assert ext_ts.exists(), "vscode-extension/src/extension.ts not found"

    def test_tsconfig_exists(self):
        tsconfig = Path(__file__).parent.parent / "vscode-extension" / "tsconfig.json"
        assert tsconfig.exists(), "vscode-extension/tsconfig.json not found"
