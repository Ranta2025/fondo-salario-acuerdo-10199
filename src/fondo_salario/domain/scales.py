"""Evaluation scales: map raw values to 1..5 scores."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

# (lower bound inclusive, score); the highest bound <= value wins.
Bands = tuple[tuple[int, int], ...]

DEFAULT_RESPONSIBILITY_BANDS: Bands = ((1, 1), (6, 2), (11, 3), (16, 4), (21, 5))
# Rafelito 3: up to 5 years 1 point, 6-10 -> 2, 11-15 -> 3, 16-20 -> 4, more than 20 -> 5
DEFAULT_SENIORITY_BANDS: Bands = ((0, 1), (6, 2), (11, 3), (16, 4), (21, 5))

MAX_SCORE = 5


def band_score(value: int, bands: Bands) -> int:
    score = bands[0][1]
    for lower, band in bands:
        if value >= lower:
            score = band
    return score


def time_score(days_worked: int, expected_days: int, months: int) -> int:
    """Score 1..5 from the share of potential days worked; 0 when nothing was worked.

    Ranges (Rafelito 3): more than 0-20 % -> 1, >20-40 % -> 2, >40-60 % -> 3, >60-80 % -> 4, >80-100 % -> 5.
    """
    if days_worked <= 0:
        return 0
    potential = expected_days * months
    score = (Decimal(MAX_SCORE * days_worked) / Decimal(potential)).to_integral_value(rounding=ROUND_CEILING)
    return int(min(max(score, 1), MAX_SCORE))


_ROMAN_PAIRS = ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))


def to_roman(number: int) -> str:
    out = ""
    for value, symbol in _ROMAN_PAIRS:
        while number >= value:
            out += symbol
            number -= value
    return out


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def parse_roman(text: str) -> int | None:
    """Value of a roman numeral, or None when the text is not one."""
    text = text.strip().upper()
    total, previous = 0, 0
    for char in reversed(text):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        total += -value if value < previous else value
        previous = max(previous, value)
    return total if total and to_roman(total) == text else None  # only well-formed numerals count
