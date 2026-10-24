"""Main window (tkinter). All user-facing text is Spanish; the layout targets older, non-technical users."""

from __future__ import annotations

import sys
import tkinter as tk
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from fondo_salario.domain.models import Position, Settings, Worker
from fondo_salario.export.excel_report import to_roman
from fondo_salario.importers.merge import ImportPlan, resolve
from fondo_salario.importers.structure import looks_like, read_structure
from fondo_salario.importers.workers import parse_roman, read_workers_auto
from fondo_salario.messages import describe
from fondo_salario.persistence.sqlite_repo import AreaInUseError, ProjectStore
from fondo_salario.ui.controller import Controller, ImportSummary, parse_money, resolve_distribute
from fondo_salario.ui.forms import Field, ask_form
from fondo_salario.ui.merge_dialogs import ask_conflict, ask_summary

APP_TITLE = "Fondo de salario — Acuerdo 10199/2025"
FILETYPES = [("Proyecto de fondo de salario", "*.fsal")]
ROMANS = [to_roman(n) for n in range(1, 26)]
FONT_SIZE = 12

# Contribution grades of the regulation («Rafelito 3»); grade 1 (not in its table) means no bonus.
CONTRIBUTION_NAMES = {5: "Excepcional", 4: "Bueno", 3: "Satisfactorio", 2: "Regular", 1: "Sin bonificación"}

COLOR_STRIPE = "#eef2f7"
COLOR_AREA = "#d9e2ef"
COLOR_OK = "#1b6e2d"
COLOR_WARN = "#b00020"
COLOR_HINT = "#4a4a4a"


def contribution_label(grade: int) -> str:
    name = CONTRIBUTION_NAMES.get(grade)
    return f"{grade} - {name}" if name else str(grade)


CONTRIBUTION_CHOICES = [contribution_label(g) for g in (5, 4, 3, 2, 1)]


def contribution_from_text(text: str) -> int:
    return int(str(text).strip().split()[0])


def money_text(value: Decimal) -> str:
    return f"{value:,.2f}"


def group_text(group: int) -> str:
    return to_roman(group) if 1 <= group <= 25 else "—"


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


# -- look and feel ----------------------------------------------------------------------
def apply_style(root: tk.Tk) -> None:
    """Bigger fonts, taller rows and roomy buttons so everything is easy to read and to click."""
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        tkfont.nametofont(name).configure(size=FONT_SIZE)
    style = ttk.Style(root)
    if sys.platform != "win32" and "clam" in style.theme_names():
        style.theme_use("clam")
    family = tkfont.nametofont("TkDefaultFont").actual("family")
    bold = (family, FONT_SIZE, "bold")
    style.configure("Treeview", rowheight=36)
    style.configure("Treeview.Heading", font=bold, padding=(6, 8))
    style.configure("Compact.Treeview", rowheight=30)
    style.configure("Compact.Treeview.Heading", font=bold, padding=(6, 6))
    style.configure("TButton", padding=(14, 9))
    style.configure("Primary.TButton", font=bold, padding=(18, 10))
    style.configure("Toolbar.TButton", font=bold, padding=(16, 10))
    style.configure("TNotebook.Tab", font=bold, padding=(24, 12))
    style.configure("TEntry", padding=5)
    style.configure("TCombobox", padding=5)
    style.configure("Title.TLabel", font=(family, FONT_SIZE + 4, "bold"))
    style.configure("Hint.TLabel", foreground=COLOR_HINT)
    style.configure("Status.TLabel", padding=(10, 6))
    style.configure("Big.TLabel", font=(family, FONT_SIZE + 2, "bold"))
    root.option_add("*TCombobox*Listbox.font", (family, FONT_SIZE))


def run_import(parent: tk.Misc, ctl: Controller, plan: ImportPlan) -> ImportSummary | None:
    """Summary first, then the differences one by one (or all at once); None if the user cancelled."""
    mode = ask_summary(parent, plan)
    if mode is None:
        return None
    if not resolve(plan, mode, lambda item, diff, i, n: ask_conflict(parent, item, diff, i, n)):
        return None
    return ctl.apply_import(plan)


