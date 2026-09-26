---
name: code-review
description: "Use when reviewing Cafena changes, pull requests, bug fixes, migrations, dashboard behavior, exports, or UI updates. Prioritize concrete bugs, data-integrity risks, security issues, regressions, and missing tests over style commentary."
---

# Cafena Code Review

## Review posture

Review changes as a senior engineer responsible for a Django finance application. Findings come first and must be actionable, evidence-based, and ordered by severity. Do not request broad refactors when a focused correction is sufficient.

## Review order

1. Data loss, corruption, incorrect financial totals, or broken migrations.
2. Authorization, CSRF, injection, secret exposure, and unsafe exports.
3. Runtime errors, broken URLs, missing dependencies, and incompatible schema changes.
4. Incorrect month boundaries, stale derived summaries, negative stock, zero division, or timezone errors.
5. Regressions in forms, templates, responsive behavior, and Spanish user-facing workflows.
6. Missing focused tests and maintainability concerns.

## Cafena-specific checks

- Sales totals use sale items and quantity/unit price consistently.
- Expenses are filtered by the intended date and category.
- Profit and margin handle zero sales and negative results correctly.
- Month selectors accept valid `YYYY-MM` values and reject unavailable or future periods.
- Monthly summaries refresh from source transactions and remain unique by year/month.
- Inventory distinguishes bags, kilos molidos, kilos pergamino, sold amounts, and available amounts.
- Exports contain the selected month, correct totals, usable formatting, and no unintended fields.
- Existing route names, app boundaries, legacy identifiers, and migrations are not changed casually.
- Templates preserve Spanish labels, accessible controls, and responsive layout.

## Evidence and validation

- Trace each finding to a concrete file and behavior.
- Read the relevant implementation and neighboring tests before concluding.
- Run the narrowest useful test first, then related tests and `python manage.py check`.
- Inspect migration state when models change.
- Distinguish confirmed defects from open questions and residual test gaps.

## Finding format

For each issue, state:

- severity: blocker, high, medium, or low
- location: file and relevant symbol or line
- impact: what can go wrong for users or data
- recommendation: the smallest credible fix

If no issues are found, say so clearly and list remaining test gaps or residual risks. Keep the summary secondary to findings.
