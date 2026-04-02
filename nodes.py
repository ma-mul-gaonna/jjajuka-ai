from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from solver import solve_shift_optimization

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, DATE_FMT)


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value, TIME_FMT)


def _date_range(start: datetime, end: datetime) -> List[datetime]:
    days = (end - start).days + 1
    if days <= 0:
        raise ValueError("endDate는 startDate보다 같거나 뒤여야 합니다.")
    return [start + timedelta(days=i) for i in range(days)]


def _shift_duration_hours(start_time: str, end_time: str) -> float:
    start_dt = _parse_time(start_time)
    end_dt = _parse_time(end_time)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return (end_dt - start_dt).total_seconds() / 3600.0


def _rest_hours_between(prev_shift: Dict[str, Any], next_shift: Dict[str, Any]) -> float:
    prev_start = _parse_time(prev_shift["startTime"])
    prev_end = _parse_time(prev_shift["endTime"])
    next_start = _parse_time(next_shift["startTime"])

    base = datetime(2026, 1, 1)
    prev_end_dt = base.replace(hour=prev_end.hour, minute=prev_end.minute)
    prev_start_dt = base.replace(hour=prev_start.hour, minute=prev_start.minute)
    next_start_dt = (base + timedelta(days=1)).replace(hour=next_start.hour, minute=next_start.minute)

    if prev_end_dt <= prev_start_dt:
        prev_end_dt += timedelta(days=1)

    return (next_start_dt - prev_end_dt).total_seconds() / 3600.0


def _normalize_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _employee_has_required(employee: Dict[str, Any], shift: Dict[str, Any]) -> bool:
    employee_roles = set(_normalize_list(employee.get("roles")))
    employee_skills = set(_normalize_list(employee.get("skills")))

    required_roles = set(_normalize_list(shift.get("requiredRoles")))
    required_skills = set(_normalize_list(shift.get("requiredSkills")))

    role_ok = not required_roles or bool(employee_roles & required_roles)
    skill_ok = required_skills.issubset(employee_skills)
    allowed_shifts = set(_normalize_list(employee.get("availableShifts")))
    shift_allowed = not allowed_shifts or shift["name"] in allowed_shifts
    return role_ok and skill_ok and shift_allowed


def _collect_off_dates(employee: Dict[str, Any]) -> set[str]:
    return set(_normalize_list(employee.get("offDays"))) | set(_normalize_list(employee.get("unavailableDates")))


