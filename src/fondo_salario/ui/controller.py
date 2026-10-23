"""Application logic behind the screens; no tkinter imports so it is testable without a display."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from fondo_salario.domain.calculation import CalculationResult, calculate
from fondo_salario.domain.models import Area, Position, Settings, Worker
from fondo_salario.export.excel_report import export_report
from fondo_salario.importers.structure import AreaRow
from fondo_salario.importers.workers import WorkerRow, _normalize_header, normalize_area
from fondo_salario.persistence.sqlite_repo import Project, ProjectStore

DEFAULT_CONTRIBUTION = 3


@dataclass
class WorkerImportSummary:
    added: int = 0
    defaults_used: int = 0
    undefined: int = 0  # imported without salary group or seniority; they must be completed by hand
    areas_created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


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

    def delete_worker(self, worker_id: int) -> None:
        self._store.delete_worker(worker_id)
        self.refresh()

    # -- imports ------------------------------------------------------------------------
    def import_structure(self, rows: list[AreaRow]) -> int:
        existing = {_normalize_header(a.name) for a in self.project.areas}
        added = 0
        for row in rows:
            if _normalize_header(row.name) in existing:
                continue
            area = self._store.add_area(row.name)
            existing.add(_normalize_header(row.name))
            for p in row.positions:
                self._store.add_position(
                    Position(0, area.id, p.name, p.vacant, p.vacant, 0, p.salary, p.months_unexecuted)
                )
            added += 1
        self.refresh()
        return added

    def import_workers(
        self,
        rows: list[WorkerRow],
        create_missing_areas: bool = False,
        allow_undefined: bool = False,
    ) -> WorkerImportSummary:
        """Add workers. Areas match ignoring number prefixes («3.- Dir» = «Dir»), accents and case.

        With `allow_undefined`, a missing salary group or seniority is stored as 0 («sin definir»): the
        calculation then reports the worker and pays 0.00 until the data is completed.
        """
        by_name = {normalize_area(a.name): a for a in self.project.areas}
        settings = self.project.settings
        full_period = settings.expected_days_per_month * settings.months_paid
        known = [(_normalize_header(w.full_name), w.national_id.strip()) for w in self.project.workers]
        summary = WorkerImportSummary()
        for row in rows:
            key = (_normalize_header(row.full_name), row.national_id.strip())
            if _is_duplicate(key, known):
                summary.skipped.append(f"{row.full_name}: ya existe")
                continue
            area = _find_area(row, by_name, self.project.areas)
            if area is None and create_missing_areas and row.area.strip():
                area = self._store.add_area(row.area.strip())
                by_name[normalize_area(row.area)] = area
                summary.areas_created.append(area.name)
            if area is None:
                summary.skipped.append(f"{row.full_name}: área desconocida «{row.area}»")
                continue
            incomplete = row.salary_group is None or row.seniority_years is None
            if incomplete and not allow_undefined:
                summary.skipped.append(f"{row.full_name}: falta el grupo salarial o la antigüedad")
                continue
            defaulted = row.days_worked is None or row.contribution is None
            self._store.add_worker(
                Worker(
                    id=0,
                    full_name=row.full_name,
                    national_id=row.national_id,
                    area_id=area.id,
                    position_name=row.position,
                    salary_group=row.salary_group or 0,
                    seniority_years=row.seniority_years or 0,
                    days_worked=full_period if row.days_worked is None else row.days_worked,
                    contribution=DEFAULT_CONTRIBUTION if row.contribution is None else row.contribution,
                )
            )
            known.append(key)
            summary.added += 1
            summary.defaults_used += int(defaulted)
            summary.undefined += int(incomplete)
        self.refresh()
        return summary

    # -- export -------------------------------------------------------------------------
    def export(self, path: str | Path) -> None:
        export_report(path, self.project.settings, self.calculation())


def _find_area(row: WorkerRow, by_name: dict[str, Area], ordered: list[Area]) -> Area | None:
    """Exact name, then one name contained in the other, then the legacy area number."""
    key = normalize_area(row.area)
    if key in by_name:
        return by_name[key]
    contained = [a for k, a in by_name.items() if len(min(k, key, key=len)) >= 5 and (k in key or key in k)]
    if len(contained) == 1:
        return contained[0]
    if row.area_number and 1 <= row.area_number <= len(ordered):
        return ordered[row.area_number - 1]
    return None


def _is_duplicate(key: tuple[str, str], known: list[tuple[str, str]]) -> bool:
    """Same normalized name and the same ID number (or one of the two has no ID yet)."""
    name, national_id = key
    return any(n == name and (not i or not national_id or i == national_id) for n, i in known)


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
