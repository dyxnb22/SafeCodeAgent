"""Enterprise tool specification registry."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.approvals.store import Action


class ToolCategory(str, Enum):
    read_local = "read_local"
    write_local = "write_local"
    command = "command"
    read_network = "read_network"
    write_network = "write_network"
    admin = "admin"


class ApprovalTier(str, Enum):
    AUTO = "AUTO"
    CONFIRM = "CONFIRM"
    GATE = "GATE"
    BLOCK = "BLOCK"


class ToolSpec(BaseModel):
    """Locally authoritative tool metadata for governance decisions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    category: ToolCategory
    approval_tier: ApprovalTier
    action: Action
    requires_network: bool = False
    requires_write: bool = False
    capabilities: list[str] = Field(default_factory=list)
    audit_event: str = "tool.executed"


class ToolRegistryError(Exception):
    """Base registry error."""


class ToolNotRegisteredError(ToolRegistryError):
    """Raised when execution is requested for an unknown tool."""


class ToolRegistryConflictError(ToolRegistryError):
    """Raised when registering a duplicate or conflicting tool spec."""


class ToolRegistry:
    """In-memory registry of enterprise-approved tool specifications."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ToolRegistryConflictError(f"tool already registered: {spec.name}")
        self._specs[spec.name] = spec

    def lookup(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def require(self, name: str) -> ToolSpec:
        spec = self.lookup(name)
        if spec is None:
            raise ToolNotRegisteredError(f"tool not registered: {name}")
        return spec

    def list_specs(self) -> list[ToolSpec]:
        return [self._specs[name] for name in sorted(self._specs)]
