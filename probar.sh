#!/usr/bin/env bash
# Ejecuta las pruebas y el análisis de código. Usa una pantalla virtual (xvfb) si está instalada,
# para que también se prueben las ventanas sin abrirlas en tu pantalla.
set -euo pipefail
cd "$(dirname "$0")"
./abrir.sh --selftest   # crea el entorno si falta y comprueba que la ventana abre y cierra
if command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a .venv/bin/pytest -q "$@"
else
    .venv/bin/pytest -q "$@"
fi
.venv/bin/ruff check src tests
