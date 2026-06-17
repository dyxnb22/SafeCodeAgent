"""Tiered approval classifier for patch proposals (v6.8.0).

Replaces the binary approve/gate model with three levels:

  auto    — single file, non-logic change (docs, comments, whitespace, config
             values). Applies immediately without stopping; checkpoint + audit
             are still written so rollback is always available.

  confirm — default. Multi-file or logic-modifying change. Stops for user diff
             review before apply (existing behaviour).

  gate    — delete operations, create of new files outside the existing tree,
             or any other high-sensitivity change. Always requires explicit
             approval even in auto_edit mode.

Safety invariants:
  - ``auto`` never bypasses checkpoint or audit — it only skips the
    interactive diff pause.
  - ``gate`` is never overridden by config or auto_edit flags.
  - Unknown / ambiguous proposals default to ``confirm``.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from safecode.patch.models import PatchBlock, PatchProposal
from safecode.config import ApprovalConfig, SafeCodeConfig


class ApprovalTier(str, Enum):
    AUTO = "auto"
    CONFIRM = "confirm"
    GATE = "gate"


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

# File extensions that are *almost always* non-logic changes when only
# comments / docstrings are touched.
_DOCS_EXTENSIONS = frozenset({
    ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".cfg",
    ".ini", ".env.example",
})

# Extensions that always require CONFIRM even on small edits
# (binary, generated, lock files)
_ALWAYS_CONFIRM_EXTENSIONS = frozenset({
    ".lock", ".sum", ".jar", ".whl", ".so", ".dylib", ".dll", ".exe",
})

# Patterns suggesting the content is logic (executable code change).
# Checks lines that are NOT pure comments/docstrings.
_LOGIC_PATTERNS = re.compile(
    r"^\s*(?!#|//|\s*\*|\"\"\"|\s*\'\'\'|\s*$)"
    r".*\b(def |class |return |if |else:|elif |for |while |import |from |"
    r"raise |assert |lambda |async |await |yield |with |try:|except:|finally:)",
    re.MULTILINE,
)


def _block_is_docs_only(block: PatchBlock) -> bool:
    """Return True when the block looks like a pure comment/docstring/config change."""
    ext = Path(block.file_path).suffix.lower()
    if ext in _DOCS_EXTENSIONS:
        return True
    if ext in _ALWAYS_CONFIRM_EXTENSIONS:
        return False
    # For code files: check whether the replace content has logic patterns
    replace = block.replace or block.content or ""
    # If the content contains executable code keywords, it's not docs-only.
    # The regex covers function/class definitions, control flow, imports, etc.
    # Docstrings, comments, and plain text won't match.
    return not _LOGIC_PATTERNS.search(replace)


def _changed_line_count(block: PatchBlock) -> int:
    if block.operation == "create":
        return len((block.content or "").splitlines())
    if block.operation == "delete":
        return len((block.search or "").splitlines())
    before = set((block.search or "").splitlines())
    after = set((block.replace or block.content or "").splitlines())
    return max(1, len(before ^ after)) if before or after else 0


def _matches_never_auto(path: Path, patterns: list[str]) -> bool:
    path_text = path.as_posix()
    for raw in patterns:
        pattern = raw.strip()
        if not pattern:
            continue
        if pattern.endswith("/") and path_text.startswith(pattern):
            return True
        if path_text == pattern or path_text.startswith(pattern.rstrip("/") + "/"):
            return True
        if path.name == pattern:
            return True
    return False


def _approval_config(config: SafeCodeConfig | ApprovalConfig | None) -> ApprovalConfig:
    if isinstance(config, SafeCodeConfig):
        return config.approval
    if isinstance(config, ApprovalConfig):
        return config
    return ApprovalConfig()


def classify_proposal(
    proposal: PatchProposal,
    config: SafeCodeConfig | ApprovalConfig | None = None,
) -> ApprovalTier:
    """Return the approval tier for *proposal*.

    Rules (evaluated in order, first match wins):
    1. Any ``delete`` block → GATE.
    2. Any ``create`` block → GATE (new file creation always confirmed).
    3. More than one file touched → CONFIRM.
    4. Single file with logic change → CONFIRM.
    5. Single file, docs/comments only → AUTO.
    """
    approval = _approval_config(config)

    for block in proposal.blocks:
        if block.operation == "delete":
            return ApprovalTier.GATE
        if block.operation == "create":
            return ApprovalTier.GATE
        if _matches_never_auto(Path(block.file_path), approval.never_auto_paths):
            return ApprovalTier.CONFIRM

    unique_files = {b.file_path for b in proposal.blocks}
    if len(unique_files) > approval.auto_max_files:
        return ApprovalTier.CONFIRM

    changed_lines = sum(_changed_line_count(block) for block in proposal.blocks)
    if changed_lines > approval.auto_max_changed_lines:
        return ApprovalTier.CONFIRM

    # Single file (or multiple blocks on same file)
    for block in proposal.blocks:
        if not _block_is_docs_only(block):
            return ApprovalTier.CONFIRM

    return ApprovalTier.AUTO


def tier_label(tier: ApprovalTier) -> str:
    return {
        ApprovalTier.AUTO: "auto (no pause)",
        ApprovalTier.CONFIRM: "confirm (diff review)",
        ApprovalTier.GATE: "gate (explicit approval required)",
    }[tier]
