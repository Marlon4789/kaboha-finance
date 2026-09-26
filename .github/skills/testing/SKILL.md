---
name: testing
description: "Use when adding, updating, debugging, or reviewing tests for Cafena. Cover Django models, forms, views, dashboard calculations, inventory totals, monthly summaries, exports, and regression cases with focused realistic tests."
---

# Cafena Testing

## Test priorities

Cafena currently has tests in `dashboard` and `inventory`. Preserve and extend that test culture for business-critical behavior.

Prioritize tests for:

- product, sale, sale item, expense, and inventory relationships
- form validation and Spanish labels/help text
- dashboard monthly selection and KPI calculations
- monthly summary refresh and uniqueness by year/month
- past-month visibility and future-month exclusion
- stock calculations for bags, kilos molidos, and kilos pergamino
- CSV/XLSX export content and dependency failure behavior
- permissions, CSRF, and invalid or missing object paths when views change

## Test style

- Use Django's `TestCase` and test client patterns already used in the repository.
- Create the smallest realistic fixtures needed for each behavior.
- Test observable behavior through models, response context, status codes, redirects, and rendered content.
- Include zero, empty, negative-profit, boundary-date, and multiple-period cases where calculations allow them.
- Avoid brittle assertions on unrelated HTML structure or implementation details.
- Keep tests independent and deterministic; do not rely on existing `db.sqlite3` data.

## Workflow

1. Read nearby tests and the implementation under change.
2. Add a regression test that expresses the required behavior.
3. Run the focused test module first.
4. Repair the implementation or test only when the failure identifies a real mismatch.
5. Run related app tests, then the full suite when practical.
6. Run `python manage.py check`; run migration checks for schema changes.

## Completion checklist

- The new or changed business rule has a focused test.
- Empty and boundary cases are covered where relevant.
- Tests do not depend on local production-like data.
- Targeted tests, broader tests, and system checks have been executed.
- Any untested risk is stated clearly rather than assumed away.