def build_solver_params(input_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    start_date = _parse_date(input_data["startDate"])
    end_date = _parse_date(input_data["endDate"])
    days = _date_range(start_date, end_date)

    employees = input_data["employees"]
    shifts = input_data["shifts"]
    rules = input_data.get("rules", {})

    shift_names = [shift["name"] for shift in shifts]
    shift_index_by_name = {name: idx for idx, name in enumerate(shift_names)}

    min_rest_hours = int(rules.get("minRestHours", 11))
    default_max_consecutive_days = int(rules.get("maxConsecutiveDays", 5))

    fixed_offs: List[List[int]] = []
    preferences: List[List[int]] = []
    eligible: List[List[List[int]]] = []
    employee_max_consecutive_days: List[int] = []
    employee_max_assignments: List[int] = []

    warnings: List[str] = []
    weekend_day_indices = [idx for idx, day in enumerate(days) if day.weekday() >= 5]
    night_shift_indices = [idx for idx, shift in enumerate(shifts) if "night" in shift["name"].lower() or shift.get("isNight")]

    for employee in employees:
        off_dates = _collect_off_dates(employee)
        fixed_offs.append([
            idx for idx, day in enumerate(days)
            if day.strftime(DATE_FMT) in off_dates
        ])

        preferred_shift_names = set(_normalize_list(employee.get("preferredShifts")))
        preferences.append([
            shift_index_by_name[name]
            for name in preferred_shift_names
            if name in shift_index_by_name
        ])

        employee_max_consecutive_days.append(
            int(employee.get("maxConsecutiveDays", default_max_consecutive_days))
        )
        employee_max_assignments.append(
            int(employee.get("maxAssignments", len(days)))
        )

        employee_eligibility: List[List[int]] = []
        for day in days:
            day_key = day.strftime(DATE_FMT)
            shift_flags: List[int] = []
            for shift in shifts:
                can_work = _employee_has_required(employee, shift) and day_key not in off_dates
                shift_flags.append(1 if can_work else 0)
            employee_eligibility.append(shift_flags)
        eligible.append(employee_eligibility)

    required_staff = [int(shift.get("requiredCount", shift.get("minStaff", 1))) for shift in shifts]
    shift_hours = [_shift_duration_hours(shift["startTime"], shift["endTime"]) for shift in shifts]

    incompatible_shift_pairs: List[List[int]] = []
    for prev_s, prev_shift in enumerate(shifts):
        for next_s, next_shift in enumerate(shifts):
            rest_hours = _rest_hours_between(prev_shift, next_shift)
            if rest_hours < min_rest_hours:
                incompatible_shift_pairs.append([prev_s, next_s])

    precheck_issues: List[Dict[str, Any]] = []
    for d_idx, day in enumerate(days):
        for s_idx, shift in enumerate(shifts):
            candidate_indices = [
                e_idx for e_idx in range(len(employees))
                if eligible[e_idx][d_idx][s_idx] == 1
            ]
            required_count = required_staff[s_idx]
            if len(candidate_indices) < required_count:
                precheck_issues.append({
                    "date": day.strftime(DATE_FMT),
                    "shiftName": shift["name"],
                    "reason": f"정적 후보 부족: 필요 {required_count}명 / 가능 {len(candidate_indices)}명",
                    "candidateUserIds": [employees[e]["userId"] for e in candidate_indices],
                })
            elif len(candidate_indices) == required_count:
                warnings.append(
                    f"{day.strftime(DATE_FMT)} {shift['name']}은(는) 후보가 정확히 {required_count}명뿐이라 여유가 없습니다."
                )

    params = {
        "num_employees": len(employees),
        "num_days": len(days),
        "num_shifts": len(shifts),
        "shifts": shifts,
        "shift_names": shift_names,
        "required_staff": required_staff,
        "fixed_offs": fixed_offs,
        "preferences": preferences,
        "eligible": eligible,
        "incompatible_shift_pairs": incompatible_shift_pairs,
        "employee_max_consecutive_days": employee_max_consecutive_days,
        "employee_max_assignments": employee_max_assignments,
        "shift_hours": shift_hours,
        "weekend_day_indices": weekend_day_indices,
        "night_shift_indices": night_shift_indices,
        "rules": {
            "minRestHours": min_rest_hours,
            "maxConsecutiveDays": default_max_consecutive_days,
        },
        "precheck_issues": precheck_issues,
    }
    return params, warnings



def extract_params_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LLM 없이 입력 JSON을 deterministic 하게 OR-Tools 파라미터로 변환합니다."""
    params, warnings = build_solver_params(state["input_json"])
    return {
        "solver_params": params,
        "warnings": warnings,
    }



def solve_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """OR-Tools를 호출해 스케줄을 생성하거나 실패 사유를 반환합니다."""
    solve_result = solve_shift_optimization(state["solver_params"])
    if solve_result["status"] != "SUCCESS":
        return {
            "error_msg": solve_result["message"],
            "solve_result": solve_result,
        }
    return {
        "raw_schedule": solve_result["assignments"],
        "solve_result": solve_result,
    }



def format_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """최종 API 응답 형태로 포맷팅합니다."""
    input_json = state["input_json"]
    solver_params = state["solver_params"]
    solve_result = state["solve_result"]
    warnings = list(state.get("warnings", []))
    warnings.extend(solve_result.get("warnings", []))

    employees = input_json["employees"]
    shifts = input_json["shifts"]
    start_date = _parse_date(input_json["startDate"])

    assignments = []
    for item in solve_result.get("assignments", []):
        day_index = item["day_index"]
        employee_index = item["employee_index"]
        shift_index = item["shift_index"]

        date_str = (start_date + timedelta(days=day_index)).strftime(DATE_FMT)
        employee = employees[employee_index]
        shift = shifts[shift_index]
        assignments.append({
            "date": date_str,
            "userId": employee["userId"],
            "userName": employee["userName"],
            "shiftName": shift["name"],
            "startTime": shift["startTime"],
            "endTime": shift["endTime"],
        })

    assignments.sort(key=lambda x: (x["date"], x["shiftName"], x["userId"]))

    final_schedule = {
        "status": solve_result["status"],
        "message": solve_result["message"],
        "period": {
            "startDate": input_json["startDate"],
            "endDate": input_json["endDate"],
        },
        "appliedRules": solver_params["rules"],
        "assignments": assignments,
        "summary": solve_result.get("summary", {}),
        "fairness": solve_result.get("fairness", {}),
        "warnings": warnings,
        "unassignedShifts": solve_result.get("unassignedShifts", []),
    }
    return {"final_schedule": final_schedule}
