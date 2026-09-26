---
name: django-architecture
description: "Use when designing, implementing, or refactoring Django models, views, forms, URLs, templates, migrations, or app boundaries in Cafena. Follow the existing Django-first modular architecture instead of introducing unnecessary layers or patterns."
---

# Django Architecture

## Project shape

Cafena uses Django 6.x with Python 3.12, server-rendered templates, Bootstrap 5, Chart.js, and domain apps named `dashboard`, `products`, `sales`, `expenses`, and `inventory`. The project configuration lives under `kaboha_finance/` and the dashboard is mounted at the project root.

## Architectural rules

- Keep business functionality inside the existing domain app that owns it.
- Follow the established CRUD pattern: `list`, `create`, `edit`, and `delete` views with `render`, `redirect`, and `get_object_or_404`.
- Use `ModelForm` for model-backed forms and preserve explicit URL names.
- Prefer Django ORM expressions, aggregates, filters, and relationships over duplicated Python-side data processing.
- Reuse existing helpers and calculated model properties before adding services or abstractions.
- Do not introduce a service layer, API layer, repository pattern, or asynchronous architecture unless the requirement genuinely needs it.
- Keep templates under `templates/` and shared styling in `static/css/style.css`.
- Preserve historical names from Kaboha Finance; do not perform broad renames as part of unrelated changes.

## When to create a new Django app

Do not create an app for every small feature, screen, or model. First evaluate whether the functionality has a meaningful and stable domain boundary.

Create a new app only when the decision is supported by most of these criteria:

- **Límite de dominio:** the functionality represents a distinct business capability with its own vocabulary and rules.
- **Cohesión:** its models, workflows, views, and tests belong together more naturally than in an existing app.
- **Dependencias:** its dependencies on other apps are explicit and do not create a circular or highly coupled design.
- **Reutilización:** the capability could be reused by more than one workflow or needs an independent public boundary.
- **Tamaño del módulo:** the feature is large enough to justify separate migrations, tests, navigation, and maintenance.
- **Ciclo de vida de los datos:** its records have a lifecycle, retention, or audit trail different from the owning app's data.
- **Separación de responsabilidades:** keeping it separate makes ownership, authorization, and business rules clearer.
- **Impacto sobre otras apps:** integration points, inventory effects, financial effects, and migration risks are understood.

Keep a feature inside an existing app when it is a small, cohesive extension of that app's current entities and lifecycle. For future agricultural functionality, decide app boundaries only after the finca, lote, cultivo, cosecha, beneficio, café verde, and traceability relationships have been designed; do not create placeholder apps or models in advance.

## Change workflow

1. Identify the owning app and the nearest code path that directly controls the behavior.
2. Inspect related models, forms, URLs, templates, and tests.
3. State the data and request-flow impact before editing.
4. Make the smallest compatible change.
5. Create migrations for every model schema change.
6. Define and prepare focused test cases before implementation; execute and update them after implementation.
7. Run the affected tests, `python manage.py check`, and migration checks when relevant.

## Data and request safety

- Use `get_object_or_404` for object lookups driven by URL parameters.
- Validate all user input through Django forms or model validation.
- Preserve CSRF protection in POST forms.
- Avoid changing public route names without a compatibility plan.
- Avoid queries in templates when the same data can be prepared in the view.
- Keep timezone handling consistent with `America/Bogota` and Django's timezone utilities.

## Completion checklist

- Ownership remains clear between apps.
- Public APIs, URLs, and template context names remain compatible unless intentionally changed.
- Schema changes include migrations.
- The implementation follows local patterns and does not add needless complexity.
- Tests and Django system checks pass.
