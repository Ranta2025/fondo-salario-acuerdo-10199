"""Evaluation scales: map raw values to 1..5 scores."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# (lower bound inclusive, score); the highest bound <= value wins.
Bands = tuple[tuple[int, int], ...]

DEFAULT_RESPONSIBILITY_BANDS: Bands = ((1, 1), (6, 2), (11, 3), (16, 4), (21, 5))
DEFAULT_SENIORITY_BANDS: Bands = ((0, 1), (8, 2), (15, 3), (22, 4), (29, 5))

MAX_SCORE = 5


def band_score(value: int, bands: Bands) -> int:
    score = bands[0][1]
    for lower, band in bands:
        if value >= lower:
            score = band
    return score


def time_score(days_worked: int, expected_days: int, months: int) -> int:
    """0 when nothing was worked, otherwise the worked ratio scaled to 1..5."""
    if days_worked <= 0:
        return 0
    ratio = Decimal(days_worked) / Decimal(expected_days * months)
    scaled = (ratio * MAX_SCORE).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(min(max(scaled, 1), MAX_SCORE))
