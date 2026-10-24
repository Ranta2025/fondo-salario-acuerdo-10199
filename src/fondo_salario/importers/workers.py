"""Import workers from a user-provided CSV or XLSX file."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}

HEADER_SCAN_ROWS = 30  # the titles may be preceded by blank rows or a heading
MIN_HEADER_SCORE = 2


def header_role(key: str) -> str | None:
    """Field a normalized column title stands for (letters and digits only), or None."""
    if "area" in key and "cargo" in key:
        return "roster"  # one column holding area rows and position rows
    if "carne" in key or "identidad" in key or key in {"ci", "id", "nationalid"}:
        return "national_id"
    if (
        key.startswith("nombre")
        or "apellidos" in key
        or key.startswith("trabajador")
        or key in {"name", "fullname"}
    ):
        return "full_name"
    if key.startswith("cargo") or key in {"plaza", "puesto", "ocupacion", "position"}:
        return "position"
    if key in {"area", "departamento", "unidad", "dependencia"} or key.startswith("areade"):
        return "area"
    if key.startswith("grupo") or "escala" in key or key == "salarygroup":
        return "salary_group"
    if "antigu" in key or key in {"anos", "anios", "seniority", "seniorityyears"}:
        return "seniority_years"
    if "dias" in key or key.startswith("tiempotrab") or key == "daysworked":
        return "days_worked"
    if "contribu" in key or "evaluacion" in key or "desempe" in key:
        return "contribution"
    return None


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
    area_number: int | None = None  # legacy sheet: number in the area header («11 Grupo Ecn.» -> 11)


@dataclass
class RowError:
    line: int
    message: str


@dataclass
class WorkerImportResult:
    rows: list[WorkerRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    legacy: bool = False  # read from a layout whose areas come from the file itself (create missing ones)
    notes: list[str] = field(default_factory=list)  # what was read and what was ignored


def _normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _map_headers(headers: list[object]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, header in enumerate(headers):
        role = header_role(_normalize_header(header)) if header not in (None, "") else None
        if role and role not in mapping:
            mapping[role] = index
    return mapping


def find_header(table: list[list[object]]) -> tuple[int, dict[str, int]] | None:
    """The row (within the first rows) whose titles match the most known columns, if it matches enough."""
    best: tuple[int, int, dict[str, int]] | None = None
    for index, row in enumerate(table[:HEADER_SCAN_ROWS]):
        mapping = _map_headers(row)
        identifies = mapping.keys() & {"full_name", "national_id", "roster"}
        if not identifies or len(mapping) < MIN_HEADER_SCORE:
            continue
        if best is None or len(mapping) > best[0]:
            best = (len(mapping), index, mapping)
    return None if best is None else (best[1], best[2])


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


def read_tables(path: Path) -> list[tuple[str, list[list[object]]]]:
    """Every sheet of a workbook (or the single CSV table) as (name, rows)."""
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            return [
                (ws.title, [list(row) for row in ws.iter_rows(values_only=True)])
                for ws in workbook.worksheets
            ]
        finally:
            workbook.close()
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:  # CSV saved by Excel on Windows
        text = raw.decode("cp1252", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
    except csv.Error:
        dialect = csv.excel
    return [("", [list(row) for row in csv.reader(io.StringIO(text, newline=""), dialect)])]


def pick_table(path: Path) -> tuple[str, list[list[object]], int, dict[str, int]] | None:
    """The sheet (and header row) that looks most like a table of workers or a staffing roster."""
    best = None
    for name, table in read_tables(path):
        found = find_header(table)
        if found is not None and (best is None or len(found[1]) > len(best[3])):
            best = (name, table, found[0], found[1])
    return best


ROLE_LABELS = {
    "full_name": "Nombre",
    "national_id": "Carné",
    "area": "Área",
    "position": "Cargo",
    "salary_group": "Grupo",
    "seniority_years": "Antigüedad",
    "days_worked": "Días trabajados",
    "contribution": "Contribución",
    "roster": "Áreas y cargos",
}


def _describe(sheet: str, columns: dict[str, int]) -> str:
    used = ", ".join(ROLE_LABELS[k] for k in ROLE_LABELS if k in columns)
    return f"Columnas reconocidas{f' en la hoja «{sheet}»' if sheet else ''}: {used}."


def read_workers(path: str | Path) -> WorkerImportResult:
    """Read workers from the best-matching table; invalid rows are reported in `errors`, never raised."""
    picked = pick_table(Path(path))
    result = WorkerImportResult()
    if picked is None:
        result.errors.append(
            RowError(
                1,
                "no se encontró una fila de títulos (se esperan columnas como Nombre, Carné, Área, Grupo)",
            )
        )
        return result
    sheet, table, header, columns = picked
    result.notes.append(_describe(sheet, columns))
    if "roster" in columns:
        result.legacy = True
        _read_roster_rows(table, header, columns, result)
        return result
    for line, raw in enumerate(table[header + 1 :], start=header + 2):
        if all(_clean_text(value) == "" for value in raw):
            continue
        try:
            row = _build_row(raw, columns)
            if not row.full_name:
                raise ValueError("falta el nombre")
        except ValueError as error:
            result.errors.append(RowError(line, str(error)))
            continue
        result.rows.append(row)
    return result


def roster_entries(table: list[list[object]], header: int, columns: dict[str, int]):
    """Rows of a staffing roster as (line, area, title, worker name, id, group text).

    A row with only the first column starts a new area (reported once with title None); any other row is a
    position, filled when it has a worker name and vacant otherwise.
    """
    area = ""
    for line, raw in enumerate(table[header + 1 :], start=header + 2):

        def cell(key: str, raw=raw) -> str:
            col = columns.get(key)
            return _clean_text(raw[col]) if col is not None and col < len(raw) else ""

        title, name, group = cell("roster"), cell("full_name"), cell("salary_group")
        if not title:
            continue
        if not name and not group:
            area = title
            yield line, area, None, "", "", ""
            continue
        col_id = columns.get("national_id")
        national_id = _normalize_national_id(raw[col_id]) if col_id is not None and col_id < len(raw) else ""
        yield line, area, title, name, national_id, group


def _read_roster_rows(table, header, columns, result: WorkerImportResult) -> None:
    for line, area, title, name, national_id, group_text in roster_entries(table, header, columns):
        if not name:
            continue  # vacant position
        group = parse_roman(group_text) if group_text and not group_text.isdigit() else None
        if group_text.isdigit():
            group = int(group_text)
        if group_text and not (group and 1 <= group <= 25):
            result.notes.append(f"Fila {line}: el grupo «{group_text}» no es válido; se deja sin definir.")
            group = None
        result.rows.append(
            WorkerRow(full_name=name, national_id=national_id, area=area, position=title, salary_group=group)
        )


# -- legacy "Dist.Monto x Trabajador" sheet ---------------------------------------------
NUMBERED_HEADER = re.compile(r"^\s*\d+[\s.,\-]")
AREA_NUMBER_PREFIX = re.compile(r"^\s*\d+\s*[.,\-]*\s*")


def normalize_area(name: object) -> str:
    """Comparable form of an area name: no «3.-» prefix, accents, case or punctuation."""
    return _normalize_header(AREA_NUMBER_PREFIX.sub("", _clean_text(name)))


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _find_legacy_sheet(workbook):
    for sheet in workbook.worksheets:
        key = _normalize_header(sheet.title)
        if "monto" in key and "trabajador" in key:
            return sheet
    return None


def read_legacy_workers(path: str | Path) -> WorkerImportResult | None:
    """Workers from the old per-worker sheet; None when the file has no such sheet.

    Area header rows have no days worked; worker rows carry the days in D:F (total in G), the roman
    salary group in I, the years in K and the contribution grade in M. Missing values stay None.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(Path(path), read_only=True, data_only=True)
    try:
        sheet = _find_legacy_sheet(workbook)
        if sheet is None:
            return None
        result = WorkerImportResult(legacy=True)
        area, area_number = "", None
        for line, row in enumerate(sheet.iter_rows(min_col=1, max_col=14, values_only=True), start=1):
            name = _clean_text(row[2])
            if not name:
                continue
            days_parts = [v for v in row[3:6] if _is_number(v)]
            total = row[6] if _is_number(row[6]) and row[6] > 0 else sum(days_parts)
            if total <= 0:
                # only numbered headers start a new area; unnumbered ones are sub-groups of the current one
                if "monto" not in name.lower() and NUMBERED_HEADER.match(name):
                    area = AREA_NUMBER_PREFIX.sub("", name).strip()
                    area_number = int(re.match(r"\s*(\d+)", name).group(1))
                continue
            if name.startswith("#"):
                result.errors.append(RowError(line, "the worker name is a broken reference (#REF!)"))
                continue
            group = parse_roman(_clean_text(row[8])) if _clean_text(row[8]) else None
            years = int(row[10]) if _is_number(row[10]) and row[10] >= 0 else None
            contribution = int(row[12]) if _is_number(row[12]) and 1 <= row[12] <= 5 else None
            result.rows.append(
                WorkerRow(
                    full_name=name,
                    national_id="",
                    area=area,
                    salary_group=group if group and 1 <= group <= 25 else None,
                    seniority_years=years,
                    days_worked=int(total),
                    contribution=contribution,
                    area_number=area_number,
                )
            )
        return result
    finally:
        workbook.close()


def read_workers_auto(path: str | Path) -> WorkerImportResult:
    """Legacy per-worker sheet when the workbook has one, otherwise the best-matching table or roster."""
    if Path(path).suffix.lower() in {".xlsx", ".xlsm"}:
        legacy = read_legacy_workers(path)
        if legacy is not None:
            return legacy
    return read_workers(path)
