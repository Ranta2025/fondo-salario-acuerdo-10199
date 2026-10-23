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
    [(0, 1), (7, 1), (8, 2), (14, 2), (15, 3), (21, 3), (22, 4), (28, 4), (29, 5), (50, 5)],
)
def test_seniority_bands_edges(years, score):
    assert band_score(years, DEFAULT_SENIORITY_BANDS) == score


@pytest.mark.parametrize("days,score", [(0, 0), (1, 1), (72, 5), (60, 4), (36, 3), (14, 1), (200, 5)])
def test_time_score(days, score):
    assert time_score(days, expected_days=24, months=3) == score


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
    assert result.workers[0].coefficient == D("5") * D("0.40") + D("3") * D("0.25") + D("2") * D("0.15") + D(
        "4"
    ) * D("0.20")


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
