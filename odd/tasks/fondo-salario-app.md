# Feature: fondo-salario-app

Objective: offline desktop app to distribute the unexecuted salary fund (Acuerdo 10199/2025) among workers and export to Excel.
Spec: `docs/SPEC.md`. Roles: Claude plans/reviews/verifies; opencode implements one task at a time on branch `feat/fondo-salario-app`.
Delivery strategy: ask-on-risk; push of branches is authorized by the user, merge to main is the user's call.
Route: delegated direct (external implementer: opencode), parent verifies each task with pytest + diff read.

## Tasks
- [x] T1 Scaffold (pyproject, package, pytest) + domain models, scales, calculation with tests (RED first) — 41 tests pass, ruff clean (RED observed before implementation)
- [ ] T2 SQLite persistence (.fsal projects, migrations) + tests
- [ ] T3 Excel export (4 sheets) + tests reading the generated workbook
- [ ] T4 Importers (workers CSV/XLSX, legacy structure sheet) + tests with synthetic data
- [ ] T5 tkinter UI (presenters tested without display) + manual smoke run
- [ ] T6 README (Spanish user guide), PyInstaller notes, final verification

## Acceptance
- Sum of area amounts == total_amount; sum of worker amounts == total_amount (exact, cents).
- Pre-nomina lists every worker, 0.00 for non-paid.
- No personal data or external documents in the repo.

## Open assumptions (flag to user)
- Seniority bands (equal 7-year bands) and time evaluation rule are inferred; legacy Excel data suggests different seniority thresholds. Editable in Parametros.
- Weights 40/25/15/20 taken from the legacy Excel; the law does not fix them.

## Progress / evidence
(none yet)
