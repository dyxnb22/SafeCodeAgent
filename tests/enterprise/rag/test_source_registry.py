"""Tests for SourceRegistry manifest loading (v1.1.1-T2)."""

from pathlib import Path

import pytest
import yaml

from safecode.enterprise.rag.exceptions import (
    DuplicateSourceIdError,
    ManifestValidationError,
    UnknownParserError,
    UnknownSourceTypeError,
)
from safecode.enterprise.rag.source_registry import SourceRegistry, SourceType

_ROOT = Path(__file__).resolve().parents[3]
_EXAMPLE_MANIFEST = _ROOT / "examples/enterprise/knowledge_sources.yaml"


def test_from_manifest_loads_example_with_four_entries():
    registry = SourceRegistry.from_manifest(_EXAMPLE_MANIFEST)
    assert len(registry.sources) == 4
    assert set(registry.sources) == {
        "policy-secure-sql-001",
        "code-app",
        "scanner-semgrep-baseline",
        "runbook-secret-leak",
    }
    policy = registry.get("policy-secure-sql-001")
    assert policy.source_type == SourceType.security_policy
    assert policy.parser == "markdown"
    assert policy.metadata["cwe"] == "CWE-89"


def test_duplicate_source_id_raises(tmp_path: Path):
    manifest = tmp_path / "dup.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {
                        "source_id": "a",
                        "source_type": "code",
                        "name": "A",
                        "path_or_uri": "a.py",
                        "owner": "dev",
                        "permission_scope": ["org"],
                        "refresh_cadence": "static",
                        "parser": "code",
                    },
                    {
                        "source_id": "a",
                        "source_type": "code",
                        "name": "B",
                        "path_or_uri": "b.py",
                        "owner": "dev",
                        "permission_scope": ["org"],
                        "refresh_cadence": "static",
                        "parser": "code",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DuplicateSourceIdError, match="duplicate source_id"):
        SourceRegistry.from_manifest(manifest)


def test_missing_required_key_reports_offending_key(tmp_path: Path):
    manifest = tmp_path / "missing.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {
                        "source_id": "a",
                        "source_type": "code",
                        "name": "A",
                        "path_or_uri": "a.py",
                        "owner": "dev",
                        "permission_scope": ["org"],
                        "refresh_cadence": "static",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ManifestValidationError, match="parser"):
        SourceRegistry.from_manifest(manifest)


def test_unknown_source_type_raises(tmp_path: Path):
    manifest = tmp_path / "bad-type.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {
                        "source_id": "a",
                        "source_type": "unknown_type",
                        "name": "A",
                        "path_or_uri": "a.py",
                        "owner": "dev",
                        "permission_scope": ["org"],
                        "refresh_cadence": "static",
                        "parser": "code",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(UnknownSourceTypeError, match="unknown source_type"):
        SourceRegistry.from_manifest(manifest)


def test_unknown_parser_raises(tmp_path: Path):
    manifest = tmp_path / "bad-parser.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {
                        "source_id": "a",
                        "source_type": "code",
                        "name": "A",
                        "path_or_uri": "a.py",
                        "owner": "dev",
                        "permission_scope": ["org"],
                        "refresh_cadence": "static",
                        "parser": "executable",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(UnknownParserError, match="unknown parser"):
        SourceRegistry.from_manifest(manifest)
