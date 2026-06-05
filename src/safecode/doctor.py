"""Environment checks for install and update polish."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from safecode import __version__
from safecode.core.diagnostic import Diagnostic, DiagnosticStatus

_PYPI_URL = "https://pypi.org/pypi/safecode/json"


def _fetch_latest_pypi_version(url: str = _PYPI_URL, *, timeout: int = 5) -> str | None:
    """Return the latest version string from PyPI, or None on any failure.

    Never raises. Sends no telemetry or identifying information beyond the
    standard HTTPS GET request User-Agent.
    """
    try:
        import json as _json
        from urllib.request import urlopen

        with urlopen(url, timeout=timeout) as resp:  # noqa: S310
            data = _json.loads(resp.read().decode("utf-8"))
            return data.get("info", {}).get("version")
    except Exception:
        return None


def _ver_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


@dataclass(frozen=True)
class DoctorCheck:
    """One doctor check (backward-compatible legacy shape)."""

    name: str
    passed: bool
    detail: str

    def to_diagnostic(self) -> Diagnostic:
        """Return the typed Diagnostic view of this check."""
        return Diagnostic.from_bool(self.name, self.passed, self.detail)


def _from_diagnostic(diagnostic: Diagnostic) -> DoctorCheck:
    """Render a Diagnostic as the legacy boolean DoctorCheck shape.

    SKIP and WARN both map to passed=False for the legacy view because the
    historical CLI surface uses a single passed bool. Internal callers should
    prefer `Doctor.run_diagnostics()` when they need PASS/FAIL/WARN/SKIP.
    """
    return DoctorCheck(
        name=diagnostic.name,
        passed=diagnostic.status is DiagnosticStatus.PASS,
        detail=diagnostic.message,
    )


class Doctor:
    """Check whether the local environment can run SafeCode."""

    def __init__(
        self,
        project_root: Path,
        *,
        fetch_latest_version: Callable[[], str | None] | None = None,
    ) -> None:
        self.project_root = project_root
        self._fetch_latest_version = fetch_latest_version or _fetch_latest_pypi_version

    def run_diagnostics(self, *, release: bool = False) -> list[Diagnostic]:
        """Return typed diagnostics (v2.8.x substrate).

        The Provider section is computed statically (config, env var presence,
        network policy text). It never makes any provider network request.
        Use ``sac smoke live-provider`` (v4.10.4) for an opt-in provider round-trip.
        """
        approval_dir = os.getenv("SAFECODE_APPROVAL_DIR")
        sandbox_dir = os.getenv("SAFECODE_SANDBOX_APPROVAL_DIR")
        diagnostics: list[Diagnostic] = [
            Diagnostic.from_bool(
                "python",
                sys.version_info >= (3, 11),
                sys.version.split()[0],
            ),
            Diagnostic.from_bool(
                "uv",
                shutil.which("uv") is not None,
                shutil.which("uv") or "not found",
            ),
            Diagnostic.from_bool(
                "project_root",
                self.project_root.exists(),
                str(self.project_root),
            ),
            Diagnostic.from_bool(
                "pyproject",
                (self.project_root / "pyproject.toml").exists(),
                "pyproject.toml",
            ),
            Diagnostic.from_bool(
                "config",
                (self.project_root / ".sac" / "config.toml").exists(),
                ".sac/config.toml",
            ),
            Diagnostic.from_bool(
                "sac_dir",
                (self.project_root / ".sac").exists(),
                ".sac",
            ),
            Diagnostic.from_bool(
                "approval_dir",
                bool(approval_dir),
                approval_dir or "not set",
            ),
            Diagnostic.from_bool(
                "sandbox_approval_dir",
                bool(sandbox_dir),
                sandbox_dir or "not set",
            ),
        ]
        diagnostics.append(self._last_session_cost_diagnostic())
        diagnostics.extend(self._sandbox_promotion_diagnostics())
        diagnostics.extend(self._project_tooling_diagnostics())
        diagnostics.extend(self._provider_diagnostics())
        diagnostics.append(self._update_check_diagnostic())
        if release:
            diagnostics.extend(self.run_release_diagnostics())
        return diagnostics

    def _project_tooling_diagnostics(self) -> list[Diagnostic]:
        """Report project command profile kinds as PASS/SKIP. (v4.2, EXPERIMENTAL)

        - PASS: kind detected and tool binary is available.
        - SKIP: kind not detected or tool binary is missing.
        Missing tool is SKIP, not FAIL, to avoid alarming users who don't use that tool.
        """
        from safecode.project.profile import load_profile

        profile = load_profile(self.project_root)
        if profile is None:
            return [Diagnostic(
                name="project_tooling",
                status=DiagnosticStatus.SKIP,
                message="no project profile; run 'sac profile detect'",
            )]

        diagnostics: list[Diagnostic] = []
        for kind in ("test", "lint", "typecheck", "build"):
            cmd = getattr(profile, kind)
            if cmd is None:
                diagnostics.append(Diagnostic(
                    name=f"project_tooling_{kind}",
                    status=DiagnosticStatus.SKIP,
                    message=f"{kind}: not detected",
                ))
            elif cmd.missing_dependency:
                binary = cmd.command[0] if cmd.command else "unknown"
                diagnostics.append(Diagnostic(
                    name=f"project_tooling_{kind}",
                    status=DiagnosticStatus.SKIP,
                    message=f"{kind}: tool missing ({binary}); install it or run 'sac profile set {kind} <cmd>'",
                ))
            else:
                argv_str = " ".join(cmd.command)
                diagnostics.append(Diagnostic(
                    name=f"project_tooling_{kind}",
                    status=DiagnosticStatus.PASS,
                    message=f"{kind}: {argv_str}",
                ))
        return diagnostics

    def _last_session_cost_diagnostic(self) -> "Diagnostic":
        """Return a PASS or SKIP diagnostic for the most recent session cost.json."""
        import glob
        pattern = str(self.project_root / ".sac" / "sessions" / "*" / "cost.json")
        cost_files = sorted(glob.glob(pattern))
        if not cost_files:
            return Diagnostic(
                name="last_session_cost",
                status=DiagnosticStatus.SKIP,
                message="no session cost data",
            )
        cost_file = cost_files[-1]
        try:
            import json as _json
            data = _json.loads(Path(cost_file).read_text(encoding="utf-8"))
            prompt = data.get("prompt_tokens", 0)
            completion = data.get("completion_tokens", 0)
            total = data.get("total_tokens", 0)
            msg = f"last_session: prompt={prompt} completion={completion} total={total}"
            return Diagnostic(name="last_session_cost", status=DiagnosticStatus.PASS, message=msg)
        except Exception:
            return Diagnostic(
                name="last_session_cost",
                status=DiagnosticStatus.SKIP,
                message="no session cost data",
            )

    def _provider_diagnostics(self) -> list[Diagnostic]:
        """Return static provider readiness diagnostics (v4.10.2, EXPERIMENTAL).

        No provider network request is made here. Key presence is checked via
        env var name only; the actual secret value is never logged or echoed.
        Network policy verdict is computed by inspecting the config, not by
        connecting to the provider host.
        """
        from urllib.parse import urlparse
        from safecode.config import SafeCodeConfig

        try:
            config = SafeCodeConfig.load(self.project_root)
        except Exception:
            return [Diagnostic(
                name="provider_config",
                status=DiagnosticStatus.SKIP,
                message="could not load config",
            )]

        provider = config.llm.provider
        diagnostics: list[Diagnostic] = []

        # 1. Provider name
        diagnostics.append(Diagnostic(
            name="provider_name",
            status=DiagnosticStatus.PASS,
            message=f"provider: {provider}",
        ))

        # 2. API key env presence (name only, never the value)
        key_env, key_source = self._resolve_provider_key_env(provider, config)
        if provider == "mock":
            diagnostics.append(Diagnostic(
                name="provider_api_key",
                status=DiagnosticStatus.PASS,
                message="mock provider: no API key required (deterministic mode)",
            ))
        elif key_source.startswith("env:"):
            diagnostics.append(Diagnostic(
                name="provider_api_key",
                status=DiagnosticStatus.PASS,
                message=f"API key env set: {key_env}",
            ))
        elif key_source == "user-config":
            diagnostics.append(Diagnostic(
                name="provider_api_key",
                status=DiagnosticStatus.PASS,
                message="API key configured in trusted user config",
            ))
        else:
            diagnostics.append(Diagnostic(
                name="provider_api_key",
                status=DiagnosticStatus.FAIL,
                message=f"API key env not set: {key_env} (also checked OPENAI_API_KEY, SAFECODE_LLM_API_KEY)",
            ))

        # 3. Base URL format check (parse only; no DNS or connect)
        base_url = config.llm.base_url
        try:
            parsed = urlparse(base_url)
            url_ok = bool(parsed.scheme in ("http", "https") and parsed.netloc)
        except Exception:
            url_ok = False
        diagnostics.append(Diagnostic(
            name="provider_base_url",
            status=DiagnosticStatus.PASS if url_ok else DiagnosticStatus.FAIL,
            message=f"base_url: {base_url}" if url_ok else f"base_url malformed: {base_url!r}",
        ))

        # 4. Model configured
        model = config.llm.model
        diagnostics.append(Diagnostic(
            name="provider_model",
            status=DiagnosticStatus.PASS,
            message=f"model: {model}",
        ))

        # 5. Static network policy verdict for the provider host (no network call)
        host = urlparse(base_url).hostname or ""
        if provider == "mock":
            net_status = DiagnosticStatus.PASS
            net_msg = "mock provider: no network call will be made"
        elif not config.sandbox.network_enabled:
            net_status = DiagnosticStatus.FAIL
            net_msg = (
                f"network disabled by policy; provider host '{host}' cannot be reached. "
                "Set network_enabled=true in config to allow real LLM calls."
            )
        elif config.sandbox.network_allowlist and host not in config.sandbox.network_allowlist:
            net_status = DiagnosticStatus.FAIL
            net_msg = (
                f"host '{host}' is not in the network allowlist "
                f"({config.sandbox.network_allowlist})"
            )
        else:
            net_status = DiagnosticStatus.PASS
            net_msg = f"network policy permits provider host: {host}"
        diagnostics.append(Diagnostic(
            name="provider_network_policy",
            status=net_status,
            message=net_msg,
        ))

        # 6. Last-session token/cost summary (SKIP if unavailable)
        # This is already reported by _last_session_cost_diagnostic(); refer there.
        diagnostics.append(Diagnostic(
            name="provider_last_session_cost",
            status=DiagnosticStatus.SKIP,
            message="see last_session_cost diagnostic above for token/cost summary",
        ))

        return diagnostics

    @staticmethod
    def _resolve_provider_key_env(provider: str, config) -> tuple[str, str]:
        """Return (env_var_name, source) for the provider's API key.

        Never returns the key value. Source is one of env:<name>,
        user-config, or missing.
        """
        if provider == "deepseek":
            from safecode.llm.deepseek import DEEPSEEK_PRESET
            env_name = DEEPSEEK_PRESET.api_key_env
        elif provider in ("openai", "openai-compatible"):
            env_name = "OPENAI_API_KEY"
        elif provider == "anthropic":
            env_name = "ANTHROPIC_API_KEY"
        else:
            env_name = "OPENAI_API_KEY"

        if os.getenv(env_name):
            return env_name, f"env:{env_name}"
        if env_name != "OPENAI_API_KEY" and os.getenv("OPENAI_API_KEY"):
            return env_name, "env:OPENAI_API_KEY"
        if os.getenv("SAFECODE_LLM_API_KEY"):
            return env_name, "env:SAFECODE_LLM_API_KEY"
        if getattr(config.llm, "api_key", None):
            return env_name, "user-config"
        return env_name, "missing"

    def _update_check_diagnostic(self) -> Diagnostic:
        """Check PyPI for a newer version. Skips silently on network failure.

        Controlled by SAFECODE_DOCTOR_UPDATE_CHECK (default 1; set to 0 to skip).
        """
        if os.getenv("SAFECODE_DOCTOR_UPDATE_CHECK", "1") == "0":
            return Diagnostic(
                name="update_check",
                status=DiagnosticStatus.SKIP,
                message="update check skipped (SAFECODE_DOCTOR_UPDATE_CHECK=0)",
            )
        latest = self._fetch_latest_version()
        if latest is None:
            return Diagnostic(
                name="update_check",
                status=DiagnosticStatus.SKIP,
                message="update check skipped (offline or network unavailable)",
            )
        if _ver_tuple(latest) > _ver_tuple(__version__):
            return Diagnostic(
                name="update_check",
                status=DiagnosticStatus.WARN,
                message=f"update available: {__version__} → {latest}",
            )
        return Diagnostic(
            name="update_check",
            status=DiagnosticStatus.PASS,
            message=f"up to date ({__version__})",
        )

    def _sandbox_promotion_diagnostics(self) -> list[Diagnostic]:
        """Report sandbox executor promotion state per backend."""
        from safecode.sandbox.executor_preflight import executor_env_var, has_executor_preflight_pass

        diagnostics: list[Diagnostic] = [
            Diagnostic(
                name="sandbox_promotion_noop",
                status=DiagnosticStatus.PASS,
                message="policy-gated default; no OS containment; Noop remains recommended default",
            )
        ]
        for backend in ("docker", "macos_seatbelt", "linux_bubblewrap"):
            env_var = executor_env_var(backend)
            passed = has_executor_preflight_pass(self.project_root, backend)
            opted_in = bool(env_var and os.getenv(env_var) == "1")
            if passed and opted_in:
                status = DiagnosticStatus.PASS
                message = f"opt-in real execution enabled ({env_var}=1, preflight passed)"
            elif passed:
                status = DiagnosticStatus.WARN
                message = f"preflight passed; set {env_var}=1 to opt in"
            else:
                status = DiagnosticStatus.SKIP
                message = f"preview; run sac sandbox executor-preflight {backend}"
            diagnostics.append(Diagnostic(name=f"sandbox_promotion_{backend}", status=status, message=message))
        return diagnostics

    def run(self, *, release: bool = False) -> list[DoctorCheck]:
        """Run environment checks, optionally including release diagnostics.

        Preserves the legacy DoctorCheck list shape used by `sac doctor`.
        """
        return [_from_diagnostic(d) for d in self.run_diagnostics(release=release)]

    def run_release_diagnostics(self) -> list[Diagnostic]:
        """Run release diagnostics without mutating the checkout."""
        from safecode.release.docs_guard import check_docs_finalized
        from safecode.release.preflight import run_release_preflight
        from safecode.release.version_guard import (
            check_tag_consistency,
            check_version_consistency,
        )

        version = check_version_consistency(
            pyproject_path=self.project_root / "pyproject.toml",
            runtime_version=__version__,
        )
        tag = check_tag_consistency(version.package_version, project_root=self.project_root)
        docs = check_docs_finalized(__version__, project_root=self.project_root)
        preflight = run_release_preflight(self.project_root)

        return [
            Diagnostic.from_bool("release_version", version.ok, version.message),
            Diagnostic.from_bool("release_tag", tag.consistent, tag.message),
            Diagnostic.from_bool(
                "release_docs",
                docs.ok,
                "docs finalized" if docs.ok else "; ".join(docs.issues),
            ),
            Diagnostic.from_bool(
                "release_preflight",
                preflight.ok,
                "preflight passed" if preflight.ok else "preflight needs attention",
            ),
        ]

    def run_release(self) -> list[DoctorCheck]:
        """Return release diagnostics in the legacy DoctorCheck shape."""
        return [_from_diagnostic(d) for d in self.run_release_diagnostics()]
