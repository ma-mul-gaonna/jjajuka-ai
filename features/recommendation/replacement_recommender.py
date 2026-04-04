from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from features.recommendation.reasoner import build_recommendation_reason_text
from features.scheduling.parser import parse_user_request


DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


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

    replaced_employee = employee_by_id[replaced_user_id]
    target_shift = shift_by_name[target_shift_name]

    normalized_user_request = _normalize_user_request(user_request)
    parse_result = parse_user_request(normalized_user_request, input_json)
    weights = _build_weights_from_instructions(parse_result)

    assignments_by_user: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for item in assignments:
        assignments_by_user[item["userId"]].append(item)

    warnings: List[Dict[str, Any] | str] = list(parse_result.get("warnings", []))
    raw_candidates: List[Dict[str, Any]] = []

    for employee in employees:
        user_id = employee["userId"]

        if user_id == replaced_user_id:
            continue

        eligible, _ = _is_candidate_eligible(
            employee=employee,
            target_date=target_date,
            target_shift=target_shift,
            assignments_by_user=assignments_by_user,
            input_json=input_json,
        )
        if not eligible:
            continue

        stats = _collect_candidate_stats(
            employee=employee,
            target_date=target_date,
            target_shift=target_shift,
            assignments_by_user=assignments_by_user,
            rules=rules,
        )

        raw_candidates.append(
            {
                "employee": employee,
                "stats": stats,
            }
        )

    candidates = _rank_candidates(
        raw_candidates=raw_candidates,
        target_shift=target_shift,
        absence=absence,
        user_request=normalized_user_request,
        weights=weights,
    )

    recommendations = []
    for idx, candidate in enumerate(candidates[:3], start=1):
        recommendations.append(
            {
                "rank": idx,
                "userId": candidate["userId"],
                "userName": candidate["userName"],
                "score": candidate["score"],
                "reasons": candidate["reasons"],
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
        "parserMode": parse_result.get("mode", "unknown"),
    }


def _build_weights_from_instructions(parse_result: Dict[str, Any]) -> Dict[str, int]:
    weights = {
        "preferred_shift": 10,
        "low_night_bias": 8,
        "low_weekend_bias": 5,
        "low_total_load": 10,
    }

    for inst in parse_result.get("instructions", []):
        if not inst.get("supported", False):
            continue

        inst_type = inst.get("type")
        if inst_type == "BOOST_NIGHT_FAIRNESS":
            weights["low_night_bias"] += int(inst.get("value", 8))
        elif inst_type == "BOOST_WEEKEND_FAIRNESS":
            weights["low_weekend_bias"] += int(inst.get("value", 5))
        elif inst_type == "PREFER_SHIFT":
            weights["preferred_shift"] += 4

    return weights


def _is_candidate_eligible(
    employee: Dict[str, Any],
    target_date: str,
    target_shift: Dict[str, Any],
    assignments_by_user: Dict[int, List[Dict[str, Any]]],
    input_json: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    user_id = employee["userId"]
    shifts = input_json.get("shifts", [])
    rules = input_json.get("rules", {})
    shift_name_to_obj = {s["name"]: s for s in shifts}

    if target_date in employee.get("offDays", []):
        return False, "OFF_DAY"

    available = employee.get("availableShifts")
    if available is not None and target_shift["name"] not in available:
        return False, "NOT_AVAILABLE_SHIFT"

    if target_shift["name"] in employee.get("forbiddenShifts", []):
        return False, "FORBIDDEN_SHIFT"

    max_shifts_per_day = int(rules.get("maxShiftsPerDay", 1))
    same_day_count = sum(1 for a in assignments_by_user[user_id] if a["date"] == target_date)
    if same_day_count >= max_shifts_per_day:
        return False, "MAX_SHIFTS_PER_DAY"

    required_roles = set(target_shift.get("requiredRoles", []))
    employee_roles = set(employee.get("roles", []))
    if required_roles and not required_roles.issubset(employee_roles):
        return False, "ROLE_MISMATCH"

    required_skills = set(target_shift.get("requiredSkills", []))
    employee_skills = set(employee.get("skills", []))
    if required_skills and not required_skills.issubset(employee_skills):
        return False, "SKILL_MISMATCH"

    min_rest_hours = int(rules.get("minRestHours", 11))
    target_start_dt, target_end_dt = _build_shift_datetimes(target_date, target_shift)

    for a in assignments_by_user[user_id]:
        other_shift = shift_name_to_obj.get(a["shiftName"])
        if not other_shift:
            continue

        other_start_dt, other_end_dt = _build_shift_datetimes(a["date"], other_shift)

        if a["date"] == target_date:
            return False, "ALREADY_ASSIGNED_SAME_DAY"

        if other_end_dt <= target_start_dt:
            gap = (target_start_dt - other_end_dt).total_seconds() / 3600
            if gap < min_rest_hours:
                return False, "REST_CONFLICT"

        if target_end_dt <= other_start_dt:
            gap = (other_start_dt - target_end_dt).total_seconds() / 3600
            if gap < min_rest_hours:
                return False, "REST_CONFLICT"

    return True, None


def _collect_candidate_stats(
    employee: Dict[str, Any],
    target_date: str,
    target_shift: Dict[str, Any],
    assignments_by_user: Dict[int, List[Dict[str, Any]]],
    rules: Dict[str, Any],
) -> Dict[str, Any]:
    user_id = employee["userId"]
    user_assignments = assignments_by_user[user_id]

    total_load = len(user_assignments)
    night_count = sum(1 for a in user_assignments if a["shiftName"] == "Night")
    weekend_count = sum(1 for a in user_assignments if _is_weekend(a["date"]))
    consecutive_days = _consecutive_days_count(user_assignments, target_date)
    preferred_shift_matched = target_shift["name"] in employee.get("preferredShifts", [])

    return {
        "totalLoad": total_load,
        "nightCount": night_count,
        "weekendCount": weekend_count,
        "consecutiveDays": consecutive_days,
        "preferredShiftMatched": preferred_shift_matched,
    }


def _rank_candidates(
    raw_candidates: List[Dict[str, Any]],
    target_shift: Dict[str, Any],
    absence: Dict[str, Any],
    user_request: str,
    weights: Dict[str, int],
) -> List[Dict[str, Any]]:
    if not raw_candidates:
        return []

    total_loads = [c["stats"]["totalLoad"] for c in raw_candidates]
    night_counts = [c["stats"]["nightCount"] for c in raw_candidates]
    weekend_counts = [c["stats"]["weekendCount"] for c in raw_candidates]
    consecutive_counts = [c["stats"]["consecutiveDays"] for c in raw_candidates]

    min_total, max_total = min(total_loads), max(total_loads)
    min_night, max_night = min(night_counts), max(night_counts)
    min_weekend, max_weekend = min(weekend_counts), max(weekend_counts)
    min_consecutive, max_consecutive = min(consecutive_counts), max(consecutive_counts)

    ranked: List[Dict[str, Any]] = []

    for item in raw_candidates:
        employee = item["employee"]
        stats = item["stats"]

        score = 0
        reason_details: List[Tuple[str, int]] = []

        score += 30
        reason_details.append(("ROLE_MATCH", 30))

        employee_skills = set(employee.get("skills", []))
        target_required_skills = set(target_shift.get("requiredSkills", []))
        if target_required_skills.issubset(employee_skills) or "GRADE_A" in employee_skills:
            score += 25
            reason_details.append(("SKILL_MATCH", 25))

        if stats["preferredShiftMatched"]:
            score += weights["preferred_shift"]
            reason_details.append(("PREFERRED_SHIFT", weights["preferred_shift"]))

        score += 10
        reason_details.append(("REST_OK", 10))

        total_load_score = _scaled_reverse(
            value=stats["totalLoad"],
            min_value=min_total,
            max_value=max_total,
            max_score=weights["low_total_load"],
        )
        score += total_load_score
        if total_load_score > 0:
            reason_details.append(("LOW_TOTAL_LOAD", total_load_score))

        night_score = _scaled_reverse(
            value=stats["nightCount"],
            min_value=min_night,
            max_value=max_night,
            max_score=weights["low_night_bias"],
        )
        score += night_score
        if night_score > 0:
            reason_details.append(("LOW_NIGHT_BIAS", night_score))

        weekend_score = _scaled_reverse(
            value=stats["weekendCount"],
            min_value=min_weekend,
            max_value=max_weekend,
            max_score=weights["low_weekend_bias"],
        )
        score += weekend_score
        if weekend_score > 0:
            reason_details.append(("LOW_WEEKEND_BIAS", weekend_score))

        fairness_score = _scaled_reverse(
            value=stats["consecutiveDays"],
            min_value=min_consecutive,
            max_value=max_consecutive,
            max_score=5,
        )
        score += fairness_score
        if fairness_score > 0:
            reason_details.append(("FAIRNESS_FRIENDLY", fairness_score))

        reason_codes = _select_reason_codes(
            stats=stats,
            min_total=min_total,
            min_night=min_night,
            min_weekend=min_weekend,
            min_consecutive=min_consecutive,
        )

        reason_text = build_recommendation_reason_text(
            employee=employee,
            absence=absence,
            reason_codes=reason_codes,
            score=score,
            user_request=user_request,
            stats={
                "totalLoad": stats["totalLoad"],
                "nightCount": stats["nightCount"],
                "weekendCount": stats["weekendCount"],
                "consecutiveDays": stats["consecutiveDays"],
                "preferredShiftMatched": stats["preferredShiftMatched"],
            },
        )

        ranked.append(
            {
                "userId": employee["userId"],
                "userName": employee["userName"],
                "score": score,
                "reasons": reason_text,
                "totalLoad": stats["totalLoad"],
                "nightCount": stats["nightCount"],
                "weekendCount": stats["weekendCount"],
                "preferredShiftMatched": stats["preferredShiftMatched"],
            }
        )

    ranked.sort(
        key=lambda x: (
            -x["score"],
            x["totalLoad"],
            x["nightCount"],
            x["weekendCount"],
            -int(x["preferredShiftMatched"]),
            x["userId"],
        )
    )
    return ranked


def _scaled_reverse(value: int, min_value: int, max_value: int, max_score: int) -> int:
    if max_score <= 0:
        return 0

    if max_value == min_value:
        return max_score // 2

    ratio = (max_value - value) / (max_value - min_value)
    return round(ratio * max_score)


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
    worked_dates = {datetime.strptime(a["date"], DATE_FMT).date() for a in assignments}
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

def _select_reason_codes(
    stats: Dict[str, Any],
    min_total: int,
    min_night: int,
    min_weekend: int,
    min_consecutive: int,
) -> List[str]:
    reason_codes: List[str] = []

    # 기본 자격
    reason_codes.append("ROLE_MATCH")
    reason_codes.append("REST_OK")

    # 후보별 상대 강점 우선 강조
    if stats["totalLoad"] == min_total:
        reason_codes.append("LOW_TOTAL_LOAD")

    if stats["nightCount"] == min_night:
        reason_codes.append("LOW_NIGHT_BIAS")

    if stats["weekendCount"] == min_weekend:
        reason_codes.append("LOW_WEEKEND_BIAS")

    if stats["preferredShiftMatched"]:
        reason_codes.append("PREFERRED_SHIFT")

    if stats["consecutiveDays"] == min_consecutive:
        reason_codes.append("FAIRNESS_FRIENDLY")

    # 중복 제거 + 최대 3개만
    deduped = []
    seen = set()
    for code in reason_codes:
        if code not in seen:
            seen.add(code)
            deduped.append(code)

    return deduped[:3]