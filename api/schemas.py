from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field


class ScheduleRequest(BaseModel):
    input_json: Dict[str, Any] = Field(..., description="스케줄 생성용 입력 JSON")
    user_request: List[str] = Field(default_factory=list)


class ExplanationResponse(BaseModel):
    mode: str
    summary: str
    details: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AssignmentResponse(BaseModel):
    date: str
    userId: int
    userName: str
    shiftName: str
    startTime: str
    endTime: str


class ScheduleResponse(BaseModel):
    status: str
    message: str
    assignments: List[AssignmentResponse] = Field(default_factory=list)
    fairnessSummary: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    solverMeta: Dict[str, Any] = Field(default_factory=dict)
    unassignedShifts: List[Dict[str, Any]] = Field(default_factory=list)
    appliedInstructions: List[Dict[str, Any]] = Field(default_factory=list)
    ignoredInstructions: List[Dict[str, Any]] = Field(default_factory=list)
    parserWarnings: List[Dict[str, Any]] = Field(default_factory=list)
    constraintCatalog: Dict[str, Any] = Field(default_factory=dict)
    parserMode: str = "unknown"
    explanation: Optional[ExplanationResponse] = None