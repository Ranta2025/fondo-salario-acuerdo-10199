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
