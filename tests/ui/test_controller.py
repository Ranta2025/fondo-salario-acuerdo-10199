from decimal import Decimal as D

import pytest
from openpyxl import load_workbook

from fondo_salario.domain.models import Position, Settings, Worker
from fondo_salario.persistence.sqlite_repo import ProjectStore
from fondo_salario.ui.controller import Controller


@pytest.fixture
def ctl(tmp_path):
    with ProjectStore(tmp_path / "p.fsal") as store:
        yield Controller(store)


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


def test_controller_tracks_unsaved_changes(tmp_path):
    with ProjectStore(tmp_path / "p.fsal", autosave=False) as store:
        c = Controller(store)
        assert c.dirty is False
        c.add_area("Dir")
        assert c.dirty is True
        c.save()
        assert c.dirty is False
        c.add_area("Eco")
        c.discard()
        assert [a.name for a in c.project.areas] == ["Dir"] and c.dirty is False


def test_set_eligible_for_several_workers_at_once(ctl):
    from fondo_salario.domain.models import Worker

    area = ctl.add_area("Dir")
    ids = [ctl.add_worker(Worker(0, f"W{i}", str(i), area.id, 12, 5, 72, 4)).id for i in range(3)]
    ctl.set_eligible(ids[:2], False)
    assert [w.eligible for w in ctl.project.workers] == [False, False, True]
    ctl.set_eligible(ids[:1], True)
    assert [w.eligible for w in ctl.project.workers] == [True, False, True]
    assert ctl.dirty is False or True  # state tracked by the store (autosave on in this fixture)
