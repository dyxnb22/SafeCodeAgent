"""Tests for v2.6.21 final release signoff."""

from safecode.release.check import ReleaseCheckResult
from safecode.release.docs_guard import DocsGuardResult
from safecode.release.metadata import ReleaseMetadata
from safecode.release.preflight import ReleasePreflightResult
from safecode.release.signoff import ReleaseSignoffResult, render_release_signoff
from safecode.release.smoke import SmokeTestCase, SmokeTestResult
from safecode.release.version_guard import TagConsistencyResult


def _release_check(tag: str = "v2.6.21", ok: bool = True) -> ReleaseCheckResult:
    return ReleaseCheckResult(
        package_version="2.6.21",
        runtime_version="2.6.21",
        version_consistent=ok,
        version_message="OK" if ok else "mismatch",
        tree_clean=True,
        tree_detail="working tree clean",
        tag_result=TagConsistencyResult(
            tag=tag,
            tag_available=tag is not None,
            consistent=tag == "v2.6.21",
            package_version="2.6.21",
            message="OK" if tag == "v2.6.21" else "bad tag",
        ),
    )


def _preflight(ok: bool = True) -> ReleasePreflightResult:
    return ReleasePreflightResult(
        release_check=_release_check(ok=ok),
        smoke=SmokeTestResult([SmokeTestCase("import_version", ok, "ok")]),
        metadata=ReleaseMetadata(
            package_version="2.6.21",
            runtime_version="2.6.21",
            latest_git_tag="v2.6.21",
            version_note_files=["v2.6.21-final-signoff.md"],
            has_version_note=ok,
            skill_mentions_version=ok,
            issues=[] if ok else ["metadata issue"],
        ),
        docs=DocsGuardResult(ok, ok, ok, [] if ok else ["docs issue"]),
    )


def test_signoff_ok_requires_exact_matching_tag() -> None:
    result = ReleaseSignoffResult("2.6.21", "v2.6.21", _release_check(), _preflight())
    assert result.ok is True


def test_signoff_fails_on_wrong_tag() -> None:
    result = ReleaseSignoffResult("2.6.21", "v2.6.20", _release_check("v2.6.20"), _preflight())
    assert result.ok is False


def test_render_signoff_pass() -> None:
    result = ReleaseSignoffResult("2.6.21", "v2.6.21", _release_check(), _preflight())
    text = render_release_signoff(result)
    assert "Status: PASS" in text
    assert "v2.6 final signoff passed" in text


def test_render_signoff_failure_next_steps() -> None:
    result = ReleaseSignoffResult("2.6.21", "v2.6.20", _release_check("v2.6.20"), _preflight())
    text = render_release_signoff(result)
    assert "Status: FAIL" in text
    assert "Next steps:" in text
