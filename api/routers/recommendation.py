from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api.schemas import (
    ReplacementRecommendationRequest,
    ReplacementRecommendationResponse,
)
from api.service import run_replacement_recommendation

router = APIRouter()


@router.post(
    "/recommend-replacement",
    response_model=ReplacementRecommendationResponse,
)
def recommend_replacement(payload: ReplacementRecommendationRequest):
    try:
        result = run_replacement_recommendation(
            input_json=payload.input_json,
            current_schedule=payload.current_schedule.model_dump(),
            absence=payload.absence.model_dump(),
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