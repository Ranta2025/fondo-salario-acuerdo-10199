"""Main window (tkinter). All user-facing text is Spanish."""

from __future__ import annotations

import tkinter as tk
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from fondo_salario.domain.models import Position, Settings, Worker
from fondo_salario.export.excel_report import to_roman
from fondo_salario.importers.structure import read_structure
from fondo_salario.importers.workers import parse_roman, read_workers
from fondo_salario.messages import describe
from fondo_salario.persistence.sqlite_repo import AreaInUseError, ProjectStore
from fondo_salario.ui.controller import Controller, parse_money, resolve_distribute
from fondo_salario.ui.forms import Field, ask_form

APP_TITLE = "Fondo de salario — Acuerdo 10199/2025"
FILETYPES = [("Proyecto de fondo de salario", "*.fsal")]
ROMANS = [to_roman(n) for n in range(1, 26)]


def money_text(value: Decimal) -> str:
    return f"{value:,.2f}"


def parse_int(text: str, label: str, low: int, high: int) -> int:
    try:
        number = int(str(text).strip())
    except ValueError:
        raise ValueError(f"«{label}» debe ser un número entero.") from None
    if not low <= number <= high:
        raise ValueError(f"«{label}» debe estar entre {low} y {high}.")
    return number


def parse_decimal(text: str, label: str) -> Decimal:
    try:
        value = parse_money(str(text))
    except InvalidOperation:
        raise ValueError(f"«{label}» debe ser un número.") from None
    if value < 0:
        raise ValueError(f"«{label}» no puede ser negativo.")
    return value


def bands_to_text(bands) -> str:
    return ", ".join(f"{lower}:{score}" for lower, score in bands)


def parse_bands(text: str, label: str):
    try:
        pairs = [tuple(int(x) for x in part.split(":")) for part in text.split(",") if part.strip()]
        if not pairs or any(len(p) != 2 for p in pairs):
            raise ValueError
    except ValueError:
        raise ValueError(f"«{label}» debe tener el formato  1:1, 6:2, 11:3 …") from None
    pairs.sort()
    if any(not 1 <= score <= 5 for _, score in pairs):
        raise ValueError(f"En «{label}» las notas deben estar entre 1 y 5.")
    return tuple(pairs)


def make_tree(parent, columns: list[tuple[str, str, int]], **kwargs) -> ttk.Treeview:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], **kwargs)
    for key, title, width in columns:
        tree.heading(key, text=title)
        tree.column(key, width=width, anchor="w" if key in ("name", "area", "position") else "e")
    scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    return tree


