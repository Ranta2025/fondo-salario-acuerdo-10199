from dataclasses import replace
from decimal import Decimal as D

import pytest

from fondo_salario.domain.models import Position, Settings, Worker
from fondo_salario.persistence.sqlite_repo import AreaInUseError, ProjectStore


@pytest.fixture
def store(tmp_path):
    with ProjectStore(tmp_path / "p.fsal") as s:
        yield s


def make_worker(area_id, **kw):
    base = dict(
        id=0,
        full_name="Ana Prueba",
        national_id="00000000001",
        area_id=area_id,
        salary_group=12,
        seniority_years=5,
        days_worked=72,
        contribution=4,
    )
    base.update(kw)
    return Worker(**base)


def test_new_project_has_default_settings(store):
    project = store.load()
    assert project.settings == Settings(total_amount=D("0"))
    assert project.areas == project.positions == project.workers == []


def test_settings_roundtrip_keeps_decimals_and_bands(store):
    custom = Settings(
        total_amount=D("100344.08"),
        months_paid=2,
        weight_time=D("0.50"),
        weight_responsibility=D("0.20"),
        weight_seniority=D("0.10"),
        weight_contribution=D("0.20"),
        seniority_bands=((0, 1), (10, 5)),
    )
    store.save_settings(custom)
    assert store.load().settings == custom


def test_area_position_worker_crud(store):
    area = store.add_area("Direccion")
    assert area.id > 0 and area.order > 0
    position = store.add_position(Position(0, area.id, "Jefe", 1, 1, 0, D("6310.50"), 3))
    worker = store.add_worker(make_worker(area.id))
    project = store.load()
    assert project.areas == [area]
    assert project.positions == [position] and position.salary == D("6310.50")
    assert project.workers == [worker]

    store.update_worker(replace(worker, contribution=5, eligible=False))
    updated = store.load().workers[0]
    assert updated.contribution == 5 and updated.eligible is False

    store.update_position(replace(position, vacant=0))
    assert store.load().positions[0].vacant == 0
    store.rename_area(area.id, "Direccion General")
    assert store.load().areas[0].name == "Direccion General"

    store.delete_worker(worker.id)
    store.delete_position(position.id)
    assert store.load().workers == [] and store.load().positions == []


def test_delete_area_with_workers_is_blocked_but_cascades_positions(store):
    area = store.add_area("A")
    store.add_position(Position(0, area.id, "p", 1, 1, 0, D("1"), 1))
    worker = store.add_worker(make_worker(area.id))
    with pytest.raises(AreaInUseError):
        store.delete_area(area.id)
    store.delete_worker(worker.id)
    store.delete_area(area.id)
    project = store.load()
    assert project.areas == [] and project.positions == []


def test_reopen_persists_data_and_sets_schema_version(tmp_path):
    path = tmp_path / "p.fsal"
    with ProjectStore(path) as s:
        s.add_area("A")
    with ProjectStore(path) as s:
        assert [a.name for a in s.load().areas] == ["A"]
        assert s.schema_version == 1


def test_rejects_file_from_newer_version(tmp_path):
    import sqlite3

    path = tmp_path / "p.fsal"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    with pytest.raises(ValueError, match="newer"):
        ProjectStore(path)
