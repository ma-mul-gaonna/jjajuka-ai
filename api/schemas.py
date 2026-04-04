from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ScheduleRequest(BaseModel):
    input_json: Dict[str, Any] = Field(..., description="스케줄 생성용 입력 JSON")
    user_request: Optional[str] = Field(default=None, description="자연어 추가 요청")


class ScheduleResponse(BaseModel):
    status: str
    message: str
    result: Dict[str, Any]