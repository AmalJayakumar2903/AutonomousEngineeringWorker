from typing import Any, TypedDict

from backend.models.schemas import BusinessGoal, VerificationResult


class AgentState(TypedDict, total=False):
    repository: str
    request: str
    run_id: str
    goal: BusinessGoal
    plan: list[dict]
    observations: list[dict[str, Any]]
    verification: VerificationResult
    status: str
    iteration: int