class ParametersTab(ttk.Frame):
    def __init__(self, app: App):
        super().__init__(app.notebook, padding=16)
        self.app = app
        self.vars: dict[str, tk.StringVar] = {}
        rows = [
            ("total", "Monto real a distribuir"),
            ("months", "Meses a pagar"),
            ("days", "Días esperados por mes"),
            ("w_time", "Peso: tiempo trabajado"),
            ("w_resp", "Peso: responsabilidad"),
            ("w_sen", "Peso: antigüedad"),
            ("w_con", "Peso: contribución"),
            ("b_resp", "Escala de responsabilidad (grupo desde:nota)"),
            ("b_sen", "Escala de antigüedad (años desde:nota)"),
        ]
        for row, (key, label) in enumerate(rows):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
            self.vars[key] = tk.StringVar()
            ttk.Entry(self, textvariable=self.vars[key], width=44).grid(row=row, column=1, sticky="w")
        self.status = ttk.Label(self, text="")
        self.status.grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(self, text="Guardar parámetros", command=self.save).grid(
            row=len(rows) + 1, column=0, sticky="w", pady=12
        )
        note = (
            "El Acuerdo 10199 no fija los criterios de reparto: "
            "cada unidad los aprueba en su reglamento interno.\n"
            "Los pesos deben sumar 1.00. Las escalas dicen desde qué valor se obtiene cada nota (1 a 5)."
        )
        ttk.Label(self, text=note, foreground="#555").grid(
            row=len(rows) + 2, column=0, columnspan=2, sticky="w"
        )

    def refresh(self) -> None:
        s = self.app.ctl.project.settings
        values = {
            "total": f"{s.total_amount:.2f}",
            "months": str(s.months_paid),
            "days": str(s.expected_days_per_month),
            "w_time": str(s.weight_time),
            "w_resp": str(s.weight_responsibility),
            "w_sen": str(s.weight_seniority),
            "w_con": str(s.weight_contribution),
            "b_resp": bands_to_text(s.responsibility_bands),
            "b_sen": bands_to_text(s.seniority_bands),
        }
        for key, value in values.items():
            self.vars[key].set(value)
        self.status.configure(text="")

    def save(self) -> None:
        v = {key: var.get() for key, var in self.vars.items()}
        try:
            settings = Settings(
                total_amount=parse_decimal(v["total"], "Monto real a distribuir"),
                months_paid=parse_int(v["months"], "Meses a pagar", 1, 12),
                expected_days_per_month=parse_int(v["days"], "Días esperados por mes", 1, 31),
                weight_time=parse_decimal(v["w_time"], "Peso: tiempo trabajado"),
                weight_responsibility=parse_decimal(v["w_resp"], "Peso: responsabilidad"),
                weight_seniority=parse_decimal(v["w_sen"], "Peso: antigüedad"),
                weight_contribution=parse_decimal(v["w_con"], "Peso: contribución"),
                responsibility_bands=parse_bands(v["b_resp"], "Escala de responsabilidad"),
                seniority_bands=parse_bands(v["b_sen"], "Escala de antigüedad"),
            )
        except ValueError as error:
            messagebox.showerror("Parámetros", str(error), parent=self)
            return
        self.app.ctl.save_settings(settings)
        total = settings.weights_sum
        self.status.configure(
            text=f"Guardado. Los pesos suman {total}" + ("" if total == 1 else "  ⚠ deben sumar 1.00"),
            foreground="#000" if total == 1 else "#b00",
        )
        self.app.changed()


