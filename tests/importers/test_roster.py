def test_staffing_roster_layout_gives_area_position_name_id_and_group(tmp_path):
    from openpyxl import Workbook

    from fondo_salario.importers.workers import read_workers_auto

    wb = Workbook()
    ws = wb.active
    ws.append([])
    ws.append(
        [None, "Areas y  Cargos", " Trabajador", "Carnet de Identidad", "Grupo de Escala / Responsabilidad"]
    )
    ws.append([None, "Dirección"])
    ws.append([None, "Director", "Ana Uno", 123, "XXV"])
    ws.append([None, "Subdirector", None, None, "XXIV"])  # vacant: not a worker
    ws.append([None, "Departamento Económico"])
    ws.append([None, "Técnico", "Beto Dos", "00112233445", "XII"])
    path = tmp_path / "plantilla.xlsx"
    wb.save(path)

    result = read_workers_auto(path)
    assert result.legacy is True and result.errors == []
    assert [(r.full_name, r.area, r.position, r.salary_group) for r in result.rows] == [
        ("Ana Uno", "Dirección", "Director", 25),
        ("Beto Dos", "Departamento Económico", "Técnico", 12),
    ]
    assert result.rows[1].national_id == "00112233445"


def _book(tmp_path, sheets):
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    path = tmp_path / "libro.xlsx"
    wb.save(path)
    return path


def test_header_can_be_on_any_sheet_and_row_with_flexible_names(tmp_path):
    from fondo_salario.importers.workers import read_workers_auto

    path = _book(
        tmp_path,
        {
            "Notas": [["nada que ver"]],
            "Datos": [
                ["Listado de personal"],
                [],
                ["Nombre y Apellidos", "C.I.", "Departamento", "Antigüedad (años)", "Grupo Salarial"],
                ["Ana Uno", "00112233445", "Dirección", 7, "XII"],
            ],
        },
    )
    result = read_workers_auto(path)
    row = result.rows[0]
    assert (row.full_name, row.national_id, row.area, row.seniority_years, row.salary_group) == (
        "Ana Uno",
        "00112233445",
        "Dirección",
        7,
        12,
    )
    assert "Datos" in result.notes[0] and "Carné" in result.notes[0]


def test_table_with_only_name_and_id_is_readable(tmp_path):
    from fondo_salario.importers.workers import read_workers_auto

    path = _book(tmp_path, {"H": [["Trabajador", "Carnet de Identidad"], ["Ana Uno", "12345678901"]]})
    (row,) = read_workers_auto(path).rows
    assert (row.full_name, row.national_id, row.area) == ("Ana Uno", "12345678901", "")


def test_roster_reports_an_invalid_group(tmp_path):
    from fondo_salario.importers.workers import read_workers_auto

    path = _book(
        tmp_path,
        {
            "H": [
                [None, "Areas y Cargos", "Trabajador", "Carnet", "Grupo"],
                [None, "Dirección"],
                [None, "Jefe", "Ana Uno", "1", "ZZ"],
            ]
        },
    )
    result = read_workers_auto(path)
    assert result.rows[0].salary_group is None
    assert any("ZZ" in note for note in result.notes)


def test_roster_gives_areas_and_positions_with_vacancies(tmp_path):
    from fondo_salario.importers.structure import read_structure

    path = _book(
        tmp_path,
        {
            "H": [
                [None, "Areas y Cargos", "Trabajador", "Carnet", "Grupo"],
                [None, "Dirección"],
                [None, "Director", "Ana Uno", "1", "XXV"],
                [None, "Técnico", "Beto Dos", "2", "XII"],
                [None, "Técnico", None, None, "XII"],
                [None, "Técnico", None, None, "XII"],
                [None, "Grupo Económico"],
            ]
        },
    )
    areas = read_structure(path)
    assert [a.name for a in areas] == ["Dirección", "Grupo Económico"]
    assert {(p.name, p.vacant) for p in areas[0].positions} == {("Director", 0), ("Técnico", 2)}


def test_area_matching_ignores_generic_words_and_finds_unique_partial_matches():
    from fondo_salario.domain.models import Area
    from fondo_salario.importers.merge import find_area

    areas = [
        Area(1, "Grupo de Atencion a la Poblacion", 1),
        Area(2, "Grupo de Subsidios", 2),
        Area(3, "Analisis Economico", 3),
    ]
    assert find_area("Sección de Atención a la Población", None, areas).id == 1
    assert find_area("Grupo de Subsidio y Esfuerzo Propio", None, areas).id == 2
    assert find_area("Departamento de Análisis Económico", None, areas).id == 3
    assert find_area("Grupo Económico", None, areas + [Area(4, "Economico Local", 4)]) is None


