"""Task evaluation fixture domain model for v2.5.0.

A TaskEvalFixture describes a replayable agent task: the repository state, the
user goal, what outcome is expected, and what safety boundaries must be upheld.
Fixtures are authored as JSON files and validated through Pydantic models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


CURRENT_FIXTURE_SCHEMA_VERSION = 1
SUPPORTED_FIXTURE_SCHEMA_VERSIONS = frozenset({1})


class RepoFixture(BaseModel):
    """Metadata describing the repository used for this eval.

    ``kind="local"`` points to an existing directory on disk.
    ``kind="inline"`` embeds file content directly in the fixture so the test
    runner can materialise the repo from scratch without external dependencies.
    """

    kind: Literal["local", "inline"] = "local"
    path: str | None = None
    files: dict[str, str] = Field(default_factory=dict)
    setup_commands: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_kind_constraints(self) -> "RepoFixture":
        if self.kind == "local" and not (self.path and self.path.strip()):
            raise ValueError("RepoFixture with kind='local' requires a non-empty 'path'.")
        if self.kind == "inline" and self.path:
            raise ValueError(
                "RepoFixture with kind='inline' must not set 'path'; use 'files' instead."
            )
        return self


class ExpectedOutcome(BaseModel):
    """What the agent is expected to produce.

    ``kind`` narrows the expected action class:
    - ``"patch"``   — the agent should propose a file diff.
    - ``"command"`` — the agent should run a shell command.
    - ``"any"``     — no restriction on action class.

    Additional constraints such as ``expected_output_contains`` and
    ``expected_diff_contains`` are evaluated by the replay runner (v2.5.1).
    """

    kind: Literal["patch", "command", "any"] = "any"
    expected_exit_code: int | None = None
    expected_output_contains: list[str] = Field(default_factory=list)
    expected_diff_contains: list[str] = Field(default_factory=list)
    expected_files_changed: list[str] = Field(default_factory=list)


class SafetyExpectations(BaseModel):
    """Safety behaviors the agent must uphold during this eval.

    All boolean flags default to the conservative (safe) value.
    ``forbidden_commands`` and ``forbidden_file_writes`` are checked by the
    replay runner to confirm the agent did not violate containment.
    ``expect_audit_events`` lists audit event types that must appear in the
    session's audit log after the eval completes.
    """

    expect_diff_review: bool = True
    expect_checkpoint: bool = True
    expect_approval_gate: bool = True
    allow_network: bool = False
    forbidden_commands: list[str] = Field(default_factory=list)
    forbidden_file_writes: list[str] = Field(default_factory=list)
    expect_audit_events: list[str] = Field(default_factory=list)

    @field_validator("forbidden_commands", "forbidden_file_writes", "expect_audit_events", mode="before")
    @classmethod
    def _must_be_list(cls, v: object) -> list:
        if not isinstance(v, list):
            raise ValueError(f"Expected a list, got {type(v).__name__!r}.")
        return v


class TaskEvalFixture(BaseModel):
    """A fully-specified, replayable task evaluation fixture.

    A fixture bundles everything the replay runner needs to reproduce an agent
    session from scratch: the repository state, the user's goal, what the agent
    should do, and which safety invariants must hold throughout.

    Required fields: ``name``, ``goal``, ``repo``, ``expected``, ``safety``.

    Serialisation round-trips through JSON without data loss:
    ``TaskEvalFixture.model_validate_json(fixture.model_dump_json())``.
    """

    schema_version: int = Field(default=CURRENT_FIXTURE_SCHEMA_VERSION)
    name: str
    goal: str
    repo: RepoFixture
    expected: ExpectedOutcome
    safety: SafetyExpectations
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    validation_commands: list[str] = Field(default_factory=list)
    expected_changed_files: list[str] = Field(default_factory=list)
    forbidden_changed_files: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _name_not_empty(cls, v: object) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("'name' must be a non-empty string.")
        return v

    @field_validator("goal", mode="before")
    @classmethod
    def _goal_not_empty(cls, v: object) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("'goal' must be a non-empty string.")
        return v

    @field_validator("schema_version", mode="before")
    @classmethod
    def _check_schema_version(cls, v: object) -> int:
        if not isinstance(v, int):
            raise ValueError(f"'schema_version' must be an integer, got {type(v).__name__!r}.")
        if v not in SUPPORTED_FIXTURE_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported fixture schema_version {v!r}. "
                f"Supported: {sorted(SUPPORTED_FIXTURE_SCHEMA_VERSIONS)}."
            )
        return v
