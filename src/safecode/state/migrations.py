"""Schema-version migration for persisted SafeCode state records (v2.3.7).

Rules:
- Missing schema_version field  →  treated as version 1 (backward compat).
- schema_version in SUPPORTED  →  returned with the field normalised to int.
- schema_version not in SUPPORTED  →  SchemaVersionError raised (fail closed).
"""

from __future__ import annotations

CURRENT_SCHEMA_VERSION: int = 1
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


class SchemaVersionError(ValueError):
    """Raised when a persisted record carries an unsupported future schema_version."""


def migrate_record(data: dict, record_type: str = "record") -> dict:
    """Validate and normalise the schema_version field of a raw JSON dict.

    The function checks both ``schema_version`` (the current canonical key) and
    ``_schema_version`` (an underscore-prefixed variant that may appear in records
    written by other tools) so that either spelling is accepted as input.

    Returns a new dict with ``schema_version`` set to the normalised integer.

    Raises:
        SchemaVersionError: if the version is a supported integer that exceeds the
            current maximum (i.e., a record from a future SafeCode Agent release).
    """
    # Accept either spelling from the raw dict; fall back to 1 when absent.
    raw = data.get("schema_version", data.get("_schema_version", 1))
    try:
        version = int(raw)
    except (TypeError, ValueError):
        version = 1
    if version < 1:
        version = 1

    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaVersionError(
            f"{record_type} has unsupported schema_version={version}. "
            f"Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}. "
            "Upgrade SafeCode Agent to read this record."
        )

    # Return a new dict with the normalised field present.
    return {**data, "schema_version": version}
