from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


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


def _minutes_between(end_dt: datetime, next_start_dt: datetime) -> int:
    return int((next_start_dt - end_dt).total_seconds() // 60)


def _build_shift_maps(shifts: Sequence[Dict[str, Any]]) -> tuple[dict[str, Dict[str, Any]], dict[str, int]]:
    by_name = {shift["name"]: shift for shift in shifts}
    idx_map = {shift["name"]: idx for idx, shift in enumerate(shifts)}
    return by_name, idx_map


def _group_assignments_by_employee(
    assignments: Sequence[Dict[str, Any]],
) -> Dict[int, List[Dict[str, Any]]]:
    grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for item in assignments:
        grouped[int(item["userId"])].append(item)
    for user_id in grouped:
        grouped[user_id].sort(key=lambda x: (x["date"], x["startTime"], x["shiftName"]))
    return grouped


def _group_assignments_by_employee_and_date(
    assignments: Sequence[Dict[str, Any]],
) -> Dict[tuple[int, str], List[Dict[str, Any]]]:
    grouped: Dict[tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
    for item in assignments:
        grouped[(int(item["userId"]), item["date"])].append(item)
    return grouped


def _normalize_vacancy(
    vacancy: Dict[str, Any],
    schedule_assignments: Sequence[Dict[str, Any]],
    shift_by_name: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    normalized = dict(vacancy)

    if "shiftName" not in normalized:
        raise ValueError("vacancy.shiftName은 필수입니다.")
    if "date" not in normalized:
        raise ValueError("vacancy.date는 필수입니다.")

    shift = shift_by_name.get(normalized["shiftName"])
    if not shift:
        raise ValueError(f"vacancy.shiftName '{normalized['shiftName']}' 에 해당하는 shift가 없습니다.")

    normalized.setdefault("startTime", shift["startTime"])
    normalized.setdefault("endTime", shift["endTime"])
    normalized.setdefault("requiredRoles", shift.get("requiredRoles", []))
    normalized.setdefault("requiredSkills", shift.get("requiredSkills", []))
    normalized.setdefault("isNight", bool(shift.get("isNight", False)))
    normalized.setdefault("requiredCount", int(shift.get("requiredCount", shift.get("minStaff", 1))))

    if "assignmentId" in normalized:
        for item in schedule_assignments:
            if item.get("assignmentId") == normalized["assignmentId"]:
                normalized.setdefault("userId", item.get("userId"))
                normalized.setdefault("userName", item.get("userName"))
                break

    return normalized


def _remove_vacancy_assignment(
    assignments: Sequence[Dict[str, Any]],
    vacancy: Dict[str, Any],
) -> List[Dict[str, Any]]:
    filtered = []
    for item in assignments:
        is_same_assignment = False

        if vacancy.get("assignmentId") is not None and item.get("assignmentId") == vacancy.get("assignmentId"):
            is_same_assignment = True
        elif (
            vacancy.get("userId") is not None
            and item.get("userId") == vacancy.get("userId")
            and item.get("date") == vacancy.get("date")
            and item.get("shiftName") == vacancy.get("shiftName")
        ):
            is_same_assignment = True

        if not is_same_assignment:
            filtered.append(item)
    return filtered


def _has_required_role(employee: Dict[str, Any], required_roles: Sequence[str]) -> bool:
    if not required_roles:
        return True
    return set(required_roles).issubset(set(employee.get("roles", [])))


def _has_required_skill(employee: Dict[str, Any], required_skills: Sequence[str]) -> bool:
    if not required_skills:
        return True
    return set(required_skills).issubset(set(employee.get("skills", [])))


def _has_available_shift(employee: Dict[str, Any], shift_name: str) -> bool:
    available_shifts = employee.get("availableShifts")
    if not available_shifts:
        return True
    return shift_name in set(available_shifts)


def _is_off_day(employee: Dict[str, Any], day_label: str) -> bool:
    return day_label in set(employee.get("offDays", []))


def _is_same_day_already_assigned(
    user_id: int,
    day_label: str,
    assignments_by_employee_date: Dict[tuple[int, str], List[Dict[str, Any]]],
) -> bool:
    return len(assignments_by_employee_date.get((user_id, day_label), [])) > 0


def _find_neighbor_assignments(
    user_id: int,
    assignments_by_employee: Dict[int, List[Dict[str, Any]]],
    target_date: str,
    target_shift_name: str,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    user_assignments = assignments_by_employee.get(user_id, [])
    target_key = (target_date, target_shift_name)

    previous_item = None
    next_item = None

    sorted_items = sorted(user_assignments, key=lambda x: (x["date"], x["startTime"], x["shiftName"]))
    for item in sorted_items:
        item_key = (item["date"], item["shiftName"])
        if item_key < target_key:
            previous_item = item
        elif item_key > target_key and next_item is None:
            next_item = item
            break

    return previous_item, next_item


def _violates_min_rest(
    user_id: int,
    vacancy: Dict[str, Any],
    assignments_by_employee: Dict[int, List[Dict[str, Any]]],
    shift_by_name: Dict[str, Dict[str, Any]],
    min_rest_hours: int,
) -> bool:
    previous_item, next_item = _find_neighbor_assignments(
        user_id=user_id,
        assignments_by_employee=assignments_by_employee,
        target_date=vacancy["date"],
        target_shift_name=vacancy["shiftName"],
    )

    vacancy_shift = {
        "name": vacancy["shiftName"],
        "startTime": vacancy["startTime"],
        "endTime": vacancy["endTime"],
    }
    vacancy_day = _parse_date(vacancy["date"])
    vacancy_start_dt, vacancy_end_dt = _build_shift_datetimes(vacancy_day, vacancy_shift)

    if previous_item:
        previous_day = _parse_date(previous_item["date"])
        prev_shift = shift_by_name[previous_item["shiftName"]]
        _, prev_end_dt = _build_shift_datetimes(previous_day, prev_shift)
        if _minutes_between(prev_end_dt, vacancy_start_dt) < min_rest_hours * 60:
            return True

    if next_item:
        next_day = _parse_date(next_item["date"])
        next_shift = shift_by_name[next_item["shiftName"]]
        next_start_dt, _ = _build_shift_datetimes(next_day, next_shift)
        if _minutes_between(vacancy_end_dt, next_start_dt) < min_rest_hours * 60:
            return True

    return False


def _count_assignments(user_id: int, assignments_by_employee: Dict[int, List[Dict[str, Any]]]) -> int:
    return len(assignments_by_employee.get(user_id, []))


def _count_night_assignments(
    user_id: int,
    assignments_by_employee: Dict[int, List[Dict[str, Any]]],
    shift_by_name: Dict[str, Dict[str, Any]],
) -> int:
    count = 0
    for item in assignments_by_employee.get(user_id, []):
        if shift_by_name[item["shiftName"]].get("isNight", False):
            count += 1
    return count


def _count_weekend_assignments(
    user_id: int,
    assignments_by_employee: Dict[int, List[Dict[str, Any]]],
) -> int:
    count = 0
    for item in assignments_by_employee.get(user_id, []):
        if _parse_date(item["date"]).weekday() >= 5:
            count += 1
    return count


def _consecutive_days_if_assigned(
    user_id: int,
    assignments_by_employee: Dict[int, List[Dict[str, Any]]],
    vacancy_date: str,
) -> int:
    worked_dates = {_parse_date(item["date"]) for item in assignments_by_employee.get(user_id, [])}
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


def _build_template_explanation(reason_tags: Sequence[str]) -> str:
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
    parts = [mapping[tag] for tag in reason_tags if tag in mapping]
    if not parts:
        return "근무 규칙을 충족해 대체 인력 후보로 추천됩니다."

    if len(parts) == 1:
        text = parts[0]
    else:
        text = " ".join(parts[:-1] + [parts[-1]])

    if not text.endswith(("니다.", "고")):
        text += " 추천 후보입니다."
    elif text.endswith("고"):
        text += " 추천 후보입니다."
    return text


def _score_candidate(
    employee: Dict[str, Any],
    vacancy: Dict[str, Any],
    assignments_by_employee: Dict[int, List[Dict[str, Any]]],
    shift_by_name: Dict[str, Dict[str, Any]],
) -> tuple[int, List[str]]:
    user_id = int(employee["userId"])
    total_count = _count_assignments(user_id, assignments_by_employee)
    night_count = _count_night_assignments(user_id, assignments_by_employee, shift_by_name)
    weekend_count = _count_weekend_assignments(user_id, assignments_by_employee)
    consecutive_count = _consecutive_days_if_assigned(user_id, assignments_by_employee, vacancy["date"])

    score = 100
    reason_tags: List[str] = ["ROLE_MATCH", "REST_OK"]

    if vacancy.get("requiredSkills"):
        reason_tags.append("SKILL_MATCH")

    score -= int(total_count * 2)
    score -= int(night_count * 3)
    score -= int(weekend_count * 2)
    score -= int(max(consecutive_count - 1, 0) * 4)

    if vacancy["shiftName"] in set(employee.get("preferredShifts", [])):
        score += 8
        reason_tags.append("PREFERRED_SHIFT")

    if total_count <= 0 or total_count <= 2:
        reason_tags.append("LOW_TOTAL_LOAD")

    if vacancy.get("isNight") and night_count <= 1:
        reason_tags.append("LOW_NIGHT_BIAS")

    if _parse_date(vacancy["date"]).weekday() >= 5 and weekend_count <= 1:
        reason_tags.append("LOW_WEEKEND_BIAS")

    if consecutive_count <= 3:
        reason_tags.append("FAIRNESS_FRIENDLY")

    return max(score, 0), reason_tags


def _validate_candidate(
    employee: Dict[str, Any],
    vacancy: Dict[str, Any],
    assignments_by_employee: Dict[int, List[Dict[str, Any]]],
    assignments_by_employee_date: Dict[tuple[int, str], List[Dict[str, Any]]],
    shift_by_name: Dict[str, Dict[str, Any]],
    rules: Dict[str, Any],
) -> tuple[bool, List[str]]:
    user_id = int(employee["userId"])
    reasons: List[str] = []

    if vacancy.get("userId") is not None and int(vacancy["userId"]) == user_id:
        reasons.append("SAME_AS_ABSENT_EMPLOYEE")

    if _is_off_day(employee, vacancy["date"]):
        reasons.append("OFF_DAY")

    if not _has_available_shift(employee, vacancy["shiftName"]):
        reasons.append("SHIFT_NOT_AVAILABLE")

    if not _has_required_role(employee, vacancy.get("requiredRoles", [])):
        reasons.append("ROLE_MISMATCH")

    if not _has_required_skill(employee, vacancy.get("requiredSkills", [])):
        reasons.append("SKILL_MISMATCH")

    if _is_same_day_already_assigned(user_id, vacancy["date"], assignments_by_employee_date):
        reasons.append("ALREADY_ASSIGNED_SAME_DAY")

    min_rest_hours = int(rules.get("minRestHours", 11))
    if _violates_min_rest(user_id, vacancy, assignments_by_employee, shift_by_name, min_rest_hours):
        reasons.append("REST_VIOLATION")

    max_assignments = int(employee.get("maxAssignments", 10**9))
    if _count_assignments(user_id, assignments_by_employee) + 1 > max_assignments:
        reasons.append("MAX_ASSIGNMENTS_EXCEEDED")

    max_consecutive = int(employee.get("maxConsecutiveDays", rules.get("maxConsecutiveDays", 10**9)))
    if _consecutive_days_if_assigned(user_id, assignments_by_employee, vacancy["date"]) > max_consecutive:
        reasons.append("MAX_CONSECUTIVE_DAYS_EXCEEDED")

    return len(reasons) == 0, reasons


def recommend_replacements(
    payload: Dict[str, Any],
    top_k: int = 5,
    explainer: Optional[Callable[[Dict[str, Any], Dict[str, Any]], str]] = None,
) -> Dict[str, Any]:
    """
    payload 예시:
    {
      "schedule": {
        "assignments": [
          {
            "assignmentId": 1,
            "date": "2026-04-12",
            "userId": 101,
            "userName": "김민지",
            "shiftName": "Night",
            "startTime": "23:00",
            "endTime": "07:00"
          }
        ]
      },
      "vacancy": {
        "assignmentId": 1,
        "date": "2026-04-12",
        "shiftName": "Night",
        "userId": 101
      },
      "rules": {
        "minRestHours": 11,
        "maxConsecutiveDays": 5
      },
      "employees": [...],
      "shifts": [...]
    }
    """
    schedule = payload.get("schedule", {})
    assignments = schedule.get("assignments", [])
    vacancy_input = payload.get("vacancy")
    rules = payload.get("rules", {})
    employees = payload.get("employees", [])
    shifts = payload.get("shifts", [])

    if not vacancy_input:
        raise ValueError("vacancy는 필수입니다.")
    if not employees:
        raise ValueError("employees는 비어 있을 수 없습니다.")
    if not shifts:
        raise ValueError("shifts는 비어 있을 수 없습니다.")

    shift_by_name, _ = _build_shift_maps(shifts)
    vacancy = _normalize_vacancy(vacancy_input, assignments, shift_by_name)

    effective_assignments = _remove_vacancy_assignment(assignments, vacancy)
    assignments_by_employee = _group_assignments_by_employee(effective_assignments)
    assignments_by_employee_date = _group_assignments_by_employee_and_date(effective_assignments)

    candidates: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for employee in employees:
        valid, fail_reasons = _validate_candidate(
            employee=employee,
            vacancy=vacancy,
            assignments_by_employee=assignments_by_employee,
            assignments_by_employee_date=assignments_by_employee_date,
            shift_by_name=shift_by_name,
            rules=rules,
        )

        if not valid:
            excluded.append(
                {
                    "userId": employee["userId"],
                    "userName": employee["userName"],
                    "excludedReasons": fail_reasons,
                }
            )
            continue

        score, reason_tags = _score_candidate(
            employee=employee,
            vacancy=vacancy,
            assignments_by_employee=assignments_by_employee,
            shift_by_name=shift_by_name,
        )

        candidate = {
            "userId": employee["userId"],
            "userName": employee["userName"],
            "score": score,
            "reasonTags": reason_tags,
            "rank": 0,
        }

        if explainer:
            candidate["explanation"] = explainer(candidate, vacancy)
        else:
            candidate["explanation"] = _build_template_explanation(reason_tags)

        candidates.append(candidate)

    candidates.sort(key=lambda x: (-x["score"], x["userName"]))

    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank

    return {
        "vacancy": {
            "assignmentId": vacancy.get("assignmentId"),
            "date": vacancy["date"],
            "userId": vacancy.get("userId"),
            "userName": vacancy.get("userName"),
            "shiftName": vacancy["shiftName"],
            "startTime": vacancy["startTime"],
            "endTime": vacancy["endTime"],
            "requiredRoles": vacancy.get("requiredRoles", []),
            "requiredSkills": vacancy.get("requiredSkills", []),
            "requiredCount": vacancy.get("requiredCount", 1),
        },
        "recommendedCandidates": candidates[:top_k],
        "excludedCandidates": excluded,
        "meta": {
            "candidateCount": len(candidates),
            "excludedCount": len(excluded),
            "topK": top_k,
        },
    }