def import_report(
    summary: ImportSummary, errors: list[str], workers: bool, notes: list[str] | None = None
) -> str:
    """Plain-Spanish result of an import."""
    lines = ["Importación terminada."]
    if workers and summary.added:
        lines.append(f"• Trabajadores nuevos agregados: {summary.added} (todos SIN derecho a cobro).")
    if summary.areas_added:
        lines.append(f"• Áreas nuevas agregadas: {summary.areas_added}.")
    if summary.positions_added:
        lines.append(f"• Cargos nuevos agregados: {summary.positions_added}.")
    if summary.areas_created:
        lines.append(f"• Áreas creadas: {len(summary.areas_created)}.")
    if summary.completed:
        lines.append(f"• Datos completados que te faltaban: {summary.completed}.")
    if summary.overwritten or summary.kept:
        lines.append(f"• Diferencias: {summary.overwritten} sobrescritas, {summary.kept} conservadas.")
    if summary.unchanged:
        lines.append(f"• Ya estaban completos y no cambian: {summary.unchanged}.")
    if summary.undefined:
        lines.append(
            f"• {summary.undefined} trabajadores no tienen grupo salarial o antigüedad en el archivo: "
            "aparecen con «—» y no cobrarán hasta que los complete (haga doble clic en cada uno)."
        )
    if summary.defaults_used:
        lines.append(
            f"• {summary.defaults_used} usaron valores por defecto "
            "(días completos, contribución 3): revíselos."
        )
    if workers and summary.added:
        lines.append("\nMárquelos en esta pestaña con «Dar derecho a cobro».")
    lines.extend(f"• {note}" for note in (notes or [])[:8])
    problems = errors + summary.skipped
    if problems:
        lines.append(f"\nNo se importaron {len(problems)} filas:")
        lines.extend(problems[:15])
        if len(problems) > 15:
            lines.append(f"… y {len(problems) - 15} más")
    return "\n".join(lines)


def nothing_new_text(plan: ImportPlan, errors: list[str], notes: list[str] | None = None) -> str:
    problems = errors + plan.skipped
    if plan.unchanged or not problems:
        text = "No hay nada nuevo: todos los datos del archivo ya estaban registrados y completos."
    else:
        text = "No se pudo importar ninguna fila del archivo."
    if problems:
        text += f"\n\nNo se pueden importar {len(problems)} filas:\n" + "\n".join(problems[:15])
    if notes:
        text += "\n\n" + "\n".join(notes[:8])
    return text


def hint(parent, text: str) -> ttk.Label:
    label = ttk.Label(parent, text=text, style="Hint.TLabel", wraplength=1000, justify="left")
    label.pack(fill="x", pady=(0, 10))
    return label


def button_bar(parent, buttons: list[tuple[str, object]]) -> ttk.Frame:
    bar = ttk.Frame(parent)
    bar.pack(fill="x", pady=(0, 10))
    for text, command in buttons:
        ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, 8))
    return bar


def make_tree(parent, columns: list[tuple[str, str, int]], expand: bool = True, **kwargs) -> ttk.Treeview:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=expand, pady=(0, 0 if expand else 8))
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], **kwargs)
    for key, title, width in columns:
        tree.heading(key, text=title)
        tree.column(key, width=width, anchor="w" if key in ("name", "area", "position") else "e")
    scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    tree.tag_configure("odd", background=COLOR_STRIPE)
    tree.tag_configure("area", background=COLOR_AREA)
    tree.tag_configure("zero", foreground="#777777")
    return tree


def stripe(tree: ttk.Treeview) -> None:
    """Alternate row shading for readability (area rows keep their own colour)."""
    visible = 0

    def walk(parent: str) -> None:
        nonlocal visible
        for iid in tree.get_children(parent):
            tags = [t for t in tree.item(iid, "tags") if t != "odd"]
            if "area" not in tags:
                visible += 1
                if visible % 2 == 0:
                    tags.append("odd")
            tree.item(iid, tags=tags)
            walk(iid)

    walk("")


