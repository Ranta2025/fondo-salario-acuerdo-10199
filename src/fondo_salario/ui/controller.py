"""Application logic behind the screens; no tkinter imports so it is testable without a display."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path

from fondo_salario.domain.calculation import CalculationResult, calculate
from fondo_salario.domain.models import Area, Position, Settings, Worker
from fondo_salario.export.excel_report import export_report
from fondo_salario.importers.merge import ImportPlan, plan_structure, plan_workers, resolve
from fondo_salario.importers.structure import AreaRow
from fondo_salario.importers.workers import WorkerRow, normalize_area
from fondo_salario.persistence.sqlite_repo import Project, ProjectStore

DEFAULT_CONTRIBUTION = 3


@dataclass
class ImportSummary:
    added: int = 0  # workers added
    areas_added: int = 0
    positions_added: int = 0
    completed: int = 0  # values of existing records filled in automatically
    overwritten: int = 0  # differing values replaced after the user accepted them
    kept: int = 0  # differing values the user decided to keep
    unchanged: int = 0  # records of the file that were already complete
    records_updated: int = 0
    defaults_used: int = 0
    undefined: int = 0  # imported without salary group or seniority; they must be completed by hand
    areas_created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


WorkerImportSummary = ImportSummary  # earlier name


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

    # -- imports (merge into existing data) --------------------------------------------------
    def plan_workers_import(
        self,
        rows: list[WorkerRow],
        create_missing_areas: bool = False,
        allow_undefined: bool = False,
    ) -> ImportPlan:
        """What importing these workers would do. Areas match ignoring number prefixes («3.- Dir» = «Dir»).

        With `allow_undefined`, a missing salary group or seniority is stored as 0 («sin definir»): the
        calculation then reports the worker and pays 0.00 until the data is completed.
        """
        p = self.project
        return plan_workers(rows, p.areas, p.workers, create_missing_areas, allow_undefined)

    def plan_structure_import(self, rows: list[AreaRow]) -> ImportPlan:
        return plan_structure(rows, self.project.areas, self.project.positions)

    def apply_import(self, plan: ImportPlan) -> ImportSummary:
        """Store the plan: add what is new, complete what is empty, apply the differences the user accepted.

        Differences that were not accepted (`accept` is not True) keep the stored value. Nothing is deleted.
        """
        settings = self.project.settings
        full_period = settings.expected_days_per_month * settings.months_paid
        summary = ImportSummary(
            unchanged=plan.unchanged, skipped=list(plan.skipped), undefined=plan.undefined
        )
        created: dict[str, Area] = {}

        def area_id_for(ref: int | str) -> int:
            if isinstance(ref, int):
                return ref
            key = normalize_area(ref)
            if key not in created:
                created[key] = self._store.add_area(ref)
                summary.areas_created.append(ref)
            return created[key].id

        for new in plan.new_workers:
            row = new.row
            self._store.add_worker(
                Worker(
                    id=0,
                    full_name=row.full_name,
                    national_id=row.national_id,
                    area_id=area_id_for(new.area),
                    position_name=row.position,
                    salary_group=row.salary_group or 0,
                    seniority_years=row.seniority_years or 0,
                    days_worked=full_period if row.days_worked is None else row.days_worked,
                    contribution=DEFAULT_CONTRIBUTION if row.contribution is None else row.contribution,
                    eligible=False,  # the right to collect is granted by hand, worker by worker
                )
            )
            summary.added += 1
            summary.defaults_used += int(new.defaulted)
        for area_row in plan.new_areas:
            area = self._store.add_area(area_row.name)
            summary.areas_added += 1
            for p in area_row.positions:
                self._add_imported_position(area.id, p)
                summary.positions_added += 1
        for new_position in plan.new_positions:
            self._add_imported_position(new_position.area_id, new_position.row)
            summary.positions_added += 1

        workers = {w.id: w for w in self.project.workers}
        positions = {p.id: p for p in self.project.positions}
        for item in plan.items:
            changes = dict(item.fills)
            summary.completed += len(item.fills)
            for diff in item.conflicts:
                if diff.accept:
                    changes[diff.key] = diff.value
                    summary.overwritten += 1
                else:
                    summary.kept += 1
            if not changes:
                continue
            summary.records_updated += 1
            if item.kind == "worker":
                if "area_id" in changes:
                    changes["area_id"] = area_id_for(changes["area_id"])
                self._store.update_worker(replace(workers[item.target_id], **changes))
            else:
                position = positions[item.target_id]
                if "vacant" in changes:
                    changes["approved"] = max(position.approved, changes["vacant"])
                self._store.update_position(replace(position, **changes))
        self.refresh()
        return summary

    def _add_imported_position(self, area_id: int, row) -> None:
        self._store.add_position(
            Position(0, area_id, row.name, row.vacant, row.vacant, 0, row.salary, row.months_unexecuted)
        )

    def import_structure(self, rows: list[AreaRow]) -> int:
        """Non-interactive import (keeps stored values on differences). Returns the number of new areas."""
        plan = self.plan_structure_import(rows)
        resolve(plan, "keep_all")
        return self.apply_import(plan).areas_added

    def import_workers(
        self,
        rows: list[WorkerRow],
        create_missing_areas: bool = False,
        allow_undefined: bool = False,
    ) -> ImportSummary:
        """Non-interactive import (keeps stored values on differences)."""
        plan = self.plan_workers_import(rows, create_missing_areas, allow_undefined)
        resolve(plan, "keep_all")
        return self.apply_import(plan)

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
