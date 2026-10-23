from decimal import Decimal as D

import pytest

from fondo_salario.domain.calculation import allocate, calculate
from fondo_salario.domain.models import Area, Position, Settings, Worker
from fondo_salario.domain.scales import (
    DEFAULT_RESPONSIBILITY_BANDS,
    DEFAULT_SENIORITY_BANDS,
    band_score,
    time_score,
)


def settings(total="100344.08", months=3, **kw):
    return Settings(total_amount=D(total), months_paid=months, **kw)


def worker(wid, area_id, **kw):
    base = dict(
        id=wid,
        full_name=f"Worker {wid}",
        national_id=f"{wid:011d}",
        area_id=area_id,
        salary_group=12,
        seniority_years=10,
        days_worked=72,
        contribution=4,
    )
    base.update(kw)
    return Worker(**base)


@pytest.fixture
def org():
    areas = [Area(1, "A", 1), Area(2, "B", 2), Area(3, "C", 3)]
    positions = [
        Position(1, 1, "p1", approved=2, vacant=1, temp_vacant=0, salary=D("6310"), months_unexecuted=3),
        Position(2, 2, "p2", approved=3, vacant=1, temp_vacant=1, salary=D("3610"), months_unexecuted=3),
        Position(3, 2, "p3", approved=1, vacant=0, temp_vacant=0, salary=D("9999"), months_unexecuted=3),
        Position(4, 3, "p4", approved=4, vacant=2, temp_vacant=0, salary=D("2100"), months_unexecuted=3),
    ]
    return areas, positions


# --- scales -----------------------------------------------------------------
@pytest.mark.parametrize(
    "group,score",
    [(1, 1), (5, 1), (6, 2), (10, 2), (11, 3), (15, 3), (16, 4), (20, 4), (21, 5), (25, 5)],
)
def test_responsibility_bands_edges(group, score):
    assert band_score(group, DEFAULT_RESPONSIBILITY_BANDS) == score


@pytest.mark.parametrize(
    "years,score",
    # Rafelito 3: up to 5 years 1, 6-10 2, 11-15 3, 16-20 4, more than 20 5
    [(0, 1), (5, 1), (6, 2), (10, 2), (11, 3), (15, 3), (16, 4), (20, 4), (21, 5), (50, 5)],
)
def test_seniority_bands_edges(years, score):
    assert band_score(years, DEFAULT_SENIORITY_BANDS) == score


@pytest.mark.parametrize(
    "days,score",
    # 3 months = 72 potential days; ranges are >0-20 %, >20-40 %, >40-60 %, >60-80 %, >80-100 %
    [
        (0, 0),
        (1, 1),
        (14, 1),
        (15, 2),
        (28, 2),
        (29, 3),
        (43, 3),
        (44, 4),
        (57, 4),
        (58, 5),
        (72, 5),
        (200, 5),
    ],
)
def test_time_score_uses_percentage_ranges(days, score):
    assert time_score(days, expected_days=24, months=3) == score


@pytest.mark.parametrize(
    "days,score",
    # one month = 24 days: 1-4, 5-9, 10-14, 15-19, 20-24 (the document's «corregido» table)
    [(1, 1), (4, 1), (5, 2), (9, 2), (10, 3), (14, 3), (15, 4), (19, 4), (20, 5), (24, 5)],
)
def test_time_score_matches_the_monthly_table_of_the_document(days, score):
    assert time_score(days, expected_days=24, months=1) == score


def test_default_weights_are_the_ones_of_the_new_regulation():
    s = Settings(total_amount=D("1"))
    assert (s.weight_responsibility, s.weight_contribution, s.weight_time, s.weight_seniority) == (
        D("0.25"),
        D("0.40"),
        D("0.20"),
        D("0.15"),
    )
    assert s.weights_sum == D("1.00")


# --- allocate ---------------------------------------------------------------
def test_allocate_sums_exactly_with_awkward_total():
    parts = allocate(D("100344.08"), [D(3), D(3), D(3)])
    assert sum(parts) == D("100344.08")
    assert max(parts) - min(parts) <= D("0.01")


