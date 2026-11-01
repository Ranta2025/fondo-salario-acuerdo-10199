"""Totals shown in «Resultados» and written in the Excel report, so both always agree."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fondo_salario.domain.calculation import CalculationResult
from fondo_salario.domain.models import Position


@dataclass(frozen=True)
class StructureTotals:
    """Sums of the numeric columns of the «Áreas y cargos» table (the months are not added up)."""

    approved: int = 0
    vacant: int = 0
    temp_vacant: int = 0
    to_distribute: int = 0
    salary: Decimal = Decimal(0)
    unexecuted: Decimal = Decimal(0)


def structure_totals(positions: list[Position]) -> StructureTotals:
    return StructureTotals(
        approved=sum(p.approved for p in positions),
        vacant=sum(p.vacant for p in positions),
        temp_vacant=sum(p.temp_vacant for p in positions),
        to_distribute=sum(p.to_distribute for p in positions),
        salary=sum((p.salary for p in positions), Decimal(0)),
        unexecuted=sum((p.unexecuted for p in positions), Decimal(0)),
    )


@dataclass(frozen=True)
class AreaTotals:
    """The areas table of «Resultados»: the structure totals plus the share and amount to pay."""

    structure: StructureTotals
    pct: Decimal
    amount: Decimal


def area_totals(result: CalculationResult) -> AreaTotals:
    positions = [p.position for a in result.areas for p in a.positions]
    return AreaTotals(
        structure=structure_totals(positions),
        pct=sum((a.pct for a in result.areas), Decimal(0)),
        amount=sum((a.amount for a in result.areas), Decimal(0)),
    )


@dataclass(frozen=True)
class WorkerTotals:
    """Totals of the workers table: how many there are, how many may collect and collect, and the sums."""

    workers: int
    entitled: int
    paid: int
    coefficient: Decimal
    amount: Decimal


def worker_totals(result: CalculationResult) -> WorkerTotals:
    return WorkerTotals(
        workers=len(result.workers),
        entitled=sum(1 for r in result.workers if r.worker.eligible),
        paid=sum(1 for r in result.workers if r.amount > 0),
        coefficient=sum((r.coefficient for r in result.workers), Decimal(0)),
        amount=sum((r.amount for r in result.workers), Decimal(0)),
    )
