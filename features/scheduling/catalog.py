from typing import Any, Dict


def build_constraint_catalog() -> Dict[str, Any]:
    return {
        "version": "1.0",
        "supported_constraints": [
            {
                "type": "ADD_OFFDAY",
                "description": "특정 직원에게 휴무일 추가",
                "required_fields": ["userId", "date"],
            },
            {
                "type": "SET_MAX_ASSIGNMENTS",
                "description": "특정 직원의 최대 총 근무 횟수 변경",
                "required_fields": ["userId", "value"],
            },
            {
                "type": "SET_MAX_CONSECUTIVE_DAYS",
                "description": "특정 직원의 최대 연속 근무일 변경",
                "required_fields": ["userId", "value"],
            },
            {
                "type": "SET_MAX_SHIFTS_PER_DAY",
                "description": "전체 규칙의 하루 최대 시프트 수 변경",
                "required_fields": ["value"],
            },
            {
                "type": "PREFER_SHIFT",
                "description": "특정 직원의 선호 시프트 추가",
                "required_fields": ["userId", "shiftName"],
            },
            {
                "type": "BOOST_NIGHT_FAIRNESS",
                "description": "야간 근무 형평성 가중치 강화",
                "required_fields": ["value"],
            },
            {
                "type": "BOOST_WEEKEND_FAIRNESS",
                "description": "주말 근무 형평성 가중치 강화",
                "required_fields": ["value"],
            },
            {
                "type": "FORBID_SHIFT",
                "description": "특정 직원이 특정 시프트에 배정되지 않도록 제한",
                "required_fields": ["userId", "shiftName"],
            },
            {
                "type": "FORCE_ASSIGN",
                "description": "특정 직원을 특정 날짜의 특정 시프트에 강제 배정",
                "required_fields": ["userId", "date", "shiftName"],
            },
            {
                "type": "FORBID_DATE",
                "description": "특정 직원이 특정 날짜에 어떤 시프트에도 배정되지 않도록 제한",
                "required_fields": ["userId", "date"],
            },
            {
                "type": "SET_MIN_ASSIGNMENTS",
                "description": "특정 직원의 최소 근무 횟수 설정",
                "required_fields": ["userId", "value"],
            },
            {
                "type": "LIMIT_NIGHT_ASSIGNMENTS",
                "description": "특정 직원의 야간 근무 최대 횟수 제한",
                "required_fields": ["userId", "value"],
            },
            {
                "type": "SET_ALL_SHIFTS_MIN_SKILL_COVERAGE",
                "description": "모든 시프트에 특정 스킬 보유 인원을 최소 N명 이상 배치",
                "required_fields": ["skill", "count"],
            }

        ],
        "unsupported_examples": [
            "분위기 좋게 짜줘",
            "인간적으로 배려해서 짜줘",
            "잘 맞는 사람끼리 붙여줘",
        ],
    }
