---
name: ui-ux
description: "Use when designing or modifying Cafena templates, forms, dashboard cards, charts, navigation, responsive layouts, or Spanish user-facing copy. Preserve the existing Bootstrap-based visual language and prioritize clear business workflows."
---

# Cafena UI/UX

## Existing visual system

The application uses server-rendered Django templates, Bootstrap 5, shared styles in `static/css/style.css`, Chart.js, and Spanish Colombian copy. The base layout is `templates/base.html`.

## Design principles

- Keep the interface minimal, organized, and oriented to daily business decisions.
- Use clear hierarchy: title, context, label, value, note, and status.
- Keep dashboard KPI cards compact, scannable, and visually distinct with readable contrast.
- Use stronger, purposeful colors for indicators without sacrificing accessible text contrast.
- Keep charts compact enough to support scanning; avoid oversized chart containers.
- Use collapsible sections for secondary indicators and monthly history when that reduces visual density.
- Make month selectors obvious and compact; show Spanish month names while preserving machine-readable `YYYY-MM` values.
- Keep forms in Spanish, with labels and help text that explain bags, kilos molidos, and kilos pergamino.
- Reuse existing Bootstrap classes and shared CSS before adding isolated styles.
- Ensure layouts work on narrow screens without clipped text, overlapping controls, or horizontal overflow.

## Interaction guidance

- Use standard form controls for filters and submit month changes predictably.
- Preserve visible feedback for empty states, validation errors, and successful navigation.
- Use familiar icons only when the project already includes the relevant icon set; keep text labels for actions that may be ambiguous.
- Do not hide essential financial values inside decorative interactions.
- Keep download actions close to the corresponding monthly record.

## Validation checklist

- Review the affected template with realistic long product names and zero-value metrics.
- Check desktop and mobile layout behavior.
- Confirm all visible copy is Spanish and terminology is consistent.
- Confirm charts and cards do not resize unpredictably.
- Verify keyboard-friendly controls, labels, focus states, and readable contrast.
- Run the relevant Django tests and inspect the rendered path when possible.
