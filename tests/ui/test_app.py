"""Window-level tests. They need a display (Xvfb on Linux); they are skipped when tkinter cannot start."""

import tkinter as tk
from decimal import Decimal as D

import pytest

from fondo_salario.domain.models import Position, Settings, Worker
from fondo_salario.persistence.sqlite_repo import ProjectStore
from fondo_salario.ui import app as app_module


@pytest.fixture
def window(tmp_path, monkeypatch):
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display available")
    path = tmp_path / "p.fsal"
    with ProjectStore(path) as store:
        store.add_area("Dir")
    win = app_module.App(path)
    win.withdraw()
    win.update()
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass


def ask(monkeypatch, answer):
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", lambda *a, **k: answer)


def reopen(path):
    with ProjectStore(path) as store:
        return store.load()


def test_opens_with_four_steps_and_visible_file_controls(window):
    assert list(window.tabs) == ["1. Parámetros", "2. Áreas y cargos", "3. Trabajadores", "4. Resultados"]
    assert window.status.cget("text").endswith("Todo guardado")


def test_closing_with_changes_asks_and_cancel_keeps_window_open(window, monkeypatch):
    window.ctl.add_area("Nueva")
    window.update_status()
    assert "sin guardar" in window.status.cget("text")
    ask(monkeypatch, None)  # Cancelar
    window.on_close()
    assert window.winfo_exists()


def test_closing_and_saving_persists_changes(window, monkeypatch):
    window.ctl.add_area("Nueva")
    ask(monkeypatch, True)  # Sí
    path = window.project_path
    window.on_close()
    assert [a.name for a in reopen(path).areas] == ["Dir", "Nueva"]


def test_closing_without_saving_discards_changes(window, monkeypatch):
    window.ctl.add_area("Nueva")
    ask(monkeypatch, False)  # No
    path = window.project_path
    window.on_close()
    assert [a.name for a in reopen(path).areas] == ["Dir"]


