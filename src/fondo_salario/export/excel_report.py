"""Excel evidence report: per-area amounts, per-worker coefficients, pre-payroll and parameters."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.worksheet import Worksheet

from fondo_salario.domain.calculation import CalculationResult
from fondo_salario.domain.models import Settings
from fondo_salario.domain.scales import to_roman  # noqa: F401  (re-exported: used by the UI and tests)
from fondo_salario.messages import describe

MONEY = "#,##0.00"
THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")
AREA_FILL = PatternFill("solid", fgColor="F2F2F2")
BOLD = Font(bold=True)


def _yes_no(flag: bool) -> str:
    return "Sí" if flag else "No"


def _money(value: Decimal) -> float:
    return float(value)


def _title(ws: Worksheet, text: str, subtitle: str, width: int) -> None:
    ws.cell(row=1, column=1, value=text).font = Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=subtitle)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)


def _header(ws: Worksheet, row: int, labels: list[str]) -> None:
    for column, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=column, value=label)
        cell.font, cell.fill, cell.border = BOLD, HEADER_FILL, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 45
    ws.print_title_rows = f"{row}:{row}"


def _row(ws: Worksheet, row: int, values: list, *, bold=False, fill=None, money_cols=()) -> None:
    for column, value in enumerate(values, start=1):
        cell = ws.cell(row=row, column=column, value=value)
        cell.border = BORDER
        if bold:
            cell.font = BOLD
        if fill:
            cell.fill = fill
        if column - 1 in money_cols:
            cell.number_format = MONEY


def _finish(ws: Worksheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


def _area_sheet(wb: Workbook, result: CalculationResult, subtitle: str) -> None:
    ws = wb.active
    ws.title = "Hoja 1 - Montos por área"
    labels = [
        "Relación de cargos por áreas",
        "Plazas aprobadas",
        "Plazas vacantes",
        "Plazas temporalmente vacantes",
        "Total de vacantes",
        "Vacantes a distribuir",
        "Salario de la plaza",
        "Meses inejecutados",
        "Monto inejecutado",
        "% sobre el total inejecutado",
        "Monto a pagar por área",
    ]
    _title(ws, "Cálculo del monto por área", subtitle, len(labels))
    _header(ws, 4, labels)
    money = (6, 8, 10)
    row = 5
    for area in result.areas:
        _row(
            ws,
            row,
            [area.area.name]
            + [None] * 7
            + [_money(area.unexecuted)]
            + [_money(area.pct), _money(area.amount)],
            bold=True,
            fill=AREA_FILL,
            money_cols=money + (9,),
        )
        row += 1
        for item in area.positions:
            p = item.position
            _row(
                ws,
                row,
                [p.name, p.approved, p.vacant, p.temp_vacant, p.total_vacancies, item.vacancies]
                + [_money(p.salary), p.months_unexecuted, _money(item.unexecuted), None, None],
                money_cols=money,
            )
            row += 1
    pct_sum = sum((a.pct for a in result.areas), Decimal(0))
    amount_sum = sum((a.amount for a in result.areas), Decimal(0))
    _row(
        ws,
        row,
        ["TOTAL GENERAL"]
        + [None] * 7
        + [_money(result.total_unexecuted), _money(pct_sum), _money(amount_sum)],
        bold=True,
        money_cols=money + (9,),
    )
    ok = "OK" if result.areas and pct_sum == 100 else "REVISAR"
    ws.cell(
        row=row + 2,
        column=1,
        value=f"Comprobación: la suma de los porcentajes es {pct_sum:.2f} (debe ser 100.00) — {ok}",
    )
    _finish(ws, [42, 11, 11, 14, 11, 13, 14, 11, 16, 14, 18])


def _worker_sheet(wb: Workbook, result: CalculationResult, subtitle: str) -> None:
    ws = wb.create_sheet("Hoja 2 - Coeficientes")
    labels = [
        "Área",
        "Trabajador",
        "Carné de identidad",
        "Cargo",
        "Derecho a cobro",
        "Tiempo trabajado (días)",
        "Eval. tiempo",
        "Grupo salarial",
        "Eval. responsabilidad",
        "Antigüedad (años)",
        "Eval. antigüedad",
        "Eval. contribución",
        "Coeficiente individual",
        "Suma de coeficientes del área",
        "Monto a cobrar",
    ]
    _title(ws, "Distribución del monto por trabajador", subtitle, len(labels))
    _header(ws, 4, labels)
    area_names = {a.area.id: a.area.name for a in result.areas}
    row = 5
    for area in result.areas:
        members = [w for w in result.workers if w.worker.area_id == area.area.id]
        for r in members:
            w = r.worker
            _row(
                ws,
                row,
                [area.area.name, w.full_name, w.national_id, w.position_name, _yes_no(w.eligible)]
                + [w.days_worked, r.time_score]
                + [to_roman(w.salary_group) if 1 <= w.salary_group <= 25 else w.salary_group]
                + [r.responsibility_score, w.seniority_years, r.seniority_score, r.contribution_score]
                + [float(r.coefficient), float(r.area_coefficient), _money(r.amount)],
                money_cols=(14,),
            )
            row += 1
        subtotal = sum((r.amount for r in members), Decimal(0))
        _row(
            ws,
            row,
            [f"Subtotal {area.area.name}"] + [None] * 13 + [_money(subtotal)],
            bold=True,
            fill=AREA_FILL,
            money_cols=(14,),
        )
        row += 1
    orphans = [r for r in result.workers if r.worker.area_id not in area_names]
    for r in orphans:
        _row(
            ws,
            row,
            ["(sin área)", r.worker.full_name, r.worker.national_id, None, _yes_no(r.worker.eligible)]
            + [None] * 9
            + [0.0],
        )
        row += 1
    total = sum((r.amount for r in result.workers), Decimal(0))
    _row(ws, row, ["TOTAL"] + [None] * 13 + [_money(total)], bold=True, money_cols=(14,))
    ws.cell(row=row + 2, column=1, value=f"Comprobación: total repartido a los trabajadores {total:,.2f}")
    _finish(ws, [30, 30, 16, 26, 12, 11, 9, 10, 12, 11, 11, 11, 12, 14, 16])


def _payroll_sheet(wb: Workbook, settings: Settings, result: CalculationResult, subtitle: str) -> None:
    ws = wb.create_sheet("Pre-nómina")
    _title(ws, "Pre-nómina", subtitle, 6)
    _header(
        ws,
        4,
        ["No.", "Nombre y apellidos", "Carné de identidad", "Área", "Monto a pagar", "Derecho a cobro"],
    )
    area_names = {a.area.id: a.area.name for a in result.areas}
    row = 5
    for number, r in enumerate(result.workers, start=1):
        w = r.worker
        values = [number, w.full_name, w.national_id, area_names.get(w.area_id, ""), _money(r.amount)]
        values.append(_yes_no(w.eligible))
        _row(ws, row, values, money_cols=(4,))
        row += 1
    total = sum((r.amount for r in result.workers), Decimal(0))
    _row(ws, row, [None, "TOTAL", None, None, _money(total), None], bold=True, money_cols=(4,))
    status = "OK" if total == settings.total_amount else "REVISAR"
    ws.cell(
        row=row + 2,
        column=1,
        value=(
            f"Comprobación: monto a distribuir {settings.total_amount:,.2f}; "
            f"total pre-nómina {total:,.2f} — {status}"
        ),
    )
    _finish(ws, [6, 38, 20, 34, 16, 16])


def _parameters_sheet(
    wb: Workbook, settings: Settings, result: CalculationResult, generated_on: date
) -> None:
    ws = wb.create_sheet("Parámetros")
    ws.cell(row=1, column=1, value="Parámetros utilizados").font = Font(bold=True, size=14)
    lines: list[tuple[str, object]] = [
        ("Fecha de generación", generated_on.isoformat()),
        ("Monto total a distribuir", _money(settings.total_amount)),
        ("Meses a pagar", settings.months_paid),
        ("Días esperados por mes", settings.expected_days_per_month),
        ("Peso: tiempo trabajado", f"{settings.weight_time:.2f}"),
        ("Peso: responsabilidad", f"{settings.weight_responsibility:.2f}"),
        ("Peso: antigüedad", f"{settings.weight_seniority:.2f}"),
        ("Peso: contribución", f"{settings.weight_contribution:.2f}"),
        ("Escala de responsabilidad (grupo desde → nota)", _bands_text(settings.responsibility_bands)),
        ("Escala de antigüedad (años desde → nota)", _bands_text(settings.seniority_bands)),
    ]
    for offset, (label, value) in enumerate(lines, start=3):
        ws.cell(row=offset, column=1, value=label).font = BOLD
        cell = ws.cell(row=offset, column=2, value=value)
        if label == "Monto total a distribuir":
            cell.number_format = MONEY
    row = len(lines) + 4
    ws.cell(row=row, column=1, value="Observaciones").font = BOLD
    messages = [describe(i) for i in result.issues] or ["Sin observaciones."]
    for offset, message in enumerate(messages, start=1):
        ws.cell(row=row + offset, column=1, value=message)
    _finish(ws, [50, 40])


def _bands_text(bands: tuple[tuple[int, int], ...]) -> str:
    return ", ".join(f"{lower}→{score}" for lower, score in bands)


def export_report(
    path: str | Path,
    settings: Settings,
    result: CalculationResult,
    generated_on: date | None = None,
) -> None:
    generated_on = generated_on or date.today()
    subtitle = f"Generado el {generated_on.isoformat()} — monto a distribuir {settings.total_amount:,.2f}"
    wb = Workbook()
    _area_sheet(wb, result, subtitle)
    _worker_sheet(wb, result, subtitle)
    _payroll_sheet(wb, settings, result, subtitle)
    _parameters_sheet(wb, settings, result, generated_on)
    wb.save(Path(path))
