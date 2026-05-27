"""Patch data models."""

from pathlib import Path

from pydantic import BaseModel


class PatchBlock(BaseModel):
    """One file operation inside a patch proposal."""

    operation: str
    file_path: Path
    search: str | None = None
    replace: str | None = None
    content: str | None = None


class PatchProposal(BaseModel):
    """A complete patch proposal saved before apply."""

    id: str
    task: str
    blocks: list[PatchBlock]
    created_at: str
    model: str
    status: str = "pending"
