---
name: database-design
description: "Use when changing Cafena models, relationships, constraints, indexes, migrations, aggregation queries, or database behavior. Protect transaction data and keep SQLite and PostgreSQL compatibility."
---

# Database Design

## Current persistence model

Cafena uses SQLite locally and supports PostgreSQL through environment configuration. Core entities are `Product`, `Sale`, `SaleItem`, `ExpenseCategory`, `Expense`, `InventoryEntry`, and `MonthlySummary`.

## Design rules

- Inspect existing models and migrations before adding an entity or field.
- Do not duplicate a value already represented by a relationship or calculated property.
- Preserve referential integrity and evaluate deletion behavior before changing foreign keys.
- Use clear `ForeignKey` relationships and stable `related_name` values.
- Keep `Meta.ordering`, `verbose_name`, and `verbose_name_plural` consistent with the existing app.
- Add constraints for invariants that must hold at the database boundary, while keeping validation in forms for user feedback.
- Choose numeric field types appropriate for money and quantities; do not silently change existing precision or semantics.
- Keep date and month filtering timezone-aware and compatible with Django ORM behavior on both supported databases.

## Migration workflow

1. Compare the model state with the latest migration state.
2. Make the smallest model change required.
3. Run `python manage.py makemigrations` and inspect the generated migration.
4. Check dependencies and migration ordering.
5. Run `python manage.py migrate` against the configured development database.
6. Run `python manage.py showmigrations` or the project's migration checks when diagnosing schema drift.
7. Test both empty and populated data paths for changed queries.

Never edit the database schema manually as a substitute for a Django migration. Do not delete or recreate migrations to hide a conflict without understanding existing applied state.

## Aggregates and derived data

- Treat sales, expenses, and inventory entries as source transactions.
- Treat `MonthlySummary` as recalculable derived data keyed by `(year, month)`.
- Use `update_or_create` or an equivalent uniqueness-safe operation for monthly summaries.
- Handle `NULL` aggregate results with explicit defaults.
- Guard divisions by zero in margin, averages, and ratios.
- Keep stock calculations transparent: additions, sales, and available stock should be distinguishable.

## Completion checklist

- No redundant entity or field was introduced.
- Relationships and delete behavior were reviewed.
- A migration exists for every schema change.
- SQLite and PostgreSQL behavior is considered.
- Data integrity, empty aggregates, and duplicate-period behavior are tested.
