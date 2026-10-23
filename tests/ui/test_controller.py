from decimal import Decimal as D

import pytest
from openpyxl import load_workbook

from fondo_salario.domain.models import Position, Settings, Worker
from fondo_salario.importers.structure import AreaRow, PositionRow
from fondo_salario.importers.workers import WorkerRow
from fondo_salario.persistence.sqlite_repo import ProjectStore
from fondo_salario.ui.controller import Controller


@pytest.fixture
def ctl(tmp_path):
    with ProjectStore(tmp_path / "p.fsal") as store:
        yield Controller(store)


def row(name="Ana Prueba", area="Dir", **kw):
    base = dict(full_name=name, national_id="1", area=area, salary_group=12, seniority_years=5)
    base.update(kw)
    return WorkerRow(**base)


def test_import_structure_creates_areas_and_skips_existing(ctl):
    data = [AreaRow(1, "Dir", [PositionRow("Jefe", 1, D("6000"), 3)]), AreaRow(2, "Eco")]
    assert ctl.import_structure(data) == 2
    assert ctl.import_structure(data) == 0
    project = ctl.project
    assert [a.name for a in project.areas] == ["Dir", "Eco"]
    assert project.positions[0].vacant == 1 and project.positions[0].distribute is None


def test_import_workers_matches_area_ignoring_case_and_accents(ctl):
    ctl.import_structure([AreaRow(1, "Dirección")])
    summary = ctl.import_workers([row(area="direccion"), row(name="Beto", area="Nope")])
    assert summary.added == 1
    assert "Nope" in summary.skipped[0]


def test_import_workers_requires_group_and_seniority_and_defaults_the_rest(ctl):
    ctl.save_settings(Settings(total_amount=D("0"), months_paid=2))
    ctl.import_structure([AreaRow(1, "Dir")])
    summary = ctl.import_workers([row(salary_group=None), row(name="Beto")])
    assert summary.added == 1 and len(summary.skipped) == 1
    worker = ctl.project.workers[0]
    assert worker.days_worked == 48 and worker.contribution == 3
    assert summary.defaults_used == 1


def test_calculation_reflects_edits(ctl):
    ctl.save_settings(Settings(total_amount=D("500.00")))
    area = ctl.add_area("Dir")
    ctl.add_position(Position(0, area.id, "Jefe", 1, 1, 0, D("1000"), 3))
    ctl.add_worker(Worker(0, "Ana", "1", area.id, 12, 5, 72, 4))
    assert ctl.calculation().workers[0].amount == D("500.00")
    ctl.update_worker(Worker(ctl.project.workers[0].id, "Ana", "1", area.id, 12, 5, 72, 4, eligible=False))
    assert ctl.calculation().workers[0].amount == D("0.00")


def test_export_writes_workbook(ctl, tmp_path):
    ctl.save_settings(Settings(total_amount=D("10.00")))
    ctl.add_area("Dir")
    out = tmp_path / "out.xlsx"
    ctl.export(out)
    assert "Pre-nómina" in load_workbook(out).sheetnames


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1234.56", "1234.56"),
        ("1 234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("100", "100"),
    ],
)
def test_parse_money(text, expected):
    from fondo_salario.ui.controller import parse_money

    assert parse_money(text) == D(expected)


@pytest.mark.parametrize(
    "text,total,expected",
    [("", 4, None), ("  ", 4, None), ("4", 4, None), ("2", 4, 2), ("0", 4, 0)],
)
def test_resolve_distribute(text, total, expected):
    from fondo_salario.ui.controller import resolve_distribute

    assert resolve_distribute(text, total) == expected


def test_resolve_distribute_rejects_more_than_available():
    from fondo_salario.ui.controller import resolve_distribute

    with pytest.raises(ValueError, match="no puede ser mayor"):
        resolve_distribute("5", 4)
    with pytest.raises(ValueError):
        resolve_distribute("x", 4)
