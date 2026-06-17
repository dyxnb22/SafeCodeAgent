#!/usr/bin/env python3
"""Model comparison sweep for SafeCode live eval fixtures.

Runs the same fixture set against multiple providers and writes a comparison
JSON to tests/snapshots/live_eval/comparison_<date>.json.

Usage:
    SAFECODE_LIVE_TESTS=1 python scripts/eval_compare.py --providers anthropic,deepseek
    SAFECODE_LIVE_TESTS=1 python scripts/eval_compare.py --providers anthropic --model claude-sonnet-4-6

The script is read-only with respect to the codebase: it writes only to
tests/snapshots/live_eval/ and stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from safecode.eval.live import (
    LiveEvalResult,
    LiveEvalRunner,
    default_live_fixtures,
    render_live_summary,
)

_SNAPSHOT_DIR = Path(__file__).parent.parent / "tests" / "snapshots" / "live_eval"


def _pass_rate(results: list[LiveEvalResult]) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r.success) / len(results)


def _render_comparison(runs: dict[str, list[LiveEvalResult]]) -> str:
    lines = ["SafeCode Live Eval — Model Comparison", "=" * 50]
    fixture_names = []
    for results in runs.values():
        fixture_names = [r.fixture_name for r in results]
        break

    # Header row
    providers = list(runs.keys())
    lines.append(f"{'Fixture':<30}  " + "  ".join(f"{p[:12]:<12}" for p in providers))
    lines.append("-" * (30 + 14 * len(providers)))

    for name in fixture_names:
        row = f"{name:<30}  "
        for provider in providers:
            result = next((r for r in runs[provider] if r.fixture_name == name), None)
            if result is None:
                row += f"{'N/A':<12}  "
            else:
                status = "PASS" if result.success else "FAIL"
                row += f"{status:<12}  "
        lines.append(row)

    lines.append("")
    lines.append("Pass rates:")
    for provider, results in runs.items():
        rate = _pass_rate(results)
        passed = sum(1 for r in results if r.success)
        lines.append(f"  {provider}: {passed}/{len(results)} ({rate:.0%})")

    return "\n".join(lines)


def _snapshot_results(path: Path) -> dict[str, bool]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", data if isinstance(data, list) else [])
    if isinstance(results, dict):
        results = results.get("results", [])
    mapping: dict[str, bool] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        name = item.get("fixture_name") or item.get("name")
        if name:
            mapping[str(name)] = bool(item.get("success", False))
    return mapping


def _compare_snapshot_files(before: Path, after: Path) -> str:
    old = _snapshot_results(before)
    new = _snapshot_results(after)
    names = sorted(set(old) | set(new))
    lines = ["SafeCode Eval Snapshot Diff", "=" * 32]
    lines.append(f"Before: {before}")
    lines.append(f"After : {after}")
    lines.append("")
    lines.append(f"{'Fixture':<40}  {'Before':<8}  {'After':<8}  Change")
    lines.append("-" * 72)
    regressions = 0
    improvements = 0
    for name in names:
        old_val = old.get(name)
        new_val = new.get(name)
        old_s = "N/A" if old_val is None else ("PASS" if old_val else "FAIL")
        new_s = "N/A" if new_val is None else ("PASS" if new_val else "FAIL")
        if old_val is True and new_val is False:
            change = "REGRESSION"
            regressions += 1
        elif old_val is False and new_val is True:
            change = "IMPROVED"
            improvements += 1
        elif old_val is None:
            change = "ADDED"
        elif new_val is None:
            change = "REMOVED"
        else:
            change = "same"
        lines.append(f"{name:<40}  {old_s:<8}  {new_s:<8}  {change}")
    old_rate = sum(1 for value in old.values() if value) / len(old) if old else 0.0
    new_rate = sum(1 for value in new.values() if value) / len(new) if new else 0.0
    lines.append("")
    lines.append(f"Pass rate: {old_rate:.0%} -> {new_rate:.0%}")
    lines.append(f"Improvements: {improvements}; regressions: {regressions}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="SafeCode live eval model comparison sweep")
    parser.add_argument("snapshots", nargs="*", help="Optional: compare two snapshot JSON files.")
    parser.add_argument(
        "--providers",
        default="anthropic",
        help="Comma-separated list of provider names (e.g. anthropic,deepseek,openai)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name to pass to all providers (optional)",
    )
    parser.add_argument(
        "--fixtures",
        default=None,
        help="Comma-separated fixture names to run (default: all)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: tests/snapshots/live_eval/comparison_<date>.json)",
    )
    args = parser.parse_args()

    if args.snapshots:
        if len(args.snapshots) != 2:
            print("Snapshot compare mode expects exactly two JSON files.", file=sys.stderr)
            return 2
        print(_compare_snapshot_files(Path(args.snapshots[0]), Path(args.snapshots[1])))
        return 0

    if not os.environ.get("SAFECODE_LIVE_TESTS"):
        print("SAFECODE_LIVE_TESTS is not set. Set it to 1 to enable live provider calls.")
        print("Dry-run: would run the following providers:", args.providers)
        return 0

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    all_fixtures = default_live_fixtures()

    if args.fixtures:
        selected = set(args.fixtures.split(","))
        all_fixtures = [f for f in all_fixtures if f.name in selected]
        if not all_fixtures:
            print(f"No fixtures matched: {args.fixtures}", file=sys.stderr)
            return 1

    print(f"Running {len(all_fixtures)} fixture(s) against {len(providers)} provider(s)...\n")

    runs: dict[str, list[LiveEvalResult]] = {}
    for provider in providers:
        label = f"{provider}/{args.model}" if args.model else provider
        print(f"--- {label} ---")
        runner = LiveEvalRunner(provider=provider, model=args.model)
        results = runner.run_all(all_fixtures)
        runs[label] = results
        print(render_live_summary(results))
        print()

    print(_render_comparison(runs))

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else _SNAPSHOT_DIR / f"comparison_{date_str}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": {
            label: [r.as_dict() for r in results]
            for label, results in runs.items()
        },
        "pass_rates": {
            label: round(_pass_rate(results), 3)
            for label, results in runs.items()
        },
    }
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nReport saved to: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
