from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Tuple

from features.scheduling.catalog import build_constraint_catalog
from features.scheduling.explain import generate_explanation
from features.scheduling.merge import apply_llm_overrides
from features.scheduling.parser import parse_user_request
from features.scheduling.solver import solve_shift_optimization


DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, DATE_FMT).date()


def _parse_time(value: str) -> time:
    return datetime.strptime(value, TIME_FMT).time()


def _minutes_between_shift_end_and_next_start(end_dt: datetime, next_start_dt: datetime) -> int:
    return int((next_start_dt - end_dt).total_seconds() // 60)


def _build_dates(start_date: str, end_date: str) -> List[date]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        raise ValueError("endDate는 startDate보다 빠를 수 없습니다.")
    total_days = (end - start).days + 1
    return [start + timedelta(days=i) for i in range(total_days)]


def _build_shift_datetimes(day_value: date, shift: Dict[str, Any]) -> Tuple[datetime, datetime]:
    start_t = _parse_time(shift["startTime"])
    end_t = _parse_time(shift["endTime"])
    start_dt = datetime.combine(day_value, start_t)
    end_dt = datetime.combine(day_value, end_t)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def _append_reason(reasons: List[Dict[str, Any]], reason: Dict[str, Any], seen: set[tuple]) -> None:
    key = (
        reason.get("reasonCode"),
        reason.get("date"),
        reason.get("shiftName"),
        reason.get("employeeId"),
        reason.get("detail"),
    )
    if key not in seen:
        seen.add(key)
        reasons.append(reason)


def llm_parse_node(state: Dict[str, Any]) -> Dict[str, Any]:
    base_input = state["input_json"]
    user_request = state.get("user_request")

    constraint_catalog = build_constraint_catalog()
    parse_result = parse_user_request(user_request, base_input)
    merged_input, applied, ignored, warnings = apply_llm_overrides(base_input, parse_result)

    return {
        "constraint_catalog": constraint_catalog,
        "input_json": merged_input,
        "llm_parse_result": parse_result,
        "applied_instructions": applied,
        "ignored_instructions": ignored,
        "parser_warnings": warnings,
    }


def extract_params_node(state: Dict[str, Any]) -> Dict[str, Any]:
    input_json = state["input_json"]
    rules = input_json.get("rules", {})
    employees = input_json.get("employees", [])
    shifts = input_json.get("shifts", [])
    if not employees:
        raise ValueError("employees는 비어 있을 수 없습니다.")
    if not shifts:
        raise ValueError("shifts는 비어 있을 수 없습니다.")

    dates = _build_dates(input_json["startDate"], input_json["endDate"])
    date_to_index = {d.strftime(DATE_FMT): idx for idx, d in enumerate(dates)}
    shift_name_to_index = {shift["name"]: idx for idx, shift in enumerate(shifts)}

    fixed_offs: List[List[int]] = []
    preferences: List[List[int]] = []
    employee_roles: List[set[str]] = []
    employee_skills: List[set[str]] = []
    employee_available_shifts: List[set[int]] = []
    employee_forbidden_shifts: List[set[int]] = []
    employee_max_assignments: List[int] = []
    employee_max_consecutive_days: List[int] = []

    for employee in employees:
        off_indices = sorted(date_to_index[d] for d in employee.get("offDays", []) if d in date_to_index)
        pref_indices = [
            shift_name_to_index[name]
            for name in employee.get("preferredShifts", [])
            if name in shift_name_to_index
        ]
        available_shift_names = employee.get("availableShifts", [shift["name"] for shift in shifts])
        available_shift_indices = {
            shift_name_to_index[name]
            for name in available_shift_names
            if name in shift_name_to_index
        }
        forbidden_shift_names = employee.get("forbiddenShifts", [])
        forbidden_shift_indices = {
            shift_name_to_index[name]
            for name in forbidden_shift_names
            if name in shift_name_to_index
        }

        fixed_offs.append(off_indices)
        preferences.append(pref_indices)
        employee_roles.append(set(employee.get("roles", [])))
        employee_skills.append(set(employee.get("skills", [])))
        employee_available_shifts.append(available_shift_indices)
        employee_max_assignments.append(int(employee.get("maxAssignments", len(dates))))
        employee_max_consecutive_days.append(
            int(employee.get("maxConsecutiveDays", rules.get("maxConsecutiveDays", len(dates))))
        )
        employee_forbidden_shifts.append(forbidden_shift_indices)

    shift_required_roles: List[set[str]] = []
    shift_required_skills: List[set[str]] = []
    shift_required_counts: List[int] = []
    shift_is_night: List[bool] = []
    rest_conflicts: List[Tuple[int, int, int]] = []
    day_to_is_weekend = [1 if d.weekday() >= 5 else 0 for d in dates]
    min_rest_hours = int(rules.get("minRestHours", 11))
    max_shifts_per_day = int(rules.get("maxShiftsPerDay", 1))
    shift_min_skill_coverage = []

    for shift in shifts:
        shift_required_roles.append(set(shift.get("requiredRoles", [])))
        shift_required_skills.append(set(shift.get("requiredSkills", [])))
        shift_required_counts.append(int(shift.get("requiredCount", shift.get("minStaff", 1))))
        shift_is_night.append(bool(shift.get("isNight", False)))

    for day_idx in range(len(dates) - 1):
        current_day = dates[day_idx]
        next_day = dates[day_idx + 1]
        for s1_idx, shift_1 in enumerate(shifts):
            _, end_dt = _build_shift_datetimes(current_day, shift_1)
            for s2_idx, shift_2 in enumerate(shifts):
                next_start_dt, _ = _build_shift_datetimes(next_day, shift_2)
                rest_hours = _minutes_between_shift_end_and_next_start(end_dt, next_start_dt) / 60
                if rest_hours < min_rest_hours:
                    rest_conflicts.append((day_idx, s1_idx, s2_idx))

    eligibility = []
    infeasible_reasons: List[Dict[str, Any]] = []
    seen_reasons: set[tuple] = set()

    for e_idx, employee in enumerate(employees):
        per_day = []
        for d_idx, _ in enumerate(dates):
            per_shift = []
            for s_idx, _ in enumerate(shifts):
                allowed = True
                if d_idx in fixed_offs[e_idx]:
                    allowed = False
                if s_idx not in employee_available_shifts[e_idx]:
                    allowed = False
                if s_idx in employee_forbidden_shifts[e_idx]:
                    allowed = False
                if shift_required_roles[s_idx] and not shift_required_roles[s_idx].issubset(employee_roles[e_idx]):
                    allowed = False
                if shift_required_skills[s_idx] and not shift_required_skills[s_idx].issubset(employee_skills[e_idx]):
                    allowed = False
                per_shift.append(allowed)
            per_day.append(per_shift)
        eligibility.append(per_day)

    total_required_assignments = sum(shift_required_counts) * len(dates)
    total_capacity = sum(employee_max_assignments)
    if total_capacity < total_required_assignments:
        _append_reason(
            infeasible_reasons,
            {
                "reasonCode": "TOTAL_CAPACITY_SHORTAGE",
                "detail": f"총 필요 배정 {total_required_assignments}건 > 직원 최대 배정 가능 합 {total_capacity}건",
                "requiredAssignments": total_required_assignments,
                "maxAssignable": total_capacity,
            },
            seen_reasons,
        )

    for d_idx, day_value in enumerate(dates):
        day_label = day_value.strftime(DATE_FMT)
        for s_idx, shift in enumerate(shifts):
            eligible_employee_indices = [
                e_idx for e_idx in range(len(employees)) if eligibility[e_idx][d_idx][s_idx]
            ]
            eligible_count = len(eligible_employee_indices)
            if eligible_count < shift_required_counts[s_idx]:
                _append_reason(
                    infeasible_reasons,
                    {
                        "reasonCode": "DAY_SHIFT_ELIGIBILITY_SHORTAGE",
                        "date": day_label,
                        "shiftName": shift["name"],
                        "detail": f"가능 인원 {eligible_count}명 / 필요 인원 {shift_required_counts[s_idx]}명",
                        "requiredCount": shift_required_counts[s_idx],
                        "eligibleCount": eligible_count,
                    },
                    seen_reasons,
                )

    for shift in shifts:
        shift_min_skill_coverage.append(shift.get("minSkillCoverage", []))

    solver_params = {
        "start_date": input_json["startDate"],
        "end_date": input_json["endDate"],
        "num_employees": len(employees),
        "num_days": len(dates),
        "num_shifts": len(shifts),
        "dates": [d.strftime(DATE_FMT) for d in dates],
        "day_to_is_weekend": day_to_is_weekend,
        "shifts": shifts,
        "fixed_offs": fixed_offs,
        "preferences": preferences,
        "eligibility": eligibility,
        "rest_conflicts": rest_conflicts,
        "employee_forbidden_shifts": employee_forbidden_shifts,
        "shift_required_counts": shift_required_counts,
        "shift_is_night": shift_is_night,
        "employee_max_assignments": employee_max_assignments,
        "employee_max_consecutive_days": employee_max_consecutive_days,
        "max_shifts_per_day": max_shifts_per_day,
        "weights": {
            "fairness": int(rules.get("fairnessWeight", 4)),
            "preference": int(rules.get("preferenceWeight", 3)),
            "weekend": int(rules.get("weekendWeight", 2)),
            "night": int(rules.get("nightWeight", 3)),
        },
        "solver_time_limit_seconds": int(rules.get("solverTimeLimitSeconds", 15)),
        "precheck_infeasible_reasons": infeasible_reasons,
        "shift_min_skill_coverage": shift_min_skill_coverage,
        "employees": employees,
    }
    return {"solver_params": solver_params}


def solve_node(state: Dict[str, Any]) -> Dict[str, Any]:
    result = solve_shift_optimization(state["solver_params"])
    if result["status"] == "FAILED":
        return {"error_msg": result["message"], "raw_schedule": result}
    return {"raw_schedule": result}


def format_node(state: Dict[str, Any]) -> Dict[str, Any]:
    raw_result = state["raw_schedule"]
    input_json = state["input_json"]
    employees = input_json["employees"]
    shifts = input_json["shifts"]

    assignments = []
    for item in raw_result["assignments"]:
        employee = employees[item["employee_index"]]
        shift = shifts[item["shift_index"]]
        assignments.append(
            {
                "date": item["date"],
                "userId": employee["userId"],
                "userName": employee["userName"],
                "shiftName": shift["name"],
                "startTime": shift["startTime"],
                "endTime": shift["endTime"],
            }
        )

    final_schedule = {
        "status": raw_result["status"],
        "message": raw_result["message"],
        "assignments": assignments,
        "fairnessSummary": raw_result.get("fairness_summary", {}),
        "warnings": raw_result.get("warnings", []),
        "solverMeta": raw_result.get("solver_meta", {}),
        "unassignedShifts": raw_result.get("unassigned_shifts", []),
        "appliedInstructions": state.get("applied_instructions", []),
        "ignoredInstructions": state.get("ignored_instructions", []),
        "parserWarnings": state.get("parser_warnings", []),
        "constraintCatalog": state.get("constraint_catalog", {}),
        "parserMode": state.get("llm_parse_result", {}).get("mode", "unknown"),
    }
    return {"final_schedule": final_schedule}


def explain_node(state: Dict[str, Any]) -> Dict[str, Any]:
    explanation = generate_explanation(
        raw_result=state["raw_schedule"],
        input_json=state["input_json"],
        applied_instructions=state.get("applied_instructions", []),
        ignored_instructions=state.get("ignored_instructions", []),
        parser_warnings=state.get("parser_warnings", []),
    )
    final_schedule = state["final_schedule"]
    final_schedule["explanation"] = explanation
    return {"final_schedule": final_schedule}
