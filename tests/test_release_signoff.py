"""Tests for final release signoff."""

from safecode.release.check import ReleaseCheckResult
from safecode.release.docs_guard import DocsGuardResult
from safecode.release.metadata import ReleaseMetadata
from safecode.release.preflight import ReleasePreflightResult
from safecode.release.signoff import ReleaseSignoffResult, render_release_signoff
from safecode.release.smoke import SmokeTestCase, SmokeTestResult
from safecode.release.version_guard import TagConsistencyResult

VERSION = "9.8.7"
TAG = f"v{VERSION}"
WRONG_TAG = "v9.8.6"


def _release_check(tag: str = TAG, ok: bool = True) -> ReleaseCheckResult:
    return ReleaseCheckResult(
        package_version=VERSION,
        runtime_version=VERSION,
        version_consistent=ok,
        version_message="OK" if ok else "mismatch",
        tree_clean=True,
        tree_detail="working tree clean",
        tag_result=TagConsistencyResult(
            tag=tag,
            tag_available=tag is not None,
            consistent=tag == TAG,
            package_version=VERSION,
            message="OK" if tag == TAG else "bad tag",
        ),
    )


def _preflight(ok: bool = True) -> ReleasePreflightResult:
    return ReleasePreflightResult(
        release_check=_release_check(ok=ok),
        smoke=SmokeTestResult([SmokeTestCase("import_version", ok, "ok")]),
        metadata=ReleaseMetadata(
            package_version=VERSION,
            runtime_version=VERSION,
            latest_git_tag=TAG,
            version_note_files=[f"{TAG}-final-signoff.md"],
            has_version_note=ok,
            skill_mentions_version=ok,
            issues=[] if ok else ["metadata issue"],
        ),
        docs=DocsGuardResult(ok, ok, ok, [] if ok else ["docs issue"]),
    )


def test_signoff_ok_requires_exact_matching_tag() -> None:
    result = ReleaseSignoffResult(VERSION, TAG, _release_check(), _preflight())
    assert result.ok is True


def test_signoff_fails_on_wrong_tag() -> None:
    result = ReleaseSignoffResult(VERSION, WRONG_TAG, _release_check(WRONG_TAG), _preflight())
    assert result.ok is False


def test_render_signoff_pass() -> None:
    result = ReleaseSignoffResult(VERSION, TAG, _release_check(), _preflight())
    text = render_release_signoff(result)
    assert "Status: PASS" in text
    assert f"Release signoff passed for v{VERSION}" in text


def test_render_signoff_failure_next_steps() -> None:
    result = ReleaseSignoffResult(VERSION, WRONG_TAG, _release_check(WRONG_TAG), _preflight())
    text = render_release_signoff(result)
    assert "Status: FAIL" in text
    assert f"Release signoff failed for v{VERSION}" in text
    assert "Next steps:" in text