class ParametersTab(ttk.Frame):
    FIELDS = [
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

    def __init__(self, app: App):
        super().__init__(app.notebook, padding=20)
        self.app = app
        self.edited = False
        self._loading = False
        ttk.Label(self, text="Paso 1: Parámetros del pago", style="Title.TLabel").pack(anchor="w")
        hint(
            self,
            "Escriba el monto real que se va a repartir y los meses que se pagan. Los pesos y las escalas "
            "ya vienen con los valores del nuevo reglamento (25 / 40 / 20 / 15); cámbielos solo si su "
            "reglamento interno dice otra cosa.",
        )
        form = ttk.Frame(self)
        form.pack(anchor="w")
        self.vars: dict[str, tk.StringVar] = {}
        # (row, label column): amounts on the left, weights on the right, the two scales below
        layout = {
            "total": (0, 0),
            "months": (1, 0),
            "days": (2, 0),
            "w_resp": (0, 2),
            "w_con": (1, 2),
            "w_time": (2, 2),
            "w_sen": (3, 2),
            "b_resp": (4, 0),
            "b_sen": (5, 0),
        }
        for key, label in self.FIELDS:
            row, col = layout[key]
            wide = key.startswith("b_")
            ttk.Label(form, text=label).grid(row=row, column=col, sticky="w", pady=5, padx=(0, 14))
            self.vars[key] = tk.StringVar()
            self.vars[key].trace_add("write", self._on_edit)
            entry = ttk.Entry(form, textvariable=self.vars[key], width=44 if wide else 16)
            entry.grid(row=row, column=col + 1, columnspan=3 if wide else 1, sticky="w", padx=(0, 40))
        ttk.Button(
            self, text="Usar los valores del nuevo reglamento", command=self.use_regulation_values
        ).pack(anchor="w", pady=(12, 0))
        self.status = ttk.Label(self, text="", style="Big.TLabel")
        self.status.pack(anchor="w", pady=(10, 0))
        ttk.Label(
            self,
            text="Los pesos deben sumar 1.00. Las escalas dicen desde qué valor se obtiene cada nota "
            "(1 a 5). "
            "Los cambios se aplican solos al cambiar de pestaña.",
            style="Hint.TLabel",
            wraplength=1000,
        ).pack(anchor="w", pady=(6, 0))

    def use_regulation_values(self) -> None:
        """Put the weights and scales of the current regulation (Rafelito 3) in the form."""
        d = Settings(total_amount=Decimal(0))
        self.vars["w_time"].set(str(d.weight_time))
        self.vars["w_resp"].set(str(d.weight_responsibility))
        self.vars["w_sen"].set(str(d.weight_seniority))
        self.vars["w_con"].set(str(d.weight_contribution))
        self.vars["b_resp"].set(bands_to_text(d.responsibility_bands))
        self.vars["b_sen"].set(bands_to_text(d.seniority_bands))

    def _on_edit(self, *_args) -> None:
        if not self._loading:
            self.edited = True
            self.app.update_status()

    def refresh(self) -> None:
        if self.edited:  # never overwrite what the user is typing
            return
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
        self._loading = True
        for key, value in values.items():
            self.vars[key].set(value)
        self._loading = False
        total = s.weights_sum
        self.status.configure(
            text="" if total == 1 else f"⚠ Los pesos suman {total}; deben sumar 1.00",
            foreground=COLOR_WARN,
        )

    def apply(self) -> bool:
        """Validate and store the typed values; returns False (after telling the user) if invalid."""
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
            return False
        self.app.ctl.save_settings(settings)
        self.edited = False
        self.refresh()
        self.app.changed()
        return True


class StructureTab(ttk.Frame):
    def __init__(self, app: App):
        super().__init__(app.notebook, padding=20)
        self.app = app
        ttk.Label(self, text="Paso 2: Áreas y cargos", style="Title.TLabel").pack(anchor="w")
        hint(
            self,
            "Cree las áreas y, dentro de cada una, sus cargos. En cada cargo indique cuántas plazas están "
            "vacantes y cuántas de esas vacantes se van a distribuir. "
            "También puede importarlas desde su Excel anterior.",
        )
        button_bar(
            self,
            [
                ("Nueva área", self.add_area),
                ("Renombrar área", self.rename_area),
                ("Agregar cargo", self.add_position),
                ("Editar cargo", self.edit_position),
                ("Eliminar", self.delete),
                ("Importar desde Excel…", self.import_excel),
            ],
        )
        columns = [
            ("approved", "Aprobadas", 105),
            ("vacant", "Vacantes", 100),
            ("temp", "Temporales", 110),
            ("distribute", "Vacantes a distribuir", 200),
            ("salary", "Salario", 110),
            ("months", "Meses", 90),
            ("unexecuted", "Monto inejecutado", 180),
        ]
        self.tree = make_tree(self, columns, show="tree headings")
        self.tree.heading("#0", text="Área / cargo")
        self.tree.column("#0", width=300)
        self.tree.bind("<Double-1>", lambda _e: self.edit_position())

    def refresh(self) -> None:
        open_areas = {iid for iid in self.tree.get_children() if self.tree.item(iid, "open")}
        first_fill = not self.tree.get_children()
        self.tree.delete(*self.tree.get_children())
        project = self.app.ctl.project
        for area in project.areas:
            iid = f"a{area.id}"
            self.tree.insert(
                "", "end", iid=iid, text=area.name, tags=("area",), open=first_fill or iid in open_areas
            )
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
        stripe(self.tree)

    def _selected(self) -> tuple[str, int] | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Áreas y cargos", "Primero haga clic en un área o en un cargo.", parent=self)
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
        if not picked:
            return
        if picked[0] != "a":
            messagebox.showinfo("Renombrar", "Haga clic en el nombre de un área.", parent=self)
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

        return ask_form(
            self,
            title,
            fields,
            initial,
            build,
            hint="Si hay 4 vacantes pero solo se reparten 2, escriba 2 en «Vacantes a distribuir».",
        )

    def add_position(self) -> None:
        picked = self._selected()
        if not picked:
            return
        area_id = picked[1] if picked[0] == "a" else self.app.ctl.position(picked[1]).area_id
        months = self.app.ctl.project.settings.months_paid
        position = self._position_form(
            "Agregar cargo",
            {
                "approved": 1,
                "vacant": 0,
                "temp_vacant": 0,
                "distribute": "",
                "salary": "0",
                "months": months,
            },
            area_id,
        )
        if position:
            self.app.ctl.add_position(position)
            self.app.changed()

    def edit_position(self) -> None:
        picked = self._selected()
        if not picked:
            return
        if picked[0] != "p":
            messagebox.showinfo("Editar cargo", "Haga clic en un cargo (no en un área).", parent=self)
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
        if not messagebox.askyesno("Eliminar", f"¿Seguro que desea eliminar «{label}»?", parent=self):
            return
        try:
            if kind == "a":
                self.app.ctl.delete_area(item_id)
            else:
                self.app.ctl.delete_position(item_id)
        except AreaInUseError:
            messagebox.showwarning(
                "Eliminar",
                "El área todavía tiene trabajadores. Elimínelos o cámbielos de área primero.",
                parent=self,
            )
            return
        self.app.changed()

    def import_excel(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Excel con la relación de áreas y cargos",
            filetypes=[("Excel o CSV", "*.xlsx *.csv"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            areas = read_structure(path)
            plan = self.app.ctl.plan_structure_import(areas)
        except Exception as error:  # unreadable or unexpected workbook
            messagebox.showerror("Importar", f"No se pudo leer el archivo:\n{error}", parent=self)
            return
        if not areas:
            text = "No se reconoció ninguna área ni cargo en el archivo."
            if looks_like(path) == "workers":
                text += "\n\nParece un archivo de trabajadores: use «Importar desde Excel/CSV» en el paso 3."
            messagebox.showinfo("Importar", text, parent=self)
            return
        if not (plan.new_count or plan.fill_count or plan.conflicts):
            messagebox.showinfo("Importar", nothing_new_text(plan, []), parent=self)
            return
        summary = run_import(self, self.app.ctl, plan)
        if summary is None:
            return
        messagebox.showinfo(
            "Importar",
            import_report(summary, [], workers=False) + "\n\nRevise las vacantes de cada cargo.",
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
        super().__init__(app.notebook, padding=20)
        self.app = app
        ttk.Label(self, text="Paso 3: Trabajadores", style="Title.TLabel").pack(anchor="w")
        hint(
            self,
            "Agregue a cada trabajador con sus datos. El derecho a cobro es solo para quienes asumen las "
            "tareas de una plaza vacante: quíteselo a los demás (puede marcar varios a la vez).",
        )
        button_bar(
            self,
            [
                ("Agregar trabajador", self.add),
                ("Editar", self.edit),
                ("Eliminar", self.delete),
                ("Dar derecho a cobro", self.grant_right),
                ("Quitar derecho a cobro", self.revoke_right),
                ("Importar desde Excel/CSV…", self.import_file),
            ],
        )
        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Buscar:").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(filters, textvariable=self.search, width=26).pack(side="left", padx=(6, 18))
        ttk.Label(filters, text="Mostrar:").pack(side="left")
        self.area_filter = tk.StringVar(value=self.ALL)
        self.combo = ttk.Combobox(filters, textvariable=self.area_filter, state="readonly", width=34)
        self.combo.pack(side="left", padx=6)
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Label(filters, text="Derecho a cobro:").pack(side="left", padx=(18, 0))
        self.right_filter = tk.StringVar(value="Todos")
        right_combo = ttk.Combobox(
            filters,
            textvariable=self.right_filter,
            values=["Todos", "Con derecho", "Sin derecho"],
            state="readonly",
            width=14,
        )
        right_combo.pack(side="left", padx=6)
        right_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        columns = [
            ("name", "Nombre y apellidos", 220),
            ("ci", "Carné de identidad", 170),
            ("area", "Área", 220),
            ("position", "Cargo", 130),
            ("group", "Grupo", 75),
            ("years", "Antigüedad", 115),
            ("days", "Días", 60),
            ("contribution", "Contrib.", 90),
            ("eligible", "Derecho a cobro", 160),
        ]
        self.tree = make_tree(self, columns, show="headings")
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        self.count = ttk.Label(self, text="", style="Hint.TLabel")
        self.count.pack(anchor="w", pady=(6, 0))

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
            right = self.right_filter.get()
            if (right == "Con derecho" and not w.eligible) or (right == "Sin derecho" and w.eligible):
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
                    group_text(w.salary_group),
                    w.seniority_years,
                    w.days_worked,
                    w.contribution,
                    "Sí" if w.eligible else "No",
                ),
                tags=() if w.eligible else ("zero",),
            )
        stripe(self.tree)
        self.count.configure(text=f"Mostrando {shown} de {len(project.workers)} trabajadores")

    def _form(self, title: str, initial: dict, worker_id: int = 0) -> Worker | None:
        areas = {a.name: a.id for a in self.app.ctl.project.areas}
        if not areas:
            messagebox.showinfo(
                "Trabajadores", "Primero cree al menos un área en el Paso 2 (Áreas y cargos).", parent=self
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
            Field("contribution", "Contribución", "choice", CONTRIBUTION_CHOICES),
            Field("eligible", "Derecho a cobro (asume tareas de una plaza vacante)", "bool"),
        ]

        def build(v: dict) -> Worker:
            if not v["name"].strip():
                raise ValueError("El nombre es obligatorio.")
            if v["area"] not in areas:
                raise ValueError("Seleccione el área.")
            group = parse_roman(v["group"])
            if group is None:
                raise ValueError("Seleccione el grupo salarial.")
            return Worker(
                id=worker_id,
                full_name=v["name"].strip(),
                national_id=v["ci"].strip(),
                area_id=areas[v["area"]],
                position_name=v["position"].strip(),
                salary_group=group,
                seniority_years=parse_int(v["years"], "Antigüedad", 0, 60),
                days_worked=parse_int(v["days"], "Días trabajados", 0, 1000),
                contribution=parse_int(str(contribution_from_text(v["contribution"])), "Contribución", 1, 5),
                eligible=bool(v["eligible"]),
            )

        return ask_form(self, title, fields, initial, build)

    def add(self) -> None:
        s = self.app.ctl.project.settings
        initial = {
            "days": s.expected_days_per_month * s.months_paid,
            "years": 0,
            "contribution": contribution_label(3),
            "eligible": False,  # granted by hand
        }
        worker = self._form("Agregar trabajador", initial)
        if worker:
            self.app.ctl.add_worker(worker)
            self.app.changed()

    def _selected_worker(self) -> Worker | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(
                "Trabajadores", "Primero haga clic en un trabajador de la lista.", parent=self
            )
            return None
        return self.app.ctl.worker(int(selection[0]))

    def edit(self) -> None:
        current = self._selected_worker()
        if current is None:
            return
        names = {a.id: a.name for a in self.app.ctl.project.areas}
        initial = {
            "name": current.full_name,
            "ci": current.national_id,
            "area": names.get(current.area_id, ""),
            "position": current.position_name,
            "group": to_roman(current.salary_group) if 1 <= current.salary_group <= 25 else "",
            "years": current.seniority_years,
            "days": current.days_worked,
            "contribution": contribution_label(current.contribution),
            "eligible": current.eligible,
        }
        worker = self._form("Editar trabajador", initial, current.id)
        if worker:
            self.app.ctl.update_worker(worker)
            self.app.changed()

    def _selected_ids(self) -> list[int]:
        ids = [int(iid) for iid in self.tree.selection()]
        if not ids:
            messagebox.showinfo(
                "Trabajadores", "Primero haga clic en uno o varios trabajadores de la lista.", parent=self
            )
        return ids

    def grant_right(self) -> None:
        ids = self._selected_ids()
        if ids:
            self.app.ctl.set_eligible(ids, True)
            self.app.changed()

    def revoke_right(self) -> None:
        ids = self._selected_ids()
        if ids:
            self.app.ctl.set_eligible(ids, False)
            self.app.changed()

    def delete(self) -> None:
        current = self._selected_worker()
        if current is None:
            return
        if messagebox.askyesno(
            "Eliminar", f"¿Seguro que desea eliminar a «{current.full_name}»?", parent=self
        ):
            self.app.ctl.delete_worker(current.id)
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
            read = read_workers_auto(path)
        except Exception as error:  # unreadable file
            messagebox.showerror("Importar", f"No se pudo leer el archivo:\n{error}", parent=self)
            return
        if not read.rows and looks_like(path) == "structure":
            messagebox.showinfo(
                "Importar",
                "Parece un archivo de áreas y cargos, no de trabajadores: use «Importar desde Excel» "
                "en el paso 2.",
                parent=self,
            )
            return
        plan = self.app.ctl.plan_workers_import(read.rows, create_missing_areas=True, allow_undefined=True)
        errors = [f"Fila {e.line}: {e.message}" for e in read.errors]
        if not (plan.new_count or plan.fill_count or plan.conflicts):
            messagebox.showinfo("Importar", nothing_new_text(plan, errors, read.notes), parent=self)
            return
        summary = run_import(self, self.app.ctl, plan)
        if summary is None:
            return
        messagebox.showinfo(
            "Importar", import_report(summary, errors, workers=True, notes=read.notes), parent=self
        )
        self.app.changed()


class ResultsTab(ttk.Frame):
    def __init__(self, app: App):
        super().__init__(app.notebook, padding=20)
        self.app = app
        ttk.Label(self, text="Paso 4: Resultados", style="Title.TLabel").pack(anchor="w")
        hint(
            self,
            "Revise los montos. Si todo cuadra, exporte el informe: incluye los cálculos y la pre-nómina.",
        )
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Exportar a Excel…", style="Primary.TButton", command=app.export).pack(
            side="left"
        )
        self.summary = ttk.Label(bar, text="", style="Big.TLabel")
        self.summary.pack(side="left", padx=20)
        area_columns = [
            ("name", "Área", 330),
            ("unexecuted", "Monto inejecutado", 160),
            ("pct", "% del total", 100),
            ("amount", "Monto a pagar", 160),
        ]
        self.areas = make_tree(
            self, area_columns, expand=False, show="headings", height=4, style="Compact.Treeview"
        )
        worker_columns = [
            ("name", "Trabajador", 280),
            ("area", "Área", 240),
            ("coef", "Coeficiente", 110),
            ("amount", "Monto a cobrar", 160),
        ]
        self.workers = make_tree(self, worker_columns, show="headings", height=6, style="Compact.Treeview")
        box = ttk.Frame(self)
        box.pack(fill="x", pady=(8, 0))
        self.issues = tk.Text(box, height=3, wrap="word", state="disabled", background="#fff8e1")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.issues.yview)
        self.issues.configure(yscrollcommand=scroll.set)
        self.issues.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")

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
        stripe(self.areas)
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
                tags=("zero",) if r.amount == 0 else (),
            )
        stripe(self.workers)
        total = ctl.project.settings.total_amount
        balanced = total > 0 and result.distributed == total
        paid = sum(1 for r in result.workers if r.amount > 0)
        if total <= 0:
            verdict = "     ⚠ Falta el monto real a distribuir (Paso 1)"
        else:
            verdict = "     ✓ Cuadra" if balanced else "     ⚠ No cuadra"
        self.summary.configure(
            text=f"A distribuir: {money_text(total)}     Repartido: {money_text(result.distributed)}"
            f"     Cobran: {paid} de {len(result.workers)}" + verdict,
            foreground=COLOR_OK if balanced else COLOR_WARN,
        )
        self.issues.configure(state="normal")
        self.issues.delete("1.0", "end")
        lines = [f"⚠ {describe(i)}" for i in result.issues] or ["Sin observaciones: los cálculos cuadran."]
        self.issues.insert("1.0", "\n".join(lines))
        self.issues.configure(state="disabled")


