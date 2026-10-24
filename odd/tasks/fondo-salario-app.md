# Feature: fondo-salario-app

Objective: offline desktop app to distribute the unexecuted salary fund (Acuerdo 10199/2025) among workers and export to Excel.
Spec: `docs/SPEC.md`. Roles: Claude plans/reviews/verifies; Claude implements (opencode was dropped by the user) on branch `feat/fondo-salario-app`.
Delivery strategy: ask-on-risk; push of branches is authorized by the user, merge to main is the user's call.
Route: inline (user asked the parent to implement everything); each task verified with pytest + ruff.

## Tasks
- [x] T1 Scaffold (pyproject, package, pytest) + domain models, scales, calculation with tests (RED first) — 41 tests pass, ruff clean (RED observed before implementation)
- [x] T2 SQLite persistence (.fsal projects, migrations) + tests — 6 tests pass
- [x] T3 Excel export (4 sheets) + tests reading the generated workbook — 7 tests pass (60 total)
- [x] T4 Importers (workers CSV/XLSX, legacy structure sheet) + tests with synthetic data — 6 tests pass; smoke-tested locally on the legacy sheet (21 areas, 72 positions)
- [x] T5 tkinter UI (presenters tested without display) + manual smoke run — controller tests (71 total) + Xvfb smoke run: tabs refresh, totals match, dialogs open
- [x] T6 README (Spanish user guide), PyInstaller notes, final verification — clean-venv install: 71 tests pass, ruff clean, no personal data tracked

