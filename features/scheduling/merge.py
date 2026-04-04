from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Tuple


DATE_FMT = "%Y-%m-%d"


def apply_llm_overrides(
    input_json: Dict[str, Any],
    parse_result: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    merged = deepcopy(input_json)
    employees = merged.get("employees", [])
    rules = merged.setdefault("rules", {})

    employee_by_id = {e["userId"]: e for e in employees}

    applied: List[Dict[str, Any]] = []
    ignored: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = list(parse_result.get("warnings", []))

    for inst in parse_result.get("instructions", []):
        inst_type = inst.get("type")

        if not inst.get("supported", False):
            ignored.append(
                {
                    "instruction": inst,
                    "reasonCode": "UNSUPPORTED_INSTRUCTION",
                    "reason": "지원되지 않는 요청입니다.",
                }
            )
            continue

        if inst_type == "ADD_OFFDAY":
            user_id = inst.get("userId")
            date_str = inst.get("date")
            if user_id not in employee_by_id:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "UNKNOWN_EMPLOYEE",
                        "reason": "존재하지 않는 userId 입니다.",
                    }
                )
                continue
            if not _is_valid_date(date_str):
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "INVALID_DATE",
                        "reason": "날짜 형식이 올바르지 않습니다.",
                    }
                )
                continue
            off_days = employee_by_id[user_id].setdefault("offDays", [])
            if date_str not in off_days:
                off_days.append(date_str)
            applied.append(
                {
                    "type": inst_type,
                    "userId": user_id,
                    "date": date_str,
                    "message": f"{employee_by_id[user_id]['userName']} 휴무일 {date_str} 추가",
                }
            )
            continue

        if inst_type == "SET_MAX_ASSIGNMENTS":
            user_id = inst.get("userId")
            value = inst.get("value")
            if user_id not in employee_by_id or not isinstance(value, int) or value < 0:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "INVALID_MAX_ASSIGNMENTS",
                        "reason": "maxAssignments 값 또는 userId가 유효하지 않습니다.",
                    }
                )
                continue
            employee_by_id[user_id]["maxAssignments"] = value
            applied.append(
                {
                    "type": inst_type,
                    "userId": user_id,
                    "value": value,
                    "message": f"{employee_by_id[user_id]['userName']} 최대 배정 수 {value}로 변경",
                }
            )
            continue

        if inst_type == "SET_MAX_CONSECUTIVE_DAYS":
            user_id = inst.get("userId")
            value = inst.get("value")
            if user_id not in employee_by_id or not isinstance(value, int) or value < 1:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "INVALID_MAX_CONSECUTIVE_DAYS",
                        "reason": "maxConsecutiveDays 값 또는 userId가 유효하지 않습니다.",
                    }
                )
                continue
            employee_by_id[user_id]["maxConsecutiveDays"] = value
            applied.append(
                {
                    "type": inst_type,
                    "userId": user_id,
                    "value": value,
                    "message": f"{employee_by_id[user_id]['userName']} 최대 연속 근무일 {value}로 변경",
                }
            )
            continue

        if inst_type == "SET_MAX_SHIFTS_PER_DAY":
            value = inst.get("value")
            if not isinstance(value, int) or value < 1 or value > 3:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "INVALID_MAX_SHIFTS_PER_DAY",
                        "reason": "maxShiftsPerDay 값은 1~3 사이의 정수여야 합니다.",
                    }
                )
                continue
            rules["maxShiftsPerDay"] = value
            applied.append(
                {
                    "type": inst_type,
                    "value": value,
                    "message": f"하루 최대 시프트 수를 {value}로 변경",
                }
            )
            continue

        if inst_type == "PREFER_SHIFT":
            user_id = inst.get("userId")
            shift_name = inst.get("shiftName")
            shift_names = {s["name"] for s in merged.get("shifts", [])}
            if user_id not in employee_by_id or shift_name not in shift_names:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "INVALID_PREFER_SHIFT",
                        "reason": "userId 또는 shiftName이 유효하지 않습니다.",
                    }
                )
                continue
            preferred = employee_by_id[user_id].setdefault("preferredShifts", [])
            if shift_name not in preferred:
                preferred.append(shift_name)
            applied.append(
                {
                    "type": inst_type,
                    "userId": user_id,
                    "shiftName": shift_name,
                    "message": f"{employee_by_id[user_id]['userName']} 선호 근무에 {shift_name} 추가",
                }
            )
            continue

        if inst_type == "BOOST_NIGHT_FAIRNESS":
            value = int(inst.get("value", 8))
            rules["nightWeight"] = value
            applied.append(
                {
                    "type": inst_type,
                    "value": value,
                    "message": f"야간 근무 공평성 요청 반영",
                }
            )
            continue

        if inst_type == "BOOST_WEEKEND_FAIRNESS":
            value = int(inst.get("value", 5))
            rules["weekendWeight"] = value
            applied.append(
                {
                    "type": inst_type,
                    "value": value,
                    "message": f"주말 근무 공평성 요청 반영",
                }
            )
            continue

        if inst_type == "FORBID_DATE":
            user_id = inst.get("userId")
            date_str = inst.get("date")

            if user_id not in employee_by_id:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "UNKNOWN_EMPLOYEE",
                        "reason": "존재하지 않는 userId 입니다.",
                    }
                )
                continue

            if not _is_valid_date(date_str):
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "INVALID_DATE",
                        "reason": "날짜 형식이 올바르지 않습니다.",
                    }
                )
                continue

            off_days = employee_by_id[user_id].setdefault("offDays", [])
            if date_str not in off_days:
                off_days.append(date_str)

            applied.append(
                {
                    "type": inst_type,
                    "userId": user_id,
                    "date": date_str,
                    "message": f"{employee_by_id[user_id]['userName']} {date_str} 근무 금지",
                }
            )
            continue

        if inst_type == "FORBID_SHIFT":
            user_id = inst.get("userId")
            shift_name = inst.get("shiftName")

            if user_id not in employee_by_id:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "UNKNOWN_EMPLOYEE",
                        "reason": "존재하지 않는 userId 입니다.",
                    }
                )
                continue

            shift_names = {s["name"] for s in merged.get("shifts", [])}
            if shift_name not in shift_names:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "UNKNOWN_SHIFT",
                        "reason": "존재하지 않는 shiftName 입니다.",
                    }
                )
                continue

            forbidden = employee_by_id[user_id].setdefault("forbiddenShifts", [])
            if shift_name not in forbidden:
                forbidden.append(shift_name)

            applied.append(
                {
                    "type": inst_type,
                    "userId": user_id,
                    "shiftName": shift_name,
                    "message": f"{employee_by_id[user_id]['userName']} {shift_name} 근무 금지",
                }
            )
            continue

        if inst_type == "SET_ALL_SHIFTS_MIN_SKILL_COVERAGE":
            skill = inst.get("skill")
            count = inst.get("count")

            if not skill or not isinstance(count, int) or count < 1:
                ignored.append(
                    {
                        "instruction": inst,
                        "reasonCode": "INVALID_MIN_SKILL_COVERAGE",
                        "reason": "skill 또는 count가 유효하지 않습니다.",
                    }
                )
                continue

            for shift in merged.get("shifts", []):
                coverage = shift.setdefault("minSkillCoverage", [])
                exists = any(c.get("skill") == skill for c in coverage)
                if not exists:
                    coverage.append({"skill": skill, "count": count})

            applied.append(
                {
                    "type": inst_type,
                    "skill": skill,
                    "count": count,
                    "message": f"모든 시프트에 {skill} 최소 {count}명 이상 배치",
                }
            )
            continue
        
        ignored.append(
            {
                "instruction": inst,
                "reasonCode": "UNMAPPABLE_POLICY",
                "reason": "현재 merge 로직에서 처리하지 않는 요청 타입입니다.",
            }
        )

    return merged, applied, ignored, warnings


def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, DATE_FMT)
        return True
    except Exception:
        return False
