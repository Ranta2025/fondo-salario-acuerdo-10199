"""Spanish, user-facing text for calculation issues."""

from __future__ import annotations

from fondo_salario.domain.calculation import Issue

_TEMPLATES = {
    "weights_sum": "Los pesos de los indicadores suman {subject}; deben sumar 1.",
    "no_unexecuted": "No hay fondo de salario no ejecutado para distribuir.",
    "distribute_exceeds": (
        "Cargo {subject}: las vacantes a distribuir superan las que hay; se usan solo las vacantes que hay."
    ),
    "invalid_worker": (
        "Datos no válidos en el trabajador {subject}: {detail}; se le asigna 0.00 hasta corregirlo."
    ),
    "undistributed": (
        "Área {subject}: tiene monto asignado pero ningún trabajador elegible; ese dinero queda sin repartir."
    ),
}


_DETAILS = {
    "unknown_area": "no tiene un área válida",
    "salary_group": "falta el grupo salarial",
    "negative": "tiene valores negativos",
    "contribution": "la contribución debe estar entre 1 y 5",
}


def describe(issue: Issue) -> str:
    template = _TEMPLATES.get(issue.code)
    if template is None:
        return issue.message
    return template.format(subject=issue.subject, detail=_DETAILS.get(issue.detail, "revise sus datos"))
