from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


@dataclass
class CandidateEvaluation:
    user_id: int
    user_name: str
    valid: bool
    score: int
    reason_tags: List[str]
    explanation: str
    fail_reasons: List[str]
    metrics: Dict[str, Any]


def _parse_date(value: str) -> date:
    return datetime.strptime(value, DATE_FMT).date()


def _parse_time(value: str) -> time:
    return datetime.strptime(value, TIME_FMT).time()


def _build_shift_datetimes(day_value: date, shift: Dict[str, Any]) -> Tuple[datetime, datetime]:
    start_t = _parse_time(shift["startTime"])
    end_t = _parse_time(shift["endTime"])
    start_dt = datetime.combine(day_value, start_t)
    end_dt = datetime.combine(day_value, end_t)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def _hours_between(end_dt: datetime, next_start_dt: datetime) -> float:
    return (next_start_dt - end_dt).total_seconds() / 3600


def _is_weekend(day_value: date) -> bool:
    return day_value.weekday() >= 5


def _normalize_assignments(existing_assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in existing_assignments:
        normalized.append(
            {
                "assignmentId": item.get("assignmentId"),
                "date": item["date"],
                "userId": item["userId"],
                "shiftName": item["shiftName"],
            }
        )
    return normalized


def _build_shift_lookup(shifts: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {shift["name"]: shift for shift in shifts}


def _group_assignments_by_user(existing_assignments: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for item in existing_assignments:
        grouped[item["userId"]].append(item)
    grouped = dict(grouped)
    for user_id, items in grouped.items():
        items.sort(key=lambda x: (x["date"], x["shiftName"]))
        grouped[user_id] = items
    return grouped


def _consecutive_days_if_assigned(
    user_assignments: List[Dict[str, Any]],
    vacancy_date: str,
) -> int:
    worked_dates = {_parse_date(item["date"]) for item in user_assignments}
    target = _parse_date(vacancy_date)
    worked_dates.add(target)

    streak = 1
    cursor = target - timedelta(days=1)
    while cursor in worked_dates:
        streak += 1
        cursor -= timedelta(days=1)

    cursor = target + timedelta(days=1)
    while cursor in worked_dates:
        streak += 1
        cursor += timedelta(days=1)

    return streak


def _count_assignments(
    user_assignments: List[Dict[str, Any]],
    shifts_by_name: Dict[str, Dict[str, Any]],
) -> Dict[str, int]:
    total = len(user_assignments)
    night = 0
    weekend = 0
    for item in user_assignments:
        shift = shifts_by_name[item["shiftName"]]
        if shift.get("isNight", False):
            night += 1
        if _is_weekend(_parse_date(item["date"])):
            weekend += 1
    return {"total": total, "night": night, "weekend": weekend}


def _same_day_assignment_exists(user_assignments: List[Dict[str, Any]], vacancy_date: str) -> bool:
    return any(item["date"] == vacancy_date for item in user_assignments)


def _rest_violations(
    employee: Dict[str, Any],
    user_assignments: List[Dict[str, Any]],
    vacancy: Dict[str, Any],
    shifts_by_name: Dict[str, Dict[str, Any]],
    rules: Dict[str, Any],
) -> List[str]:
    min_rest_hours = int(rules.get("minRestHours", 11))
    vacancy_date = _parse_date(vacancy["date"])
    vacancy_shift = shifts_by_name[vacancy["shiftName"]]
    vacancy_start_dt, vacancy_end_dt = _build_shift_datetimes(vacancy_date, vacancy_shift)

    reasons: List[str] = []
    for assignment in user_assignments:
        assigned_date = _parse_date(assignment["date"])
        assigned_shift = shifts_by_name[assignment["shiftName"]]
        assigned_start_dt, assigned_end_dt = _build_shift_datetimes(assigned_date, assigned_shift)

        if assigned_date == vacancy_date:
            reasons.append("ALREADY_ASSIGNED_SAME_DAY")
            continue

        if assigned_end_dt <= vacancy_start_dt:
            rest = _hours_between(assigned_end_dt, vacancy_start_dt)
            if rest < min_rest_hours:
                reasons.append("REST_VIOLATION_PREV_SHIFT")
        elif vacancy_end_dt <= assigned_start_dt:
            rest = _hours_between(vacancy_end_dt, assigned_start_dt)
            if rest < min_rest_hours:
                reasons.append("REST_VIOLATION_NEXT_SHIFT")

    return sorted(set(reasons))


def _check_hard_constraints(
    employee: Dict[str, Any],
    vacancy: Dict[str, Any],
    shifts_by_name: Dict[str, Dict[str, Any]],
    user_assignments: List[Dict[str, Any]],
    rules: Dict[str, Any],
) -> List[str]:
    fail_reasons: List[str] = []
    vacancy_date = vacancy["date"]
    vacancy_shift = shifts_by_name[vacancy["shiftName"]]

    if employee["userId"] == vacancy.get("absentUserId"):
        fail_reasons.append("ABSENT_USER")

    if vacancy_date in set(employee.get("offDays", [])):
        fail_reasons.append("OFF_DAY")

    available_shifts = set(employee.get("availableShifts", list(shifts_by_name.keys())))
    if vacancy["shiftName"] not in available_shifts:
        fail_reasons.append("SHIFT_NOT_AVAILABLE")

    employee_roles = set(employee.get("roles", []))
    required_roles = set(vacancy_shift.get("requiredRoles", []))
    if required_roles and not required_roles.issubset(employee_roles):
        fail_reasons.append("ROLE_MISMATCH")

    employee_skills = set(employee.get("skills", []))
    required_skills = set(vacancy_shift.get("requiredSkills", []))
    if required_skills and not required_skills.issubset(employee_skills):
        fail_reasons.append("SKILL_MISMATCH")

    if _same_day_assignment_exists(user_assignments, vacancy_date):
        fail_reasons.append("ALREADY_ASSIGNED_SAME_DAY")

    fail_reasons.extend(_rest_violations(employee, user_assignments, vacancy, shifts_by_name, rules))

    max_assignments = int(employee.get("maxAssignments", 10**9))
    if len(user_assignments) + 1 > max_assignments:
        fail_reasons.append("MAX_ASSIGNMENTS_EXCEEDED")

    max_consecutive_days = int(employee.get("maxConsecutiveDays", rules.get("maxConsecutiveDays", 10**9)))
    if _consecutive_days_if_assigned(user_assignments, vacancy_date) > max_consecutive_days:
        fail_reasons.append("MAX_CONSECUTIVE_DAYS_EXCEEDED")

    return sorted(set(fail_reasons))


def _build_reason_tags(
    employee: Dict[str, Any],
    vacancy: Dict[str, Any],
    shifts_by_name: Dict[str, Dict[str, Any]],
    counts: Dict[str, int],
    consecutive_days: int,
) -> List[str]:
    tags: List[str] = ["REST_OK"]
    shift = shifts_by_name[vacancy["shiftName"]]

    if set(shift.get("requiredRoles", [])).issubset(set(employee.get("roles", []))):
        tags.append("ROLE_MATCH")
    if set(shift.get("requiredSkills", [])).issubset(set(employee.get("skills", []))):
        tags.append("SKILL_MATCH")
    if vacancy["shiftName"] in set(employee.get("preferredShifts", [])):
        tags.append("PREFERRED_SHIFT")
    if counts["night"] <= 1:
        tags.append("LOW_NIGHT_BIAS")
    if counts["weekend"] <= 1:
        tags.append("LOW_WEEKEND_BIAS")
    if counts["total"] <= 3:
        tags.append("LOW_TOTAL_LOAD")
    if consecutive_days <= 2:
        tags.append("FAIRNESS_FRIENDLY")

    return tags


def _build_explanation(reason_tags: List[str], counts: Dict[str, int]) -> str:
    messages = []
    mapping = {
        "ROLE_MATCH": "역할 요건을 충족하고",
        "SKILL_MATCH": "필요 스킬을 보유했으며",
        "PREFERRED_SHIFT": "선호 근무와 일치하고",
        "REST_OK": "최소 휴식시간을 만족하며",
        "LOW_NIGHT_BIAS": "현재 야간 편중이 낮고",
        "LOW_WEEKEND_BIAS": "현재 주말 편중이 낮고",
        "LOW_TOTAL_LOAD": "전체 배정 부담이 비교적 낮고",
        "FAIRNESS_FRIENDLY": "연속 근무 부담도 과하지 않습니다",
    }

    for tag in reason_tags:
        if tag in mapping:
            messages.append(mapping[tag])

    if not messages:
        return "규칙을 만족하는 대체 가능 인원입니다."

    sentence = " ".join(messages)
    sentence = sentence.rstrip("고며고")
    return f"{sentence} 현재 총 배정 {counts['total']}회 기준으로 대체 후보로 적합합니다."


def _score_candidate(
    employee: Dict[str, Any],
    vacancy: Dict[str, Any],
    shifts_by_name: Dict[str, Dict[str, Any]],
    user_assignments: List[Dict[str, Any]],
    rules: Dict[str, Any],
) -> Tuple[int, List[str], Dict[str, Any], str]:
    counts = _count_assignments(user_assignments, shifts_by_name)
    consecutive_days = _consecutive_days_if_assigned(user_assignments, vacancy["date"])
    score = 100

    fairness_weight = int(rules.get("fairnessWeight", 4))
    weekend_weight = int(rules.get("weekendWeight", 2))
    night_weight = int(rules.get("nightWeight", 3))
    preference_weight = int(rules.get("preferenceWeight", 3))

    score -= counts["total"] * fairness_weight
    score -= counts["weekend"] * weekend_weight
    score -= counts["night"] * night_weight
    score -= consecutive_days * 4

    if vacancy["shiftName"] in set(employee.get("preferredShifts", [])):
        score += 5 + preference_weight

    if _is_weekend(_parse_date(vacancy["date"])) and counts["weekend"] == 0:
        score += 4

    if shifts_by_name[vacancy["shiftName"]].get("isNight", False) and counts["night"] == 0:
        score += 5

    reason_tags = _build_reason_tags(employee, vacancy, shifts_by_name, counts, consecutive_days)
    explanation = _build_explanation(reason_tags, counts)
    metrics = {
        "existingTotalAssignments": counts["total"],
        "existingNightAssignments": counts["night"],
        "existingWeekendAssignments": counts["weekend"],
        "consecutiveDaysIfAssigned": consecutive_days,
    }
    return max(score, 0), reason_tags, metrics, explanation


def evaluate_candidate(
    employee: Dict[str, Any],
    vacancy: Dict[str, Any],
    shifts_by_name: Dict[str, Dict[str, Any]],
    user_assignments: List[Dict[str, Any]],
    rules: Dict[str, Any],
) -> CandidateEvaluation:
    fail_reasons = _check_hard_constraints(employee, vacancy, shifts_by_name, user_assignments, rules)
    if fail_reasons:
        return CandidateEvaluation(
            user_id=employee["userId"],
            user_name=employee["userName"],
            valid=False,
            score=0,
            reason_tags=[],
            explanation="",
            fail_reasons=fail_reasons,
            metrics={},
        )

    score, reason_tags, metrics, explanation = _score_candidate(
        employee=employee,
        vacancy=vacancy,
        shifts_by_name=shifts_by_name,
        user_assignments=user_assignments,
        rules=rules,
    )
    return CandidateEvaluation(
        user_id=employee["userId"],
        user_name=employee["userName"],
        valid=True,
        score=score,
        reason_tags=reason_tags,
        explanation=explanation,
        fail_reasons=[],
        metrics=metrics,
    )


def recommend_replacements(payload: Dict[str, Any]) -> Dict[str, Any]:
    employees = payload.get("employees", [])
    shifts = payload.get("shifts", [])
    rules = payload.get("rules", {})
    vacancy = payload.get("vacancy")
    existing_assignments = _normalize_assignments(payload.get("existingAssignments", []))
    top_k = int(payload.get("topK", 5))

    if not vacancy:
        raise ValueError("vacancy는 필수입니다.")
    if not employees:
        raise ValueError("employees는 비어 있을 수 없습니다.")
    if not shifts:
        raise ValueError("shifts는 비어 있을 수 없습니다.")
    if vacancy.get("shiftName") is None:
        raise ValueError("vacancy.shiftName은 필수입니다.")
    if vacancy.get("date") is None:
        raise ValueError("vacancy.date는 필수입니다.")

    shifts_by_name = _build_shift_lookup(shifts)
    if vacancy["shiftName"] not in shifts_by_name:
        raise ValueError(f"알 수 없는 shiftName입니다: {vacancy['shiftName']}")

    assignments_by_user = _group_assignments_by_user(existing_assignments)
    recommended_candidates: List[Dict[str, Any]] = []
    excluded_candidates: List[Dict[str, Any]] = []

    for employee in employees:
        evaluation = evaluate_candidate(
            employee=employee,
            vacancy=vacancy,
            shifts_by_name=shifts_by_name,
            user_assignments=assignments_by_user.get(employee["userId"], []),
            rules=rules,
        )

        if not evaluation.valid:
            excluded_candidates.append(
                {
                    "userId": evaluation.user_id,
                    "userName": evaluation.user_name,
                    "reason": evaluation.fail_reasons[0],
                    "allFailReasons": evaluation.fail_reasons,
                }
            )
            continue

        recommended_candidates.append(
            {
                "userId": evaluation.user_id,
                "userName": evaluation.user_name,
                "score": evaluation.score,
                "reasonTags": evaluation.reason_tags,
                "explanation": evaluation.explanation,
                "metrics": evaluation.metrics,
            }
        )

    recommended_candidates.sort(
        key=lambda x: (
            -x["score"],
            x["metrics"]["existingTotalAssignments"],
            x["metrics"]["existingNightAssignments"],
            x["userId"],
        )
    )

    for rank, candidate in enumerate(recommended_candidates, start=1):
        candidate["rank"] = rank

    return {
        "assignmentId": vacancy.get("assignmentId"),
        "vacancy": {
            "date": vacancy["date"],
            "shiftName": vacancy["shiftName"],
            "startTime": shifts_by_name[vacancy["shiftName"]]["startTime"],
            "endTime": shifts_by_name[vacancy["shiftName"]]["endTime"],
            "requiredRoles": shifts_by_name[vacancy["shiftName"]].get("requiredRoles", []),
            "requiredSkills": shifts_by_name[vacancy["shiftName"]].get("requiredSkills", []),
            "absentUserId": vacancy.get("absentUserId"),
        },
        "recommendedCandidates": recommended_candidates[:top_k],
        "excludedCandidates": excluded_candidates,
        "meta": {
            "requestedTopK": top_k,
            "candidateCount": len(recommended_candidates),
            "excludedCount": len(excluded_candidates),
        },
    }


if __name__ == "__main__":
    sample_payload = {
        "rules": {
            "minRestHours": 11,
            "maxConsecutiveDays": 5,
            "fairnessWeight": 4,
            "preferenceWeight": 3,
            "weekendWeight": 2,
            "nightWeight": 6,
        },
        "vacancy": {
            "assignmentId": 845,
            "date": "2026-04-12",
            "shiftName": "Night",
            "absentUserId": 105,
        },
        "employees": [
            {
                "userId": 101,
                "userName": "김민지",
                "roles": ["nurse"],
                "skills": ["ICU"],
                "availableShifts": ["Day", "Evening", "Night"],
                "offDays": ["2026-04-12"],
                "preferredShifts": ["Day"],
                "maxAssignments": 21,
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
        "existingAssignments": [
            {"assignmentId": 1, "date": "2026-04-11", "userId": 106, "shiftName": "Day"},
            {"assignmentId": 2, "date": "2026-04-13", "userId": 106, "shiftName": "Evening"},
            {"assignmentId": 3, "date": "2026-04-10", "userId": 103, "shiftName": "Night"},
            {"assignmentId": 4, "date": "2026-04-11", "userId": 103, "shiftName": "Night"},
        ],
        "topK": 5,
    }

    import json
    print(json.dumps(recommend_replacements(sample_payload), ensure_ascii=False, indent=2))
