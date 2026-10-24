"""Application logic behind the screens; no tkinter imports so it is testable without a display."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path

from fondo_salario.domain.calculation import CalculationResult, calculate
from fondo_salario.domain.models import Area, Position, Settings, Worker
from fondo_salario.export.excel_report import export_report
from fondo_salario.importers.table import (
    StructurePlan,
    WorkersPlan,
    key,
    plan_structure,
    plan_workers,
    read_structure,
    read_workers,
    write_template,
)
from fondo_salario.persistence.sqlite_repo import Project, ProjectStore


@dataclass
class ImportSummary:
    """What an import added; existing records are never changed."""

    workers_added: int = 0
    areas_added: int = 0
    positions_added: int = 0
    unchanged: int = 0  # records of the file that were already stored
    skipped: list[str] = field(default_factory=list)  # rows that could not be used, with the reason


class Controller:
    def __init__(self, store: ProjectStore):
        self._store = store
        self.project: Project = store.load()

    @property
    def dirty(self) -> bool:
        return self._store.dirty

    def save(self) -> None:
        self._store.save()

    def discard(self) -> None:
        self._store.discard()
        self.refresh()

    def refresh(self) -> Project:
        self.project = self._store.load()
        return self.project

    def position(self, position_id: int) -> Position:
        return next(p for p in self.project.positions if p.id == position_id)

    def worker(self, worker_id: int) -> Worker:
        return next(w for w in self.project.workers if w.id == worker_id)

    def calculation(self) -> CalculationResult:
        p = self.project
        return calculate(p.settings, p.areas, p.positions, p.workers)

    # -- settings / areas / positions / workers (thin wrappers that keep state fresh) ----
    def save_settings(self, settings: Settings) -> None:
        self._store.save_settings(settings)
        self.refresh()

    def add_area(self, name: str) -> Area:
        area = self._store.add_area(name)
        self.refresh()
        return area

    def rename_area(self, area_id: int, name: str) -> None:
        self._store.rename_area(area_id, name)
        self.refresh()

    def delete_area(self, area_id: int) -> None:
        self._store.delete_area(area_id)
        self.refresh()

    def add_position(self, position: Position) -> Position:
        saved = self._store.add_position(position)
        self.refresh()
        return saved

    def update_position(self, position: Position) -> None:
        self._store.update_position(position)
        self.refresh()

    def delete_position(self, position_id: int) -> None:
        self._store.delete_position(position_id)
        self.refresh()

    def add_worker(self, worker: Worker) -> Worker:
        saved = self._store.add_worker(worker)
        self.refresh()
        return saved

    def update_worker(self, worker: Worker) -> None:
        self._store.update_worker(worker)
        self.refresh()

    def set_eligible(self, worker_ids: list[int], eligible: bool) -> None:
        """Give or take away the right to collect for several workers at once."""
        wanted = set(worker_ids)
        for worker in self.project.workers:
            if worker.id in wanted and worker.eligible != eligible:
                self._store.update_worker(replace(worker, eligible=eligible))
        self.refresh()

    def delete_worker(self, worker_id: int) -> None:
        self._store.delete_worker(worker_id)
        self.refresh()

    def clear_workers(self) -> int:
        """Delete every worker (areas, positions and parameters stay). Returns how many were deleted."""
        workers = list(self.project.workers)
        for worker in workers:
            self._store.delete_worker(worker.id)
        self.refresh()
        return len(workers)

    def clear_structure(self) -> tuple[int, int, int]:
        """Delete every worker, position and area (the parameters stay): (workers, positions, areas)."""
        project = self.project
        workers = self.clear_workers()
        for position in project.positions:
            self._store.delete_position(position.id)
        for area in project.areas:
            self._store.delete_area(area.id)
        self.refresh()
        return workers, len(project.positions), len(project.areas)

    # -- imports (fixed structure, add-only) -------------------------------------------------
    def plan_workers_import(self, path: str | Path) -> WorkersPlan:
        """What importing this file would add. Raises ImportFormatError when the structure is wrong."""
        p = self.project
        return plan_workers(read_workers(path), p.areas, p.workers)

    def plan_structure_import(self, path: str | Path) -> StructurePlan:
        p = self.project
        return plan_structure(read_structure(path), p.areas, p.positions)

    def apply_workers_import(self, plan: WorkersPlan) -> ImportSummary:
        """Add the new workers (without the right to collect unless the file says so)."""
        areas = {key(a.name): a.id for a in self.project.areas}
        for row in plan.new:
            self._store.add_worker(
                Worker(
                    id=0,
                    full_name=row.name,
                    national_id=row.national_id,
                    area_id=areas[key(row.area)],
                    position_name=row.position,
                    salary_group=row.salary_group,
                    seniority_years=row.seniority_years,
                    days_worked=row.days_worked,
                    contribution=row.contribution,
                    eligible=row.eligible,
                )
            )
        self.refresh()
        return ImportSummary(
            workers_added=len(plan.new), unchanged=plan.unchanged, skipped=list(plan.skipped)
        )

    def apply_structure_import(self, plan: StructurePlan) -> ImportSummary:
        """Add the new areas and positions."""
        areas = {key(a.name): a.id for a in self.project.areas}
        for name in plan.new_areas:
            areas[key(name)] = self._store.add_area(name).id
        for row in plan.new_positions:
            self._store.add_position(
                Position(
                    0,
                    areas[key(row.area)],
                    row.position,
                    row.approved,
                    row.vacant,
                    row.temp_vacant,
                    row.salary,
                    row.months_unexecuted,
                    row.distribute,
                )
            )
        self.refresh()
        return ImportSummary(
            areas_added=len(plan.new_areas),
            positions_added=len(plan.new_positions),
            unchanged=plan.unchanged,
            skipped=list(plan.skipped),
        )

    def save_template(self, path: str | Path) -> None:
        write_template(path)

    # -- export -------------------------------------------------------------------------
    def export(self, path: str | Path) -> None:
        export_report(path, self.project.settings, self.calculation())


def parse_money(text: str) -> Decimal:
    """Accept '1 234,56', '1,234.56' and '1234.56'."""
    cleaned = text.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = (
            cleaned.replace(",", "")
            if cleaned.rfind(".") > cleaned.rfind(",")
            else cleaned.replace(".", "").replace(",", ".")
        )
    else:
        cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def resolve_distribute(text: str, total_vacancies: int) -> int | None:
    """Blank or equal to the total means «all vacancies» (stored as None)."""
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        number = int(cleaned)
    except ValueError:
        raise ValueError("«Vacantes a distribuir» debe ser un número entero.") from None
    if number < 0:
        raise ValueError("«Vacantes a distribuir» no puede ser negativo.")
    if number > total_vacancies:
        raise ValueError(
            f"«Vacantes a distribuir» no puede ser mayor que las vacantes que hay ({total_vacancies})."
        )
    return None if number == total_vacancies else number
