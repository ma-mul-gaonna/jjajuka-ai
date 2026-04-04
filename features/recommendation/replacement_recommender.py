from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


REASON_TEXT = {
    "ROLE_MATCH": "역할 요건을 충족하고",
    "SKILL_MATCH": "필요 스킬을 보유했으며",
    "PREFERRED_SHIFT": "선호 근무와 일치하고",
    "REST_OK": "최소 휴식시간을 만족하고",
    "LOW_NIGHT_BIAS": "현재 야간 편중이 낮고",
    "LOW_WEEKEND_BIAS": "주말 편중이 비교적 낮고",
    "LOW_TOTAL_LOAD": "전체 배정 부담이 비교적 낮고",
    "FAIRNESS_FRIENDLY": "연속 근무 부담도 과하지 않습니다",
}


def recommend_replacements(
    input_json: Dict[str, Any],
    current_schedule: Dict[str, Any],
    absence: Dict[str, Any],
    user_request: Optional[List[str] | str] = None,
) -> Dict[str, Any]:
    employees = input_json.get("employees", [])
    shifts = input_json.get("shifts", [])
    rules = input_json.get("rules", {})
    assignments = current_schedule.get("assignments", [])

    if not employees:
        raise ValueError("employees는 비어 있을 수 없습니다.")
    if not shifts:
        raise ValueError("shifts는 비어 있을 수 없습니다.")
    if not absence:
        raise ValueError("absence는 비어 있을 수 없습니다.")

    target_date = absence.get("date")
    target_shift_name = absence.get("shiftName")
    replaced_user_id = absence.get("userId")

    if not target_date or not target_shift_name or replaced_user_id is None:
        raise ValueError("absence에는 userId, date, shiftName이 필요합니다.")

    employee_by_id = {e["userId"]: e for e in employees}
    shift_by_name = {s["name"]: s for s in shifts}

    if replaced_user_id not in employee_by_id:
        raise ValueError("absence.userId가 employees에 없습니다.")
    if target_shift_name not in shift_by_name:
        raise ValueError("absence.shiftName이 shifts에 없습니다.")

    target_shift = shift_by_name[target_shift_name]
    replaced_employee = employee_by_id[replaced_user_id]

    weights = _build_preference_weights(user_request)

    assignments_by_user = defaultdict(list)
    assignments_by_date = defaultdict(list)
    for item in assignments:
        user_id = item["userId"]
        assignments_by_user[user_id].append(item)
        assignments_by_date[item["date"]].append(item)

    candidates: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for employee in employees:
        user_id = employee["userId"]

        if user_id == replaced_user_id:
            continue

        eligible, fail_reason = _is_candidate_eligible(
            employee=employee,
            target_date=target_date,
            target_shift=target_shift,
            assignments=assignments,
            assignments_by_user=assignments_by_user,
            input_json=input_json,
        )
        if not eligible:
            continue

        score, reason_codes = _score_candidate(
            employee=employee,
            target_date=target_date,
            target_shift=target_shift,
            replaced_employee=replaced_employee,
            assignments_by_user=assignments_by_user,
            rules=rules,
            weights=weights,
        )

        candidates.append(
            {
                "userId": user_id,
                "userName": employee["userName"],
                "score": score,
                "reasonCodes": reason_codes,
            }
        )

    candidates.sort(key=lambda x: (-x["score"], x["userId"]))

    recommendations = []
    for idx, candidate in enumerate(candidates[:3], start=1):
        recommendations.append(
            {
                "rank": idx,
                "userId": candidate["userId"],
                "userName": candidate["userName"],
                "score": candidate["score"],
                "reasons": [REASON_TEXT[code] for code in candidate["reasonCodes"]],
            }
        )

    if not recommendations:
        warnings.append("추천 가능한 대체 인력이 없습니다.")

    return {
        "status": "SUCCESS",
        "message": "대체인력 추천이 완료되었습니다.",
        "absence": {
            "userId": replaced_user_id,
            "userName": replaced_employee["userName"],
            "date": target_date,
            "shiftName": target_shift_name,
        },
        "recommendations": recommendations,
        "warnings": warnings,
    }


def _build_preference_weights(user_request: Optional[List[str] | str]) -> Dict[str, int]:
    base = {
        "preferred_shift": 10,
        "low_night_bias": 8,
        "low_weekend_bias": 5,
        "low_total_load": 10,
    }

    if not user_request:
        return base

    text = _normalize_user_request(user_request)

    if "선호 근무" in text:
        base["preferred_shift"] += 4
    if "야간" in text and ("우선" in text or "편중" in text):
        base["low_night_bias"] += 4
    if "주말" in text and ("우선" in text or "편중" in text):
        base["low_weekend_bias"] += 3

    return base


