"""SecurityFinding model tests (v1.3.4-T1)."""

from safecode.enterprise.scanners.models import Location, SecurityFinding
from safecode.enterprise.workflow.types import RiskTier


def test_security_finding_fields():
    finding = SecurityFinding(
        finding_id="finding-abc",
        source="semgrep",
        rule_id="python.lang.security.audit",
        severity=RiskTier.high,
        title="SQL injection",
        description="Use parameterized queries.",
        location=Location(path="app.py", start_line=1, end_line=2, snippet_hash="sha256:abc"),
    )
    assert finding.source == "semgrep"
