"""GitHub PR connector evidence tests (v1.3.2-T2)."""

from pathlib import Path

from safecode.enterprise.connectors.github_pr import PullRequestConnectorSpec, fetch_pr

_ROOT = Path(__file__).resolve().parent


def test_fetch_pr_from_fixture_has_stable_hunk_ids():
    spec = PullRequestConnectorSpec(
        mode="fixture",
        fixture_path="fixtures/pr_sample.json",
        project_root=str(_ROOT),
    )
    evidence = fetch_pr(spec)
    assert evidence.title.startswith("Fix SQL")
    assert len(evidence.files) == 2
    assert len(evidence.hunks) == 1
    assert evidence.hunks[0].hunk_id.startswith("hunk-")
    again = fetch_pr(spec)
    assert again.hunks[0].hunk_id == evidence.hunks[0].hunk_id
