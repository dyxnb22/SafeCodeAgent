"""Enterprise evaluation models.

中文包说明：企业评测用例与结果模型。
- 评测在确定性夹具上运行，不依赖实时模型提供商或外部网络。
- 评测通过不代表可绕过审批或策略门控。
"""

from safecode.enterprise.eval.cases import CostBudget, EvaluationCase, EvaluationResult, EvalSuite
from safecode.enterprise.eval.exceptions import (
    DuplicateCaseIdError,
    EvalError,
    InvalidEvalCaseError,
)

__all__ = [
    "CostBudget",
    "DuplicateCaseIdError",
    "EvalError",
    "EvalSuite",
    "EvaluationCase",
    "EvaluationResult",
    "InvalidEvalCaseError",
]
