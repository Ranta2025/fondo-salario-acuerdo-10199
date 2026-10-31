"""The «Diagnóstico» document (Word) built from the project: staffing, vacancies, amount and beneficiaries."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from fondo_salario.domain.calculation import CalculationResult

INTRO = (
    "En cumplimiento de lo establecido en el Acuerdo 10199 del Comité Ejecutivo del Consejo de Ministros, "
    "que autoriza la distribución de los fondos salariales no ejecutados en las unidades presupuestadas, y "
    "utilizando como fuente de financiamiento los fondos provenientes de montos no ejecutados por concepto "
    "de plazas vacantes y de vacantes temporales por licencias sin sueldo, certificados médicos, licencia de "
    "maternidad y otros, se procedió a hacer el levantamiento."
)
CONCLUSION = (
    "De lo que concluimos que podemos proponer la aprobación de este Diagnóstico al Consejo de Dirección "
    "de la Entidad y proceder a hacer efectivo este pago."
)
SIGNATURES = [
    "Jefe de Departamento Administrativo",
    "Representante del Grupo de Recursos Humanos",
    "Representante del Grupo Económico",
]


@dataclass(frozen=True)
class VacancyLine:
    area: str
    position: str
    vacant: int
    temp_vacant: int


@dataclass(frozen=True)
class Payee:
    name: str
    position: str
    amount: Decimal


@dataclass(frozen=True)
class AreaPayees:
    area: str
    payees: list[Payee]

    @property
    def subtotal(self) -> Decimal:
        return sum((p.amount for p in self.payees), Decimal(0))


@dataclass(frozen=True)
class Diagnostic:
    on: date
    approved: int
    vacant: int
    temp_vacant: int
    total_amount: Decimal
    vacancies: list[VacancyLine] = field(default_factory=list)
    areas: list[AreaPayees] = field(default_factory=list)

    @property
    def total_vacancies(self) -> int:
        return self.vacant + self.temp_vacant

    @property
    def percentage(self) -> Decimal | None:
        """Share of the approved staff that the vacancies (permanent and temporary) represent."""
        if self.approved <= 0:
            return None
        return (Decimal(100 * self.total_vacancies) / Decimal(self.approved)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def beneficiaries(self) -> int:
        return sum(len(a.payees) for a in self.areas)


def build_diagnostic(total_amount: Decimal, result: CalculationResult, on: date) -> Diagnostic:
    """Gather the data of the document from a calculation (beneficiaries are the workers who collect > 0)."""
    vacancies, areas = [], []
    approved = vacant = temp = 0
    for area in result.areas:
        for pr in area.positions:
            p = pr.position
            approved += p.approved
            vacant += p.vacant
            temp += p.temp_vacant
            if p.vacant or p.temp_vacant:
                vacancies.append(VacancyLine(area.area.name, p.name, p.vacant, p.temp_vacant))
        payees = [
            Payee(r.worker.full_name, r.worker.position_name, r.amount)
            for r in result.workers
            if r.worker.area_id == area.area.id and r.amount > 0
        ]
        if payees:
            areas.append(AreaPayees(area.area.name, payees))
    return Diagnostic(on, approved, vacant, temp, total_amount, vacancies, areas)


# -- Word (WordprocessingML) writer, no external dependency ----------------------------------------
def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _run(text: str, bold: bool = False, size: int = 22) -> str:
    props = f'<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>{"<w:b/>" if bold else ""}'
    props += f'<w:sz w:val="{size}"/>'
    return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _para(runs: str, align: str = "left", before: int = 0, after: int = 120, keep_next: bool = False) -> str:
    keep = "<w:keepNext/>" if keep_next else ""
    return (
        f'<w:p><w:pPr>{keep}<w:spacing w:before="{before}" w:after="{after}"/>'
        f'<w:jc w:val="{align}"/></w:pPr>{runs}</w:p>'
    )


def text_para(text: str, bold: bool = False, align: str = "both", size: int = 22, **kwargs) -> str:
    return _para(_run(text, bold, size), align, **kwargs)


def _cell(text: str, width: int, bold: bool = False, align: str = "left", shade: str = "") -> str:
    fill = f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>' if shade else ""
    return (
        f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{fill}</w:tcPr>'
        f"{_para(_run(text, bold, 20), align, after=40)}</w:tc>"
    )


def table(widths: list[int], header: list[str], rows: list[list[str]], bold_last: bool = False) -> str:
    """Bordered table; the first two columns are text (left), the others numbers (right)."""
    borders = "".join(
        f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    out = [
        f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/>'
        f"<w:tblBorders>{borders}</w:tblBorders></w:tblPr>"
    ]
    out.append("<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>")

    def row(values: list[str], bold: bool, shade: str, is_header: bool = False) -> str:
        cells = "".join(
            _cell(v, widths[i], bold, "left" if i < 2 or is_header else "right", shade)
            for i, v in enumerate(values)
        )
        head = (
            "<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>"
            if is_header
            else "<w:trPr><w:cantSplit/></w:trPr>"
        )
        return f"<w:tr>{head}{cells}</w:tr>"

    out.append(row(header, True, "D9E2F3", is_header=True))
    for index, values in enumerate(rows):
        last = bold_last and index == len(rows) - 1
        out.append(row(values, last, "F2F2F2" if last else ""))
    out.append("</w:tbl>")
    return "".join(out) + _para("", after=60)


def _kv(label: str, value: str) -> str:
    return _para(_run(label + " ", True) + _run(value), "left", after=60)


def body_xml(d: Diagnostic) -> str:
    parts = [
        text_para("Diagnóstico", True, "center", 32, after=200),
        _kv("Fecha:", d.on.strftime("%d/%m/%Y")),
        text_para(INTRO, before=120, after=160),
        _kv("Plantilla aprobada:", str(d.approved)),
        _kv("Plantilla vacante:", str(d.vacant)),
        _kv("Vacantes temporales:", str(d.temp_vacant)),
        _kv("Total de vacantes (plazas vacantes y vacantes temporales):", str(d.total_vacancies)),
        _kv(
            "% que representan las vacantes de las aprobadas:",
            "—" if d.percentage is None else f"{d.percentage} %",
        ),
        text_para("Listado de vacantes y vacantes temporales", True, "left", before=160, keep_next=True),
    ]
    if d.vacancies:
        rows = [
            [v.area, v.position, str(v.vacant), str(v.temp_vacant), str(v.vacant + v.temp_vacant)]
            for v in d.vacancies
        ]
        rows.append(["Total", "", str(d.vacant), str(d.temp_vacant), str(d.total_vacancies)])
        parts.append(
            table(
                [2700, 3400, 1000, 1100, 900],
                ["Área", "Cargo", "Vacantes", "Temporales", "Total"],
                rows,
                True,
            )
        )
    else:
        parts.append(text_para("No hay vacantes registradas.", align="left"))
    parts.append(
        text_para(
            f"Para un monto real asignado para la distribución de {_money(d.total_amount)} "
            f"fueron beneficiados {d.beneficiaries} trabajadores.",
            before=160,
        )
    )
    parts.append(text_para("Listado de trabajadores por áreas", True, "left", before=120, keep_next=True))
    for area in d.areas:
        parts.append(text_para(area.area, True, "left", before=80, after=60, keep_next=True))
        rows = [[p.name, p.position, _money(p.amount)] for p in area.payees]
        rows.append(["Subtotal", "", _money(area.subtotal)])
        parts.append(table([3900, 3100, 2100], ["Trabajador", "Cargo", "Monto a cobrar"], rows, True))
    if d.areas:
        parts.append(_kv("Total repartido:", _money(sum((a.subtotal for a in d.areas), Decimal(0)))))
    parts.append(text_para(CONCLUSION, before=200, after=360, keep_next=True))
    for title in SIGNATURES:
        parts.append(
            text_para(
                "Firma: ______________________________", align="left", before=360, after=0, keep_next=True
            )
        )
        parts.append(text_para(title, align="left", before=0, after=120))
    return "".join(parts)


NAMESPACE = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
PAGE = (
    '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
    '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
    'w:header="708" w:footer="708" w:gutter="0"/>'
    "</w:sectPr>"
)
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)


def write_diagnostic(path: str | Path, diagnostic: Diagnostic) -> None:
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NAMESPACE}><w:body>'
        f"{body_xml(diagnostic)}{PAGE}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES)
        package.writestr("_rels/.rels", RELS)
        package.writestr("word/document.xml", document)