class StructureTab(ttk.Frame):
    def __init__(self, app: App):
        super().__init__(app.notebook, padding=8)
        self.app = app
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        for text, command in [
            ("Nueva área", self.add_area),
            ("Renombrar área", self.rename_area),
            ("Agregar cargo", self.add_position),
            ("Editar cargo", self.edit_position),
            ("Eliminar", self.delete),
            ("Importar desde Excel…", self.import_excel),
        ]:
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=2)
        columns = [
            ("approved", "Plazas aprobadas", 90),
            ("vacant", "Vacantes", 70),
            ("temp", "Temp. vacantes", 90),
            ("distribute", "A distribuir", 90),
            ("salary", "Salario", 90),
            ("months", "Meses inejecutados", 110),
            ("unexecuted", "Monto inejecutado", 120),
        ]
        self.tree = make_tree(self, columns, show="tree headings")
        self.tree.heading("#0", text="Área / cargo")
        self.tree.column("#0", width=340)
        self.tree.bind("<Double-1>", lambda _e: self.edit_position())

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        project = self.app.ctl.project
        for area in project.areas:
            self.tree.insert("", "end", iid=f"a{area.id}", text=area.name, open=True)
        for p in project.positions:
            unexecuted = p.to_distribute * p.salary * p.months_unexecuted
            self.tree.insert(
                f"a{p.area_id}",
                "end",
                iid=f"p{p.id}",
                text=p.name,
                values=(
                    p.approved,
                    p.vacant,
                    p.temp_vacant,
                    p.to_distribute,
                    money_text(p.salary),
                    p.months_unexecuted,
                    money_text(unexecuted),
                ),
            )

    def _selected(self) -> tuple[str, int] | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Áreas y cargos", "Selecciona primero un área o un cargo.", parent=self)
            return None
        return selection[0][0], int(selection[0][1:])

    def add_area(self) -> None:
        name = ask_form(
            self, "Nueva área", [Field("name", "Nombre del área")], {}, _non_empty("name", "Nombre")
        )
        if name:
            self.app.ctl.add_area(name)
            self.app.changed()

    def rename_area(self) -> None:
        picked = self._selected()
        if not picked or picked[0] != "a":
            return
        current = self.tree.item(f"a{picked[1]}", "text")
        name = ask_form(
            self,
            "Renombrar área",
            [Field("name", "Nombre del área")],
            {"name": current},
            _non_empty("name", "Nombre"),
        )
        if name:
            self.app.ctl.rename_area(picked[1], name)
            self.app.changed()

    def _position_form(
        self, title: str, initial: dict, area_id: int, position_id: int = 0
    ) -> Position | None:
        fields = [
            Field("name", "Cargo"),
            Field("approved", "Plazas aprobadas"),
            Field("vacant", "Plazas vacantes"),
            Field("temp_vacant", "Plazas temporalmente vacantes"),
            Field("distribute", "Vacantes a distribuir (vacío = todas)"),
            Field("salary", "Salario de la plaza"),
            Field("months", "Meses inejecutados"),
        ]

        def build(v: dict) -> Position:
            if not v["name"].strip():
                raise ValueError("El nombre del cargo es obligatorio.")
            vacant = parse_int(v["vacant"], "Plazas vacantes", 0, 10_000)
            temp_vacant = parse_int(v["temp_vacant"], "Plazas temporalmente vacantes", 0, 10_000)
            return Position(
                position_id,
                area_id,
                v["name"].strip(),
                parse_int(v["approved"], "Plazas aprobadas", 0, 10_000),
                vacant,
                temp_vacant,
                parse_decimal(v["salary"], "Salario de la plaza"),
                parse_int(v["months"], "Meses inejecutados", 0, 12),
                resolve_distribute(v["distribute"], vacant + temp_vacant),
            )

        return ask_form(self, title, fields, initial, build)

    def add_position(self) -> None:
        picked = self._selected()
        if not picked:
            return
        area_id = picked[1] if picked[0] == "a" else self.app.ctl.position(picked[1]).area_id
        months = self.app.ctl.project.settings.months_paid
        position = self._position_form(
            "Agregar cargo",
            {"approved": 1, "vacant": 0, "temp_vacant": 0, "distribute": "", "salary": "0", "months": months},
            area_id,
        )
        if position:
            self.app.ctl.add_position(position)
            self.app.changed()

    def edit_position(self) -> None:
        picked = self._selected()
        if not picked or picked[0] != "p":
            return
        current = self.app.ctl.position(picked[1])
        initial = {
            "name": current.name,
            "approved": current.approved,
            "vacant": current.vacant,
            "temp_vacant": current.temp_vacant,
            "distribute": "" if current.distribute is None else current.distribute,
            "salary": current.salary,
            "months": current.months_unexecuted,
        }
        position = self._position_form("Editar cargo", initial, current.area_id, current.id)
        if position:
            self.app.ctl.update_position(position)
            self.app.changed()

    def delete(self) -> None:
        picked = self._selected()
        if not picked:
            return
        kind, item_id = picked
        label = self.tree.item(f"{kind}{item_id}", "text")
        if not messagebox.askyesno("Eliminar", f"¿Eliminar «{label}»?", parent=self):
            return
        try:
            if kind == "a":
                self.app.ctl.delete_area(item_id)
            else:
                self.app.ctl.delete_position(item_id)
        except AreaInUseError:
            messagebox.showwarning(
                "Eliminar", "El área todavía tiene trabajadores. Elimínalos o muévelos primero.", parent=self
            )
            return
        self.app.changed()

    def import_excel(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Excel con la relación de áreas y cargos", filetypes=[("Excel", "*.xlsx")]
        )
        if not path:
            return
        try:
            added = self.app.ctl.import_structure(read_structure(path))
        except Exception as error:  # unreadable or unexpected workbook
            messagebox.showerror("Importar", f"No se pudo leer el archivo:\n{error}", parent=self)
            return
        messagebox.showinfo(
            "Importar",
            f"Áreas nuevas importadas: {added}.\n\n"
            "Recuerda indicar en cada cargo cuántas plazas están vacantes.",
            parent=self,
        )
        self.app.changed()


def _non_empty(key: str, label: str):
    def build(values: dict) -> str:
        text = values[key].strip()
        if not text:
            raise ValueError(f"«{label}» es obligatorio.")
        return text

    return build


