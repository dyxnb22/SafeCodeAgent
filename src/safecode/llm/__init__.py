"""LLM client abstractions.

中文包说明：大语言模型客户端抽象层。
- 职责：定义 ``LLMClient`` 协议及 OpenAI、Anthropic、DeepSeek、Mock 等提供商实现；
  提供结构化输出（计划、补丁提案、工具意图）与重试、流式、成本计量辅助。
- 架构位置：位于 Agent 编排与策略门控之间；模型仅返回结构化提案，不直接写文件或执行命令。
- 与 Enterprise 的关系：Enterprise 工作流 LLM 节点（分析、计划、提案）通过本层调用；
  输出须经 schema 校验与审批门，不得绕过策略快照。
"""
