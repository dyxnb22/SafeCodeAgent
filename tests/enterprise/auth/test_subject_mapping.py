"""Subject mapping tests (v2.1.6-T2)."""

from __future__ import annotations

import pytest

from safecode.enterprise.auth.oidc import TokenClaims
from safecode.enterprise.auth.subject import SubjectMappingError, map_claims_to_subject
from safecode.enterprise.rbac.models import Role


def _claims(**overrides) -> TokenClaims:
    base = {
        "sub": "user:reviewer",
        "iss": "https://issuer.example",
        "aud": "safecode-enterprise",
        "exp": 4_000_000_000,
        "tenant_id": "tenant-a",
        "roles": ["maintainer"],
    }
    base.update(overrides)
    return TokenClaims.model_validate(base)


def test_known_claim_maps_to_expected_role() -> None:
    subject = map_claims_to_subject(_claims(roles=["security_reviewer"]))

    assert subject.actor_id == "user:reviewer"
    assert subject.tenant_id == "tenant-a"
    assert subject.roles == (Role.security_reviewer,)
    assert {"security", "appsec", "secops"}.issubset(subject.permission_scopes)


def test_unknown_role_defaults_to_viewer() -> None:
    subject = map_claims_to_subject(_claims(roles=["unknown-role"]))

    assert subject.roles == (Role.viewer,)


def test_missing_role_claim_defaults_to_viewer() -> None:
    subject = map_claims_to_subject(_claims(roles=None, role=None))

    assert subject.roles == (Role.viewer,)


def test_missing_tenant_claim_fails_closed() -> None:
    with pytest.raises(SubjectMappingError, match="tenant_id"):
        map_claims_to_subject(_claims(tenant_id=None))


@pytest.mark.parametrize("tenant_id", ["../tenant-b", "tenant/a", "tenant:b"])
def test_path_or_namespace_tenant_claim_fails_closed(tenant_id: str) -> None:
    with pytest.raises(SubjectMappingError, match="tenant_id claim is invalid"):
        map_claims_to_subject(_claims(tenant_id=tenant_id))
