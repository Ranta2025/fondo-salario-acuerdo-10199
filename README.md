# Fondo de salario — Acuerdo 10199/2025

Aplicación de escritorio, **local y sin conexión**, para repartir el fondo de salario no ejecutado entre
los trabajadores de una unidad presupuestada y exportar la evidencia de los cálculos a Excel.

El [Acuerdo 10199](https://www.mfp.gob.cu/noticia/919) (Gaceta Oficial Extraordinaria No. 45, 11/08/2025) permite
usar las inejecuciones del fondo de salario para incentivar la estabilidad de la fuerza de trabajo. El acuerdo **no fija
los criterios de reparto**: cada unidad los aprueba en su reglamento interno (Consejo de Dirección, sindicato y
asamblea de trabajadores). Por eso los pesos y las escalas son configurables.

## Cómo se calcula

1. **Monto por área.** Por cada cargo: `(vacantes + temporalmente vacantes) × salario × meses inejecutados`.
   Cada área recibe el porcentaje que representa su monto inejecutado sobre el total (los porcentajes suman 100)
   y ese porcentaje se aplica al monto real a distribuir.
2. **Coeficiente individual.** Cada trabajador se evalúa de 1 a 5 en cuatro indicadores:

   | Indicador | Peso por defecto | Cómo se evalúa |
   |---|---|---|
   | Tiempo trabajado | 0.40 | días trabajados ÷ (24 × meses a pagar), llevado a 1–5 (0 si no trabajó) |
   | Responsabilidad | 0.25 | grupo salarial I–XXV según la escala |
   | Antigüedad | 0.15 | años en la institución según la escala |
   | Contribución | 0.20 | nota 1–5 que da el jefe |

   `coeficiente = Σ peso × evaluación`
3. **Monto por trabajador.** `coeficiente ÷ suma de coeficientes del área × monto del área`.
   Los redondeos se hacen al centavo con el método del mayor resto, así que **la suma siempre cuadra al centavo**.
4. **Pre-nómina.** Todos los trabajadores, con 0.00 a los que no les toca.

Los pesos (0.40/0.25/0.15/0.20) y las escalas por defecto son un punto de partida: se editan en la pestaña
**Parámetros**. Verifica que coincidan con el reglamento de tu unidad.

## Uso

1. **Parámetros**: monto real a distribuir, meses a pagar, pesos y escalas.
2. **Áreas y cargos**: crea las áreas y sus cargos (o impórtalos desde el Excel antiguo). En cada cargo indica
   plazas aprobadas, vacantes, temporalmente vacantes, salario y meses inejecutados.
3. **Trabajadores**: agrega, edita o elimina trabajadores, o impórtalos desde CSV/Excel
   (columnas: nombre, carné, área, cargo, grupo, antigüedad, días, contribución).
   Marca «Cobra» en No para quien no deba recibir pago.
4. **Resultados**: revisa los montos y las observaciones. Pulsa **Exportar a Excel** para generar el informe
   (montos por área, coeficientes por trabajador, pre-nómina y parámetros usados), listo para imprimir.

Todo se guarda automáticamente en el archivo del proyecto (`.fsal`). Para el próximo período usa
**Archivo → Guardar una copia** y trabaja sobre la copia.

## Instalación y ejecución

Requiere Python 3.10 o superior (en Windows, el instalador de python.org ya incluye tkinter).

```bash
python -m venv .venv
.venv/bin/pip install -e .          # Windows: .venv\Scripts\pip install -e .
.venv/bin/python -m fondo_salario   # o: .venv/bin/python -m fondo_salario ruta/proyecto.fsal
```

### Windows: ejecutable listo (sin instalar Python)

Cada subida al repositorio compila `FondoSalario.exe` en un Windows real con GitHub Actions
(`.github/workflows/windows.yml`), tras pasar las pruebas. Para obtenerlo:

1. Abre la pestaña **Actions** del repositorio y entra en la última ejecución verde.
2. Descarga el artefacto **FondoSalario-windows** (un `.zip` con `FondoSalario.exe`).
3. Copia el `.exe` a cualquier carpeta y haz doble clic. No necesita instalación ni internet.

Si Windows muestra el aviso «SmartScreen», pulsa *Más información → Ejecutar de todas formas*
(el ejecutable no está firmado digitalmente).

Para compilarlo a mano en Windows: `pip install pyinstaller` y
`pyinstaller --onefile --windowed --name FondoSalario --paths src src/fondo_salario/__main__.py`.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

Estructura: `domain` (reglas de cálculo, sin dependencias), `persistence` (SQLite), `export` (Excel),
`importers`, `ui` (tkinter). Diseño completo en [`docs/SPEC.md`](docs/SPEC.md).

## Privacidad

Este repositorio no contiene datos reales ni documentos externos, y `.gitignore` bloquea `.xlsx`, `.docx`,
`.csv` y `.fsal` para que los datos de los trabajadores (nombres y carnés de identidad) no se suban por accidente.
