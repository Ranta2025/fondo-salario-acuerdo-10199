"""Dialogs of the smart import: a summary first, then the differences one by one."""

from __future__ import annotations

import tkinter as tk
from collections import Counter
from tkinter import ttk

from fondo_salario.importers.merge import FieldDiff, ImportPlan, MergeItem

KIND_TEXT = {"worker": "Trabajador", "position": "Cargo"}


def _center(dialog: tk.Toplevel, parent: tk.Misc) -> None:
    dialog.update_idletasks()
    root = parent.winfo_toplevel()
    x = root.winfo_rootx() + max((root.winfo_width() - dialog.winfo_width()) // 2, 0)
    y = root.winfo_rooty() + max((root.winfo_height() - dialog.winfo_height()) // 3, 0)
    dialog.geometry(f"+{x}+{y}")


def _modal(parent: tk.Misc, title: str) -> tuple[tk.Toplevel, ttk.Frame, dict]:
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent.winfo_toplevel())
    dialog.resizable(False, False)
    frame = ttk.Frame(dialog, padding=22)
    frame.pack()
    return dialog, frame, {}


def _buttons(
    frame: ttk.Frame, dialog: tk.Toplevel, result: dict, options: list[tuple[str, str | None, bool]]
):
    bar = ttk.Frame(frame)
    bar.pack(fill="x", pady=(18, 0))
    for text, value, primary in options:

        def choose(v=value):
            result["value"] = v
            dialog.destroy()

        ttk.Button(bar, text=text, style="Primary.TButton" if primary else "TButton", command=choose).pack(
            fill="x", pady=4
        )
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)  # closing the window = cancel


def summary_lines(plan: ImportPlan) -> list[str]:
    """What the import is going to do, in plain Spanish."""
    lines: list[str] = []
    if plan.kind == "workers":
        if plan.new_workers:
            lines.append(f"• Trabajadores nuevos que se agregarán: {len(plan.new_workers)}")
    else:
        if plan.new_areas:
            lines.append(f"• Áreas nuevas que se agregarán: {len(plan.new_areas)}")
        if plan.new_positions:
            lines.append(f"• Cargos nuevos en áreas que ya tenías: {len(plan.new_positions)}")
    if plan.areas_to_create:
        lines.append(f"• Áreas que se crearán: {', '.join(plan.areas_to_create)}")
    if plan.fill_count:
        labels = Counter(label for item in plan.items for label in item.fill_labels)
        detail = ", ".join(f"{label} ({n})" for label, n in labels.items())
        lines.append(f"• Datos que te faltaban y se completarán solos: {plan.fill_count} — {detail}")
    if plan.conflicts:
        lines.append(f"• Datos distintos a los que ya tienes (tú decides): {len(plan.conflicts)}")
    if plan.unchanged:
        lines.append(f"• Ya estaban completos y no cambian: {plan.unchanged}")
    if plan.skipped:
        lines.append(f"• Filas que no se pueden importar: {len(plan.skipped)}")
    return lines


def ask_summary(parent: tk.Misc, plan: ImportPlan) -> str | None:
    """Returns "review", "accept_all", "keep_all" or None (cancel)."""
    dialog, frame, result = _modal(parent, "Importar datos")
    ttk.Label(frame, text="Esto es lo que va a pasar con el archivo", style="Title.TLabel").pack(anchor="w")
    ttk.Label(frame, text="\n".join(summary_lines(plan)), justify="left", wraplength=560).pack(
        anchor="w", pady=(12, 0)
    )
    ttk.Label(
        frame,
        text="No se borra nada de lo que ya tienes.",
        style="Hint.TLabel",
    ).pack(anchor="w", pady=(8, 0))
    if plan.conflicts:
        options = [
            ("Revisar las diferencias una por una", "review", True),
            ("Aceptar todas las diferencias directamente (sobrescribir)", "accept_all", False),
            ("Solo agregar y completar lo que falta (conservar lo mío)", "keep_all", False),
            ("Cancelar", None, False),
        ]
    else:
        options = [("Aplicar", "keep_all", True), ("Cancelar", None, False)]
    _buttons(frame, dialog, result, options)
    _center(dialog, parent)
    dialog.grab_set()
    parent.wait_window(dialog)
    return result.get("value")


def ask_conflict(parent: tk.Misc, item: MergeItem, diff: FieldDiff, index: int, total: int) -> str | None:
    """Returns "overwrite", "keep", "overwrite_rest" or None (cancel the whole import)."""
    dialog, frame, result = _modal(parent, f"Diferencia {index} de {total}")
    ttk.Label(frame, text=f"Diferencia {index} de {total}", style="Hint.TLabel").pack(anchor="w")
    ttk.Label(frame, text=f"{KIND_TEXT.get(item.kind, '')}: {item.name}", style="Title.TLabel").pack(
        anchor="w", pady=(4, 0)
    )
    ttk.Label(frame, text=f"Campo: {diff.label}", style="Big.TLabel").pack(anchor="w", pady=(10, 6))
    grid = ttk.Frame(frame)
    grid.pack(anchor="w")
    ttk.Label(grid, text="Lo que tienes ahora:").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=3)
    ttk.Label(grid, text=f"«{diff.current or '(vacío)'}»", style="Big.TLabel").grid(
        row=0, column=1, sticky="w"
    )
    ttk.Label(grid, text="Lo que trae el archivo:").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=3)
    ttk.Label(grid, text=f"«{diff.incoming}»", style="Big.TLabel").grid(row=1, column=1, sticky="w")
    options = [
        ("Sobrescribir con el del archivo", "overwrite", True),
        ("Conservar el mío", "keep", False),
    ]
    if index < total:
        rest = total - index
        label = (
            "Sobrescribir esta y la que falta" if rest == 1 else f"Sobrescribir esta y las {rest} que faltan"
        )
        options.append((label, "overwrite_rest", False))
    options.append(("Cancelar toda la importación", None, False))
    _buttons(frame, dialog, result, options)
    _center(dialog, parent)
    dialog.grab_set()
    parent.wait_window(dialog)
    return result.get("value")
