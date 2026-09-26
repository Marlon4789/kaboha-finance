---
description: "Review and improve Cafena UI/UX for clarity, Spanish copy, accessibility, responsive behavior, dashboard density, and Bootstrap consistency."
name: "Review Cafena UI"
agent: "cafena-frontend"
tools: [read, search, edit, execute]
argument-hint: "Describe the screen, template, form, or UI issue to review"
---

Review the requested Cafena interface.

Inspect the affected template, base layout, shared CSS, view context, and nearby tests. Check:
- hierarchy and scannability for a daily business user
- Spanish labels, help text, and empty/error states
- keyboard labels, focus, contrast, and readable controls
- mobile layout, long text, zero values, and overflow
- dashboard card density, chart sizing, and existing Bootstrap consistency

Make only focused UI changes that preserve backend contracts. Validate with relevant tests and system checks, and report any visual checks that require a browser.
