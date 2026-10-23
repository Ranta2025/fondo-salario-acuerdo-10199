from decimal import Decimal as D

from fondo_salario.domain.models import Area, Position, Worker
from fondo_salario.importers.merge import plan_structure, plan_workers, resolve
from fondo_salario.importers.structure import AreaRow, PositionRow
from fondo_salario.importers.workers import WorkerRow

AREAS = [Area(1, "Dirección", 1), Area(2, "Economía", 2)]


def worker(wid=1, name="Ana Pérez Gómez", ci="", area=1, **kw):
    base = dict(
        id=wid,
        full_name=name,
        national_id=ci,
        area_id=area,
        salary_group=12,
        seniority_years=5,
        days_worked=72,
        contribution=3,
        position_name="Técnico",
    )
    base.update(kw)
    return Worker(**base)


def row(name="Ana Pérez Gómez", ci="", area="Dirección", **kw):
    base = dict(full_name=name, national_id=ci, area=area)
    base.update(kw)
    return WorkerRow(**base)


def plan(rows, workers, **kw):
    kw.setdefault("create_missing_areas", False)
    kw.setdefault("allow_undefined", False)
    return plan_workers(rows, AREAS, workers, **kw)


# --- workers: matching ---------------------------------------------------------------
def test_unknown_worker_is_new_and_known_one_is_not():
    p = plan([row("Beto Ruiz", salary_group=3, seniority_years=1), row("ana perez gomez")], [worker()])
    assert [n.row.full_name for n in p.new_workers] == ["Beto Ruiz"]
    assert p.unchanged == 1 and p.items == []


def test_match_by_name_ignores_case_accents_and_spaces():
    p = plan([row("  ANA  PEREZ gomez ")], [worker()])
    assert p.unchanged == 1 and not p.new_workers


def test_match_by_id_even_if_the_name_differs_and_ask_about_the_name():
    p = plan([row("Ana P. Gómez", ci="123")], [worker(ci="123")])
    assert not p.new_workers
    (item,) = p.items
    assert [d.key for d in item.conflicts] == ["full_name"]
    assert (item.conflicts[0].current, item.conflicts[0].incoming) == ("Ana Pérez Gómez", "Ana P. Gómez")


# --- workers: joining ----------------------------------------------------------------
def test_missing_id_is_completed_automatically():
    p = plan([row(ci="00001111222")], [worker()])
    (item,) = p.items
    assert item.fills == {"national_id": "00001111222"} and item.conflicts == []
    assert item.fill_labels == ["Carné de identidad"]


def test_zero_group_and_zero_seniority_count_as_empty():
    p = plan([row(salary_group=9, seniority_years=4)], [worker(salary_group=0, seniority_years=0)])
    (item,) = p.items
    assert item.fills == {"salary_group": 9, "seniority_years": 4} and item.conflicts == []


def test_different_values_are_conflicts_with_readable_text():
    p = plan([row(ci="9", salary_group=15, seniority_years=7)], [worker(ci="1")])
    (item,) = p.items
    by_key = {d.key: d for d in item.conflicts}
    assert set(by_key) == {"national_id", "salary_group", "seniority_years"}
    assert (by_key["salary_group"].current, by_key["salary_group"].incoming) == ("XII", "XV")
    assert by_key["salary_group"].value == 15 and by_key["salary_group"].accept is None


def test_values_missing_in_the_file_are_ignored():
    p = plan([row()], [worker(ci="5", salary_group=0)])  # the file has nothing new for this worker
    assert p.unchanged == 1 and p.items == []


def test_area_difference_is_a_conflict_and_unknown_area_is_not_compared():
    p = plan([row(area="Economía"), row("Beto", area="Zzz")], [worker(), worker(2, "Beto")])
    (item,) = p.items
    assert item.conflicts[0].key == "area_id" and item.conflicts[0].value == 2
    assert (item.conflicts[0].current, item.conflicts[0].incoming) == ("Dirección", "Economía")
    assert p.unchanged == 1  # «Zzz» does not exist, so nothing to compare for Beto


def test_missing_area_can_be_created_when_allowed():
    p = plan(
        [row("Nuevo Uno", area="Banco", salary_group=1, seniority_years=1)], [], create_missing_areas=True
    )
    assert p.areas_to_create == ["Banco"] and p.new_workers[0].area == "Banco"


