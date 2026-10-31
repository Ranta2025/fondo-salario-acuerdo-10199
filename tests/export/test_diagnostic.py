import zipfile
from datetime import date
from decimal import Decimal as D
from xml.etree import ElementTree

from fondo_salario.domain.calculation import calculate
from fondo_salario.domain.models import Area, Position, Settings, Worker
from fondo_salario.export.diagnostic import build_diagnostic, write_diagnostic

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def project():
    areas = [Area(1, "Dirección", 1), Area(2, "Economía", 2)]
    positions = [
        Position(1, 1, "Director", 2, 1, 1, D("6000"), 3),
        Position(2, 1, "Técnico", 3, 2, 0, D("4000"), 3, 1),
        Position(3, 2, "Contador", 2, 1, 0, D("5000"), 3),
        Position(4, 2, "Chofer", 1, 0, 0, D("2000"), 3),  # no vacancy: not listed
    ]
    workers = [
        Worker(1, "Ana Uno", "", 1, 25, 12, 72, 5, "Director", True),
        Worker(2, "Beto Dos", "", 1, 12, 3, 60, 3, "Técnico", True),
        Worker(3, "Carla Tres", "", 2, 19, 8, 72, 4, "Contador", True),
        Worker(4, "Dani Cuatro", "", 2, 3, 1, 72, 1, "", True),  # contribution 1: collects nothing
        Worker(5, "Eva Cinco", "", 2, 3, 1, 72, 4, "", False),  # no right to collect
    ]
    settings = Settings(total_amount=D("10000.00"), months_paid=3)
    return settings, calculate(settings, areas, positions, workers)


def test_counts_percentage_and_beneficiaries():
    settings, result = project()
    d = build_diagnostic(settings.total_amount, result, date(2026, 10, 31))
    assert (d.approved, d.vacant, d.temp_vacant, d.total_vacancies) == (8, 4, 1, 5)
    assert d.percentage == D("62.50")
    assert d.beneficiaries == 3 and [a.area for a in d.areas] == ["Dirección", "Economía"]
    assert [(v.position, v.vacant, v.temp_vacant) for v in d.vacancies] == [
        ("Director", 1, 1),
        ("Técnico", 2, 0),
        ("Contador", 1, 0),
    ]
    assert sum(a.subtotal for a in d.areas) == settings.total_amount


def test_percentage_is_none_without_approved_positions():
    settings, result = project()
    d = build_diagnostic(settings.total_amount, calculate(settings, [], [], []), date(2026, 1, 1))
    assert d.percentage is None and d.beneficiaries == 0


def test_the_word_file_is_a_valid_package_with_the_expected_content(tmp_path):
    settings, result = project()
    path = tmp_path / "d.docx"
    write_diagnostic(path, build_diagnostic(settings.total_amount, result, date(2026, 10, 31)))
    with zipfile.ZipFile(path) as package:
        assert set(package.namelist()) == {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
        root = ElementTree.fromstring(package.read("word/document.xml"))
    text = "".join(t.text or "" for t in root.iter(f"{W}t"))
    for expected in (
        "Diagnóstico",
        "31/10/2026",
        "Acuerdo 10199",
        "Plantilla aprobada: 8",
        "62.50 %",
        "10,000.00 fueron beneficiados 3 trabajadores",
        "Ana Uno",
        "Carla Tres",
        "Jefe de Departamento Administrativo",
        "Representante del Grupo de Recursos Humanos",
        "Representante del Grupo Económico",
    ):
        assert expected in text, expected
    assert "Dani Cuatro" not in text and "Eva Cinco" not in text  # they do not collect


def test_special_characters_are_escaped(tmp_path):
    settings, _ = project()
    areas = [Area(1, "A&B <x>", 1)]
    positions = [Position(1, 1, "Jefe", 1, 1, 0, D("100"), 1)]
    workers = [Worker(1, 'Ana "Q" & Co', "", 1, 12, 5, 72, 4, "Jefe", True)]
    settings = Settings(total_amount=D("100.00"), months_paid=1)
    d = build_diagnostic(
        settings.total_amount, calculate(settings, areas, positions, workers), date(2026, 1, 1)
    )
    path = tmp_path / "d.docx"
    write_diagnostic(path, d)
    with zipfile.ZipFile(path) as package:
        root = ElementTree.fromstring(package.read("word/document.xml"))
    text = "".join(t.text or "" for t in root.iter(f"{W}t"))
    assert "A&B <x>" in text and 'Ana "Q" & Co' in text


def test_illegal_control_characters_do_not_break_the_document(tmp_path):
    areas = [Area(1, "Dir\x00ección", 1)]
    positions = [Position(1, 1, "Jefe\x0b", 1, 1, 0, D("100"), 1)]
    workers = [Worker(1, "Ana\x01 Uno", "", 1, 12, 5, 72, 4, "Jefe", True)]
    settings = Settings(total_amount=D("100.00"), months_paid=1)
    d = build_diagnostic(
        settings.total_amount, calculate(settings, areas, positions, workers), date(2026, 1, 1)
    )
    path = tmp_path / "d.docx"
    write_diagnostic(path, d)
    with zipfile.ZipFile(path) as package:
        root = ElementTree.fromstring(package.read("word/document.xml"))  # parses: no illegal characters left
    assert "Ana Uno" in "".join(t.text or "" for t in root.iter(f"{W}t"))


def test_a_project_without_vacancies_says_so(tmp_path):
    areas = [Area(1, "Dirección", 1)]
    settings = Settings(total_amount=D("100.00"), months_paid=1)
    d = build_diagnostic(settings.total_amount, calculate(settings, areas, [], []), date(2026, 1, 1))
    path = tmp_path / "d.docx"
    write_diagnostic(path, d)
    with zipfile.ZipFile(path) as package:
        text = "".join(
            t.text or "" for t in ElementTree.fromstring(package.read("word/document.xml")).iter(f"{W}t")
        )
    assert "No hay vacantes registradas." in text
