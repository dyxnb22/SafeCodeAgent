"""Internal tool metadata registry."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    """Description of a SafeCode internal tool."""

    name: str
    description: str
    risk: str


class ToolRegistry:
    """List built-in runtime tools."""

    def list(self) -> list[ToolSpec]:
        """Return built-in tools."""
        return [
            ToolSpec("context.collect", "Collect bounded project context.", "low"),
            ToolSpec("patch.propose", "Create a pending patch proposal.", "medium"),
            ToolSpec("patch.apply", "Apply a reviewed patch after checkpoint.", "medium"),
            ToolSpec("shell.run", "Run a classified shell command.", "medium"),
            ToolSpec("checkpoint.rollback", "Restore a previous checkpoint.", "medium"),
        ]
