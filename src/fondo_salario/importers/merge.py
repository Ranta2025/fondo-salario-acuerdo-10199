"""Plan an import into data that already exists.

New records are added; records that already exist are joined: values the stored record lacks are completed
automatically, and values that differ are returned as conflicts for the user to decide one by one.
Nothing is ever deleted. This module is pure (no database, no UI) so it can be tested in isolation.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from fondo_salario.domain.models import Area, Position, Worker
from fondo_salario.domain.scales import to_roman
from fondo_salario.importers.structure import AreaRow, PositionRow
from fondo_salario.importers.workers import (
    AREA_NUMBER_PREFIX,
    WorkerRow,
    _normalize_header,
    normalize_area,
)


@dataclass
class FieldDiff:
    """A value that exists on both sides and differs."""

    key: str  # attribute of the stored record
    label: str  # Spanish label for the user
    current: str  # what is stored (display text)
    incoming: str  # what the file says (display text)
    value: object  # what gets stored if the user accepts
    accept: bool | None = None  # None = undecided


@dataclass
class MergeItem:
    kind: str  # "worker" | "position"
    target_id: int
    name: str
    fills: dict[str, object] = field(default_factory=dict)  # stored without asking
    fill_labels: list[str] = field(default_factory=list)
    conflicts: list[FieldDiff] = field(default_factory=list)


@dataclass
class NewWorker:
    row: WorkerRow
    area: int | str  # id of an existing area, or the name of an area to create
    incomplete: bool  # no salary group or seniority in the file
    defaulted: bool  # days or contribution filled with defaults


@dataclass
class NewPosition:
    area_id: int
    row: PositionRow


@dataclass
class ImportPlan:
    kind: str  # "workers" | "structure"
    new_workers: list[NewWorker] = field(default_factory=list)
    new_areas: list[AreaRow] = field(default_factory=list)
    new_positions: list[NewPosition] = field(default_factory=list)
    areas_to_create: list[str] = field(default_factory=list)
    items: list[MergeItem] = field(default_factory=list)
    unchanged: int = 0
    undefined: int = 0
    skipped: list[str] = field(default_factory=list)

    @property
    def new_count(self) -> int:
        return len(self.new_workers) + len(self.new_areas) + len(self.new_positions)

    @property
    def fill_count(self) -> int:
        return sum(len(i.fills) for i in self.items)

    @property
    def conflicts(self) -> list[tuple[MergeItem, FieldDiff]]:
        return [(item, diff) for item in self.items for diff in item.conflicts]


# -- helpers --------------------------------------------------------------------------------
def _same_text(a: str, b: str) -> bool:
    return _normalize_header(a) == _normalize_header(b)


def _group_text(group: int) -> str:
    return to_roman(group) if 1 <= group <= 25 else "—"


AREA_STOPWORDS = {
    "de",
    "la",
    "el",
    "los",
    "las",
    "del",
    "y",
    "en",
    "a",
    "grupo",
    "departamento",
    "dpto",
    "seccion",
}


def _area_tokens(name: str) -> frozenset[str]:
    """Distinctive words of an area name: no prefix number, accents, articles or generic words."""
    text = unicodedata.normalize("NFKD", AREA_NUMBER_PREFIX.sub("", name)).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(w.rstrip("s") if len(w) > 3 else w for w in words if w not in AREA_STOPWORDS)


def find_area(name: str, number: int | None, areas: list[Area], loose: bool = True) -> Area | None:
    """Exact name, one name inside the other, the same distinctive words, then the legacy area number."""
    key = normalize_area(name)
    by_name = {normalize_area(a.name): a for a in areas}
    if key in by_name:
        return by_name[key]
    contained = [a for k, a in by_name.items() if len(min(k, key, key=len)) >= 5 and (k in key or key in k)]
    if loose and len(contained) == 1:
        return contained[0]
    tokens = _area_tokens(name)
    if tokens:
        same = [a for a in areas if _area_tokens(a.name) == tokens]
        if len(same) == 1:
            return same[0]
        overlap = [a for a in areas if (t := _area_tokens(a.name)) and (t < tokens or tokens < t)]
        if len(overlap) == 1 and not same:
            return overlap[0]
    if number and 1 <= number <= len(areas):
        return areas[number - 1]
    return None


def _match_worker(row: WorkerRow, workers: list[Worker]) -> Worker | None:
    """The ID number identifies a person; otherwise the normalized full name does."""
    national_id = row.national_id.strip()
    if national_id:
        for w in workers:
            if w.national_id.strip() == national_id:
                return w
    name = _normalize_header(row.full_name)
    for w in workers:
        if _normalize_header(w.full_name) == name:
            return w
    return None


# -- workers --------------------------------------------------------------------------------
def plan_workers(
    rows: list[WorkerRow],
    areas: list[Area],
    workers: list[Worker],
    create_missing_areas: bool = False,
    allow_undefined: bool = False,
    full_period_days: int = 0,
) -> ImportPlan:
    plan = ImportPlan("workers")
    area_names = {a.id: a.name for a in areas}
    pending: list[WorkerRow] = []  # new rows already accepted, to skip repeats inside the same file
    for row in rows:
        existing = _match_worker(row, workers)
        if existing is not None:
            item = _worker_item(row, existing, areas, area_names, create_missing_areas)
            if item.fills or item.conflicts:
                plan.items.append(item)
            else:
                plan.unchanged += 1
            continue
        if any(_match_worker(row, [_as_worker(p)]) for p in pending):
            plan.unchanged += 1
            continue
        area = find_area(row.area, row.area_number, areas)
        area_ref: int | str
        if area is not None:
            area_ref = area.id
        elif create_missing_areas and row.area.strip():
            area_ref = row.area.strip()
        else:
            reason = f"área desconocida «{row.area}»" if row.area.strip() else "no trae el área"
            plan.skipped.append(f"{row.full_name}: {reason}")
            continue
        incomplete = row.salary_group is None or row.seniority_years is None
        if incomplete and not allow_undefined:
            plan.skipped.append(f"{row.full_name}: falta el grupo salarial o la antigüedad")
            continue
        if isinstance(area_ref, str) and not any(_same_text(area_ref, n) for n in plan.areas_to_create):
            plan.areas_to_create.append(area_ref)
        defaulted = row.days_worked is None or row.contribution is None
        plan.new_workers.append(NewWorker(row, area_ref, incomplete, defaulted))
        plan.undefined += int(incomplete)
        pending.append(row)
    return plan


def _as_worker(row: WorkerRow) -> Worker:
    return Worker(0, row.full_name, row.national_id, 0, 0, 0, 0, 0)


def _worker_item(
    row: WorkerRow,
    worker: Worker,
    areas: list[Area],
    area_names: dict[int, str],
    create_missing_areas: bool,
) -> MergeItem:
    item = MergeItem("worker", worker.id, worker.full_name)
    area = find_area(row.area, row.area_number, areas) if row.area.strip() else None
    area_value: int | str | None = None
    area_text = ""
    if area is not None:
        area_value, area_text = area.id, area.name
    elif create_missing_areas and row.area.strip():
        area_value = area_text = row.area.strip()
    # (key, label, incoming (None = not in the file), current, value to store, current is empty?, same?)
    candidates = [
        ("full_name", "Nombre", row.full_name.strip() or None, worker.full_name, None, False, _same_text),
        (
            "national_id",
            "Carné de identidad",
            row.national_id.strip() or None,
            worker.national_id.strip(),
            None,
            not worker.national_id.strip(),
            lambda a, b: a.strip() == b.strip(),
        ),
        (
            "position_name",
            "Cargo",
            row.position.strip() or None,
            worker.position_name,
            None,
            not worker.position_name.strip(),
            _same_text,
        ),
        (
            "area_id",
            "Área",
            area_text or None,
            area_names.get(worker.area_id, ""),
            area_value,
            False,
            lambda a, b: _same_text(a, b) or (area_value == worker.area_id),
        ),
    ]
    for key, label, incoming, current, value, empty, same in candidates:
        if incoming is None or same(current, incoming):
            continue
        _record(item, key, label, current, incoming, incoming if value is None else value, empty)
    numeric = [
        ("salary_group", "Grupo salarial", row.salary_group, worker.salary_group, worker.salary_group == 0),
        (
            "seniority_years",
            "Antigüedad (años)",
            row.seniority_years,
            worker.seniority_years,
            worker.seniority_years == 0,
        ),
        ("days_worked", "Días trabajados", row.days_worked, worker.days_worked, False),
        ("contribution", "Contribución", row.contribution, worker.contribution, False),
    ]
    for key, label, incoming, current, empty in numeric:
        if incoming is None or incoming == current:
            continue
        show = _group_text if key == "salary_group" else str
        _record(item, key, label, show(current), show(incoming), incoming, empty)
    return item


def _record(item: MergeItem, key: str, label: str, current: str, incoming: str, value: object, empty: bool):
    if empty:
        item.fills[key] = value
        item.fill_labels.append(label)
    else:
        item.conflicts.append(FieldDiff(key, label, str(current), str(incoming), value))


# -- areas and positions ---------------------------------------------------------------------
def plan_structure(rows: list[AreaRow], areas: list[Area], positions: list[Position]) -> ImportPlan:
    plan = ImportPlan("structure")
    for area_row in rows:
        area = find_area(area_row.name, None, areas, loose=False)
        if area is None:
            plan.new_areas.append(area_row)
            continue
        seen: set[str] = set()
        for pos_row in area_row.positions:
            key = _normalize_header(pos_row.name)
            if key in seen:
                continue
            seen.add(key)
            existing = next(
                (p for p in positions if p.area_id == area.id and _normalize_header(p.name) == key), None
            )
            if existing is None:
                plan.new_positions.append(NewPosition(area.id, pos_row))
                continue
            item = _position_item(pos_row, existing)
            if item.fills or item.conflicts:
                plan.items.append(item)
            else:
                plan.unchanged += 1
    return plan


def _position_item(row: PositionRow, position: Position) -> MergeItem:
    item = MergeItem("position", position.id, position.name)
    fields = [
        ("vacant", "Plazas vacantes", row.vacant, position.vacant),
        ("salary", "Salario", row.salary, position.salary),
        ("months_unexecuted", "Meses inejecutados", row.months_unexecuted, position.months_unexecuted),
    ]
    for key, label, incoming, current in fields:
        if not incoming or incoming == current:  # 0 in the file means «no data»
            continue
        text = (lambda v: f"{v:,.2f}") if isinstance(incoming, Decimal) else str
        _record(item, key, label, text(current), text(incoming), incoming, not current)
    return item


# -- deciding ------------------------------------------------------------------------------------
Ask = Callable[[MergeItem, FieldDiff, int, int], "str | None"]


def resolve(plan: ImportPlan, mode: str, ask: Ask | None = None) -> bool:
    """Decide every difference. Returns False if the user cancelled (then nothing must be applied).

    mode: "accept_all" overwrite everything, "keep_all" keep what is stored, "review" ask one by one
    through `ask(item, diff, index, total)`, which answers "overwrite", "keep", "overwrite_rest" (accept this
    and every remaining difference) or None (cancel).
    """
    pairs = plan.conflicts
    if mode == "accept_all":
        for _, diff in pairs:
            diff.accept = True
        return True
    if mode == "keep_all":
        for _, diff in pairs:
            diff.accept = False
        return True
    if mode != "review" or ask is None:
        raise ValueError(f"unknown mode {mode!r}")
    for index, (item, diff) in enumerate(pairs, start=1):
        answer = ask(item, diff, index, len(pairs))
        if answer is None:
            return False
        if answer == "overwrite_rest":
            for _, rest in pairs[index - 1 :]:
                rest.accept = True
            return True
        diff.accept = answer == "overwrite"
    return True
