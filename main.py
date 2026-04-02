from __future__ import annotations

import json
from typing import Any, Dict

from nodes import extract_params_node, format_node, solve_node


SUCCESS_SAMPLE_INPUT = {
    "startDate": "2026-04-01",
    "endDate": "2026-04-07",
    "rules": {
        "minRestHours": 11,
        "maxConsecutiveDays": 5,
    },
    "employees": [
        {
            "userId": 101,
            "userName": "김민지",
            "roles": ["nurse"],
            "skills": ["ICU"],
            "availableShifts": ["Day", "Night"],
            "offDays": ["2026-04-03"],
            "preferredShifts": ["Night"],
        },
        {
            "userId": 102,
            "userName": "박성훈",
            "roles": ["nurse"],
            "skills": ["ER"],
            "availableShifts": ["Day", "Evening"],
            "offDays": [],
            "preferredShifts": ["Day"],
        },
        {
            "userId": 103,
            "userName": "이철수",
            "roles": ["nurse"],
            "skills": ["ICU", "ER"],
            "availableShifts": ["Evening", "Night"],
            "offDays": ["2026-04-02"],
            "preferredShifts": ["Evening"],
        },
        {
            "userId": 104,
            "userName": "최영희",
            "roles": ["assistant"],
            "skills": ["WARD"],
            "availableShifts": ["Day", "Evening"],
            "offDays": ["2026-04-06"],
            "preferredShifts": ["Evening"],
            "maxConsecutiveDays": 4,
        },
        {
            "userId": 105,
            "userName": "홍길동",
            "roles": ["assistant", "nurse"],
            "skills": ["WARD", "ER"],
            "availableShifts": ["Day", "Evening", "Night"],
            "offDays": [],
            "preferredShifts": ["Night"],
        },
        {
            "userId": 106,
            "userName": "한지수",
            "roles": ["assistant"],
            "skills": ["WARD"],
            "availableShifts": ["Evening", "Night"],
            "offDays": ["2026-04-05"],
            "preferredShifts": ["Evening"],
        },
    ],
    "shifts": [
        {
            "name": "Day",
            "startTime": "07:00",
            "endTime": "15:00",
            "requiredCount": 1,
            "requiredRoles": ["nurse"],
            "requiredSkills": [],
        },
        {
            "name": "Evening",
            "startTime": "15:00",
            "endTime": "23:00",
            "requiredCount": 1,
            "requiredRoles": ["assistant"],
            "requiredSkills": [],
        },
        {
            "name": "Night",
            "startTime": "23:00",
            "endTime": "07:00",
            "requiredCount": 1,
            "requiredRoles": ["nurse"],
            "requiredSkills": [],
            "isNight": True,
        },
    ],
}

FAILED_SAMPLE_INPUT = {
    "startDate": "2026-04-01",
    "endDate": "2026-04-03",
    "rules": {
        "minRestHours": 11,
        "maxConsecutiveDays": 2,
    },
    "employees": [
        {
            "userId": 201,
            "userName": "야간불가간호사",
            "roles": ["nurse"],
            "skills": ["ER"],
            "availableShifts": ["Day"],
            "offDays": [],
            "preferredShifts": ["Day"],
        },
        {
            "userId": 202,
            "userName": "휴가중간호사",
            "roles": ["nurse"],
            "skills": ["ER"],
            "availableShifts": ["Night"],
            "offDays": ["2026-04-01", "2026-04-02", "2026-04-03"],
            "preferredShifts": ["Night"],
        },
    ],
    "shifts": [
        {
            "name": "Night",
            "startTime": "22:00",
            "endTime": "06:00",
            "requiredCount": 1,
            "requiredRoles": ["nurse"],
            "requiredSkills": [],
            "isNight": True,
        }
    ],
}


def run_schedule(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "input_json": input_payload,
        "solver_params": {},
        "raw_schedule": [],
        "final_schedule": {},
        "solve_result": {},
        "warnings": [],
        "error_msg": None,
    }

    state.update(extract_params_node(state))
    state.update(solve_node(state))

    if state.get("error_msg"):
        return state.get("solve_result", {
            "status": "FAILED",
            "message": state["error_msg"],
        })

    state.update(format_node(state))
    return state["final_schedule"]


if __name__ == "__main__":
    print("🚀 DutyFlow AI 엔진 가동 중...\n")

    print("[성공 시나리오]")
    success_result = run_schedule(SUCCESS_SAMPLE_INPUT)
    print(json.dumps(success_result, indent=2, ensure_ascii=False))

    print("\n[실패 시나리오]")
    failed_result = run_schedule(FAILED_SAMPLE_INPUT)
    print(json.dumps(failed_result, indent=2, ensure_ascii=False))
