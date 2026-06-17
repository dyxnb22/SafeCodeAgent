"""Terminal-only language service discovery and diagnostics."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from safecode.index.lsp_bridge import PyrightBridge


@dataclass(frozen=True)
class LanguageServiceStatus:
    language: str
    available: bool
    command: str
    reason: str = ""


@dataclass(frozen=True)
class LanguageDiagnostic:
    language: str
    file: str
    line: int
    message: str
    rule: str = ""
    severity: str = "error"


class LanguageServiceManager:
    """Detect lightweight language services and return normalized diagnostics."""

    def __init__(self, project_root: Path, *, timeout_seconds: int = 20) -> None:
        self.project_root = project_root.resolve()
        self.timeout_seconds = timeout_seconds

    def status(self) -> list[LanguageServiceStatus]:
        return [
            LanguageServiceStatus("python", PyrightBridge.is_available(), "pyright", "" if PyrightBridge.is_available() else "pyright not found"),
            LanguageServiceStatus("typescript", shutil.which("tsc") is not None, "tsc --noEmit", "" if shutil.which("tsc") else "tsc not found"),
            LanguageServiceStatus("go", shutil.which("go") is not None, "go test ./...", "" if shutil.which("go") else "go not found"),
            LanguageServiceStatus("rust", shutil.which("cargo") is not None, "cargo check --message-format=json", "" if shutil.which("cargo") else "cargo not found"),
        ]

    def diagnostics(self) -> list[LanguageDiagnostic]:
        diagnostics: list[LanguageDiagnostic] = []
        diagnostics.extend(self._python_diagnostics())
        diagnostics.extend(self._tsc_diagnostics())
        diagnostics.extend(self._go_diagnostics())
        diagnostics.extend(self._rust_diagnostics())
        return diagnostics

    def _python_diagnostics(self) -> list[LanguageDiagnostic]:
        if not PyrightBridge.is_available():
            return []
        return [
            LanguageDiagnostic(
                language="python",
                file=str(item.file),
                line=item.line,
                message=item.message,
                rule=item.rule or "",
                severity=item.severity or "error",
            )
            for item in PyrightBridge.get_diagnostics(self.project_root)
        ]

    def _tsc_diagnostics(self) -> list[LanguageDiagnostic]:
        if shutil.which("tsc") is None or not self._has_any("tsconfig.json", "package.json"):
            return []
        result = self._run(["tsc", "--noEmit", "--pretty", "false"])
        if result is None or result.returncode == 0:
            return []
        diagnostics: list[LanguageDiagnostic] = []
        for line in (result.stdout + "\n" + result.stderr).splitlines():
            # src/foo.ts(12,3): error TS2322: ...
            if "): error TS" not in line or "(" not in line:
                continue
            path_part, rest = line.split("(", 1)
            loc, msg = rest.split("):", 1) if "):" in rest else ("1,1", rest)
            line_no = _safe_int(loc.split(",", 1)[0], 1)
            rule = ""
            msg = msg.strip()
            if msg.startswith("error "):
                first, _, tail = msg.partition(":")
                rule = first.replace("error", "").strip()
                msg = tail.strip() or msg
            diagnostics.append(LanguageDiagnostic("typescript", _rel(self.project_root, path_part), line_no, msg, rule))
        return diagnostics

    def _go_diagnostics(self) -> list[LanguageDiagnostic]:
        if shutil.which("go") is None or not self._has_any("go.mod"):
            return []
        result = self._run(["go", "test", "./..."])
        if result is None or result.returncode == 0:
            return []
        diagnostics: list[LanguageDiagnostic] = []
        for line in (result.stdout + "\n" + result.stderr).splitlines():
            # ./foo.go:12:3: message
            parts = line.split(":", 3)
            if len(parts) < 4 or not parts[0].endswith(".go"):
                continue
            diagnostics.append(LanguageDiagnostic("go", _rel(self.project_root, parts[0]), _safe_int(parts[1], 1), parts[3].strip()))
        return diagnostics

    def _rust_diagnostics(self) -> list[LanguageDiagnostic]:
        if shutil.which("cargo") is None or not self._has_any("Cargo.toml"):
            return []
        result = self._run(["cargo", "check", "--message-format=json"])
        if result is None or result.returncode == 0:
            return []
        diagnostics: list[LanguageDiagnostic] = []
        for line in result.stdout.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("reason") != "compiler-message":
                continue
            message = payload.get("message") or {}
            spans = message.get("spans") or []
            span = next((s for s in spans if s.get("file_name")), {})
            diagnostics.append(
                LanguageDiagnostic(
                    "rust",
                    _rel(self.project_root, str(span.get("file_name") or "Cargo.toml")),
                    int(span.get("line_start") or 1),
                    str(message.get("message") or ""),
                    str(message.get("code", {}).get("code") or ""),
                    str(message.get("level") or "error"),
                )
            )
        return diagnostics

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _has_any(self, *names: str) -> bool:
        return any((self.project_root / name).exists() for name in names)


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def _rel(root: Path, value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return value
