from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ortools.sat.python import cp_model


def _summarize_fairness(
    solver: cp_model.CpSolver,
    work: Dict[Tuple[int, int, int], cp_model.IntVar],
    num_employees: int,
    num_days: int,
    num_shifts: int,
    day_to_is_weekend: List[int],
    shift_is_night: List[bool],
) -> Dict[str, Any]:
    total_counts = []
    night_counts = []
    weekend_counts = []

    for e in range(num_employees):
        total = 0
        night = 0
        weekend = 0
        for d in range(num_days):
            for s in range(num_shifts):
                val = solver.Value(work[(e, d, s)])
                total += val
                if shift_is_night[s]:
                    night += val
                if day_to_is_weekend[d]:
                    weekend += val
        total_counts.append(total)
        night_counts.append(night)
        weekend_counts.append(weekend)

    def _spread(values: List[int]) -> int:
        return (max(values) - min(values)) if values else 0

    warnings = []
    total_spread = _spread(total_counts)
    night_spread = _spread(night_counts)
    weekend_spread = _spread(weekend_counts)

    if total_spread >= 3:
        warnings.append("총 근무 수 편차가 다소 큽니다.")
    if night_spread >= 2:
        warnings.append("야간 근무 편차가 다소 큽니다.")
    if weekend_spread >= 2:
        warnings.append("주말 근무 편차가 다소 큽니다.")

    return {
        "totalsPerEmployee": total_counts,
        "nightPerEmployee": night_counts,
        "weekendPerEmployee": weekend_counts,
        "totalSpread": total_spread,
        "nightSpread": night_spread,
        "weekendSpread": weekend_spread,
        "warnings": warnings,
    }


