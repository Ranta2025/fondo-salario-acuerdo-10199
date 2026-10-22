from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fondo_salario.domain.scales import (
    DEFAULT_RESPONSIBILITY_BANDS,
    DEFAULT_SENIORITY_BANDS,
    Bands,
)


@dataclass(frozen=True)
class Settings:
    total_amount: Decimal
    months_paid: int = 3
    expected_days_per_month: int = 24
    weight_time: Decimal = Decimal("0.40")
    weight_responsibility: Decimal = Decimal("0.25")
    weight_seniority: Decimal = Decimal("0.15")
    weight_contribution: Decimal = Decimal("0.20")
    responsibility_bands: Bands = DEFAULT_RESPONSIBILITY_BANDS
    seniority_bands: Bands = DEFAULT_SENIORITY_BANDS

    @property
    def weights_sum(self) -> Decimal:
        return (
            self.weight_time + self.weight_responsibility + self.weight_seniority + self.weight_contribution
        )


@dataclass(frozen=True)
class Area:
    id: int
    name: str
    order: int = 0


@dataclass(frozen=True)
class Position:
    id: int
    area_id: int
    name: str
    approved: int
    vacant: int
    temp_vacant: int
    salary: Decimal
    months_unexecuted: int


@dataclass(frozen=True)
class Worker:
    id: int
    full_name: str
    national_id: str
    area_id: int
    salary_group: int
    seniority_years: int
    days_worked: int
    contribution: int
    position_name: str = ""
    eligible: bool = True
