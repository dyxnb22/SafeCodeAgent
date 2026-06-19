"""Operator Console v2.3 public contract snapshot helpers (v2.3.5-T1)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from safecode.enterprise.contracts.v2_1 import assert_snapshot_safe, _scrub
from safecode.enterprise.trace.render_markdown import SECTION_ORDER

_CONSOLE_ROOT = Path(__file__).resolve().parents[4] / "console"

CONSOLE_ROUTES: tuple[str, ...] = (
    "/login",
    "/t/{tenantId}/runs",
    "/t/{tenantId}/runs/{runId}",
    "/t/{tenantId}/runs/{runId}/evidence",
    "/t/{tenantId}/approvals",
    "/t/{tenantId}/eval",
)

CONSOLE_API_READ_PATHS: tuple[str, ...] = (
    "/v2/runs",
    "/v2/runs/{run_id}",
    "/v2/runs/{run_id}/timeline",
    "/v2/runs/{run_id}/trace",
    "/v2/approvals",
    "/v2/evidence/{run_id}",
    "/v2/eval/baselines",
)

CONSOLE_API_WRITE_PATHS: tuple[str, ...] = (
    "/v2/approvals/{approval_id}/decide",
)

CONSOLE_SOURCE_FILES: tuple[str, ...] = (
    "src/lib/api/client.ts",
    "src/lib/api/runs.ts",
    "src/lib/api/approvals.ts",
    "src/lib/api/evidence.ts",
    "src/lib/api/eval.ts",
    "src/lib/redaction/display.ts",
    "src/components/timeline/RunTimelineView.tsx",
    "src/components/timeline/TraceEventsView.tsx",
    "src/components/approvals/ApprovalList.tsx",
    "src/components/approvals/ApprovalDecideForm.tsx",
    "src/components/cost/CostSummary.tsx",
    "src/app/t/[tenantId]/runs/page.tsx",
    "src/app/t/[tenantId]/runs/[runId]/page.tsx",
    "src/app/t/[tenantId]/runs/[runId]/evidence/page.tsx",
    "src/app/t/[tenantId]/approvals/page.tsx",
    "src/app/t/[tenantId]/eval/page.tsx",
)


def _console_source_digest() -> str:
    parts: list[str] = []
    for relative in CONSOLE_SOURCE_FILES:
        path = _CONSOLE_ROOT / relative
        parts.append(f"{relative}:{path.stat().st_size}")
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _session_storage_key() -> str:
    session_module = _CONSOLE_ROOT / "src" / "lib" / "auth" / "session.ts"
    text = session_module.read_text(encoding="utf-8")
    match = re.search(r'SESSION_STORAGE_KEY = "([^"]+)"', text)
    if match is None:
        raise ValueError("console session storage key not found")
    return match.group(1)


def operator_console_v2_3_contract() -> dict[str, Any]:
    contract = {
        "contract": "OperatorConsoleV2_3",
        "contract_status": "supported",
        "console_routes": list(CONSOLE_ROUTES),
        "api_read_paths": list(CONSOLE_API_READ_PATHS),
        "api_write_paths": list(CONSOLE_API_WRITE_PATHS),
        "timeline_sections": list(SECTION_ORDER),
        "redaction_profile_default": "strict",
        "strict_hidden_fields": [
            "debug",
            "debug_payload",
            "raw_prompt",
            "raw_model_prompt",
            "file_content",
            "secret",
            "secrets",
        ],
        "session_storage_key": _session_storage_key(),
        "required_headers": {
            "read": ["Authorization", "tenant_id"],
            "write": ["Authorization", "X-Tenant-Id", "Idempotency-Key"],
        },
        "console_source_digest": _console_source_digest(),
        "console_source_files": list(CONSOLE_SOURCE_FILES),
        "vitest_suites": [
            "tests/auth.test.ts",
            "tests/runs.test.ts",
            "tests/approvals.test.ts",
            "tests/evidence-eval.test.ts",
        ],
        "offline_python_suites": [
            "tests/enterprise/console/test_console_auth_contract.py",
            "tests/enterprise/console/test_run_views_offline.py",
            "tests/enterprise/console/test_approval_flow_offline.py",
            "tests/enterprise/console/test_evidence_eval_readonly.py",
            "tests/enterprise/console/test_console_e2e_offline.py",
        ],
    }
    return _scrub(contract)


def assert_ui_snapshot_safe(contract: dict[str, Any]) -> None:
    assert_snapshot_safe(contract)
