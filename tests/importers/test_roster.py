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
