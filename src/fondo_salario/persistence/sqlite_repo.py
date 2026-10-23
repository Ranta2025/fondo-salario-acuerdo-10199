"""SQLite storage: one project = one `.fsal` file."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from fondo_salario.domain.models import Area, Position, Settings, Worker

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_amount TEXT NOT NULL,
    months_paid INTEGER NOT NULL,
    expected_days_per_month INTEGER NOT NULL,
    weight_time TEXT NOT NULL,
    weight_responsibility TEXT NOT NULL,
    weight_seniority TEXT NOT NULL,
    weight_contribution TEXT NOT NULL,
    responsibility_bands TEXT NOT NULL,
    seniority_bands TEXT NOT NULL
);
CREATE TABLE areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    approved INTEGER NOT NULL,
    vacant INTEGER NOT NULL,
    temp_vacant INTEGER NOT NULL,
    salary TEXT NOT NULL,
    months_unexecuted INTEGER NOT NULL,
    distribute INTEGER
);
CREATE TABLE workers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    national_id TEXT NOT NULL,
    area_id INTEGER NOT NULL REFERENCES areas(id),
    position_name TEXT NOT NULL,
    salary_group INTEGER NOT NULL,
    seniority_years INTEGER NOT NULL,
    days_worked INTEGER NOT NULL,
    contribution INTEGER NOT NULL,
    eligible INTEGER NOT NULL
);
"""


class AreaInUseError(Exception):
    """The area still has workers assigned."""


@dataclass(frozen=True)
class Project:
    settings: Settings
    areas: list[Area]
    positions: list[Position]
    workers: list[Worker]


