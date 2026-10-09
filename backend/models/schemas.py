from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_APPROVAL = "needs_approval"


class BusinessGoal(BaseModel):
    request: str
    objective: str
    success_criteria: list[str]
    constraints: list[str] = Field(default_factory=list)


class PlannedAction(BaseModel):
    id: str
    description: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: str = "low"
    requires_approval: bool = False


class ExecutionObservation(BaseModel):
    action_id: str
    tool: str
    success: bool
    output: str = ""
    error: str | None = None
    duration_ms: float = 0


class VerificationResult(BaseModel):
    verified: bool
    criteria_results: dict[str, bool] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    summary: str = ""


class WorkerResult(BaseModel):
    status: RunStatus
    goal: BusinessGoal | None = None
    plan: list[PlannedAction] = Field(default_factory=list)
    observations: list[ExecutionObservation] = Field(default_factory=list)
    verification: VerificationResult | None = None
    summary: str = ""