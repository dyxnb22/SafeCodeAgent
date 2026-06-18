"""pip-audit normalization tests."""

from safecode.enterprise.scanners.pip_audit import normalize_pip_audit


def test_pip_audit_maps_cve_package_and_severity():
    payload = [
        {
            "name": "requests",
            "version": "2.25.0",
            "vulns": [
                {
                    "id": "CVE-2024-1234",
                    "severity": "high",
                    "description": "Advisory details only.",
                    "fix_versions": ["2.32.0"],
                }
            ],
        }
    ]
    findings = normalize_pip_audit(payload)
    assert findings[0].cve == "CVE-2024-1234"
    assert findings[0].source == "pip_audit"
    assert "requests" in findings[0].title