def test_allocate_zero_weights_gives_zeros():
    assert allocate(D("10"), [D(0), D(0)]) == [D("0.00"), D("0.00")]


def test_allocate_ignores_zero_weight_items():
    assert allocate(D("10"), [D(0), D(5)]) == [D("0.00"), D("10.00")]


# --- calculate --------------------------------------------------------------
def test_area_percentages_sum_to_100_and_amounts_to_total(org):
    areas, positions = org
    result = calculate(settings(), areas, positions, [worker(1, 1), worker(2, 2), worker(3, 3)])
    assert sum(a.pct for a in result.areas) == D("100")
    assert sum(a.amount for a in result.areas) == D("100344.08")
    # unexecuted: A=6310*1*3, B=3610*2*3, C=2100*2*3
    assert [a.unexecuted for a in result.areas] == [D("18930"), D("21660"), D("12600")]


def test_worker_amounts_sum_to_total(org):
    areas, positions = org
    workers = [worker(i, 1 + i % 3, contribution=1 + i % 5) for i in range(1, 12)]
    result = calculate(settings(), areas, positions, workers)
    assert sum(w.amount for w in result.workers) == D("100344.08")
    assert not [i for i in result.issues if i.code == "undistributed"]


def test_worker_amounts_sum_to_area_amount_per_area(org):
    areas, positions = org
    workers = [worker(i, 1 + i % 3, contribution=1 + i % 5) for i in range(1, 12)]
    result = calculate(settings(), areas, positions, workers)
    for area in result.areas:
        assert sum(w.amount for w in result.workers if w.worker.area_id == area.area.id) == area.amount


def test_coefficient_uses_weights(org):
    areas, positions = org
    w = worker(1, 1, salary_group=12, seniority_years=10, days_worked=72, contribution=4)
    result = calculate(settings(), areas, positions, [w])
    # time 5, responsibility 3, seniority 2, contribution 4
    assert result.workers[0].coefficient == (
        D("5") * D("0.20") + D("3") * D("0.25") + D("2") * D("0.15") + D("4") * D("0.40")
    )


def test_ineligible_worker_gets_zero_and_others_share(org):
    areas, positions = org
    ws = [worker(1, 1), worker(2, 1, eligible=False)]
    result = calculate(settings(), areas, positions, ws)
    by_id = {r.worker.id: r for r in result.workers}
    assert by_id[2].amount == D("0.00") and by_id[2].coefficient == D(0)
    assert by_id[1].amount == next(a for a in result.areas if a.area.id == 1).amount


def test_area_without_unexecuted_money_pays_zero(org):
    areas, positions = org
    areas = areas + [Area(4, "D", 4)]
    result = calculate(settings(), areas, positions, [worker(1, 1), worker(9, 4)])
    assert next(r for r in result.workers if r.worker.id == 9).amount == D("0.00")


def test_zero_grand_total_warns_without_dividing_by_zero():
    areas = [Area(1, "A", 1)]
    positions = [Position(1, 1, "p", 1, 0, 0, D("1000"), 3)]
    result = calculate(settings(), areas, positions, [worker(1, 1)])
    assert result.areas[0].amount == D("0.00")
    assert any(i.code == "no_unexecuted" for i in result.issues)


def test_area_with_money_but_no_eligible_workers_warns(org):
    areas, positions = org
    result = calculate(settings(), areas, positions, [worker(1, 1), worker(2, 2)])
    codes = [i.code for i in result.issues]
    assert "undistributed" in codes
    assert result.distributed < D("100344.08")


def test_weights_not_summing_to_one_warns(org):
    areas, positions = org
    result = calculate(settings(weight_time=D("0.50")), areas, positions, [worker(1, 1)])
    assert any(i.code == "weights_sum" for i in result.issues)


def test_invalid_worker_data_is_reported_and_paid_zero(org):
    areas, positions = org
    bad = [worker(1, 1, salary_group=40), worker(2, 99), worker(3, 1, contribution=0), worker(4, 1)]
    result = calculate(settings(), areas, positions, bad)
    by_id = {r.worker.id: r for r in result.workers}
    assert by_id[1].amount == by_id[2].amount == by_id[3].amount == D("0.00")
    assert sum(1 for i in result.issues if i.code == "invalid_worker") == 3
    assert by_id[4].amount == next(a for a in result.areas if a.area.id == 1).amount


