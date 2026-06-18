"""Unified shell session manifest.

The manifest is the stable identity shared by the shell, conversation buffer,
and agent loop. Legacy stores remain readable while new interactive sessions
use ``.sac/sessions/<id>/manifest.json``.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from safecode.utils.time import utc_now_iso


class ShellSessionManifest(BaseModel):
    session_id: str
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    mode: str = "build"
    status: str = "active"
    agent_session_id: str | None = None
    task_id: str | None = None
    turns: int = 0
    interrupted: bool = False
    title: str = "New conversation"
    last_response: str = ""
    files_changed: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    cost_input_tokens: int = 0
    cost_output_tokens: int = 0
    cost_cache_read_tokens: int = 0
    payload_version: int = 1


class ShellSessionManager:
    """Create, resume, and atomically update unified shell manifests."""

    def __init__(self, sac_dir: Path) -> None:
        self.sac_dir = sac_dir
        self.sessions_dir = sac_dir / "sessions"
        self.latest_path = self.sessions_dir / "latest"

    def open(self, session_id: str | None = None, *, mode: str = "build") -> ShellSessionManifest:
        selected = session_id or self.latest_id()
        manifest = self.load(selected) if selected else None
        if manifest is None:
            manifest = ShellSessionManifest(session_id=selected or uuid.uuid4().hex, mode=mode)
        else:
            manifest = manifest.model_copy(update={"status": "active", "mode": mode, "interrupted": False})
        return self.save(manifest)

    def create(self, *, mode: str = "build") -> ShellSessionManifest:
        return self.save(ShellSessionManifest(session_id=uuid.uuid4().hex, mode=mode))

    def list(self, *, limit: int | None = None) -> list[ShellSessionManifest]:
        manifests: list[ShellSessionManifest] = []
        paths = sorted(
            self.sessions_dir.glob("*/manifest.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ) if self.sessions_dir.exists() else []
        for path in paths:
            manifest = self.load(path.parent.name)
            if manifest is not None:
                manifests.append(manifest)
        return manifests[:limit] if limit is not None else manifests

    def rename(self, session_id: str, title: str) -> ShellSessionManifest:
        manifest = self.load(session_id)
        if manifest is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        cleaned = " ".join(title.split()).strip()[:80]
        if not cleaned:
            raise ValueError("Session title cannot be empty.")
        return self.save(manifest.model_copy(update={"title": cleaned}))

    @staticmethod
    def title_from_goal(goal: str) -> str:
        cleaned = " ".join(goal.split()).strip()
        return cleaned[:60] + ("..." if len(cleaned) > 60 else "") or "New conversation"

    def load(self, session_id: str | None) -> ShellSessionManifest | None:
        if not session_id:
            return None
        path = self._path(session_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("payload_version", 1) > 1:
                return None
            return ShellSessionManifest.model_validate(data)
        except (OSError, json.JSONDecodeError, ValidationError, TypeError):
            return None

    def save(self, manifest: ShellSessionManifest) -> ShellSessionManifest:
        updated = manifest.model_copy(update={"updated_at": utc_now_iso()})
        path = self._path(updated.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, updated.model_dump_json(indent=2) + "\n")
        self._atomic_write(self.latest_path, updated.session_id + "\n")
        return updated

    def latest_id(self) -> str | None:
        try:
            value = self.latest_path.read_text(encoding="utf-8").strip()
            return value or None
        except OSError:
            manifests = sorted(
                self.sessions_dir.glob("*/manifest.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            ) if self.sessions_dir.exists() else []
            return manifests[0].parent.name if manifests else None

    def _path(self, session_id: str) -> Path:
        if not session_id or session_id in {".", ".."} or "/" in session_id or "\\" in session_id:
            raise ValueError("Invalid shell session id.")
        return self.sessions_dir / session_id / "manifest.json"

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
