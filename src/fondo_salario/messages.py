"""Spanish, user-facing text for calculation issues."""

from __future__ import annotations

from fondo_salario.domain.calculation import Issue

_TEMPLATES = {
    "weights_sum": "Los pesos de los indicadores suman {subject}; deben sumar 1.",
    "no_unexecuted": "No hay fondo de salario no ejecutado para distribuir.",
    "distribute_exceeds": (
        "Cargo {subject}: las vacantes a distribuir superan las que hay; se usan solo las vacantes que hay."
    ),
    "invalid_worker": "Datos no válidos en el trabajador {subject}; se le asigna 0.00.",
    "undistributed": (
        "Área {subject}: tiene monto asignado pero ningún trabajador elegible; ese dinero queda sin repartir."
    ),
}


def describe(issue: Issue) -> str:
    template = _TEMPLATES.get(issue.code)
    return template.format(subject=issue.subject) if template else issue.message