def solve_shift_optimization(params: Dict[str, Any]) -> Dict[str, Any]:
    precheck_infeasible_reasons = params.get("precheck_infeasible_reasons", [])
    if precheck_infeasible_reasons:
        return {
            "status": "FAILED",
            "message": "사전 검증에서 배정 불가능한 시프트가 발견되었습니다.",
            "assignments": [],
            "unassigned_shifts": precheck_infeasible_reasons,
            "warnings": [],
            "solver_meta": {"phase": "precheck"},
        }

    num_employees = params["num_employees"]
    num_days = params["num_days"]
    num_shifts = params["num_shifts"]
    eligibility = params["eligibility"]
    shift_required_counts = params["shift_required_counts"]
    rest_conflicts = params["rest_conflicts"]
    employee_max_assignments = params["employee_max_assignments"]
    employee_forbidden_shifts = params.get(
        "employee_forbidden_shifts",
        [set() for _ in range(num_employees)]
    )
    employee_max_consecutive_days = params["employee_max_consecutive_days"]
    preferences = params["preferences"]
    day_to_is_weekend = params["day_to_is_weekend"]
    shift_is_night = params["shift_is_night"]
    weights = params["weights"]
    time_limit_seconds = params["solver_time_limit_seconds"]
    max_shifts_per_day = params.get("max_shifts_per_day", 1)
    shift_min_skill_coverage = params.get("shift_min_skill_coverage", [])
    employees = params.get("employees", [])
    employee_skills = [set(e.get("skills", [])) for e in employees]
    night_shift_indices = [s for s in range(num_shifts) if shift_is_night[s]]
    total_night_slots = num_days * sum(shift_required_counts[s] for s in night_shift_indices)

    night_eligible_employees: List[int] = []
    for e in range(num_employees):
        if any(
            eligibility[e][d][s]
            for d in range(num_days)
            for s in night_shift_indices
        ):
            night_eligible_employees.append(e)

    model = cp_model.CpModel()
    work: Dict[Tuple[int, int, int], cp_model.IntVar] = {}
    works_day: Dict[Tuple[int, int], cp_model.IntVar] = {}

    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_shifts):
                work[(e, d, s)] = model.NewBoolVar(f"work_e{e}_d{d}_s{s}")
                if not eligibility[e][d][s]:
                    model.Add(work[(e, d, s)] == 0)

    for e in range(num_employees):
        for d in range(num_days):
            for s in employee_forbidden_shifts[e]:
                model.Add(work[(e, d, s)] == 0)

    for e in range(num_employees):
        for d in range(num_days):
            works_day[(e, d)] = model.NewBoolVar(f"works_day_e{e}_d{d}")
            daily_sum = sum(work[(e, d, s)] for s in range(num_shifts))
            model.Add(daily_sum <= max_shifts_per_day)
            model.AddMaxEquality(works_day[(e, d)], [work[(e, d, s)] for s in range(num_shifts)])

    for d in range(num_days):
        for s in range(num_shifts):
            model.Add(sum(work[(e, d, s)] for e in range(num_employees)) == shift_required_counts[s])

    for e in range(num_employees):
        model.Add(sum(works_day[(e, d)] for d in range(num_days)) <= employee_max_assignments[e])

    for e in range(num_employees):
        max_consecutive = employee_max_consecutive_days[e]
        if max_consecutive < num_days:
            for start in range(num_days - max_consecutive):
                model.Add(
                    sum(works_day[(e, d)] for d in range(start, start + max_consecutive + 1))
                    <= max_consecutive
                )

    for e in range(num_employees):
        for d, s1, s2 in rest_conflicts:
            model.Add(work[(e, d, s1)] + work[(e, d + 1, s2)] <= 1)

    for d in range(num_days):
        for s in range(num_shifts):
            for rule in shift_min_skill_coverage[s]:
                skill = rule["skill"]
                count = int(rule["count"])

                eligible_with_skill = [
                    work[(e, d, s)]
                    for e in range(num_employees)
                    if skill in employee_skills[e]
                ]
                model.Add(sum(eligible_with_skill) >= count)

    total_assignments = []
    night_assignments = []
    weekend_assignments = []
    preference_hits = []

    for e in range(num_employees):
        total_var = model.NewIntVar(0, num_days * max_shifts_per_day, f"total_e{e}")
        night_var = model.NewIntVar(0, total_night_slots, f"night_e{e}")
        weekend_var = model.NewIntVar(0, num_days * max_shifts_per_day, f"weekend_e{e}")
        pref_var = model.NewIntVar(0, num_days * max_shifts_per_day, f"pref_e{e}")

        model.Add(total_var == sum(work[(e, d, s)] for d in range(num_days) for s in range(num_shifts)))
        model.Add(
            night_var
            == sum(
                work[(e, d, s)]
                for d in range(num_days)
                for s in range(num_shifts)
                if shift_is_night[s]
            )
        )
        model.Add(
            weekend_var
            == sum(
                work[(e, d, s)]
                for d in range(num_days)
                for s in range(num_shifts)
                if day_to_is_weekend[d]
            )
        )
        preferred_shift_indices = preferences[e]
        model.Add(
            pref_var
            == sum(
                work[(e, d, s)]
                for d in range(num_days)
                for s in preferred_shift_indices
            )
        )

        total_assignments.append(total_var)
        night_assignments.append(night_var)
        weekend_assignments.append(weekend_var)
        preference_hits.append(pref_var)

    total_max = model.NewIntVar(0, num_days * max_shifts_per_day, "total_max")
    total_min = model.NewIntVar(0, num_days * max_shifts_per_day, "total_min")
    weekend_max = model.NewIntVar(0, num_days * max_shifts_per_day, "weekend_max")
    weekend_min = model.NewIntVar(0, num_days * max_shifts_per_day, "weekend_min")

    model.AddMaxEquality(total_max, total_assignments)
    model.AddMinEquality(total_min, total_assignments)
    model.AddMaxEquality(weekend_max, weekend_assignments)
    model.AddMinEquality(weekend_min, weekend_assignments)

    total_spread = model.NewIntVar(0, num_days * max_shifts_per_day, "total_spread")
    weekend_spread = model.NewIntVar(0, num_days * max_shifts_per_day, "weekend_spread")
    model.Add(total_spread == total_max - total_min)
    model.Add(weekend_spread == weekend_max - weekend_min)

    night_fairness_penalty_terms = []
    night_spread_eligible = None

    if len(night_eligible_employees) >= 2:
        eligible_night_vars = [night_assignments[e] for e in night_eligible_employees]

        night_max_eligible = model.NewIntVar(0, total_night_slots, "night_max_eligible")
        night_min_eligible = model.NewIntVar(0, total_night_slots, "night_min_eligible")
        night_spread_eligible = model.NewIntVar(0, total_night_slots, "night_spread_eligible")
        model.AddMaxEquality(night_max_eligible, eligible_night_vars)
        model.AddMinEquality(night_min_eligible, eligible_night_vars)
        model.Add(night_spread_eligible == night_max_eligible - night_min_eligible)
        night_fairness_penalty_terms.append(night_spread_eligible)

        for i in range(len(night_eligible_employees)):
            for j in range(i + 1, len(night_eligible_employees)):
                ei = night_eligible_employees[i]
                ej = night_eligible_employees[j]
                diff = model.NewIntVar(0, total_night_slots, f"night_diff_{ei}_{ej}")
                model.AddAbsEquality(diff, night_assignments[ei] - night_assignments[ej])
                night_fairness_penalty_terms.append(diff)

    objective = (
        weights["preference"] * sum(preference_hits)
        - weights["fairness"] * total_spread
        - weights["weekend"] * weekend_spread
        - weights["night"] * sum(night_fairness_penalty_terms)
    )
    model.Maximize(objective)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": "FAILED",
            "message": "모든 하드 제약을 만족하는 근무표를 찾지 못했습니다.",
            "assignments": [],
            "unassigned_shifts": [],
            "warnings": [],
            "solver_meta": {
                "status": int(status),
                "phase": "solve",
                "nightEligibleEmployeeIndices": night_eligible_employees,
                "nightEligibleCount": len(night_eligible_employees),
            },
        }

    assignments = []
    for d, date_label in enumerate(params["dates"]):
        for e in range(num_employees):
            for s in range(num_shifts):
                if solver.Value(work[(e, d, s)]):
                    assignments.append(
                        {
                            "date": date_label,
                            "day_index": d,
                            "employee_index": e,
                            "shift_index": s,
                        }
                    )

    fairness_summary = _summarize_fairness(
        solver,
        work,
        num_employees,
        num_days,
        num_shifts,
        day_to_is_weekend,
        shift_is_night,
    )

    message = "근무표 생성이 완료되었습니다."
    if status == cp_model.FEASIBLE:
        message = "근무표 생성이 완료되었습니다. 시간 제한 내에서 실행 가능한 최선안을 반환했습니다."

    solver_meta = {
        "status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
        "objectiveValue": solver.ObjectiveValue(),
        "bestBound": solver.BestObjectiveBound(),
        "wallTimeSeconds": solver.WallTime(),
        "timeLimitSeconds": time_limit_seconds,
        "nightEligibleEmployeeIndices": night_eligible_employees,
        "nightEligibleCount": len(night_eligible_employees),
        "maxShiftsPerDay": max_shifts_per_day,
    }
    if night_spread_eligible is not None:
        solver_meta["nightSpreadEligibleOnly"] = solver.Value(night_spread_eligible)

    return {
        "status": "SUCCESS",
        "message": message,
        "assignments": assignments,
        "fairness_summary": {k: v for k, v in fairness_summary.items() if k != "warnings"},
        "warnings": fairness_summary["warnings"],
        "unassigned_shifts": [],
        "solver_meta": solver_meta,
    }
