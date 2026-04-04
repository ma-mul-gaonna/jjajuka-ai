from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api.schemas import ScheduleRequest, ScheduleResponse
from api.service import run_schedule

router = APIRouter()


@router.post("/schedule", response_model=ScheduleResponse)
def create_schedule(payload: ScheduleRequest):
    try:
        result = run_schedule(
            input_json=payload.input_json,
            user_request=payload.user_request,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "FAILED",
                "message": "서버 내부 오류",
                "detail": str(e),
            },
        )