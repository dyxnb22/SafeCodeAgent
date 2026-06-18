"""LangGraph topology contract tests."""

import importlib
import importlib.util

import pytest

from safecode.enterprise.workflow.graph import CONDITIONAL_EDGES, EXPECTED_WORKFLOW_NODES
from safecode.enterprise.workflow.nodes.registry import WORKFLOW_NODE_ORDER


def test_graph_module_imports_without_eager_langgraph():
    graph = importlib.import_module("safecode.enterprise.workflow.graph")
    assert graph.EXPECTED_WORKFLOW_NODES
    assert graph.CONDITIONAL_EDGES


def test_langgraph_runtime_raises_when_missing(monkeypatch):
    monkeypatch.setenv("WORKFLOW_RUNTIME", "langgraph")
    graph = importlib.import_module("safecode.enterprise.workflow.graph")
    from safecode.enterprise.workflow.exceptions import LangGraphUnavailableError

    if importlib.util.find_spec("langgraph") is not None:
        pytest.skip("langgraph already installed in test environment")
    with pytest.raises(LangGraphUnavailableError):
        graph.build_state_graph()


def test_expected_workflow_nodes_include_all_local_nodes():
    for node in WORKFLOW_NODE_ORDER:
        assert node in EXPECTED_WORKFLOW_NODES


def test_expected_workflow_nodes_include_repair_or_blocker():
    assert "repair_or_blocker" in EXPECTED_WORKFLOW_NODES


def test_conditional_edge_keys():
    assert set(CONDITIONAL_EDGES) == {"missing_evidence", "high_risk", "validation_failed"}


@pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="langgraph optional extra not installed",
)
def test_state_graph_node_set():
    from safecode.enterprise.workflow.graph import build_state_graph

    compiled = build_state_graph()
    nodes = set(compiled.get_graph().nodes)
    assert set(EXPECTED_WORKFLOW_NODES).issubset(nodes)
