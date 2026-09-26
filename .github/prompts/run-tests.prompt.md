---
description: "Run the appropriate Cafena Django tests and system checks for a requested module, feature, or regression."
name: "Run Cafena Tests"
agent: "cafena-qa"
tools: [read, search, execute]
argument-hint: "Specify the app, feature, failing test, or validation scope"
---

Validate the requested Cafena scope.

1. Inspect the affected app and existing test modules.
2. Run the narrowest relevant test command first.
3. If it passes, run related tests and `python manage.py check`.
4. For model changes, inspect migration state and run migration checks.
5. Report exact commands, outcomes, failures, and residual risks.

Do not hide failures or change production code unless the user explicitly asks for a fix.
