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
- [ ] T11 Release the new Windows build (needs user OK for the tag) — build 322779e passed on windows-latest incl. packaged-exe self-test; waiting for user to approve the release tag

## Iteration 3 (user's «Rafelito 3.docx»: new specification)
Source: weights 25/40/20/15 (resp/contrib/time/seniority); time = % of days worked over months*24 in 5 ranges
(ceil(5*ratio), 0 days -> no score); seniority <=5:1, 6-10:2, 11-15:3, 16-20:4, >20:5; contribution 5 Excepcional,
4 Bueno, 3 Satisfactorio, 2 Regular (1 not described); worker's right to collect must be identifiable (only those who
cover the vacant position's tasks); area amount -> workers by coef / sum of area coefs. Doc examples used as tests.
- [x] T12 New defaults (weights, seniority bands), time-score rule by % ranges; tests from the document's monthly example — 122 tests; document monthly example reproduced (15.50 points, 8,000 distributed)
- [x] T13 Schema v3: old default settings upgrade to the new ones; «restablecer» button; docs (SPEC, README) updated — 125 tests; v2 projects with old defaults are upgraded, customized ones untouched
- [x] T14 «Derecho a cobro»: clear column/filter/bulk toggle in Trabajadores, column in the Excel report, contribution labels — 130 tests; bulk grant/revoke, filter, Excel columns, contribution labels; parameters form fits 1366x680

## Acceptance
- Sum of area amounts == total_amount; sum of worker amounts == total_amount (exact, cents).
- Pre-nomina lists every worker, 0.00 for non-paid.
- No personal data or external documents in the repo.

## Open assumptions (flag to user)
- RESOLVED by «Rafelito 3»: weights 25/40/20/15, seniority bands and the time-worked ranges now come from the document.
- Contribution score 1 has no descriptor in the document (only 5, 4, 3, 2): shown as the plain number.

## Progress / evidence
(none yet)
