"""Typed pending-action objects for the agent loop.

The loop creates these objects to represent the decision made at each step.
The CLI rendering layer converts them to human-readable output.

Avoids boolean stringification (e.g. ``"true"``/``"false"`` strings) and
ad hoc dict construction for agent pending-action state.

All action types are frozen dataclasses. ``to_dict()`` produces the same
``dict[str, object]`` shape previously written directly into session state,
so the ``AgentSessionState.pending_action`` field remains backward-compatible.
``from_dict()`` reconstructs a typed object from a stored dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


@dataclass
class PendingAction:
    """Base for all typed pending-action objects."""

    type: str = ""

    def to_dict(self) -> dict[str, object]:
        raise NotImplementedError(f"{self.__class__.__name__} must implement to_dict()")


# ---------------------------------------------------------------------------
# Concrete action types
# ---------------------------------------------------------------------------


@dataclass
class StopForUserAction(PendingAction):
    """The agent stopped and is waiting for the user to provide guidance.

    Corresponds to ``AgentStopForUserResponse`` — no tool was routed.
    """

    type: str = field(default="stop_for_user", init=False)
    reason: str = ""
    message: str = ""
    requires_approval: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "reason": self.reason,
            "message": self.message,
            "requires_approval": self.requires_approval,
        }


@dataclass
class PatchPendingAction(PendingAction):
    """The agent proposed or is blocked on a patch that requires approval.

    Corresponds to the ``patch.propose`` route.
    """

    type: str = field(default="patch", init=False)
    route: str = "patch.propose"
    requires_approval: bool = True
    reason: str = ""
    patch_id: str = ""
    pending_patch_path: str = ""
    files: tuple[str, ...] = field(default_factory=tuple)
    target: str = ""

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "type": self.type,
            "route": self.route,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
        }
        if self.patch_id:
            d["patch_id"] = self.patch_id
        if self.pending_patch_path:
            d["pending_patch_path"] = self.pending_patch_path
        if self.files:
            d["files"] = list(self.files)
        if self.target:
            d["target"] = self.target
        return d


@dataclass
class ToolPendingAction(PendingAction):
    """A tool intent was routed but requires approval or is not executable now.

    Covers the generic routing path for sandbox, MCP write proposals, and
    other intent types that are not immediately executable.

    ``intent_fields`` carries the serialized ``ToolIntent`` fields so the
    stored dict remains backward-compatible with existing session readers.
    """

    route: str = ""
    executable_now: bool = False
    requires_approval: bool = False
    reason: str = ""
    tool_name: str = ""
    description: str = ""
    intent_fields: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            **self.intent_fields,
            "type": self.type,
            "route": self.route,
            "executable_now": self.executable_now,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
        }
        if self.tool_name:
            d["tool_name"] = self.tool_name
        if self.description:
            d["description"] = self.description
        return d


# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, type[PendingAction]] = {
    "stop_for_user": StopForUserAction,
    "patch": PatchPendingAction,
}


def pending_action_from_dict(data: dict[str, object]) -> PendingAction | None:
    """Reconstruct a typed ``PendingAction`` from a stored dict.

    Returns ``None`` when *data* is empty or the type is unrecognized.
    Unknown keys in *data* are ignored for forward compatibility.
    """
    if not data:
        return None
    action_type = str(data.get("type", ""))

    if action_type == "stop_for_user":
        return StopForUserAction(
            reason=str(data.get("reason", "")),
            message=str(data.get("message", "")),
            requires_approval=bool(data.get("requires_approval", True)),
        )

    if action_type == "patch":
        raw_files = data.get("files", [])
        files: tuple[str, ...] = tuple(str(f) for f in raw_files) if isinstance(raw_files, list) else ()
        return PatchPendingAction(
            route=str(data.get("route", "patch.propose")),
            requires_approval=bool(data.get("requires_approval", True)),
            reason=str(data.get("reason", "")),
            patch_id=str(data.get("patch_id", "")),
            pending_patch_path=str(data.get("pending_patch_path", "")),
            files=files,
            target=str(data.get("target", "")),
        )

    if action_type:
        return ToolPendingAction(
            type=action_type,
            route=str(data.get("route", "")),
            executable_now=bool(data.get("executable_now", False)),
            requires_approval=bool(data.get("requires_approval", False)),
            reason=str(data.get("reason", "")),
            tool_name=str(data.get("tool_name", "")),
            description=str(data.get("description", "")),
        )

    return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_pending_action(action: PendingAction) -> str:
    """Return a concise human-readable label for the given pending action."""
    if isinstance(action, StopForUserAction):
        label = "Stopped for user input"
        if action.message:
            label += f": {action.message}"
        if action.requires_approval:
            label += " [approval required]"
        return label

    if isinstance(action, PatchPendingAction):
        if action.patch_id:
            return f"Patch proposal {action.patch_id} awaiting approval ({action.reason})"
        return f"Patch action pending ({action.reason})"

    if isinstance(action, ToolPendingAction):
        parts = [f"Tool action '{action.type}'"]
        if action.route:
            parts.append(f"via {action.route}")
        if action.requires_approval:
            parts.append("[approval required]")
        elif not action.executable_now:
            parts.append("[not executable now]")
        return " ".join(parts)

    return f"Pending action: {action.type}"
