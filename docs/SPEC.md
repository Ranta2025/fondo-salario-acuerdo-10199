# Specification: salary-fund payment app (Acuerdo 10199/2025)

Offline desktop app (Python 3.10+, tkinter, SQLite, openpyxl) that distributes the
unexecuted salary fund among workers of a budgeted unit and exports the evidence to Excel.

Legal context: Acuerdo 10199 of the Council of Ministers (Gaceta Oficial Extraordinaria No. 45,
11-Aug-2025) lets budgeted units redistribute unexecuted salary-fund amounts as salary. The
agreement does NOT fix the distribution criteria: each unit approves an internal regulation
(Consejo de Direccion + union + workers assembly). Therefore weights and scales are
configurable settings, never hard-coded constants in calculations.

## Conventions
- Code, identifiers, comments, docs: English. **UI strings: Spanish** (end users are Spanish-speaking), neutral register.
- Money: `decimal.Decimal`, quantized to cents. Never `float` for money.
- Conventional Commits. No AI attribution lines in commits.
- NEVER commit .xlsx/.docx/.csv/.sqlite or any real worker data (names, ID numbers). Tests use synthetic data only.
- Layered: `domain` has no imports from ui/persistence/export. Dependencies point inward.
- TDD: write the failing test first, then the code.

## Layout
```
pyproject.toml            # deps: openpyxl; dev extra: pytest, ruff
src/fondo_salario/
  domain/{models.py,scales.py,calculation.py}
  persistence/sqlite_repo.py
  export/excel_report.py
  importers/{workers.py,structure.py}
  ui/                      # tkinter; logic in presenters/view-models testable without a display
  __main__.py              # python -m fondo_salario
tests/
```

## Domain model
- `Settings`: `total_amount` (real money to distribute), `months_paid` (int >=1), `expected_days_per_month` (24),
  `weights` {time:0.40, responsibility:0.25, seniority:0.15, contribution:0.20} (must sum to 1.00),
  `responsibility_bands`, `seniority_bands`.
- `Area(id, name, order)`.
- `Position(id, area_id, name, approved, vacant, temp_vacant, salary, months_unexecuted)`.
- `Worker(id, full_name, national_id, area_id, position_name, salary_group 1..25, seniority_years 0..60,
  days_worked, contribution 1..5, eligible: bool=True)`.
  `days_worked` is the total days worked in the paid period (max = expected_days_per_month * months_paid).

## Calculation (sheet 1: amount per area)
1. `vacancies = vacant + temp_vacant`
2. `unexecuted = vacancies * salary * months_unexecuted` per position; area unexecuted = sum; grand total = sum of areas.
3. `area_pct = area_unexecuted / grand_total * 100` (all percentages must sum to exactly 100; verification).
4. `area_amount = area_pct/100 * settings.total_amount`. Rounded to cents with the **largest-remainder method** so that
   the sum of area amounts equals `total_amount` exactly.
5. If grand_total == 0: every amount is 0 and a warning is produced (no division by zero).

## Calculation (sheet 2: amount per worker)
Each indicator is evaluated 1..5:
- time: `ratio = days_worked / (expected_days_per_month * months_paid)`; `eval = 0` if days_worked == 0 else `clamp(round_half_up(5*ratio), 1, 5)`.
- responsibility: salary group (I..XXV, stored as int 1..25) mapped through `responsibility_bands`.
  Default bands (5 equal): 1-5 -> 1, 6-10 -> 2, 11-15 -> 3, 16-20 -> 4, 21-25 -> 5.
- seniority: years mapped through `seniority_bands`. Default (5 equal over 1..35): 0-7 -> 1, 8-14 -> 2, 15-21 -> 3, 22-28 -> 4, 29+ -> 5.
- contribution: entered by the boss, integer 1..5.

`coefficient = sum(weight_i * eval_i)` (Decimal). Non-eligible workers (`eligible=False`) get coefficient 0 and amount 0.
`worker_amount = coefficient / sum(coefficients of eligible workers in the area) * area_amount`, rounded with
largest-remainder per area so that the worker amounts in an area sum exactly to `area_amount`.
Warnings (never exceptions): area with amount > 0 and no eligible workers (money left undistributed);
weights not summing to 1; worker with missing/invalid data; total distributed != total_amount.
A worker's area comes from `area_id`. Required verification: sum of all worker amounts == total_amount.

## Persistence
One project = one SQLite file (extension `.fsal`). Menu: New / Open / Save as. Tables: settings (single row),
areas, positions, workers. Schema version in `PRAGMA user_version` with simple forward migrations.
Repository interface lives in `domain` (a Protocol); SQLite implementation in `persistence`.

## Excel export (openpyxl, values not formulas, A4 landscape, fit to 1 page wide, repeat header rows)
Sheets: `Hoja 1 - Montos por area` (per area: positions with columns 1..10 of the spec in the project README: approved, vacant,
temp vacant, vacant sum, salary, months, unexecuted amount, % of total, amount to pay; area totals; grand total row;
a "check: sum of % = 100" line), `Hoja 2 - Coeficientes` (per worker: name, ID, area, position, the 4 evaluations,
coefficient, area coefficient sum, amount; per-area subtotal; check line), `Pre-nomina` (ALL workers, full name +
national ID + area + amount, 0.00 for those who get nothing, total + check), `Parametros` (settings used, bands, weights, date).
Number format `#,##0.00`. Bold headers, borders, column widths set, no merged-cell tricks beyond titles.

## Importers (read user's own files at runtime; nothing external is stored in the repo)
- `workers.py`: CSV/XLSX with header aliases (nombre, ci/carne, area, cargo, grupo, antiguedad, dias, contribucion); returns rows + per-row errors.
- `structure.py`: best-effort import of areas/positions from the legacy sheet layout "Dist.Monto x area":
  col B = area number, col C = name, area header rows match `^\s*\d+\s*[.\-]`, position rows follow under the same B number,
  col D approved, col E salary, col G months. Tests build a synthetic workbook with that layout.

## UI (tkinter/ttk, Spanish)
Tabs: Parametros | Areas y cargos | Trabajadores | Resultados. Add/edit/delete dialogs; search + area filter in workers;
Resultados recalculates live and shows warnings in red/amber; buttons "Exportar a Excel", "Importar trabajadores".
Confirm before deleting. Deleting an area with workers is blocked or reassigns (ask). Keyboard-friendly, works at 1366x768.
Packaging notes (PyInstaller one-file for Windows) go in README.
