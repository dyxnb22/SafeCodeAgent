"""Agent orchestration layer.

中文包说明：Agent 编排层。
- 职责：定义 Agent 步骤类型（只读/需审批等）与步骤结果模型，供 CLI 与 Agent 循环消费。
- 架构位置：位于 LLM 输出与工具执行之间，将模型提议映射为可审计、可门控的离散步骤。
- 与 Enterprise 的关系：Enterprise 工作流节点复用步骤分类语义；审批与策略裁决仍由 policy/tools 门控，不由本层自行放行。
"""

from safecode.agent.step_model import (  # noqa: F401
    AgentStepKind,
    AgentStepStatus,
    TypedAgentStep,
    TypedAgentStepResult,
    APPROVAL_REQUIRED_KINDS,
    READ_ONLY_AUTO_APPROVABLE_KINDS,
)
