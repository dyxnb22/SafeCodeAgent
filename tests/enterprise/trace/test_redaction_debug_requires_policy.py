"""Debug trace profile policy gate tests."""

import pytest

from safecode.enterprise.policy.resolver import resolve_policy
from safecode.enterprise.trace.redaction import DebugTraceNotAllowed, resolve_export_profile


def test_debug_profile_requires_policy_unlock(tmp_path):
    snapshot = resolve_policy(tmp_path)
    with pytest.raises(DebugTraceNotAllowed):
        resolve_export_profile(snapshot, requested="debug")
