"""Live GitHub PR connector tests with recorded httpx transport (v2.2.2-T1)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from safecode.enterprise.connectors.github_app import assert_output_safe
from safecode.enterprise.connectors.github_pr import (
    ConnectorError,
    GitHubPullRequestClient,
    PullRequestConnectorSpec,
    fetch_pr,
)
from safecode.enterprise.connectors.models import PullRequestEvidence

_ROOT = Path(__file__).resolve().parent
_LIVE_FIXTURES = _ROOT / "fixtures" / "live"
_OWNER = "acme"
_REPO = "webapp"
_PR_NUMBER = 42
_INSTALLATION_ID = "987654"
_ACCESS_TOKEN = SecretStr("ghs_recorded_installation_token_for_pr_fetch_tests")
_TOKEN_RE = re.compile(r"gh[ps]_[A-Za-z0-9]{20,}")


def _load_live_fixture(name: str) -> object:
    return json.loads((_LIVE_FIXTURES / name).read_text(encoding="utf-8"))


def _recorded_transport(
    *,
    pull_payload: object | None = None,
    files_payload: object | None = None,
    files_link: str | None = None,
    pull_status: int = 200,
    files_status: int = 200,
    pull_body: str | None = None,
    files_body: str | None = None,
) -> httpx.MockTransport:
    pull = _load_live_fixture("pull.json") if pull_payload is None else pull_payload
    files = _load_live_fixture("files_page1.json") if files_payload is None else files_payload

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith(f"/repos/{_OWNER}/{_REPO}/pulls/{_PR_NUMBER}/files"):
            headers = {}
            if files_link:
                headers["Link"] = files_link
            if files_body is not None:
                return httpx.Response(files_status, text=files_body, headers=headers)
            return httpx.Response(files_status, json=files, headers=headers)
        if path.endswith(f"/repos/{_OWNER}/{_REPO}/pulls/{_PR_NUMBER}"):
            if pull_body is not None:
                return httpx.Response(pull_status, text=pull_body)
            return httpx.Response(pull_status, json=pull)
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler)


def _live_spec(**overrides: object) -> PullRequestConnectorSpec:
    base = {
        "mode": "live",
        "owner": _OWNER,
        "repo": _REPO,
        "pr_number": _PR_NUMBER,
        "installation_id": _INSTALLATION_ID,
        "api_base_url": "https://api.github.com",
    }
    base.update(overrides)
    return PullRequestConnectorSpec.model_validate(base)


def _fixture_evidence() -> PullRequestEvidence:
    return fetch_pr(
        PullRequestConnectorSpec(
            mode="fixture",
            fixture_path="fixtures/pr_sample.json",
            project_root=str(_ROOT),
        )
    )


def test_live_fetch_with_recorded_transport_matches_fixture_equivalence():
    transport = _recorded_transport()
    live = fetch_pr(
        _live_spec(),
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )
    fixture = _fixture_evidence()
    assert live.model_dump() == fixture.model_dump()


def test_live_client_repr_and_errors_redact_tokens():
    client = GitHubPullRequestClient.from_spec(
        _live_spec(),
        access_token=_ACCESS_TOKEN,
        transport=_recorded_transport(),
    )
    rendered = repr(client)
    assert _ACCESS_TOKEN.get_secret_value() not in rendered
    assert "**********" in rendered


def test_live_fetch_without_transport_uses_client_directly():
    client = GitHubPullRequestClient.from_spec(
        _live_spec(),
        access_token=_ACCESS_TOKEN,
        transport=_recorded_transport(),
    )
    evidence = client.fetch(_PR_NUMBER)
    assert evidence.title.startswith("Fix SQL")
    blob = evidence.model_dump_json()
    assert _TOKEN_RE.search(blob) is None
    assert_output_safe(blob, context="pull request evidence")


def test_malformed_pull_response_fails_closed():
    transport = _recorded_transport(pull_body="{not-json")
    with pytest.raises(ConnectorError, match="malformed GitHub pull response"):
        fetch_pr(_live_spec(), access_token=_ACCESS_TOKEN, transport=transport)


def test_malformed_files_response_fails_closed():
    transport = _recorded_transport(files_body="{not-json")
    with pytest.raises(ConnectorError, match="malformed GitHub files response"):
        fetch_pr(_live_spec(), access_token=_ACCESS_TOKEN, transport=transport)


def test_redirect_response_fails_closed():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.example/phish"})

    with pytest.raises(ConnectorError, match="redirect responses are not allowed"):
        fetch_pr(
            _live_spec(),
            access_token=_ACCESS_TOKEN,
            transport=httpx.MockTransport(handler),
        )


def test_rate_limit_fails_closed():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limit exceeded"})

    with pytest.raises(ConnectorError, match="rate limit exhausted"):
        fetch_pr(
            _live_spec(),
            access_token=_ACCESS_TOKEN,
            transport=httpx.MockTransport(handler),
        )


def test_installation_mismatch_fails_closed():
    transport = _recorded_transport(pull_status=404, pull_payload={"message": "Not Found"})
    with pytest.raises(ConnectorError, match="installation mismatch"):
        fetch_pr(_live_spec(), access_token=_ACCESS_TOKEN, transport=transport)


def test_oversized_response_fails_closed():
    transport = _recorded_transport(
        pull_status=200,
        pull_body="x" * (1_048_576 + 1),
    )
    with pytest.raises(ConnectorError, match="exceeds size limit"):
        fetch_pr(_live_spec(), access_token=_ACCESS_TOKEN, transport=transport)


def test_recorded_pagination_normalizes_to_fixture_equivalent_evidence():
    files_fixture = _load_live_fixture("files_page1.json")
    assert isinstance(files_fixture, list)
    page_one = [files_fixture[0]]
    page_two = [files_fixture[1]]
    link = (
        f'<https://api.github.com/repos/{_OWNER}/{_REPO}/pulls/{_PR_NUMBER}/files?page=2>; '
        'rel="next"'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/files"):
            if "page=2" in str(request.url):
                return httpx.Response(200, json=page_two)
            return httpx.Response(200, json=page_one, headers={"Link": link})
        if path.endswith(f"/pulls/{_PR_NUMBER}"):
            return httpx.Response(200, json=_load_live_fixture("pull.json"))
        return httpx.Response(404, json={"message": "Not Found"})

    live = fetch_pr(
        _live_spec(),
        access_token=_ACCESS_TOKEN,
        transport=httpx.MockTransport(handler),
    )
    fixture = _fixture_evidence()
    assert live.model_dump() == fixture.model_dump()


def test_live_mode_requires_owner_repo_and_token():
    with pytest.raises(ConnectorError, match="owner and repo"):
        GitHubPullRequestClient.from_spec(
            _live_spec(owner="", repo=""),
            access_token=_ACCESS_TOKEN,
            transport=_recorded_transport(),
        )
    with pytest.raises(ConnectorError, match="access_token is required"):
        fetch_pr(_live_spec(), transport=_recorded_transport())
