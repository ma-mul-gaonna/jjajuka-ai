import json
import os
import sys
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scheduling.nodes import extract_params_node, format_node, solve_node


class AgentState(TypedDict):
    input_json: Dict[str, Any]
    solver_params: Dict[str, Any]
    raw_schedule: Dict[str, Any]
    final_schedule: Dict[str, Any]
    error_msg: Optional[str]


workflow = StateGraph(AgentState)
workflow.add_node("extract", extract_params_node)
workflow.add_node("solve", solve_node)
workflow.add_node("format", format_node)
workflow.set_entry_point("extract")
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
workflow.add_edge("format", END)
app = workflow.compile()


if __name__ == "__main__":
    sample_input = {
        "startDate": "2026-04-01",
        "endDate": "2026-04-30",
        "rules": {
            "minRestHours": 11,
            "maxConsecutiveDays": 5,
            "fairnessWeight": 4,
            "preferenceWeight": 3,
            "weekendWeight": 2,
            "nightWeight": 6,
            "solverTimeLimitSeconds": 15,
        },
        "employees": [
            {
                "userId": 101,
                "userName": "김민지",
                "roles": ["nurse"],
                "skills": ["ICU"],
                "availableShifts": ["Day", "Evening", "Night"],
                "offDays": ["2026-04-03", "2026-04-14"],
                "preferredShifts": ["Day"],
                "maxAssignments": 21,
                "maxConsecutiveDays": 5,
            },
            {
                "userId": 102,
                "userName": "박성훈",
                "roles": ["nurse"],
                "skills": ["ER", "ICU"],
                "availableShifts": ["Day", "Evening", "Night"],
                "offDays": ["2026-04-10", "2026-04-24"],
                "preferredShifts": ["Evening"],
                "maxAssignments": 20,
                "maxConsecutiveDays": 5,
            },
            {
                "userId": 103,
                "userName": "이철수",
                "roles": ["nurse"],
                "skills": ["ICU", "ER"],
                "availableShifts": ["Day", "Night"],
                "offDays": ["2026-04-05", "2026-04-06"],
                "preferredShifts": ["Night"],
                "maxAssignments": 21,
                "maxConsecutiveDays": 4,
            },
            {
                "userId": 104,
                "userName": "최영희",
                "roles": ["nurse"],
                "skills": ["Ward", "ICU"],
                "availableShifts": ["Day", "Evening", "Night"],
                "offDays": ["2026-04-20"],
                "preferredShifts": ["Day"],
                "maxAssignments": 20,
                "maxConsecutiveDays": 5,
            },
            {
                "userId": 105,
                "userName": "홍길동",
                "roles": ["nurse"],
                "skills": ["ICU"],
                "availableShifts": ["Evening", "Night"],
                "offDays": ["2026-04-25"],
                "preferredShifts": ["Night"],
                "maxAssignments": 20,
                "maxConsecutiveDays": 5,
            },
            {
                "userId": 106,
                "userName": "정은지",
                "roles": ["charge_nurse", "nurse"],
                "skills": ["ICU", "Ward"],
                "availableShifts": ["Day", "Evening", "Night"],
                "offDays": ["2026-04-08", "2026-04-22"],
                "preferredShifts": ["Day"],
                "maxAssignments": 20,
                "maxConsecutiveDays": 5,
            },
        ],
        "shifts": [
            {
                "name": "Day",
                "startTime": "07:00",
                "endTime": "15:00",
                "requiredCount": 2,
                "requiredRoles": ["nurse"],
                "requiredSkills": [],
                "isNight": False,
            },
            {
                "name": "Evening",
                "startTime": "15:00",
                "endTime": "23:00",
                "requiredCount": 1,
                "requiredRoles": ["nurse"],
                "requiredSkills": [],
                "isNight": False,
            },
            {
                "name": "Night",
                "startTime": "23:00",
                "endTime": "07:00",
                "requiredCount": 1,
                "requiredRoles": ["nurse"],
                "requiredSkills": ["ICU"],
                "isNight": True,
            },
        ],
    }

    result = app.invoke(
        {
            "input_json": sample_input,
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
