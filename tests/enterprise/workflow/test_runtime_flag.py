"""WORKFLOW_RUNTIME flag behavior."""

import pytest

from safecode.enterprise.workflow.exceptions import InvalidWorkflowRuntimeError
from safecode.enterprise.workflow.orchestrator import workflow_runtime


def test_invalid_workflow_runtime_fail_closed(monkeypatch):
    monkeypatch.setenv("WORKFLOW_RUNTIME", "cloud")
    with pytest.raises(InvalidWorkflowRuntimeError):
        workflow_runtime()


def test_default_workflow_runtime_is_local(monkeypatch):
    monkeypatch.delenv("WORKFLOW_RUNTIME", raising=False)
    assert workflow_runtime() == "local"