def test_closing_with_nothing_pending_does_not_ask(window, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not ask")

    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", boom)
    window.on_close()


def test_edited_parameters_are_applied_on_save(window):
    params = window.tabs["1. Parámetros"]
    params.vars["total"].set("500.25")
    assert params.edited and "sin guardar" in window.status.cget("text")
    assert window.save() is True
    assert window.ctl.project.settings.total_amount == D("500.25") and not params.edited
    assert reopen(window.project_path).settings.total_amount == D("500.25")


def test_invalid_parameters_block_saving(window, monkeypatch):
    errors = []
    monkeypatch.setattr(app_module.messagebox, "showerror", lambda *a, **k: errors.append(a))
    window.tabs["1. Parámetros"].vars["months"].set("abc")
    assert window.save() is False and errors


def test_results_tab_balances_with_vacancies_to_distribute(window):
    window.ctl.save_settings(Settings(total_amount=D("1000.00")))
    area = window.ctl.project.areas[0]
    window.ctl.add_position(Position(0, area.id, "Jefe", 2, 3, 1, D("100"), 3, distribute=2))
    window.ctl.add_worker(Worker(0, "Ana Prueba", "1", area.id, 12, 5, 72, 4))
    window.changed()
    results = window.tabs["4. Resultados"]
    assert "Cuadra" in results.summary.cget("text") and "No cuadra" not in results.summary.cget("text")
    assert (
        window.tabs["2. Áreas y cargos"].tree.item(f"p{window.ctl.project.positions[0].id}", "values")[3]
        == "2"
    )


def test_selftest_opens_and_closes_the_window(tmp_path):
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display available")
    assert app_module.selftest() == 0
    assert app_module.main(["--selftest"]) == 0


def test_results_do_not_claim_balance_when_the_total_is_missing(window):
    area = window.ctl.project.areas[0]
    window.ctl.add_position(Position(0, area.id, "Jefe", 1, 1, 0, D("100"), 3))
    window.ctl.add_worker(Worker(0, "Ana Prueba", "1", area.id, 12, 5, 72, 4))
    window.changed()
    text = window.tabs["4. Resultados"].summary.cget("text")
    assert "Falta" in text and "Cuadra" not in text


def test_reset_button_restores_the_regulation_values(window):
    params = window.tabs["1. Parámetros"]
    params.vars["w_time"].set("0.50")
    params.vars["b_sen"].set("0:1, 10:5")
    params.use_regulation_values()
    assert params.vars["w_time"].get() == "0.20" and params.vars["w_con"].get() == "0.40"
    assert params.vars["b_sen"].get() == "0:1, 6:2, 11:3, 16:4, 21:5"


def _add_workers(window, count=3):
    area = window.ctl.project.areas[0]
    for i in range(count):
        window.ctl.add_worker(Worker(0, f"Trabajador {i}", str(i), area.id, 12, 5, 72, 4))
    window.changed()
    return window.tabs["3. Trabajadores"]


def test_bulk_toggle_of_the_right_to_collect(window):
    tab = _add_workers(window)
    ids = tab.tree.get_children()
    tab.tree.selection_set(ids[:2])
    tab.revoke_right()
    assert [w.eligible for w in window.ctl.project.workers] == [False, False, True]
    tab.tree.selection_set(ids[:1])
    tab.grant_right()
    assert [w.eligible for w in window.ctl.project.workers] == [True, False, True]


def test_filter_by_right_to_collect(window):
    tab = _add_workers(window)
    window.ctl.set_eligible([window.ctl.project.workers[0].id], False)
    window.changed()
    tab.right_filter.set("Con derecho")
    tab.refresh()
    assert len(tab.tree.get_children()) == 2
    tab.right_filter.set("Sin derecho")
    tab.refresh()
    assert len(tab.tree.get_children()) == 1


def test_contribution_labels_follow_the_regulation():
    assert app_module.CONTRIBUTION_CHOICES == [
        "5 - Excepcional",
        "4 - Bueno",
        "3 - Satisfactorio",
        "2 - Regular",
        "1 - Sin bonificación",
    ]
    assert app_module.contribution_from_text("4 - Bueno") == 4
    assert app_module.contribution_from_text("1 - Sin bonificación") == 1
    assert app_module.contribution_label(3) == "3 - Satisfactorio"


# --- smart import ---------------------------------------------------------------------------
def _csv(tmp_path, text):
    path = tmp_path / "w.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _patch_import(monkeypatch, path, summary_mode, answers=()):
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda *a, **k: str(path))
    shown = []
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda t, m, **k: shown.append(m))
    asked = {"summary": 0, "conflicts": []}

    def summary(parent, plan):
        asked["summary"] += 1
        return summary_mode

    replies = iter(answers)

    def conflict(parent, item, diff, index, total):
        asked["conflicts"].append((diff.key, index, total))
        return next(replies)

    monkeypatch.setattr(app_module, "ask_summary", summary)
    monkeypatch.setattr(app_module, "ask_conflict", conflict)
    return shown, asked


def _window_with_ana(window):
    area = window.ctl.project.areas[0]  # "Dir"
    window.ctl.add_worker(Worker(0, "Ana Pérez Gómez", "", area.id, 12, 5, 72, 3))
    window.ctl.save()
    window.changed()
    return window.tabs["3. Trabajadores"]


def test_import_completes_the_id_and_adds_new_workers(window, monkeypatch, tmp_path):
    tab = _window_with_ana(window)
    path = _csv(
        tmp_path,
        "nombre;carné;área;grupo;antigüedad\nana perez gomez;00112233445;Dir;XII;5\nBeto Nuevo;;Dir;III;1\n",
    )
    shown, asked = _patch_import(monkeypatch, path, "keep_all")
    tab.import_file()
    by_name = {w.full_name: w for w in window.ctl.project.workers}
    assert by_name["Ana Pérez Gómez"].national_id == "00112233445"
    assert "Beto Nuevo" in by_name and by_name["Beto Nuevo"].eligible is False
    assert len(window.ctl.project.workers) == 2  # Ana was joined, not duplicated
    assert asked["summary"] == 1 and "completad" in shown[-1].lower()


def test_import_asks_each_difference_one_by_one(window, monkeypatch, tmp_path):
    tab = _window_with_ana(window)
    path = _csv(tmp_path, "nombre;carné;área;grupo;antigüedad\nAna Pérez Gómez;00112233445;Dir;XV;9\n")
    shown, asked = _patch_import(monkeypatch, path, "review", answers=["overwrite", "keep"])
    tab.import_file()
    ana = window.ctl.project.workers[0]
    assert [c[1:] for c in asked["conflicts"]] == [(1, 2), (2, 2)]
    assert (ana.salary_group, ana.seniority_years, ana.national_id) == (15, 5, "00112233445")


