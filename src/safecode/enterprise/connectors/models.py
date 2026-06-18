"""Connector evidence models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PullRequestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    status: Literal["added", "modified", "removed", "renamed"] = "modified"


class DiffHunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hunk_id: str
    file_path: str
    start_line: int
    end_line: int
    patch: str = ""


class PullRequestEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    title: str
    body: str
    author: str
    base_ref: str
    head_ref: str
    labels: list[str] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)
    files: list[PullRequestFile] = Field(default_factory=list)
    hunks: list[DiffHunk] = Field(default_factory=list)


class IssueEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    issue_id: str
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)
    severity: Literal["unknown", "low", "medium", "high", "critical"] = "unknown"
    reporter: str = ""
    linked_prs: list[str] = Field(default_factory=list)
