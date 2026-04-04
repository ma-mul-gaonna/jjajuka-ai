import json
import os
import sys
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from features.scheduling.nodes import (
    llm_parse_node,
    extract_params_node,
    solve_node,
    format_node,
    explain_node,
)


class AgentState(TypedDict):
    input_json: Dict[str, Any]
    user_request: Optional[str]

    constraint_catalog: Dict[str, Any]
    llm_parse_result: Dict[str, Any]
    parser_warnings: List[Dict[str, Any]]
    applied_instructions: List[Dict[str, Any]]
    ignored_instructions: List[Dict[str, Any]]

    solver_params: Dict[str, Any]
    raw_schedule: Dict[str, Any]
    final_schedule: Dict[str, Any]
    error_msg: Optional[str]


workflow = StateGraph(AgentState)

workflow.add_node("llm_parse", llm_parse_node)
workflow.add_node("extract", extract_params_node)
workflow.add_node("solve", solve_node)
workflow.add_node("format", format_node)
workflow.add_node("explain", explain_node)

workflow.set_entry_point("llm_parse")
workflow.add_edge("llm_parse", "extract")
workflow.add_edge("extract", "solve")


def route_after_solve(state: AgentState):
    return "end" if state.get("error_msg") else "format"


workflow.add_conditional_edges(
    "solve",
    route_after_solve,
    {
        "format": "format",
        "end": END,
    },
)

workflow.add_edge("format", "explain")
workflow.add_edge("explain", END)

app = workflow.compile()


if __name__ == "__main__":
    sample_input = {
        "startDate": "2026-04-01",
        "endDate": "2026-04-07",
        "rules": {
            "minRestHours": 11,
            "maxConsecutiveDays": 5,
            "maxShiftsPerDay": 1,
            "solverTimeLimitSeconds": 20, # 인원이 늘어났으므로 시간을 약간 늘림
        },
        "employees": [
            # --- GRADE_A 숙련 간호사 (6명) ---
            {"userId": 101, "userName": "김민지", "roles": ["nurse"], "skills": ["GRADE_A"], "availableShifts": ["Day", "Evening", "Night"], "offDays": ["2026-04-03"], "preferredShifts": ["Day"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 102, "userName": "박성훈", "roles": ["nurse"], "skills": ["GRADE_A"], "availableShifts": ["Day", "Evening", "Night"], "offDays": ["2026-04-04"], "preferredShifts": ["Evening"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 103, "userName": "이철수", "roles": ["nurse"], "skills": ["GRADE_A", "ICU"], "availableShifts": ["Day", "Evening", "Night"], "offDays": ["2026-04-05"], "preferredShifts": ["Night"], "maxAssignments": 21, "maxConsecutiveDays": 4},
            {"userId": 104, "userName": "최영희", "roles": ["nurse"], "skills": ["GRADE_A", "Ward"], "availableShifts": ["Day", "Evening", "Night"], "offDays": [], "preferredShifts": ["Day"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 105, "userName": "홍길동", "roles": ["nurse"], "skills": ["GRADE_A", "ER"], "availableShifts": ["Day", "Evening", "Night"], "offDays": [], "preferredShifts": ["Night"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 106, "userName": "정은지", "roles": ["charge_nurse", "nurse"], "skills": ["GRADE_A", "ICU"], "availableShifts": ["Day", "Evening", "Night"], "offDays": ["2026-04-01"], "preferredShifts": ["Day"], "maxAssignments": 21, "maxConsecutiveDays": 5},

            # --- 일반 간호사 (6명) ---
            {"userId": 107, "userName": "강지훈", "roles": ["nurse"], "skills": ["Ward"], "availableShifts": ["Day", "Evening"], "offDays": [], "preferredShifts": ["Day"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 108, "userName": "윤서연", "roles": ["nurse"], "skills": ["ICU"], "availableShifts": ["Day", "Evening", "Night"], "offDays": ["2026-04-02"], "preferredShifts": ["Evening"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 109, "userName": "임현우", "roles": ["nurse"], "skills": ["ER"], "availableShifts": ["Day", "Evening", "Night"], "offDays": [], "preferredShifts": ["Night"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 110, "userName": "한소희", "roles": ["nurse"], "skills": ["Ward"], "availableShifts": ["Day", "Evening"], "offDays": ["2026-04-07"], "preferredShifts": ["Day"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 111, "userName": "오지명", "roles": ["nurse"], "skills": ["ICU"], "availableShifts": ["Day", "Evening", "Night"], "offDays": [], "preferredShifts": ["Evening"], "maxAssignments": 21, "maxConsecutiveDays": 5},
            {"userId": 112, "userName": "배수지", "roles": ["nurse"], "skills": ["ER"], "availableShifts": ["Day", "Evening", "Night"], "offDays": [], "preferredShifts": ["Day"], "maxAssignments": 21, "maxConsecutiveDays": 5},
        ],
        "shifts": [
            {
                "name": "Day",
                "startTime": "07:00",
                "endTime": "15:00",
                "requiredCount": 2, # 인원이 늘었으므로 각 시프트당 2명씩 배치
                "requiredRoles": ["nurse"],
                "requiredSkills": [], # 적어도 1명은 GRADE_A여야 함 (솔버 로직에 따라 해석됨)
                "isNight": False,
            },
            {
                "name": "Evening",
                "startTime": "15:00",
                "endTime": "23:00",
                "requiredCount": 2,
                "requiredRoles": ["nurse"],
                "requiredSkills": [],
                "isNight": False,
            },
            {
                "name": "Night",
                "startTime": "23:00",
                "endTime": "07:00",
                "requiredCount": 2,
                "requiredRoles": ["nurse"],
                "requiredSkills": [],
                "isNight": True,
            },
        ],
    }

    result = app.invoke(
        {
            "input_json": sample_input,
            "user_request": "김민지는 2026-04-10 쉬게 하고, 김민지 Night 금지하고, 나머지 야간은 최대한 공평하게 해줘. 하루 최대 1개 시프트만 유지해줘. 분위기 좋게 짜줘.",
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
    )

    if result.get("error_msg"):
        failure_payload = result.get("raw_schedule") or {
            "status": "FAILED",
            "message": result["error_msg"],
        }
        print(json.dumps(failure_payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result["final_schedule"], ensure_ascii=False, indent=2))