## Iteration 2 (user feedback after testing on the target Windows PC)
Users are elderly: big fonts/buttons, simple flow. Local test env: `.venv` + Xvfb screenshots (+ wine available).
- [x] T7 "Vacantes a distribuir" per position (None = all vacancies) in domain, SQLite v2 migration, Excel, UI form; fix legacy structure import (column D = vacancies used for the amount, was imported as approved with 0 vacancies -> nothing distributed) — 84 tests pass; real legacy file now yields unexecuted 320,220, percentages sum 100
- [x] T8 Explicit save model: changes pending until Guardar; ask to save on close; unsaved indicator — store autosave=False + save/discard, close prompt, unsaved indicator; window tests under Xvfb (96 tests)
- [x] T9 UI redesign for elderly users: larger fonts, visible toolbar (Nuevo/Abrir/Guardar/Exportar) while keeping the Archivo menu, work-oriented layout, status bar — verified with Xvfb screenshots at 1366x680
- [x] T10 Import workers from the legacy "Dist.Monto x Trabajador" sheet (name, area, years, days, contribution, roman group when present); undefined group imported as 0 and flagged — 101 tests; on the real legacy file: 36 workers read (5 broken #REF! names reported), areas matched by name/containment/number, 12 incomplete flagged
- [x] T11 Release v0.1.3 published (main fast-forwarded to d9c93e1; tag build green incl. packaged-exe self-test)

## Iteration 3 (user's «Rafelito 3.docx»: new specification)
Source: weights 25/40/20/15 (resp/contrib/time/seniority); time = % of days worked over months*24 in 5 ranges
(ceil(5*ratio), 0 days -> no score); seniority <=5:1, 6-10:2, 11-15:3, 16-20:4, >20:5; contribution 5 Excepcional,
4 Bueno, 3 Satisfactorio, 2 Regular (1 not described); worker's right to collect must be identifiable (only those who
cover the vacant position's tasks); area amount -> workers by coef / sum of area coefs. Doc examples used as tests.
- [x] T12 New defaults (weights, seniority bands), time-score rule by % ranges; tests from the document's monthly example — 122 tests; document monthly example reproduced (15.50 points, 8,000 distributed)
- [x] T13 Schema v3: old default settings upgrade to the new ones; «restablecer» button; docs (SPEC, README) updated — 125 tests; v2 projects with old defaults are upgraded, customized ones untouched
- [x] T14 «Derecho a cobro»: clear column/filter/bulk toggle in Trabajadores, column in the Excel report, contribution labels — 130 tests; bulk grant/revoke, filter, Excel columns, contribution labels; parameters form fits 1366x680

## Iteration 4 (user: smart import = merge into existing data)
Branch `feat/merge-import`. Identify workers by CI or name, positions by area + position name. New records are added;
existing ones are joined: empty fields are completed automatically, differing values are asked ONE BY ONE with an
«accept all the rest» shortcut (plus summary dialog: review one by one / accept all / only add what is missing).
Nothing is deleted. Applies to Excel and CSV imports (workers and areas/positions).
- [x] T15 Pure merge planner (`importers/merge.py`): match, fills, conflicts, resolve(mode, ask) + tests — 22 planner tests
- [x] T16 Controller: plan_*/apply_import (import_workers/import_structure become thin wrappers) + tests — 160 tests
- [x] T17 Dialogs: summary + one-by-one conflict dialog with «accept all the rest»; wire both import buttons; window tests
- [x] T18 Docs + full verification (168 tests); merged to main and released as v0.1.4

## Iteration 5 (user: imports must be as intelligent as possible; real file «Raflito 4.xlsx» was not recognized)
Branch `fix/import-creates-areas`. Import whatever matches in any table: header row anywhere, any sheet, flexible
column names, area optional (join ids by name), hierarchical staffing roster (areas/positions/workers) usable from both
import buttons, fuzzy area matching, honest report of what was read/ignored. Follows the review advisories.
- [x] T19 Roster reader (workers) + create missing areas for any file + honest "nothing new" message — 171 tests
- [x] T20 Smart header detection (any sheet/row, flexible names, optional area, notes), roster structure (areas + positions), fuzzy area matching, report of used columns; tests; real-file check — 176 tests; real roster: 86 workers/22 areas/70 positions read, 17 of 21 areas matched to existing ones
- [x] T20b Review advisories fixed (name-of-area columns, roster footers/vacants, strict structure matching), plain areas table on its own sheet/CSV, wrong-file hints — 182 tests
- [x] T21 Merged to main and released as v0.1.5

## Iteration 6 (user: generic/smart import keeps failing -> fixed structure, add-only)
Decision (user): the import has ONE predefined structure, the same as the app's tables; the file must comply, otherwise
the import stops with a clear message. A new record is added; existing ones are never touched (no join, no questions).
The Excel report also carries both tables in that exact structure (export -> import round trip) and a blank template can
be saved. Replaces the heuristic readers (legacy, roster, fuzzy matching) and the merge dialogs.
Branch `feat/strict-import`.
- [x] T22 `importers/table.py`: structure constants, template writer, strict readers + add-only plans, tests
- [x] T23 Controller + UI: import buttons, template buttons, summary confirm; remove old importers/dialogs; tests
- [x] T24 Excel report: «Trabajadores» and «Áreas y cargos» sheets in import structure; round-trip test; README/SPEC
- [x] T24b «Vaciar trabajadores» / «Vaciar todo» (confirm, keeps parameters) + review advisories (zeros in template IDs, robust numbers, same name different ID) — 144 tests
- [x] T25 (verified: 165 tests, ruff, e2e script in clean project, selftest; released as v0.2.0) Verify (pytest, ruff, real flow incl. export->import in a clean project), merge + release (needs user OK)

## Acceptance
- Sum of area amounts == total_amount; sum of worker amounts == total_amount (exact, cents).
- Pre-nomina lists every worker, 0.00 for non-paid.
- No personal data or external documents in the repo.

## Open assumptions (flag to user)
- RESOLVED by «Rafelito 3»: weights 25/40/20/15, seniority bands and the time-worked ranges now come from the document.
- DECIDED by user: contribution 1 = no bonus (paid 0.00, excluded from the distribution); new/imported workers start WITHOUT the right to collect; no field for the vacant position covered.

## Progress / evidence
(none yet)