class ProjectStore:
    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        version = self.schema_version
        if version > SCHEMA_VERSION:
            self._conn.close()
            raise ValueError("this project was created by a newer version of the application")
        if version == 1:
            self._conn.execute("ALTER TABLE positions ADD COLUMN distribute INTEGER")
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.commit()
        if version == 0:
            self._conn.executescript(SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._write_settings(Settings(total_amount=Decimal("0")))
            self._conn.commit()

    # -- lifecycle ---------------------------------------------------------
    @property
    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def backup_to(self, path: str | Path) -> None:
        """Write a consistent copy of the whole project to `path`."""
        destination = sqlite3.connect(str(path))
        try:
            self._conn.backup(destination)
        finally:
            destination.close()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ProjectStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- reads -------------------------------------------------------------
    def load(self) -> Project:
        c = self._conn
        s = c.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        settings = Settings(
            total_amount=Decimal(s["total_amount"]),
            months_paid=s["months_paid"],
            expected_days_per_month=s["expected_days_per_month"],
            weight_time=Decimal(s["weight_time"]),
            weight_responsibility=Decimal(s["weight_responsibility"]),
            weight_seniority=Decimal(s["weight_seniority"]),
            weight_contribution=Decimal(s["weight_contribution"]),
            responsibility_bands=_bands(s["responsibility_bands"]),
            seniority_bands=_bands(s["seniority_bands"]),
        )
        areas = [
            Area(r["id"], r["name"], r["sort_order"])
            for r in c.execute("SELECT * FROM areas ORDER BY sort_order, id")
        ]
        positions = [
            Position(
                r["id"],
                r["area_id"],
                r["name"],
                r["approved"],
                r["vacant"],
                r["temp_vacant"],
                Decimal(r["salary"]),
                r["months_unexecuted"],
                r["distribute"],
            )
            for r in c.execute("SELECT * FROM positions ORDER BY id")
        ]
        workers = [
            Worker(
                id=r["id"],
                full_name=r["full_name"],
                national_id=r["national_id"],
                area_id=r["area_id"],
                position_name=r["position_name"],
                salary_group=r["salary_group"],
                seniority_years=r["seniority_years"],
                days_worked=r["days_worked"],
                contribution=r["contribution"],
                eligible=bool(r["eligible"]),
            )
            for r in c.execute("SELECT * FROM workers ORDER BY id")
        ]
        return Project(settings, areas, positions, workers)

    # -- settings ----------------------------------------------------------
    def save_settings(self, settings: Settings) -> None:
        self._write_settings(settings)
        self._conn.commit()

    def _write_settings(self, s: Settings) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO settings VALUES (1,?,?,?,?,?,?,?,?,?)",
            (
                str(s.total_amount),
                s.months_paid,
                s.expected_days_per_month,
                str(s.weight_time),
                str(s.weight_responsibility),
                str(s.weight_seniority),
                str(s.weight_contribution),
                json.dumps(s.responsibility_bands),
                json.dumps(s.seniority_bands),
            ),
        )

    # -- areas -------------------------------------------------------------
    def add_area(self, name: str) -> Area:
        order = self._conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM areas").fetchone()[0]
        cur = self._conn.execute("INSERT INTO areas (name, sort_order) VALUES (?, ?)", (name, order))
        self._conn.commit()
        return Area(cur.lastrowid, name, order)

    def rename_area(self, area_id: int, name: str) -> None:
        self._conn.execute("UPDATE areas SET name = ? WHERE id = ?", (name, area_id))
        self._conn.commit()

    def delete_area(self, area_id: int) -> None:
        count = self._conn.execute("SELECT COUNT(*) FROM workers WHERE area_id = ?", (area_id,)).fetchone()[0]
        if count:
            raise AreaInUseError(f"the area still has {count} worker(s)")
        self._conn.execute("DELETE FROM areas WHERE id = ?", (area_id,))
        self._conn.commit()

    # -- positions ---------------------------------------------------------
    def add_position(self, p: Position) -> Position:
        cur = self._conn.execute(
            "INSERT INTO positions (area_id, name, approved, vacant, temp_vacant, salary,"
            " months_unexecuted, distribute) VALUES (?,?,?,?,?,?,?,?)",
            (
                p.area_id,
                p.name,
                p.approved,
                p.vacant,
                p.temp_vacant,
                str(p.salary),
                p.months_unexecuted,
                p.distribute,
            ),
        )
        self._conn.commit()
        return replace(p, id=cur.lastrowid)

    def update_position(self, p: Position) -> None:
        self._conn.execute(
            "UPDATE positions SET area_id=?, name=?, approved=?, vacant=?, temp_vacant=?, salary=?,"
            " months_unexecuted=?, distribute=? WHERE id=?",
            (
                p.area_id,
                p.name,
                p.approved,
                p.vacant,
                p.temp_vacant,
                str(p.salary),
                p.months_unexecuted,
                p.distribute,
                p.id,
            ),
        )
        self._conn.commit()

    def delete_position(self, position_id: int) -> None:
        self._conn.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        self._conn.commit()

    # -- workers -----------------------------------------------------------
    def add_worker(self, w: Worker) -> Worker:
        cur = self._conn.execute(
            "INSERT INTO workers (full_name, national_id, area_id, position_name, salary_group,"
            " seniority_years, days_worked, contribution, eligible) VALUES (?,?,?,?,?,?,?,?,?)",
            _worker_values(w),
        )
        self._conn.commit()
        return replace(w, id=cur.lastrowid)

    def update_worker(self, w: Worker) -> None:
        self._conn.execute(
            "UPDATE workers SET full_name=?, national_id=?, area_id=?, position_name=?, salary_group=?,"
            " seniority_years=?, days_worked=?, contribution=?, eligible=? WHERE id=?",
            (*_worker_values(w), w.id),
        )
        self._conn.commit()

    def delete_worker(self, worker_id: int) -> None:
        self._conn.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        self._conn.commit()


def _worker_values(w: Worker) -> tuple:
    return (
        w.full_name,
        w.national_id,
        w.area_id,
        w.position_name,
        w.salary_group,
        w.seniority_years,
        w.days_worked,
        w.contribution,
        int(w.eligible),
    )


def _bands(text: str) -> tuple[tuple[int, int], ...]:
    return tuple((lower, score) for lower, score in json.loads(text))
