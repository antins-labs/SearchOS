"""Trajectory data models for episodic memory / skill mining."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from searchos.util.base_model import CamelModel


class StateDelta(CamelModel):
    """The change a single step made to the search state."""

    coverage_before: float = 0.0
    coverage_after: float = 0.0
    new_evidence_count: int = 0
    frontier_resolved: list[str] = Field(default_factory=list)
    frontier_added: list[str] = Field(default_factory=list)
    conflicts_detected: int = 0
    conflicts_resolved: int = 0

    @property
    def coverage_gain(self) -> float:
        return self.coverage_after - self.coverage_before

    @property
    def is_valuable(self) -> bool:
        """Whether this step produced meaningful progress."""
        return (
            self.coverage_gain >= 0.05
            or self.new_evidence_count >= 1
            or len(self.frontier_resolved) >= 1
            or self.conflicts_resolved >= 1
        )


class TrajectoryStep(CamelModel):
    """One step in a search trajectory. Append-only to JSONL."""

    timestamp: str
    step_index: int = 0
    action: str  # tool name or description
    action_input_summary: str = ""  # truncated input
    observation_summary: str = ""  # truncated output
    state_delta: StateDelta = Field(default_factory=StateDelta)
    step_value: float = 0.0  # computed from state_delta


class ConversationMessage(CamelModel):
    """完整的对话消息，记录 assistant/user/tool_call/tool_result 轨迹。"""

    timestamp: str = ""
    step_index: int = 0
    agent_name: str = "orchestrator"  # 产生此消息的 agent
    parent_agent: str = ""  # 父 agent（空表示顶层 orchestrator）
    role: Literal["user", "assistant", "tool_call", "tool_result"] = "assistant"
    content: str = ""
    reasoning: str = ""  # 分离字段里的思考（qwen3/glm-5/deepseek-r1 的 reasoning_content）
    tool_name: str = ""  # tool_call / tool_result 时填充
    tool_call_id: str = ""  # 关联 tool_call 与 tool_result
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSummary(CamelModel):
    """End-of-task summary appended after all steps."""

    task_id: str
    task_type: str = ""
    query: str
    timestamp_start: str
    timestamp_end: str
    total_steps: int = 0
    total_queries: int = 0
    final_coverage: float = 0.0
    effective_strategies: list[str] = Field(default_factory=list)
    failed_strategies: list[str] = Field(default_factory=list)
    bottlenecks_encountered: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