def _is_candidate_eligible(
    employee: Dict[str, Any],
    target_date: str,
    target_shift: Dict[str, Any],
    assignments: List[Dict[str, Any]],
    assignments_by_user: Dict[int, List[Dict[str, Any]]],
    input_json: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    user_id = employee["userId"]
    shifts = input_json.get("shifts", [])
    rules = input_json.get("rules", {})
    shift_name_to_obj = {s["name"]: s for s in shifts}

    # off day
    if target_date in employee.get("offDays", []):
        return False, "OFF_DAY"

    # available shifts
    available = employee.get("availableShifts")
    if available is not None and target_shift["name"] not in available:
        return False, "NOT_AVAILABLE_SHIFT"

    # forbidden shifts
    if target_shift["name"] in employee.get("forbiddenShifts", []):
        return False, "FORBIDDEN_SHIFT"

    # same-day already assigned
    max_shifts_per_day = int(rules.get("maxShiftsPerDay", 1))
    same_day_count = sum(
        1 for a in assignments_by_user[user_id]
        if a["date"] == target_date
    )
    if same_day_count >= max_shifts_per_day:
        return False, "MAX_SHIFTS_PER_DAY"

    # role check
    required_roles = set(target_shift.get("requiredRoles", []))
    employee_roles = set(employee.get("roles", []))
    if required_roles and not required_roles.issubset(employee_roles):
        return False, "ROLE_MISMATCH"

    # skill check
    required_skills = set(target_shift.get("requiredSkills", []))
    employee_skills = set(employee.get("skills", []))
    if required_skills and not required_skills.issubset(employee_skills):
        return False, "SKILL_MISMATCH"

    # rest hour check
    min_rest_hours = int(rules.get("minRestHours", 11))
    target_start_dt, target_end_dt = _build_shift_datetimes(target_date, target_shift)

    for a in assignments_by_user[user_id]:
        other_shift = shift_name_to_obj.get(a["shiftName"])
        if not other_shift:
            continue
        other_start_dt, other_end_dt = _build_shift_datetimes(a["date"], other_shift)

        gap1 = abs((target_start_dt - other_end_dt).total_seconds()) / 3600
        gap2 = abs((other_start_dt - target_end_dt).total_seconds()) / 3600

        # target shift가 기존 shift 뒤에 오거나, 기존 shift가 target 뒤에 오는 양방향 체크
        if other_end_dt <= target_start_dt and gap1 < min_rest_hours:
            return False, "REST_CONFLICT"
        if target_end_dt <= other_start_dt and gap2 < min_rest_hours:
            return False, "REST_CONFLICT"

        # 같은 날짜 다른 시프트면 무조건 제외
        if a["date"] == target_date:
            return False, "ALREADY_ASSIGNED_SAME_DAY"

    return True, None


def _score_candidate(
    employee: Dict[str, Any],
    target_date: str,
    target_shift: Dict[str, Any],
    replaced_employee: Dict[str, Any],
    assignments_by_user: Dict[int, List[Dict[str, Any]]],
    rules: Dict[str, Any],
    weights: Dict[str, int],
) -> Tuple[int, List[str]]:
    user_id = employee["userId"]
    reason_codes: List[str] = []
    score = 0

    score += 30
    reason_codes.append("ROLE_MATCH")

    replaced_required_skills = set(target_shift.get("requiredSkills", []))
    employee_skills = set(employee.get("skills", []))
    replaced_skills = set(replaced_employee.get("skills", []))

    has_grade_coverage = "GRADE_A" in employee_skills or "GRADE_A" in replaced_skills
    if replaced_required_skills.issubset(employee_skills) or has_grade_coverage:
        score += 25
        reason_codes.append("SKILL_MATCH")

    if target_shift["name"] in employee.get("preferredShifts", []):
        score += weights["preferred_shift"]
        reason_codes.append("PREFERRED_SHIFT")

    score += 10
    reason_codes.append("REST_OK")

    user_assignments = assignments_by_user[user_id]
    total_load = len(user_assignments)
    night_count = sum(1 for a in user_assignments if a["shiftName"] == "Night")
    weekend_count = sum(1 for a in user_assignments if _is_weekend(a["date"]))

    if total_load <= 3:
        score += weights["low_total_load"]
        reason_codes.append("LOW_TOTAL_LOAD")
    elif total_load <= 5:
        score += max(4, weights["low_total_load"] // 2)

    if night_count <= 1:
        score += weights["low_night_bias"]
        reason_codes.append("LOW_NIGHT_BIAS")
    elif night_count <= 2:
        score += max(3, weights["low_night_bias"] // 2)

    if weekend_count <= 1:
        score += weights["low_weekend_bias"]
        reason_codes.append("LOW_WEEKEND_BIAS")
    elif weekend_count <= 2:
        score += max(2, weights["low_weekend_bias"] // 2)

    if _consecutive_days_count(user_assignments, target_date) < int(rules.get("maxConsecutiveDays", 5)):
        score += 5
        reason_codes.append("FAIRNESS_FRIENDLY")

    return score, reason_codes[:5]


def _normalize_user_request(user_request: Optional[List[str] | str]) -> str:
    if not user_request:
        return ""
    if isinstance(user_request, str):
        return user_request.strip()
    return ", ".join(str(x).strip() for x in user_request if x is not None and str(x).strip())


def _build_shift_datetimes(date_str: str, shift: Dict[str, Any]) -> Tuple[datetime, datetime]:
    day_value = datetime.strptime(date_str, DATE_FMT).date()
    start_t = datetime.strptime(shift["startTime"], TIME_FMT).time()
    end_t = datetime.strptime(shift["endTime"], TIME_FMT).time()
    start_dt = datetime.combine(day_value, start_t)
    end_dt = datetime.combine(day_value, end_t)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def _is_weekend(date_str: str) -> bool:
    return datetime.strptime(date_str, DATE_FMT).weekday() >= 5


def _consecutive_days_count(assignments: List[Dict[str, Any]], target_date: str) -> int:
    worked_dates = {
        datetime.strptime(a["date"], DATE_FMT).date()
        for a in assignments
    }
    target = datetime.strptime(target_date, DATE_FMT).date()
    worked_dates.add(target)

    count = 1

    cur = target - timedelta(days=1)
    while cur in worked_dates:
        count += 1
        cur -= timedelta(days=1)

    cur = target + timedelta(days=1)
    while cur in worked_dates:
        count += 1
        cur += timedelta(days=1)

    return count