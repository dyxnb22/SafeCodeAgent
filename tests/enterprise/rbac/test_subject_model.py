"""RBAC subject model tests."""

from safecode.enterprise.rbac.models import RBACSubject, Role


def test_roles_enum_values():
    assert Role.viewer.value == "viewer"
    assert Role.developer.value == "developer"
    assert Role.security_reviewer.value == "security_reviewer"
    assert Role.maintainer.value == "maintainer"
    assert Role.platform_admin.value == "platform_admin"


def test_subject_defaults_tenant_to_local():
    subject = RBACSubject(actor_id="user:test")
    assert subject.tenant_id == "local"
    assert subject.roles == (Role.developer,)


def test_subject_is_immutable():
    subject = RBACSubject(actor_id="user:test", roles=(Role.maintainer,))
    assert subject.highest_role() == Role.maintainer