class WorkersTab(ttk.Frame):
    ALL = "(Todas las áreas)"

    def __init__(self, app: App):
        super().__init__(app.notebook, padding=8)
        self.app = app
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        for text, command in [
            ("Agregar trabajador", self.add),
            ("Editar", self.edit),
            ("Eliminar", self.delete),
            ("Importar CSV/Excel…", self.import_file),
        ]:
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=2)
        ttk.Label(bar, text="  Buscar:").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(bar, textvariable=self.search, width=22).pack(side="left", padx=4)
        self.area_filter = tk.StringVar(value=self.ALL)
        self.combo = ttk.Combobox(bar, textvariable=self.area_filter, state="readonly", width=30)
        self.combo.pack(side="left", padx=4)
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        columns = [
            ("name", "Nombre y apellidos", 230),
            ("ci", "Carné de identidad", 110),
            ("area", "Área", 190),
            ("position", "Cargo", 160),
            ("group", "Grupo", 55),
            ("years", "Antigüedad", 70),
            ("days", "Días", 50),
            ("contribution", "Contrib.", 60),
            ("eligible", "Cobra", 50),
        ]
        self.tree = make_tree(self, columns, show="headings")
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        self.count = ttk.Label(self, text="")
        self.count.pack(anchor="w")

    def refresh(self) -> None:
        project = self.app.ctl.project
        names = {a.id: a.name for a in project.areas}
        self.combo.configure(values=[self.ALL, *names.values()])
        if self.area_filter.get() not in (self.ALL, *names.values()):
            self.area_filter.set(self.ALL)
        text = self.search.get().strip().lower()
        wanted = self.area_filter.get()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for w in project.workers:
            area = names.get(w.area_id, "")
            if wanted != self.ALL and area != wanted:
                continue
            if text and text not in w.full_name.lower() and text not in w.national_id:
                continue
            shown += 1
            self.tree.insert(
                "",
                "end",
                iid=str(w.id),
                values=(
                    w.full_name,
                    w.national_id,
                    area,
                    w.position_name,
                    to_roman(w.salary_group),
                    w.seniority_years,
                    w.days_worked,
                    w.contribution,
                    "Sí" if w.eligible else "No",
                ),
            )
        self.count.configure(text=f"{shown} de {len(project.workers)} trabajadores")

    def _form(self, title: str, initial: dict, worker_id: int = 0) -> Worker | None:
        areas = {a.name: a.id for a in self.app.ctl.project.areas}
        if not areas:
            messagebox.showinfo(
                "Trabajadores", "Primero crea al menos un área en «Áreas y cargos».", parent=self
            )
            return None
        fields = [
            Field("name", "Nombre y apellidos"),
            Field("ci", "Carné de identidad"),
            Field("area", "Área", "choice", list(areas)),
            Field("position", "Cargo"),
            Field("group", "Grupo salarial", "choice", ROMANS),
            Field("years", "Antigüedad (años)"),
            Field("days", "Días trabajados en el período"),
            Field("contribution", "Contribución (1 a 5)", "choice", ["1", "2", "3", "4", "5"]),
            Field("eligible", "Cobra en este período", "bool"),
        ]

        def build(v: dict) -> Worker:
            if not v["name"].strip():
                raise ValueError("El nombre es obligatorio.")
            if v["area"] not in areas:
                raise ValueError("Selecciona un área.")
            group = parse_roman(v["group"])
            if group is None:
                raise ValueError("Selecciona el grupo salarial.")
            return Worker(
                id=worker_id,
                full_name=v["name"].strip(),
                national_id=v["ci"].strip(),
                area_id=areas[v["area"]],
                position_name=v["position"].strip(),
                salary_group=group,
                seniority_years=parse_int(v["years"], "Antigüedad", 0, 60),
                days_worked=parse_int(v["days"], "Días trabajados", 0, 1000),
                contribution=parse_int(v["contribution"], "Contribución", 1, 5),
                eligible=bool(v["eligible"]),
            )

        return ask_form(self, title, fields, initial, build)

    def add(self) -> None:
        s = self.app.ctl.project.settings
        initial = {
            "days": s.expected_days_per_month * s.months_paid,
            "years": 0,
            "contribution": "3",
            "eligible": True,
        }
        worker = self._form("Agregar trabajador", initial)
        if worker:
            self.app.ctl.add_worker(worker)
            self.app.changed()

    def edit(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Trabajadores", "Selecciona primero un trabajador.", parent=self)
            return
        current = self.app.ctl.worker(int(selection[0]))
        names = {a.id: a.name for a in self.app.ctl.project.areas}
        initial = {
            "name": current.full_name,
            "ci": current.national_id,
            "area": names.get(current.area_id, ""),
            "position": current.position_name,
            "group": to_roman(current.salary_group),
            "years": current.seniority_years,
            "days": current.days_worked,
            "contribution": str(current.contribution),
            "eligible": current.eligible,
        }
        worker = self._form("Editar trabajador", initial, current.id)
        if worker:
            self.app.ctl.update_worker(worker)
            self.app.changed()

    def delete(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Trabajadores", "Selecciona primero un trabajador.", parent=self)
            return
        name = self.tree.item(selection[0], "values")[0]
        if messagebox.askyesno("Eliminar", f"¿Eliminar a «{name}»?", parent=self):
            self.app.ctl.delete_worker(int(selection[0]))
            self.app.changed()

    def import_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Archivo de trabajadores",
            filetypes=[("Excel o CSV", "*.xlsx *.csv"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            read = read_workers(path)
        except Exception as error:  # unreadable file
            messagebox.showerror("Importar", f"No se pudo leer el archivo:\n{error}", parent=self)
            return
        summary = self.app.ctl.import_workers(read.rows)
        problems = [f"Fila {e.line}: {e.message}" for e in read.errors] + summary.skipped
        text = f"Trabajadores importados: {summary.added}."
        if summary.defaults_used:
            text += (
                f"\n{summary.defaults_used} usaron valores por defecto "
                "(días completos, contribución 3): revísalos."
            )
        if problems:
            text += f"\n\nNo se importaron {len(problems)} filas:\n" + "\n".join(problems[:15])
            if len(problems) > 15:
                text += f"\n… y {len(problems) - 15} más"
        messagebox.showinfo("Importar", text, parent=self)
        self.app.changed()


class ResultsTab(ttk.Frame):
    def __init__(self, app: App):
        super().__init__(app.notebook, padding=8)
        self.app = app
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Exportar a Excel…", command=self.export).pack(side="left")
        self.summary = ttk.Label(bar, text="")
        self.summary.pack(side="left", padx=12)
        area_columns = [
            ("name", "Área", 300),
            ("unexecuted", "Monto inejecutado", 130),
            ("pct", "% del total", 80),
            ("amount", "Monto a pagar", 130),
        ]
        self.areas = make_tree(self, area_columns, show="headings", height=7)
        worker_columns = [
            ("name", "Trabajador", 260),
            ("area", "Área", 220),
            ("coef", "Coeficiente", 90),
            ("amount", "Monto a cobrar", 130),
        ]
        self.workers = make_tree(self, worker_columns, show="headings", height=10)
        self.issues = tk.Text(self, height=5, wrap="word", state="disabled", background="#fff8e1")
        self.issues.pack(fill="x", pady=(6, 0))

    def refresh(self) -> None:
        ctl = self.app.ctl
        result = ctl.calculation()
        names = {a.area.id: a.area.name for a in result.areas}
        self.areas.delete(*self.areas.get_children())
        for a in result.areas:
            self.areas.insert(
                "",
                "end",
                values=(a.area.name, money_text(a.unexecuted), f"{a.pct:.2f}", money_text(a.amount)),
            )
        self.workers.delete(*self.workers.get_children())
        for r in result.workers:
            self.workers.insert(
                "",
                "end",
                values=(
                    r.worker.full_name,
                    names.get(r.worker.area_id, ""),
                    f"{r.coefficient:.2f}",
                    money_text(r.amount),
                ),
            )
        total = ctl.project.settings.total_amount
        self.summary.configure(
            text=f"A distribuir: {money_text(total)}   Repartido: {money_text(result.distributed)}",
            foreground="#000" if result.distributed == total else "#b00",
        )
        self.issues.configure(state="normal")
        self.issues.delete("1.0", "end")
        lines = [f"⚠ {describe(i)}" for i in result.issues] or ["Sin observaciones: los cálculos cuadran."]
        self.issues.insert("1.0", "\n".join(lines))
        self.issues.configure(state="disabled")

    def export(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar informe",
            defaultextension=".xlsx",
            initialfile="fondo-de-salario.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        try:
            self.app.ctl.export(path)
        except OSError as error:
            messagebox.showerror("Exportar", f"No se pudo guardar el archivo:\n{error}", parent=self)
            return
        messagebox.showinfo("Exportar", f"Informe guardado en:\n{path}", parent=self)


class App(tk.Tk):
    def __init__(self, project_path: str | Path | None = None):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1150x680")
        self.minsize(900, 560)
        self.store: ProjectStore | None = None
        self.ctl: Controller | None = None
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.tabs = {
            "Parámetros": ParametersTab(self),
            "Áreas y cargos": StructureTab(self),
            "Trabajadores": WorkersTab(self),
            "Resultados": ResultsTab(self),
        }
        for title, tab in self.tabs.items():
            self.notebook.add(tab, text=title)
        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self._refresh_current())
        self._build_menu()
        if project_path:
            self.open_project(project_path)
        else:
            self.after(100, self.start_prompt)

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Nuevo proyecto…", command=self.new_project)
        file_menu.add_command(label="Abrir proyecto…", command=self.ask_open_project)
        file_menu.add_command(label="Guardar una copia…", command=self.save_copy)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.destroy)
        menu.add_cascade(label="Archivo", menu=file_menu)
        self.configure(menu=menu)

    # -- project lifecycle -------------------------------------------------------------
    def start_prompt(self) -> None:
        answer = messagebox.askyesnocancel(
            APP_TITLE,
            "¿Quieres abrir un proyecto existente?\n\n"
            "Sí: abrir uno\nNo: crear un proyecto nuevo\nCancelar: salir",
            parent=self,
        )
        if answer is None:
            self.destroy()
        elif answer:
            self.ask_open_project(exit_on_cancel=True)
        else:
            self.new_project(exit_on_cancel=True)

    def new_project(self, exit_on_cancel: bool = False) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Crear proyecto",
            defaultextension=".fsal",
            initialfile="fondo-de-salario.fsal",
            filetypes=FILETYPES,
        )
        self._finish_pick(path, exit_on_cancel)

    def ask_open_project(self, exit_on_cancel: bool = False) -> None:
        path = filedialog.askopenfilename(parent=self, title="Abrir proyecto", filetypes=FILETYPES)
        self._finish_pick(path, exit_on_cancel)

    def _finish_pick(self, path: str, exit_on_cancel: bool) -> None:
        if path:
            self.open_project(path)
        elif exit_on_cancel and self.ctl is None:
            self.destroy()

    def open_project(self, path: str | Path) -> None:
        try:
            store = ProjectStore(path)
        except (ValueError, OSError) as error:
            messagebox.showerror(APP_TITLE, f"No se pudo abrir el proyecto:\n{error}", parent=self)
            return
        if self.store:
            self.store.close()
        self.store, self.ctl = store, Controller(store)
        self.title(f"{APP_TITLE} — {Path(path).name}")
        self.changed()

    def save_copy(self) -> None:
        if not self.store:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Guardar una copia", defaultextension=".fsal", filetypes=FILETYPES
        )
        if path:
            self.store.backup_to(path)
            messagebox.showinfo(
                APP_TITLE, "Copia guardada. Úsala como punto de partida para el próximo período.", parent=self
            )

    # -- refresh ------------------------------------------------------------------------
    def changed(self) -> None:
        for tab in self.tabs.values():
            tab.refresh()

    def _refresh_current(self) -> None:
        if self.ctl is None:
            return
        tab = self.nametowidget(self.notebook.select())
        tab.refresh()


def main(argv: list[str] | None = None) -> None:
    import sys

    args = sys.argv[1:] if argv is None else argv
    App(args[0] if args else None).mainloop()