class App(tk.Tk):
    def __init__(self, project_path: str | Path | None = None):
        super().__init__()
        apply_style(self)
        self.title(APP_TITLE)
        self.geometry("1280x760")
        self.minsize(1000, 640)
        self._maximize()
        self.store: ProjectStore | None = None
        self.ctl: Controller | None = None
        self.project_path: Path | None = None
        self._current_tab: ttk.Frame | None = None

        self._build_toolbar()
        self._build_footer()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        self.tabs = {
            "1. Parámetros": ParametersTab(self),
            "2. Áreas y cargos": StructureTab(self),
            "3. Trabajadores": WorkersTab(self),
            "4. Resultados": ResultsTab(self),
        }
        for title, tab in self.tabs.items():
            self.notebook.add(tab, text=title)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._build_menu()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Control-s>", lambda _e: self.save())
        if project_path:
            self.open_project(project_path)
        else:
            self.after(150, self.start_prompt)

    def _maximize(self) -> None:
        try:
            self.state("zoomed")  # Windows
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)  # Linux
            except tk.TclError:
                pass

    # -- chrome ---------------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        for text, command in [
            ("Nuevo proyecto", self.new_project),
            ("Abrir", self.ask_open_project),
            ("Guardar", self.save),
            ("Guardar una copia", self.save_copy),
        ]:
            ttk.Button(bar, text=text, style="Toolbar.TButton", command=command).pack(
                side="left", padx=(0, 8)
            )
        ttk.Button(bar, text="Exportar a Excel", style="Toolbar.TButton", command=self.export).pack(
            side="right"
        )
        ttk.Separator(self).pack(fill="x")

    def _build_footer(self) -> None:
        # packed from the bottom up, before the notebook, so it is always visible
        self.status = ttk.Label(self, text="", style="Status.TLabel")
        self.status.pack(side="bottom", fill="x")
        ttk.Separator(self).pack(side="bottom", fill="x")
        nav = ttk.Frame(self, padding=(12, 6))
        nav.pack(side="bottom", fill="x")
        ttk.Button(nav, text="‹ Anterior", style="Toolbar.TButton", command=lambda: self._step(-1)).pack(
            side="left"
        )
        ttk.Button(nav, text="Siguiente ›", style="Primary.TButton", command=lambda: self._step(1)).pack(
            side="right"
        )

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Nuevo proyecto…", command=self.new_project)
        file_menu.add_command(label="Abrir proyecto…", command=self.ask_open_project)
        file_menu.add_command(label="Guardar        Ctrl+S", command=self.save)
        file_menu.add_command(label="Guardar una copia…", command=self.save_copy)
        file_menu.add_command(label="Exportar a Excel…", command=self.export)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.on_close)
        menu.add_cascade(label="Archivo", menu=file_menu)
        self.configure(menu=menu)

    def _step(self, delta: int) -> None:
        index = self.notebook.index(self.notebook.select()) + delta
        if 0 <= index < len(self.tabs):
            self.notebook.select(index)

    def update_status(self) -> None:
        if self.ctl is None:
            self.status.configure(text="Ningún proyecto abierto.", foreground=COLOR_HINT)
            return
        name = self.project_path.name if self.project_path else ""
        pending = self.ctl.dirty or self.tabs["1. Parámetros"].edited
        if pending:
            self.status.configure(
                text=f"Proyecto: {name}      ● Hay cambios sin guardar (pulse Guardar)",
                foreground=COLOR_WARN,
            )
        else:
            self.status.configure(text=f"Proyecto: {name}      ✓ Todo guardado", foreground=COLOR_OK)
        self.title(f"{'* ' if pending else ''}{APP_TITLE} — {name}")

    # -- tabs -----------------------------------------------------------------------------
    def _on_tab_changed(self, _event=None) -> None:
        if self.ctl is None:
            return
        current = self.nametowidget(self.notebook.select())
        previous = self._current_tab
        if isinstance(previous, ParametersTab) and current is not previous and previous.edited:
            if not previous.apply():
                self.notebook.select(previous)
                return
        self._current_tab = current
        current.refresh()

    def _apply_pending_parameters(self) -> bool:
        params = self.tabs["1. Parámetros"]
        if params.edited and not params.apply():
            self.notebook.select(params)
            return False
        return True

    # -- project lifecycle ----------------------------------------------------------------
    def start_prompt(self) -> None:
        answer = messagebox.askyesnocancel(
            APP_TITLE,
            "¿Quiere abrir un proyecto que ya tiene guardado?\n\n"
            "Sí: abrir uno existente\nNo: crear un proyecto nuevo\nCancelar: salir",
            parent=self,
        )
        if answer is None:
            self.destroy()
        elif answer:
            self.ask_open_project(exit_on_cancel=True, check_unsaved=False)
        else:
            self.new_project(exit_on_cancel=True, check_unsaved=False)

    def confirm_leave(self) -> bool:
        """Ask what to do with unsaved changes; False means the user cancelled."""
        params = self.tabs["1. Parámetros"]
        if self.ctl is None or not (self.ctl.dirty or params.edited):
            return True
        answer = messagebox.askyesnocancel(
            "Guardar cambios",
            "Hay cambios sin guardar.\n\n¿Desea guardarlos?\n\n"
            "Sí: guardar\nNo: descartar los cambios\nCancelar: volver al programa",
            icon="warning",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return self.save()
        params.edited = False
        self.ctl.discard()
        return True

    def new_project(self, exit_on_cancel: bool = False, check_unsaved: bool = True) -> None:
        if check_unsaved and not self.confirm_leave():
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Crear proyecto nuevo",
            defaultextension=".fsal",
            initialfile="fondo-de-salario.fsal",
            filetypes=FILETYPES,
        )
        self._finish_pick(path, exit_on_cancel)

    def ask_open_project(self, exit_on_cancel: bool = False, check_unsaved: bool = True) -> None:
        if check_unsaved and not self.confirm_leave():
            return
        path = filedialog.askopenfilename(parent=self, title="Abrir proyecto", filetypes=FILETYPES)
        self._finish_pick(path, exit_on_cancel)

    def _finish_pick(self, path: str, exit_on_cancel: bool) -> None:
        if path:
            self.open_project(path)
        elif exit_on_cancel and self.ctl is None:
            self.destroy()

    def open_project(self, path: str | Path) -> None:
        try:
            store = ProjectStore(path, autosave=False)
        except (ValueError, OSError) as error:
            messagebox.showerror(APP_TITLE, f"No se pudo abrir el proyecto:\n{error}", parent=self)
            return
        if self.store:
            self.store.close()
        self.store, self.ctl = store, Controller(store)
        self.project_path = Path(path)
        self.tabs["1. Parámetros"].edited = False
        self._current_tab = None
        self.notebook.select(0)
        self.changed()

    def save(self) -> bool:
        if self.ctl is None:
            return False
        if not self._apply_pending_parameters():
            return False
        self.ctl.save()
        self.update_status()
        return True

    def save_copy(self) -> None:
        if self.store is None or not self._apply_pending_parameters():
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar una copia del proyecto",
            defaultextension=".fsal",
            filetypes=FILETYPES,
        )
        if not path:
            return
        self.store.backup_to(path)
        self.update_status()
        messagebox.showinfo(
            APP_TITLE,
            "Copia guardada (el proyecto actual también quedó guardado).\n"
            "Use la copia como punto de partida para el próximo período.",
            parent=self,
        )

    def export(self) -> None:
        if self.ctl is None or not self._apply_pending_parameters():
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar informe de Excel",
            defaultextension=".xlsx",
            initialfile="fondo-de-salario.xlsx",
            filetypes=[("Excel o CSV", "*.xlsx *.csv"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            self.ctl.export(path)
        except OSError as error:
            messagebox.showerror(
                "Exportar",
                f"No se pudo guardar el archivo. ¿Está abierto en Excel?\n{error}",
                parent=self,
            )
            return
        messagebox.showinfo("Exportar", f"Informe guardado en:\n{path}", parent=self)

    def on_close(self) -> None:
        if self.confirm_leave():
            self.destroy()

    def destroy(self) -> None:
        # always release the project file (Windows cannot delete or move a file that is still open)
        if self.store is not None:
            self.store.close()
            self.store = None
        super().destroy()

    # -- refresh --------------------------------------------------------------------------
    def changed(self) -> None:
        for tab in self.tabs.values():
            tab.refresh()
        self.update_status()


def selftest() -> int:
    """Open the main window on a throwaway project and close it; used to check a packaged build starts."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        window = App(Path(folder) / "selftest.fsal")
        window.update()
        window.destroy()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["--selftest"]:
        return selftest()
    App(args[0] if args else None).mainloop()
    return 0