def test_import_can_accept_all_differences_directly(window, monkeypatch, tmp_path):
    tab = _window_with_ana(window)
    path = _csv(tmp_path, "nombre;área;grupo;antigüedad\nAna Pérez Gómez;Dir;XV;9\n")
    _, asked = _patch_import(monkeypatch, path, "accept_all")
    tab.import_file()
    ana = window.ctl.project.workers[0]
    assert (ana.salary_group, ana.seniority_years) == (15, 9) and asked["conflicts"] == []


def test_cancelling_the_import_changes_nothing(window, monkeypatch, tmp_path):
    tab = _window_with_ana(window)
    path = _csv(tmp_path, "nombre;área;grupo;antigüedad\nAna Pérez Gómez;Dir;XV;9\nBeto Nuevo;Dir;III;1\n")
    _patch_import(monkeypatch, path, None)
    tab.import_file()
    assert [w.full_name for w in window.ctl.project.workers] == ["Ana Pérez Gómez"]
    assert window.ctl.project.workers[0].salary_group == 12


def test_cancelling_in_the_middle_of_the_review_applies_nothing(window, monkeypatch, tmp_path):
    tab = _window_with_ana(window)
    path = _csv(tmp_path, "nombre;área;grupo;antigüedad\nAna Pérez Gómez;Dir;XV;9\nBeto Nuevo;Dir;III;1\n")
    _patch_import(monkeypatch, path, "review", answers=["overwrite", None])
    tab.import_file()
    assert len(window.ctl.project.workers) == 1 and window.ctl.project.workers[0].salary_group == 12


def test_importing_data_that_is_already_there_says_so_without_asking(window, monkeypatch, tmp_path):
    tab = _window_with_ana(window)
    path = _csv(tmp_path, "nombre;área;grupo;antigüedad\nana perez gomez;Dir;XII;5\n")
    shown, asked = _patch_import(monkeypatch, path, "keep_all")
    tab.import_file()
    assert asked["summary"] == 0 and "nada nuevo" in shown[-1].lower()


def test_structure_import_adds_positions_to_an_existing_area(window, monkeypatch, tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Dist.Monto x area"
    ws.append([])
    ws.append([None, 1, "1.- Dir", None, None, None, None])
    ws.append([None, 1, "Jefe", 1, 6060, None, 3])
    path = tmp_path / "s.xlsx"
    wb.save(path)
    shown, _ = _patch_import(monkeypatch, path, "keep_all")
    window.tabs["2. Áreas y cargos"].import_excel()
    (position,) = window.ctl.project.positions
    assert (position.name, position.vacant, position.salary) == ("Jefe", 1, D("6060"))
    assert [a.name for a in window.ctl.project.areas] == ["Dir"]


def _press(root, text):
    """Click the button with this text in the open dialog."""

    def walk(widget):
        for child in widget.winfo_children():
            if child.winfo_class() == "TButton" and child.cget("text").startswith(text):
                child.invoke()
                return True
            if walk(child):
                return True
        return False

    walk(root)


def test_the_real_dialogs_return_the_chosen_option(window):
    from fondo_salario.importers.merge import plan_workers
    from fondo_salario.importers.workers import WorkerRow
    from fondo_salario.ui.merge_dialogs import ask_conflict, ask_summary, summary_lines

    area = window.ctl.project.areas[0]
    window.ctl.add_worker(Worker(0, "Ana Pérez", "", area.id, 12, 5, 72, 3))
    rows = [WorkerRow("Ana Pérez", "001", "Dir", salary_group=15, seniority_years=5)]
    plan = plan_workers(rows, window.ctl.project.areas, window.ctl.project.workers)
    text = "\n".join(summary_lines(plan))
    assert "completarán solos" in text and "Carné de identidad" in text and "tú decides" in text
    window.after(200, lambda: _press(window, "Revisar"))
    assert ask_summary(window, plan) == "review"
    window.after(200, lambda: _press(window, "Aceptar todas"))
    assert ask_summary(window, plan) == "accept_all"
    item, diff = plan.conflicts[0]
    window.after(200, lambda: _press(window, "Conservar"))
    assert ask_conflict(window, item, diff, 1, 3) == "keep"
    window.after(200, lambda: _press(window, "Sobrescribir esta y las 2"))
    assert ask_conflict(window, item, diff, 1, 3) == "overwrite_rest"
    window.after(200, lambda: _press(window, "Cancelar"))
    assert ask_conflict(window, item, diff, 3, 3) is None