def test_new_rows_that_cannot_be_imported_are_skipped_with_a_reason():
    p = plan([row("A", area="Zzz"), row("B", salary_group=None)], [])
    assert len(p.skipped) == 2 and "área desconocida" in p.skipped[0] and "grupo" in p.skipped[1]
    assert p.new_workers == []


def test_undefined_group_is_allowed_for_legacy_imports():
    p = plan([row("B")], [], allow_undefined=True)
    assert len(p.new_workers) == 1 and p.new_workers[0].incomplete and p.undefined == 1


def test_repeated_rows_in_the_same_file_are_added_once():
    p = plan([row("Beto", salary_group=1, seniority_years=1)] * 2, [])
    assert len(p.new_workers) == 1


# --- positions (areas file) ---------------------------------------------------------------
POSITIONS = [Position(1, 1, "Jefe de Departamento", 1, 0, 0, D("0"), 0)]


def structure(rows):
    return plan_structure(rows, AREAS, POSITIONS)


def test_new_area_comes_with_its_positions():
    p = structure([AreaRow(3, "Recursos Humanos", [PositionRow("EP", 1, D("4610"), 3)])])
    assert [a.name for a in p.new_areas] == ["Recursos Humanos"]


def test_new_position_in_an_existing_area():
    p = structure([AreaRow(1, "Dirección", [PositionRow("Secretaria", 1, D("3000"), 3)])])
    assert [(n.area_id, n.row.name) for n in p.new_positions] == [(1, "Secretaria")]


def test_existing_position_is_completed_and_differences_are_asked():
    rows = [AreaRow(1, "Dirección", [PositionRow("jefe de departamento", 2, D("6060"), 3)])]
    p = structure(rows)
    (item,) = p.items
    assert item.kind == "position" and item.name == "Jefe de Departamento"
    assert item.fills == {"vacant": 2, "salary": D("6060"), "months_unexecuted": 3}


def test_existing_position_with_other_values_gives_conflicts_and_zero_means_not_provided():
    positions = [Position(1, 1, "Jefe", 1, 1, 0, D("5000"), 3)]
    rows = [AreaRow(1, "Dirección", [PositionRow("Jefe", 0, D("6060"), 3)])]
    p = plan_structure(rows, AREAS, positions)
    (item,) = p.items
    assert [d.key for d in item.conflicts] == ["salary"]  # vacant 0 in the file = no data; months equal
    assert item.conflicts[0].value == D("6060")


# --- resolving the differences ---------------------------------------------------------
def _plan_with_three_conflicts():
    return plan([row(ci="9", salary_group=15, seniority_years=7)], [worker(ci="1")])


def test_accept_all_and_keep_all():
    p = _plan_with_three_conflicts()
    assert resolve(p, "accept_all") is True and all(d.accept is True for i in p.items for d in i.conflicts)
    q = _plan_with_three_conflicts()
    assert resolve(q, "keep_all") is True and all(d.accept is False for i in q.items for d in i.conflicts)


def test_review_one_by_one_asks_for_each_difference():
    p = _plan_with_three_conflicts()
    seen = []

    def ask(item, diff, index, total):
        seen.append((diff.key, index, total))
        return "overwrite" if diff.key == "national_id" else "keep"

    assert resolve(p, "review", ask) is True
    assert [s[1:] for s in seen] == [(1, 3), (2, 3), (3, 3)]
    assert {d.key: d.accept for d in p.items[0].conflicts} == {
        "national_id": True,
        "salary_group": False,
        "seniority_years": False,
    }


def test_accept_the_rest_stops_asking():
    p = _plan_with_three_conflicts()
    calls = []

    def ask(item, diff, index, total):
        calls.append(diff.key)
        return "keep" if index == 1 else "overwrite_rest"

    assert resolve(p, "review", ask) is True
    assert len(calls) == 2
    assert [d.accept for d in p.items[0].conflicts] == [False, True, True]


def test_cancelling_the_review_aborts():
    p = _plan_with_three_conflicts()
    assert resolve(p, "review", lambda *a: None) is False
