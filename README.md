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

## Abrirlo y compilarlo en tu PC (Linux)

Necesitas Python 3.10 o superior **con tkinter**:

| Sistema | Cómo tener tkinter |
|---|---|
| Ubuntu / Debian | `sudo apt install python3-tk python3-venv` |
| Homebrew (Linux/macOS) | `brew install python-tk` |
| Windows | ya viene con el instalador de python.org |

### Abrir el programa (lo más rápido)

```bash
./abrir.sh                     # la primera vez crea el entorno e instala; después abre directo
./abrir.sh mi-proyecto.fsal    # abre directamente un proyecto guardado
./probar.sh                    # (opcional) pruebas + análisis de código
```

Si todavía no tienes la carpeta:

```bash
git clone https://github.com/Ranta2025/fondo-salario-acuerdo-10199.git
cd fondo-salario-acuerdo-10199
git switch feat/fondo-salario-app    # el código vive en esta rama hasta que se fusione en main
./abrir.sh
```

Si algo falla, el script te dice qué falta (por ejemplo tkinter). Lo de abajo explica lo mismo paso a paso.

**1. Preparar el entorno (una sola vez)**

```bash
cd fondo-salario-acuerdo-10199
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip install -e ".[dev]"
```

**2. Abrir el programa** (usa siempre el código actual, sin compilar)

```bash
.venv/bin/python -m fondo_salario                    # te pregunta si abrir o crear un proyecto
.venv/bin/python -m fondo_salario mi-proyecto.fsal   # abre directamente un proyecto
```

**3. Comprobar que todo funciona**

```bash
.venv/bin/pytest                # 100+ pruebas; las de la ventana se saltan si no hay pantalla
xvfb-run -a .venv/bin/pytest    # (opcional) con una pantalla virtual, para ejecutarlas todas
.venv/bin/ruff check src tests
```

**4. Compilar un ejecutable para Linux** (carpeta `dist/FondoSalario/`)

```bash
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller --onedir --windowed --name FondoSalario --paths src src/fondo_salario/__main__.py
dist/FondoSalario/FondoSalario                       # ejecutarlo
dist/FondoSalario/FondoSalario --selftest            # abre y cierra la ventana: comprueba que arranca
```

> **El `.exe` de Windows no se puede compilar desde Linux.** PyInstaller solo genera ejecutables
> del sistema donde se ejecuta. Para Windows se compila automáticamente en GitHub (ver abajo) y no hace falta
> Windows para obtenerlo. Probarlo con Wine/Lutris no es fiable: usa el paso 2, que es lo mismo que el `.exe`.

### Windows: programa listo (sin instalar Python)

Cada subida al repositorio compila la aplicación en un Windows real con GitHub Actions
(`.github/workflows/windows.yml`), tras pasar las pruebas, y la empaqueta en `FondoSalario-windows.zip`.
Se descarga desde la última [release](../../releases/latest) (o desde *Actions → artefacto FondoSalario-windows*).

1. Extrae **toda** la carpeta del `.zip` (clic derecho → Extraer todo).
2. Abre la carpeta `FondoSalario` y haz doble clic en `FondoSalario.exe`. No necesita instalación ni internet.

Se entrega como carpeta y no como un único `.exe` porque los ejecutables de un solo archivo sin firmar son
borrados con frecuencia por el antivirus. Aun así, al no estar firmado digitalmente, Windows puede mostrar
SmartScreen (*Más información → Ejecutar de todas formas*); `packaging/LEEME.txt`, incluido en el zip,
explica qué hacer si el antivirus lo pone en cuarentena.

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
