from typing import Any, Dict, Optional, List

from app.graph import graph_app
from features.recommendation.replacement_recommender import recommend_replacements


def run_schedule(input_json: Dict[str, Any], user_request: Optional[str | List[str]] = None) -> Dict[str, Any]:
    state = {
        "input_json": input_json,
        "user_request": user_request,
        "constraint_catalog": {},
        "llm_parse_result": {},
        "parser_warnings": [],
        "applied_instructions": [],
        "ignored_instructions": [],
        "solver_params": {},
        "raw_schedule": {},
        "final_schedule": {},
        "error_msg": None,
    }

    result = graph_app.invoke(state)

    if result.get("error_msg"):
        return result.get("raw_schedule") or {
            "status": "FAILED",
            "message": result["error_msg"],
        }

    return result["final_schedule"]

def run_replacement_recommendation(
    input_json: Dict[str, Any],
    current_schedule: Dict[str, Any],
    absence: Dict[str, Any],
    user_request: Optional[List[str] | str] = None,
) -> Dict[str, Any]:
    return recommend_replacements(
        input_json=input_json,
        current_schedule=current_schedule,
        absence=absence,
        user_request=user_request,
    )