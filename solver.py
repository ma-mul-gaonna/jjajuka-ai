from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class EmployeeState:
    assigned_days: Set[int] = field(default_factory=set)
    day_to_shift: Dict[int, int] = field(default_factory=dict)
    total_assignments: int = 0
    night_assignments: int = 0
    weekend_assignments: int = 0


@dataclass
class SearchState:
    employee_states: List[EmployeeState]
    assignments: List[Dict[str, int]]
    best_assignments: List[Dict[str, int]] = field(default_factory=list)
    best_score: Optional[int] = None


MAX_BACKTRACK_STEPS = 200000


def _build_static_unassigned(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(params.get("precheck_issues", []))



def _build_generic_infeasible_reasons(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    reasons = _build_static_unassigned(params)
    if reasons:
        return reasons

    tight_spots: List[Dict[str, Any]] = []
    required_staff = params["required_staff"]
    shift_names = params["shift_names"]
    eligible = params["eligible"]
    for d in range(params["num_days"]):
        for s in range(params["num_shifts"]):
            candidate_count = sum(eligible[e][d][s] for e in range(params["num_employees"]))
            if candidate_count <= required_staff[s] + 1:
                tight_spots.append({
                    "dayIndex": d,
                    "shiftName": shift_names[s],
                    "reason": (
                        "후보 풀이 매우 좁아 휴식시간/연속근무/전체 수요 제약과 결합되면서 "
                        "배정 불가능해졌을 수 있습니다."
                    ),
                    "candidateCount": candidate_count,
                    "requiredCount": required_staff[s],
                })
    if tight_spots:
        return tight_spots[:10]

    return [{
        "reason": "정적 후보 수는 충분하지만, 최소 휴식시간·연속근무 제한·총 수요가 동시에 충돌해 해를 찾지 못했습니다."
    }]



def _is_consecutive_limit_ok(employee_state: EmployeeState, day: int, limit: int) -> bool:
    if day in employee_state.assigned_days:
        return False

    streak = 1
    cursor = day - 1
    while cursor in employee_state.assigned_days:
        streak += 1
        cursor -= 1
    cursor = day + 1
    while cursor in employee_state.assigned_days:
        streak += 1
        cursor += 1
    return streak <= limit



def _violates_rest(employee_state: EmployeeState, day: int, shift_idx: int, incompatible_pairs: Set[Tuple[int, int]]) -> bool:
    prev_shift = employee_state.day_to_shift.get(day - 1)
    if prev_shift is not None and (prev_shift, shift_idx) in incompatible_pairs:
        return True

    next_shift = employee_state.day_to_shift.get(day + 1)
    if next_shift is not None and (shift_idx, next_shift) in incompatible_pairs:
        return True
    return False



def _candidate_soft_score(
    employee_index: int,
    day: int,
    shift_idx: int,
    employee_state: EmployeeState,
    params: Dict[str, Any],
) -> int:
    preferences = params["preferences"]
    night_shift_indices = set(params.get("night_shift_indices", []))
    weekend_day_indices = set(params.get("weekend_day_indices", []))

    score = 0
    if shift_idx in preferences[employee_index]:
        score += 100

    score -= employee_state.total_assignments * 4
    if shift_idx in night_shift_indices:
        score -= employee_state.night_assignments * 8
    if day in weekend_day_indices:
        score -= employee_state.weekend_assignments * 6

    # 같은 shift 반복을 약간 선호하지 않음
    prev_shift = employee_state.day_to_shift.get(day - 1)
    if prev_shift == shift_idx:
        score -= 3

    return score



def _build_slots(params: Dict[str, Any]) -> List[Tuple[int, int, int]]:
    slots: List[Tuple[int, int, int]] = []
    eligible = params["eligible"]
    required_staff = params["required_staff"]
    num_employees = params["num_employees"]
    num_days = params["num_days"]
    num_shifts = params["num_shifts"]

    slot_meta: List[Tuple[int, int, int, int]] = []
    for d in range(num_days):
        for s in range(num_shifts):
            candidate_count = sum(eligible[e][d][s] for e in range(num_employees))
            for k in range(required_staff[s]):
                slot_meta.append((candidate_count, d, s, k))

    slot_meta.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return [(d, s, k) for _, d, s, k in slot_meta]



def _compute_fairness(employee_states: List[EmployeeState]) -> Dict[str, Any]:
    totals = [es.total_assignments for es in employee_states]
    nights = [es.night_assignments for es in employee_states]
    weekends = [es.weekend_assignments for es in employee_states]
    return {
        "assignmentSpread": max(totals) - min(totals) if totals else 0,
        "nightSpread": max(nights) - min(nights) if nights else 0,
        "weekendSpread": max(weekends) - min(weekends) if weekends else 0,
        "perEmployee": [
            {
                "employeeIndex": idx,
                "totalAssignments": es.total_assignments,
                "nightAssignments": es.night_assignments,
                "weekendAssignments": es.weekend_assignments,
            }
            for idx, es in enumerate(employee_states)
        ],
    }



def solve_shift_optimization(params: Dict[str, Any]) -> Dict[str, Any]:
    precheck_issues = _build_static_unassigned(params)
    if precheck_issues:
        return {
            "status": "FAILED",
            "message": "정적 제약만으로도 일부 근무를 채울 수 없습니다.",
            "assignments": [],
            "summary": {},
            "fairness": {},
            "warnings": [],
            "unassignedShifts": precheck_issues,
        }

    num_employees = params["num_employees"]
    night_shift_indices = set(params.get("night_shift_indices", []))
    weekend_day_indices = set(params.get("weekend_day_indices", []))
    incompatible_pairs = {tuple(pair) for pair in params.get("incompatible_shift_pairs", [])}

    slots = _build_slots(params)
    search_state = SearchState(
        employee_states=[EmployeeState() for _ in range(num_employees)],
        assignments=[],
    )
    visited = {"count": 0}

    def dfs(slot_index: int, running_score: int) -> None:
        if visited["count"] >= MAX_BACKTRACK_STEPS:
            return
        visited["count"] += 1

        if slot_index == len(slots):
            fairness = _compute_fairness(search_state.employee_states)
            final_score = (
                running_score
                - fairness["assignmentSpread"] * 10
                - fairness["nightSpread"] * 20
                - fairness["weekendSpread"] * 10
            )
            if search_state.best_score is None or final_score > search_state.best_score:
                search_state.best_score = final_score
                search_state.best_assignments = [dict(item) for item in search_state.assignments]
            return

        day, shift_idx, _ = slots[slot_index]
        candidates = []
        for employee_index in range(num_employees):
            employee_state = search_state.employee_states[employee_index]
            if params["eligible"][employee_index][day][shift_idx] == 0:
                continue
            if day in employee_state.assigned_days:
                continue
            if employee_state.total_assignments >= params["employee_max_assignments"][employee_index]:
                continue
            if not _is_consecutive_limit_ok(
                employee_state,
                day,
                params["employee_max_consecutive_days"][employee_index],
            ):
                continue
            if _violates_rest(employee_state, day, shift_idx, incompatible_pairs):
                continue

            score = _candidate_soft_score(employee_index, day, shift_idx, employee_state, params)
            candidates.append((score, employee_index))

        candidates.sort(reverse=True)

        for score, employee_index in candidates:
            employee_state = search_state.employee_states[employee_index]
            employee_state.assigned_days.add(day)
            employee_state.day_to_shift[day] = shift_idx
            employee_state.total_assignments += 1
            if shift_idx in night_shift_indices:
                employee_state.night_assignments += 1
            if day in weekend_day_indices:
                employee_state.weekend_assignments += 1

            assignment = {
                "day_index": day,
                "employee_index": employee_index,
                "shift_index": shift_idx,
            }
            search_state.assignments.append(assignment)

            dfs(slot_index + 1, running_score + score)

            search_state.assignments.pop()
            if day in weekend_day_indices:
                employee_state.weekend_assignments -= 1
            if shift_idx in night_shift_indices:
                employee_state.night_assignments -= 1
            employee_state.total_assignments -= 1
            del employee_state.day_to_shift[day]
            employee_state.assigned_days.remove(day)

    dfs(0, 0)

    if not search_state.best_assignments:
        return {
            "status": "FAILED",
            "message": "모든 하드 제약을 만족하는 배정안을 찾지 못했습니다.",
            "assignments": [],
            "summary": {},
            "fairness": {},
            "warnings": [],
            "unassignedShifts": _build_generic_infeasible_reasons(params),
        }

    best_employee_states = [EmployeeState() for _ in range(num_employees)]
    for assignment in search_state.best_assignments:
        day = assignment["day_index"]
        employee_index = assignment["employee_index"]
        shift_idx = assignment["shift_index"]
        es = best_employee_states[employee_index]
        es.assigned_days.add(day)
        es.day_to_shift[day] = shift_idx
        es.total_assignments += 1
        if shift_idx in night_shift_indices:
            es.night_assignments += 1
        if day in weekend_day_indices:
            es.weekend_assignments += 1

    fairness = _compute_fairness(best_employee_states)
    preference_matches = sum(
        1
        for assignment in search_state.best_assignments
        if assignment["shift_index"] in params["preferences"][assignment["employee_index"]]
    )

    warnings: List[str] = []
    if fairness["assignmentSpread"] > 2:
        warnings.append("총 근무 수 편차가 다소 큽니다.")
    if fairness["nightSpread"] > 1:
        warnings.append("야간 근무 편차가 다소 큽니다.")
    if fairness["weekendSpread"] > 1:
        warnings.append("주말 근무 편차가 다소 큽니다.")
    if visited["count"] >= MAX_BACKTRACK_STEPS:
        warnings.append("탐색 한도 내 최선안을 반환했습니다. 데이터가 커지면 OR-Tools 전환을 권장합니다.")

    summary = {
        "totalAssignments": len(search_state.best_assignments),
        "requiredSlots": sum(params["required_staff"]) * params["num_days"],
        "preferenceMatches": preference_matches,
        "solverStatus": "BACKTRACKING_BEST_EFFORT",
        "searchSteps": visited["count"],
    }

    return {
        "status": "SUCCESS",
        "message": "하드 제약을 만족하는 근무표 초안을 생성했습니다.",
        "assignments": sorted(
            search_state.best_assignments,
            key=lambda x: (x["day_index"], x["shift_index"], x["employee_index"]),
        ),
        "summary": summary,
        "fairness": fairness,
        "warnings": warnings,
        "unassignedShifts": [],
    }
