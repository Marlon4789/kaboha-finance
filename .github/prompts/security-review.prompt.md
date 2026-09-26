---
description: "Perform a focused security review of a Cafena endpoint, feature, export, form, template, or configuration change."
name: "Security Review Cafena"
agent: "cafena-security"
tools: [read, search, execute]
argument-hint: "Describe the endpoint, files, or feature to review"
---

Perform a focused security review of the requested Cafena scope.

Trace:
- actor and authorization decision
- request validation and CSRF
- user-controlled data through ORM queries and templates
- sensitive data returned in pages, logs, filenames, CSV, or XLSX
- environment and dependency risks

Report confirmed findings first with severity, location, impact, and remediation. Run relevant tests and `python manage.py check`. Separate hardening suggestions from exploitable defects.
