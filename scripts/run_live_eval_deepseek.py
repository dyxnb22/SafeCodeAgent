#!/usr/bin/env python3
"""Run live eval fixtures against DeepSeek v4-flash and write a snapshot.

Usage:
    SAFECODE_DEEPSEEK_API_KEY=sk-... python scripts/run_live_eval_deepseek.py
    python scripts/run_live_eval_deepseek.py  # reads key from env

Output:
    tests/snapshots/live_eval/deepseek-YYYYMMDD.json
    Console: pass rate, per-fixture results table
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

# Ensure src/ is on the path when running from project root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from safecode.eval.live import LiveEvalRunner, default_live_fixtures as default_fixtures  # noqa: E402


def main() -> None:
    api_key = os.environ.get("SAFECODE_DEEPSEEK_API_KEY", "")
    if not api_key:
        # Allow passing key as first CLI arg for convenience (not logged)
        api_key = sys.argv[1] if len(sys.argv) > 1 else ""
    if not api_key:
        print("ERROR: set SAFECODE_DEEPSEEK_API_KEY env var or pass key as first argument", file=sys.stderr)
        sys.exit(1)

    # Inject API key for the DeepSeek provider
    os.environ["SAFECODE_DEEPSEEK_API_KEY"] = api_key
    os.environ["SAFECODE_LIVE_TESTS"] = "1"

    # Configure the provider to use the key via env
    # The LLM factory reads DEEPSEEK_API_KEY or provider profile api_key
    os.environ["DEEPSEEK_API_KEY"] = api_key

    runner = LiveEvalRunner(provider="deepseek", model="deepseek-chat")
    fixtures = default_fixtures()

    print(f"Running {len(fixtures)} live eval fixtures against deepseek-chat ...")
    print()

    results = []
    t0 = time.perf_counter()
    for fixture in fixtures:
        print(f"  [{fixture.name}] running ...", end="", flush=True)
        result = runner.run_fixture(fixture)
        status = "PASS" if result.success else "FAIL"
        err_msg = f" ({result.error[:60]})" if result.error else ""
        print(f" {status}{err_msg}")
        results.append(result)

    elapsed = time.perf_counter() - t0
    passed = sum(1 for r in results if r.success)
    total = len(results)
    print()
    print(f"Results: {passed}/{total} passed  ({elapsed:.1f}s)")
    print()

    # Build snapshot
    snapshot = {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "date": date.today().isoformat(),
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "passed": passed,
        "total": total,
        "elapsed_seconds": round(elapsed, 1),
        "fixtures": [],
    }
    for r in results:
        snapshot["fixtures"].append({
            "name": r.fixture_name,
            "success": r.success,
            "turns_used": r.turns_used,
            "tool_calls": r.tool_calls,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "wall_seconds": round(r.wall_seconds, 2),
            "error": r.error,
            "failure_category": r.failure_category,
            "relevant_file_recall": r.relevant_file_recall,
            "relevant_file_precision": r.relevant_file_precision,
        })

    # Write snapshot
    snapshot_dir = Path(__file__).parent.parent / "tests" / "snapshots" / "live_eval"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    out_path = snapshot_dir / f"deepseek-{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Snapshot written: {out_path}")

    # Pretty table
    print()
    header = f"{'Fixture':<35} {'Status':<6} {'Turns':>5} {'Tokens':>7} {'Error'}"
    print(header)
    print("-" * len(header))
    for r in results:
        status = "PASS" if r.success else "FAIL"
        tokens = r.input_tokens + r.output_tokens
        err = (r.error or "")[:40]
        print(f"{r.fixture_name:<35} {status:<6} {r.turns_used:>5} {tokens:>7} {err}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
