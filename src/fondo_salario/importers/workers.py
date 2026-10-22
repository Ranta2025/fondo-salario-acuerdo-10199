"""Import workers from a user-provided CSV or XLSX file."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}

FIELD_ALIASES = {
    "full_name": {
        "nombre",
        "nombreyapellidos",
        "nombrecompleto",
        "trabajador",
        "name",
        "fullname",
    },
    "national_id": {
        "ci",
        "carne",
        "carneidentidad",
        "carnedeidentidad",
        "identidad",
        "nationalid",
        "id",
    },
    "area": {"area", "departamento"},
    "position": {"cargo", "plaza", "puesto", "position"},
    "salary_group": {"grupo", "gruposalarial", "grupoescala", "salarygroup"},
    "seniority_years": {
        "antiguedad",
        "anos",
        "aniosantiguedad",
        "seniority",
        "seniorityyears",
    },
    "days_worked": {"dias", "diastrabajados", "tiempotrabajado", "daysworked"},
    "contribution": {"contribucion", "evaluacion", "contribution"},
}
REQUIRED = ("full_name", "area")


@dataclass
class WorkerRow:
    full_name: str
    national_id: str
    area: str
    position: str = ""
    salary_group: int | None = None
    seniority_years: int | None = None
    days_worked: int | None = None
    contribution: int | None = None


@dataclass
class RowError:
    line: int
    message: str


@dataclass
class WorkerImportResult:
    rows: list[WorkerRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def _normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _map_headers(headers: list[object]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, header in enumerate(headers):
        key = _normalize_header(header)
        for field_name, aliases in FIELD_ALIASES.items():
            if key in aliases and field_name not in mapping:
                mapping[field_name] = index
    return mapping


def parse_roman(text: str) -> int | None:
    total, previous = 0, 0
    for char in reversed(text.upper()):
        value = ROMAN.get(char)
        if value is None:
            return None
        total += -value if value < previous else value
        previous = max(previous, value)
    return total


def _to_int(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (int, float)):
        if float(value) != int(value):
            raise ValueError("not a whole number")
        return int(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+([.,]0+)?", text):
        return int(re.split(r"[.,]", text)[0])
    raise ValueError("not a whole number")


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def _normalize_national_id(value: object) -> str:
    if isinstance(value, float) and value == int(value):
        value = int(value)
    text = _clean_text(value)
    return text.zfill(11) if text.isdigit() and len(text) < 11 else text


def _parse_group(value: object) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    return parse_roman(text) if not text.isdigit() else int(text)


def _in_range(name: str, number: int | None, low: int, high: int) -> None:
    if number is not None and not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


def _build_row(raw: list[object], columns: dict[str, int]) -> WorkerRow:
    def cell(name: str) -> object:
        index = columns.get(name)
        return raw[index] if index is not None and index < len(raw) else None

    group = _parse_group(cell("salary_group"))
    if cell("salary_group") not in (None, "") and group is None:
        raise ValueError("salary group is not a valid number or roman numeral")
    _in_range("salary group", group, 1, 25)
    seniority = _to_int(cell("seniority_years"))
    _in_range("seniority", seniority, 0, 60)
    days = _to_int(cell("days_worked"))
    _in_range("days worked", days, 0, 10_000)
    contribution = _to_int(cell("contribution"))
    _in_range("contribution", contribution, 1, 5)
    return WorkerRow(
        full_name=_clean_text(cell("full_name")),
        national_id=_normalize_national_id(cell("national_id")),
        area=_clean_text(cell("area")),
        position=_clean_text(cell("position")),
        salary_group=group,
        seniority_years=seniority,
        days_worked=days,
        contribution=contribution,
    )


def _read_table(path: Path) -> list[list[object]]:
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            return [list(row) for row in workbook.worksheets[0].iter_rows(values_only=True)]
        finally:
            workbook.close()
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:  # CSV saved by Excel on Windows
        text = raw.decode("cp1252", errors="replace")
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
    return [list(row) for row in csv.reader(io.StringIO(text, newline=""), dialect)]


def read_workers(path: str | Path) -> WorkerImportResult:
    """Read workers; invalid rows are reported in `errors`, never raised."""
    table = _read_table(Path(path))
    result = WorkerImportResult()
    if not table:
        result.errors.append(RowError(1, "the file is empty"))
        return result
    columns = _map_headers(table[0])
    missing = [name for name in REQUIRED if name not in columns]
    if missing:
        result.errors.append(RowError(1, f"missing required columns: {', '.join(missing)}"))
        return result
    for line, raw in enumerate(table[1:], start=2):
        if all(_clean_text(value) == "" for value in raw):
            continue
        try:
            row = _build_row(raw, columns)
            if not row.full_name or not row.area:
                raise ValueError("name and area are required")
        except ValueError as error:
            result.errors.append(RowError(line, str(error)))
            continue
        result.rows.append(row)
    return result
