---
description: "Plan and implement a new Cafena Django module or domain feature while preserving existing architecture and naming."
name: "Create Cafena Module"
agent: "cafena-architect"
tools: [read, search, edit, execute, todo]
argument-hint: "Describe the module, business entity, workflow, and acceptance criteria"
---

Act as the Cafena principal architect and handle the requested module or domain feature through the following mandatory stages, in order:

1. ANALIZAR
2. DISEÑAR
3. PROPONER ARQUITECTURA
4. APROBACIÓN ARQUITECTÓNICA
5. IMPLEMENTAR
6. TESTS
7. SEGURIDAD
8. UI/UX
9. REVISIÓN FINAL

## Gate before implementation

Before editing, inspect existing models, relationships, migrations, views, forms, URLs, templates, tests, and relevant skills. Confirm that the requested entity or behavior does not already exist. Define the owning app, business rules, workflow, schema impact, source-of-truth data, derived data, security implications, and test strategy.

Produce the design and architecture proposal first. Do not begin an important implementation until the architectural proposal has been explicitly approved by the user. If approval has not been given, stop after the proposal and ask for it.

## Implementation and validation

After approval, follow the existing Django CRUD and Bootstrap patterns. Preserve existing URLs, names, and historical `kaboha_finance` identifiers unless explicitly asked to rename them. Prepare focused test cases from the design, then implement with migrations when schema changes are required.

After implementation, execute the tests, perform the security review, validate UI/UX consistency, and complete a final regression review. Keep all user-facing copy in Colombian Spanish. Report each stage, files changed, decisions, tests, and remaining risks.