def test_time_evaluation_scales_with_months_paid(org):
    areas, positions = org
    result = calculate(settings(months=2), areas, positions, [worker(1, 1, days_worked=48)])
    assert result.workers[0].time_score == 5


# --- vacancies to distribute -------------------------------------------------
def _one_position(distribute):
    areas = [Area(1, "A", 1)]
    positions = [Position(1, 1, "p", 5, 3, 1, D("1000"), 3, distribute=distribute)]
    return areas, positions


def test_only_the_vacancies_to_distribute_count():
    areas, positions = _one_position(distribute=2)
    result = calculate(settings(), areas, positions, [worker(1, 1)])
    assert result.areas[0].positions[0].vacancies == 2
    assert result.areas[0].unexecuted == D("6000")  # 2 * 1000 * 3, not 4 vacancies


def test_distribute_none_means_all_vacancies():
    areas, positions = _one_position(distribute=None)
    result = calculate(settings(), areas, positions, [worker(1, 1)])
    assert result.areas[0].unexecuted == D("12000")  # (3 + 1) * 1000 * 3


def test_distribute_above_total_vacancies_is_clamped_and_reported():
    areas, positions = _one_position(distribute=9)
    result = calculate(settings(), areas, positions, [worker(1, 1)])
    assert result.areas[0].unexecuted == D("12000")
    assert any(i.code == "distribute_exceeds" for i in result.issues)


# --- explaining zeros ---------------------------------------------------------------
def test_missing_total_amount_is_reported(org):
    areas, positions = org
    result = calculate(settings(total="0"), areas, positions, [worker(1, 1)])
    assert any(i.code == "no_total" for i in result.issues)


def test_area_with_workers_but_no_money_is_reported_with_the_worker_count(org):
    areas, positions = org
    areas = areas + [Area(4, "Sin vacantes", 4)]
    result = calculate(
        settings(), areas, positions, [worker(1, 1), worker(8, 4), worker(9, 4, eligible=False)]
    )
    issue = next(i for i in result.issues if i.code == "area_without_money")
    assert (issue.subject, issue.detail) == ("Sin vacantes", "1")  # only eligible workers are counted


def test_monthly_example_of_the_document():
    """Rafelito 3, «Ejemplo mensual»: fund 8,000 among five workers of one area; total of points 15.50."""
    areas = [Area(1, "A", 1)]
    positions = [Position(1, 1, "p", 1, 1, 0, D("1000"), 1)]
    #  group, contribution, days (of 24), years   -> expected final score
    people = [
        (18, 5, 24, 12, "4.45"),  # A: resp 4, contr 5, time 5, antig 3
        (9, 4, 24, 8, "3.40"),  # B: resp 2, contr 4, time 5, antig 2
        (13, 4, 17, 12, "3.60"),  # C: resp 3, contr 4, time 4, antig 3
        (4, 3, 12, 3, "2.20"),  # D: resp 1, contr 3, time 3, antig 1
        (8, 2, 7, 3, "1.85"),  # E: resp 2, contr 2, time 2, antig 1
    ]
    workers = [
        worker(i, 1, salary_group=g, contribution=c, days_worked=d, seniority_years=y)
        for i, (g, c, d, y, _) in enumerate(people, start=1)
    ]
    result = calculate(settings(total="8000.00", months=1), areas, positions, workers)
    assert [r.coefficient for r in result.workers] == [D(p[4]) for p in people]
    assert result.workers[0].area_coefficient == D("15.50")
    document_amounts = ["2296.78", "1754.84", "1858.07", "1135.49", "954.84"]
    for got, expected in zip(result.workers, document_amounts, strict=True):
        assert abs(got.amount - D(expected)) <= D("0.01")  # the document rounds the point value first
    assert sum(r.amount for r in result.workers) == D("8000.00")
