#!/usr/bin/env python3
"""Re-run fixtures that failed in a previous snapshot and merge results.

Usage:
    DEEPSEEK_API_KEY=sk-... python scripts/retry_failed_fixtures.py tests/snapshots/live_eval/deepseek-2026-06-17.json

Reads the snapshot, picks all failed fixtures, re-runs them, and writes an
updated snapshot with the new results replacing the old ones.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from safecode.eval.live import LiveEvalRunner, default_live_fixtures  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: retry_failed_fixtures.py <snapshot.json> [api_key]", file=sys.stderr)
        sys.exit(1)

    snapshot_path = Path(sys.argv[1])
    if not snapshot_path.exists():
        print(f"Snapshot not found: {snapshot_path}", file=sys.stderr)
        sys.exit(1)

    api_key = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: set DEEPSEEK_API_KEY or pass key as second argument", file=sys.stderr)
        sys.exit(1)

    os.environ["DEEPSEEK_API_KEY"] = api_key
    os.environ["SAFECODE_LIVE_TESTS"] = "1"

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    failed_names = {f["name"] for f in snapshot["fixtures"] if not f["success"]}

    if not failed_names:
        print("No failed fixtures in snapshot. Nothing to retry.")
        sys.exit(0)

    print(f"Retrying {len(failed_names)} failed fixture(s): {', '.join(sorted(failed_names))}")
    print()

    all_fixtures = {f.name: f for f in default_live_fixtures()}
    to_retry = [all_fixtures[name] for name in failed_names if name in all_fixtures]
    missing = failed_names - set(all_fixtures)
    if missing:
        print(f"WARNING: fixtures not found in default set: {missing}", file=sys.stderr)

    runner = LiveEvalRunner(provider="deepseek", model="deepseek-chat")
    new_results: dict[str, dict] = {}
    for fixture in to_retry:
        print(f"  [{fixture.name}] running ...", end="", flush=True)
        result = runner.run_fixture(fixture)
        status = "PASS" if result.success else "FAIL"
        err_msg = f" ({result.error[:80]})" if result.error else ""
        print(f" {status}{err_msg}")
        new_results[fixture.name] = {
            "name": result.fixture_name,
            "success": result.success,
            "turns_used": result.turns_used,
            "tool_calls": result.tool_calls,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "wall_seconds": round(result.wall_seconds, 2),
            "error": result.error,
            "failure_category": result.failure_category,
            "relevant_file_recall": result.relevant_file_recall,
            "relevant_file_precision": result.relevant_file_precision,
        }

    # Merge: replace failed entries with retry results
    updated_fixtures = []
    for f in snapshot["fixtures"]:
        if f["name"] in new_results:
            updated_fixtures.append(new_results[f["name"]])
        else:
            updated_fixtures.append(f)

    passed = sum(1 for f in updated_fixtures if f["success"])
    total = len(updated_fixtures)
    snapshot["fixtures"] = updated_fixtures
    snapshot["passed"] = passed
    snapshot["total"] = total
    snapshot["pass_rate"] = round(passed / total, 4) if total else 0.0
    snapshot["retry_note"] = f"Retried {len(to_retry)} fixture(s) after initial run."

    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print()
    print(f"Updated snapshot: {snapshot_path}")
    print(f"Final results: {passed}/{total} passed  (pass_rate={snapshot['pass_rate']})")

    # Summary table
    print()
    still_failed = [f for f in updated_fixtures if not f["success"]]
    if still_failed:
        print("Still failing:")
        for f in still_failed:
            print(f"  [{f['name']}] {f.get('error', '')[:80]}")
    else:
        print("All fixtures now passing.")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