def test_area_column_named_name_of_area_is_not_the_worker_name():
    from fondo_salario.importers.workers import header_role

    assert header_role("nombredelarea") == "area"
    assert header_role("nombredelcargo") == "position"
    assert header_role("nombreyapellidos") == "full_name"


def test_roster_footer_and_vacant_without_group_do_not_become_areas(tmp_path):
    from fondo_salario.importers.structure import read_structure

    path = _book(
        tmp_path,
        {
            "H": [
                [None, "Areas y Cargos", "Trabajador", "Carnet", "Grupo"],
                [None, "Dirección"],
                [None, "Técnico", "Ana Uno", "1", "XII"],
                [None, "Técnico"],  # vacant, group left blank
                [None, "Total de plazas"],
            ]
        },
    )
    (area,) = read_structure(path)
    assert area.name == "Dirección" and [(p.name, p.vacant) for p in area.positions] == [("Técnico", 1)]


def test_plain_areas_table_on_its_own_sheet_is_read(tmp_path):
    from fondo_salario.importers.structure import looks_like, read_structure

    path = _book(
        tmp_path,
        {
            "Trabajadores": [["Nombre", "Carné", "Área"], ["Ana Uno", "1", "Dirección"]],
            "Áreas": [
                ["Área", "Cargo", "Vacantes", "Salario", "Meses"],
                ["Dirección", "Director", 1, 6000, 3],
                [None, "Técnico", 2, 4000, 3],
                ["Economía", "Jefe", 1, 5000, 3],
            ],
        },
    )
    areas = read_structure(path)
    assert [a.name for a in areas] == ["Dirección", "Economía"]
    tecnico = areas[0].positions[1]
    assert (tecnico.name, tecnico.vacant, tecnico.salary, tecnico.months_unexecuted) == (
        "Técnico",
        2,
        4000,
        3,
    )
    assert looks_like(path) == "workers"


def test_structure_file_is_recognized_as_such_and_csv_works(tmp_path):
    from fondo_salario.importers.structure import looks_like, read_structure

    path = tmp_path / "areas.csv"
    path.write_text("Área;Cargo;Vacantes\nDirección;Director;1\n", encoding="utf-8")
    assert looks_like(path) == "structure"
    assert read_structure(path)[0].positions[0].vacant == 1


def test_plain_xlsx_table_without_roster_still_reads_normally(tmp_path):
    from fondo_salario.importers.workers import read_workers_auto

    path = _book(
        tmp_path, {"H": [["Nombre", "Área", "Grupo", "Antigüedad"], ["Ana Uno", "Dirección", "XII", 3]]}
    )
    (row,) = read_workers_auto(path).rows
    assert (row.full_name, row.area, row.salary_group, row.seniority_years) == ("Ana Uno", "Dirección", 12, 3)


def test_structure_matching_is_strict_about_partial_names():
    from fondo_salario.domain.models import Area
    from fondo_salario.importers.merge import find_area

    areas = [Area(1, "Subdirección", 1)]
    assert find_area("Dirección", None, areas) is not None  # loose (workers/legacy)
    assert find_area("Dirección", None, areas, loose=False) is None


def test_worker_table_is_not_mistaken_for_an_areas_table(tmp_path):
    from fondo_salario.importers.structure import looks_like

    path = _book(
        tmp_path,
        {"H": [["Nombre", "Carné", "Área", "Cargo", "Grupo"], ["Ana Uno", "1", "Dirección", "Jefe", "XII"]]},
    )
    assert looks_like(path) == "workers"


def test_roster_worker_without_position_is_reported(tmp_path):
    from fondo_salario.importers.workers import read_workers_auto

    path = _book(
        tmp_path,
        {
            "H": [
                [None, "Areas y Cargos", "Trabajador", "Carnet", "Grupo"],
                [None, "Dirección"],
                [None, None, "Ana Uno", "1", "XII"],
            ]
        },
    )
    result = read_workers_auto(path)
    assert result.rows == [] and "no tiene cargo" in result.errors[0].message


def test_strict_structure_matching_does_not_use_the_partial_word_rule():
    from fondo_salario.domain.models import Area
    from fondo_salario.importers.merge import find_area

    areas = [Area(1, "Dirección Provincial", 1)]
    assert find_area("Dirección", None, areas) is not None
    assert find_area("Dirección", None, areas, loose=False) is None
