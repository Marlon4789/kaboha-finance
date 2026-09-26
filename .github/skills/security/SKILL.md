---
name: security
description: "Use when implementing or reviewing Cafena authentication, authorization, forms, views, exports, templates, database queries, environment configuration, or user-controlled data. Apply Django security practices without exposing business data or secrets."
---

# Cafena Security

## Required protections

- Never commit secrets, credentials, tokens, private keys, or production database details.
- Keep secrets in environment configuration and avoid printing them in logs or responses.
- Preserve Django CSRF protection on every state-changing form.
- Validate user input with Django forms and model validation.
- Use ORM queries and parameters; never construct SQL or HTML from untrusted strings.
- Escape user-controlled values in templates; use `|safe` only for deliberately generated, validated data such as serialized chart JSON.
- Review authorization before exposing sales, expenses, inventory, dashboard, admin, or export data.
- Avoid leaking sensitive information through error responses, filenames, query parameters, or exports.
- Use `get_object_or_404` and validate route parameters before accessing records.
- Consider ownership and role boundaries before adding new users or permissions.

## Export and reporting safety

- Ensure export endpoints only return the requested period and intended columns.
- Avoid formula injection when writing spreadsheet cells from user-controlled text.
- Keep XLSX dependency handling explicit and do not turn import failures into silent empty exports.
- Do not expose internal model fields or secrets in CSV/XLSX output.

## Data and configuration review

- Check `.env` handling and confirm sensitive files remain ignored.
- Review changes to `settings.py`, URL exposure, admin registration, and debug behavior.
- Use timezone-aware dates for financial periods.
- Treat deletion and bulk operations as high risk; require explicit POST and confirmation where applicable.

## Security validation checklist

- Identify the actor, resource, action, and authorization decision for every new endpoint.
- Verify CSRF, input validation, output escaping, and query safety.
- Test unauthenticated, unauthorized, malformed, and boundary requests when applicable.
- Run Django system checks and inspect dependency changes.
- Report residual risks and assumptions instead of declaring a feature secure without evidence.
