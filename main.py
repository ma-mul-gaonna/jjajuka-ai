from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from api.schemas import ScheduleRequest, ScheduleResponse
from api.service import run_schedule

app = FastAPI(
    title="Scheduling API",
    version="1.0.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/schedule", response_model=ScheduleResponse)
def create_schedule(payload: ScheduleRequest):
    try:
        result = run_schedule(
            input_json=payload.input_json,
            user_request=payload.user_request,
        )

        return {
            "status": result.get("status", "SUCCESS"),
            "message": result.get("message", ""),
            "result": result,
        }

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