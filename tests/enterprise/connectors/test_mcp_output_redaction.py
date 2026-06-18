"""MCP output redaction and bounds."""

from safecode.enterprise.connectors.mcp_adapter import redact_and_bound_output


def test_mcp_output_redaction_and_4kb_cap():
    secret = "ghp_" + ("a" * 40)
    bounded = redact_and_bound_output(secret + ("x" * 5000))
    assert "ghp_" not in bounded
    assert len(bounded) <= 4096
