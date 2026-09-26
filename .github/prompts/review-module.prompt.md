---
description: "Review a Cafena module or feature for bugs, data-integrity risks, regressions, security issues, and missing tests."
name: "Review Cafena Module"
agent: "cafena-architect"
tools: [read, search, execute]
argument-hint: "Provide the module, files, feature, or change to review"
---

Review the requested Cafena module or change as a senior Django code reviewer, applying the `code-review` skill as specialized review guidance.

Prioritize findings in this order:
1. Financial data corruption, data loss, and broken migrations.
2. Authorization, CSRF, injection, secret exposure, and unsafe exports.
3. Runtime failures, broken URLs, missing dependencies, and schema incompatibilities.
4. Incorrect monthly boundaries, stale summaries, stock calculations, zero division, or timezone errors.
5. UI regressions and missing focused tests.

For every finding, include severity, file/symbol location, impact, and the smallest credible fix. Run the narrowest useful checks before concluding. If there are no findings, state that clearly and list residual test gaps.
