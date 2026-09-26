---
name: cafena-domain
description: "Use when implementing or reviewing Cafena business features involving products, sales, expenses, inventory, dashboard metrics, monthly summaries, exports, or the future agricultural and green-coffee domain. Apply the project's Spanish domain vocabulary and preserve the historical Kaboha Finance identifiers unless an explicit rename is requested."
---

# Cafena Domain

## Purpose

Use this skill to reason about Cafena's business rules before changing domain behavior. Cafena is a Django application for a specialty coffee business, with financial, sales, inventory, and profitability workflows.

## Future agricultural domain

The agricultural domain is a planned conceptual extension. Do not create Django models, migrations, apps, or functional workflows for it until the domain design is explicitly approved.

The future domain may include:

- finca, lote, cultivo, variedad, and siembra
- labores agrícolas, fertilización, and insumos
- enfermedades y plagas
- cosecha, producción, and café recolectado
- beneficio, café verde, and factor de rendimiento
- calidad and inventory of café verde
- venta de café verde
- production costs and end-to-end trazabilidad

Treat these concepts as a connected traceability domain. Before implementation, define their boundaries, relationships, units of measure, lifecycle, source-of-truth records, derived calculations, quality data, inventory movements, financial impacts, and permissions. Do not assume that a new concept belongs in `inventory` or `products` merely because it has a quantity or a price.

## Current domain

- `Product`: sellable coffee product with weight, sale price, production cost, profit, margin, and active status.
- `Sale`: sale header with date, payment method, optional customer, and notes.
- `SaleItem`: product, quantity, and unit price belonging to a sale.
- `ExpenseCategory`: expense classification.
- `Expense`: dated expense with category, description, and amount.
- `InventoryEntry`: dated inventory input with bags, kilos molidos, kilos pergamino, and notes.
- `MonthlySummary`: persisted monthly aggregate for sales, expenses, profit, and bags sold.
- `dashboard`: KPIs, monthly selector, charts, monthly history, and CSV/XLSX exports.

## Business rules

- Sales are calculated from sale items using quantity multiplied by unit price.
- Profit is sales minus expenses for the selected period.
- Margin is net profit divided by sales, expressed as a percentage; avoid division by zero.
- Bag stock is inventory bags added minus bags sold, without presenting negative stock as available stock.
- Monthly summaries are recalculable snapshots, not immutable source-of-truth transactions.
- Dashboard month selection must use `YYYY-MM` values and show Spanish month names.
- Future months must not appear as historical periods.
- Inventory must distinguish bags, kilos molidos, and kilos pergamino.
- Keep user-facing labels and form help text in Colombian Spanish.

## Implementation guidance

1. Read the existing model, form, view, template, and tests before adding a new domain concept.
2. Reuse existing relationships and calculated properties before adding redundant fields.
3. Keep source transactions authoritative; refresh derived monthly summaries when relevant data changes or the dashboard loads.
4. Preserve existing route names, model names, app names, and legacy `kaboha_finance` identifiers unless the user explicitly approves a rename.
5. Add focused tests for new calculations, period boundaries, empty data, and inventory totals.

## Completion checklist

- The change matches the domain model and existing relationships.
- Calculations handle empty and zero-value cases.
- Spanish labels are clear and consistent.
- Historical and future month behavior is preserved.
- Derived data can be refreshed without duplicating records.
- Relevant Django tests and system checks pass.
