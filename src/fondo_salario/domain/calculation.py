"""Distribution of the unexecuted salary fund (see docs/SPEC.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

from fondo_salario.domain.models import Area, Position, Settings, Worker
from fondo_salario.domain.scales import band_score, time_score

CENT = Decimal("0.01")
ONE = Decimal(1)


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    subject: str = ""
    detail: str = ""


@dataclass(frozen=True)
class PositionResult:
    position: Position
    vacancies: int
    unexecuted: Decimal


@dataclass(frozen=True)
class AreaResult:
    area: Area
    positions: list[PositionResult]
    unexecuted: Decimal
    pct: Decimal
    amount: Decimal


@dataclass(frozen=True)
class WorkerResult:
    worker: Worker
    time_score: int
    responsibility_score: int
    seniority_score: int
    contribution_score: int
    coefficient: Decimal
    area_coefficient: Decimal
    amount: Decimal


@dataclass(frozen=True)
class CalculationResult:
    areas: list[AreaResult]
    workers: list[WorkerResult]
    total_unexecuted: Decimal
    distributed: Decimal
    issues: list[Issue] = field(default_factory=list)


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` proportionally to `weights` in whole cents (largest remainder).

    The parts always add up to `total` exactly; with no positive weight, all parts are 0.
    """
    zero = Decimal("0.00")
    weight_sum = sum(weights, Decimal(0))
    if weight_sum <= 0:
        return [zero for _ in weights]
    exact = [total * w / weight_sum for w in weights]
    parts = [value.quantize(CENT, rounding=ROUND_FLOOR) for value in exact]
    leftover_cents = int((total - sum(parts, Decimal(0))) / CENT)
    by_remainder = sorted(range(len(weights)), key=lambda i: (parts[i] - exact[i], i))
    for index in [i for i in by_remainder if weights[i] > 0][:leftover_cents]:
        parts[index] += CENT
    return parts


def _worker_problem(worker: Worker, area_ids: set[int]) -> tuple[str, str] | None:
    """(machine code, English description) of what is wrong with the worker's data, if anything."""
    if worker.area_id not in area_ids:
        return "unknown_area", "unknown area"
    if not 1 <= worker.salary_group <= 25:
        return "salary_group", "salary group must be between 1 and 25"
    if worker.seniority_years < 0 or worker.days_worked < 0:
        return "negative", "seniority and days worked cannot be negative"
    if not 1 <= worker.contribution <= 5:
        return "contribution", "contribution must be between 1 and 5"
    return None


def _score_worker(worker: Worker, settings: Settings) -> tuple[int, int, int, int, Decimal]:
    time = time_score(worker.days_worked, settings.expected_days_per_month, settings.months_paid)
    responsibility = band_score(worker.salary_group, settings.responsibility_bands)
    seniority = band_score(worker.seniority_years, settings.seniority_bands)
    coefficient = (
        time * settings.weight_time
        + responsibility * settings.weight_responsibility
        + seniority * settings.weight_seniority
        + worker.contribution * settings.weight_contribution
    )
    return time, responsibility, seniority, worker.contribution, coefficient


def calculate(
    settings: Settings,
    areas: list[Area],
    positions: list[Position],
    workers: list[Worker],
) -> CalculationResult:
    issues: list[Issue] = []
    if settings.weights_sum != ONE:
        issues.append(
            Issue(
                "weights_sum",
                f"weights add up to {settings.weights_sum}, expected 1",
                str(settings.weights_sum),
            )
        )

    # Sheet 1: amount per area.
    area_positions: dict[int, list[PositionResult]] = {a.id: [] for a in areas}
    for position in positions:
        if position.area_id not in area_positions:
            continue
        vacancies = position.to_distribute
        if position.distribute is not None and position.distribute > position.total_vacancies:
            issues.append(
                Issue(
                    "distribute_exceeds",
                    f"{position.name}: distributing {position.distribute} of "
                    f"{position.total_vacancies} vacancies",
                    position.name,
                )
            )
        unexecuted = Decimal(vacancies) * position.salary * position.months_unexecuted
        area_positions[position.area_id].append(PositionResult(position, vacancies, unexecuted))
    area_unexecuted = [sum((p.unexecuted for p in area_positions[a.id]), Decimal(0)) for a in areas]
    total_unexecuted = sum(area_unexecuted, Decimal(0))
    if total_unexecuted == 0:
        issues.append(Issue("no_unexecuted", "there is no unexecuted salary fund to distribute"))
    pcts = allocate(Decimal(100), area_unexecuted)
    amounts = allocate(settings.total_amount, area_unexecuted)
    area_results = [
        AreaResult(area, area_positions[area.id], unexecuted, pct, amount)
        for area, unexecuted, pct, amount in zip(areas, area_unexecuted, pcts, amounts, strict=True)
    ]

    # Sheet 2: amount per worker.
    area_ids = {a.id for a in areas}
    scored: dict[int, tuple[int, int, int, int, Decimal]] = {}
    for worker in workers:
        problem = _worker_problem(worker, area_ids)
        if problem:
            code, description = problem
            issues.append(
                Issue("invalid_worker", f"{worker.full_name}: {description}", worker.full_name, code)
            )
        elif worker.eligible:
            scored[worker.id] = _score_worker(worker, settings)

    results: dict[int, WorkerResult] = {}
    for area_result in area_results:
        members = [w for w in workers if w.area_id == area_result.area.id and w.id in scored]
        coefficients = [scored[w.id][4] for w in members]
        shares = allocate(area_result.amount, coefficients)
        area_coefficient = sum(coefficients, Decimal(0))
        if area_result.amount > 0 and not members:
            issues.append(
                Issue(
                    "undistributed",
                    f"{area_result.area.name}: {area_result.amount} has no eligible worker",
                    area_result.area.name,
                )
            )
        for worker, share in zip(members, shares, strict=True):
            t, r, s, c, coefficient = scored[worker.id]
            results[worker.id] = WorkerResult(worker, t, r, s, c, coefficient, area_coefficient, share)

    zero = Decimal("0.00")
    worker_results = [
        results.get(w.id) or WorkerResult(w, 0, 0, 0, 0, Decimal(0), Decimal(0), zero) for w in workers
    ]
    distributed = sum((r.amount for r in worker_results), Decimal(0))
    return CalculationResult(area_results, worker_results, total_unexecuted, distributed, issues)
