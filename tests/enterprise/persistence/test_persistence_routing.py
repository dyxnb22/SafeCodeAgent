"""Regression guard: production modules route persistence through backends."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTERPRISE_SRC = ROOT / "src" / "safecode" / "enterprise"

_ALLOWED_DIRECT_STORE_MODULES = {
    ENTERPRISE_SRC / "persistence" / "local_backend.py",
    ENTERPRISE_SRC / "persistence" / "strict_fake.py",
    ENTERPRISE_SRC / "approvals" / "store.py",
    ENTERPRISE_SRC / "workflow" / "checkpoint.py",
    ENTERPRISE_SRC / "evidence" / "export.py",
    ENTERPRISE_SRC / "audit" / "chain.py",
    ENTERPRISE_SRC / "trace" / "timeline.py",
    ENTERPRISE_SRC / "trace" / "session.py",
    ENTERPRISE_SRC / "trace" / "emitter.py",
}

_FORBIDDEN_IMPORTS: tuple[tuple[str, str], ...] = (
    ("safecode.enterprise.workflow.checkpoint", "load_checkpoint"),
    ("safecode.enterprise.workflow.checkpoint", "save_checkpoint"),
    ("safecode.enterprise.approvals.store", "consume_approved_request"),
    ("safecode.enterprise.approvals.store", "consume_grant"),
    ("safecode.enterprise.approvals.store", "save_grant"),
    ("safecode.enterprise.approvals.store", "save_request"),
    ("safecode.enterprise.approvals.store", "load_grant"),
    ("safecode.enterprise.approvals.store", "load_request"),
    ("safecode.enterprise.approvals.store", "decide_request"),
    ("safecode.enterprise.evidence.export", "export_run_evidence"),
)


def _module_imports(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.append((node.module, alias.name))
    return imports


def test_production_modules_do_not_bypass_persistence_backends() -> None:
    violations: list[str] = []
    for path in sorted(ENTERPRISE_SRC.rglob("*.py")):
        if path in _ALLOWED_DIRECT_STORE_MODULES:
            continue
        if "persistence/postgres" in path.as_posix():
            continue
        for module, symbol in _FORBIDDEN_IMPORTS:
            if (module, symbol) in _module_imports(path):
                violations.append(f"{path.relative_to(ROOT)} imports {module}.{symbol}")
    assert not violations, "direct persistence store imports found:\n" + "\n".join(violations)
