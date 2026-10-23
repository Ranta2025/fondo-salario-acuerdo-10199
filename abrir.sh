#!/usr/bin/env bash
# Abre el programa desde el código fuente. La primera vez crea el entorno (.venv) e instala lo necesario.
# Uso:  ./abrir.sh                  (te pregunta si abrir o crear un proyecto)
#       ./abrir.sh mi-proyecto.fsal (abre directamente ese proyecto)
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "No se encontró Python 3. Instálalo (en Ubuntu/Debian: sudo apt install python3 python3-venv python3-tk)." >&2
    exit 1
fi
if ! "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
    echo "A este Python le falta tkinter (la parte gráfica)." >&2
    echo "  Ubuntu/Debian: sudo apt install python3-tk" >&2
    echo "  Homebrew:      brew install python-tk" >&2
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "Creando el entorno virtual (solo la primera vez)..."
    "$PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c "import fondo_salario, openpyxl" >/dev/null 2>&1; then
    echo "Instalando dependencias (solo la primera vez)..."
    .venv/bin/pip install --quiet -e ".[dev]"
fi

exec .venv/bin/python -m fondo_salario "$@"
