"""Small modal form dialog shared by all add/edit screens."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import Any


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"  # text | choice | bool
    choices: list[str] = field(default_factory=list)


def ask_form(
    parent: tk.Misc,
    title: str,
    fields: list[Field],
    initial: dict[str, Any],
    build: Callable[[dict[str, Any]], Any],
    hint: str = "",
) -> Any | None:
    """Show the form; `build` turns raw values into a result or raises ValueError(message).

    The dialog stays open until `build` succeeds or the user cancels (returns None).
    """
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent.winfo_toplevel())
    dialog.resizable(False, False)
    variables: dict[str, tk.Variable] = {}
    frame = ttk.Frame(dialog, padding=20)
    frame.grid(sticky="nsew")
    first_widget: tk.Widget | None = None
    top = 0
    if hint:
        ttk.Label(frame, text=hint, style="Hint.TLabel", wraplength=480, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        top = 1
    for row, item in enumerate(fields, start=top):
        ttk.Label(frame, text=item.label).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=6)
        value = initial.get(item.key, "")
        if item.kind == "bool":
            var: tk.Variable = tk.BooleanVar(value=bool(value))
            widget: tk.Widget = ttk.Checkbutton(frame, variable=var)
        elif item.kind == "choice":
            var = tk.StringVar(value=str(value))
            widget = ttk.Combobox(frame, textvariable=var, values=item.choices, state="readonly", width=34)
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(frame, textvariable=var, width=38)
        widget.grid(row=row, column=1, sticky="ew", pady=6)
        variables[item.key] = var
        first_widget = first_widget or widget

    result: dict[str, Any] = {}

    def accept(_event=None) -> None:
        try:
            result["value"] = build({key: var.get() for key, var in variables.items()})
        except ValueError as error:
            messagebox.showerror(title, str(error), parent=dialog)
            return
        dialog.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=len(fields) + top, column=0, columnspan=2, pady=(16, 0), sticky="e")
    ttk.Button(buttons, text="Aceptar", style="Primary.TButton", command=accept).pack(side="left", padx=6)
    ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side="left")
    dialog.bind("<Return>", accept)
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    if first_widget is not None:
        first_widget.focus_set()
    dialog.update_idletasks()
    root = parent.winfo_toplevel()
    x = root.winfo_rootx() + max((root.winfo_width() - dialog.winfo_width()) // 2, 0)
    y = root.winfo_rooty() + max((root.winfo_height() - dialog.winfo_height()) // 3, 0)
    dialog.geometry(f"+{x}+{y}")
    dialog.grab_set()
    parent.wait_window(dialog)
    return result.get("value")
