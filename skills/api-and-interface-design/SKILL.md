---
name: api-and-interface-design
description: Use when designing any interface others will call - REST/HTTP APIs, library functions, CLI commands, configuration schemas, tool definitions. Covers naming, shape, errors, versioning, and the make-the-easy-path-correct principle.
category: software
hint: design clean APIs and interfaces
---
# API & Interface Design

An interface is a promise you must keep forever (or pay to break). Design for the CALLER's mental model, not your implementation's convenience.

## Universal principles

1. **Easy things easy, wrong things hard.** The obvious way to call it should be the correct way. Required things are required parameters; dangerous things demand explicit opt-in (`force=true`), never defaults.
2. **Good defaults, few knobs.** Every parameter is a question you're forcing every caller to answer. Add options when real callers need them, with defaults that make the simple call `do_the_thing(input)`.
3. **Be conservative in what you emit, liberal-but-explicit in what you accept.** Emit one canonical format. Accept reasonable variants only if you document them; silently guessing intent breeds heisenbugs.
4. **Consistency beats local optimality.** Same parameter order, same naming scheme, same error shape across every endpoint/function of the surface. A caller who's used one should correctly guess the next.
5. **Don't leak the implementation.** Names and shapes reflect the domain (`order.cancel()`), not the storage (`orders_table_row.set_status_flag(3)`). What you leak, callers depend on, and then you can't change it (Hyrum's Law: every observable behavior will be depended on by someone).

## Function/library interfaces

- Inputs: take the narrowest type that expresses the need. Avoid boolean flags that change behavior (`export(data, true, false)` — unreadable); use enums or separate functions.
- Outputs: return one coherent thing. Don't return `None`-or-value when you can return an empty collection; don't encode errors as magic values (−1, "") — raise/return proper errors.
- No hidden globals: same inputs → same behavior. Side effects (writes, network) belong in obviously-named functions.
- Make the common composition chainable: functions that take and return the same shape compose; functions that mutate in place and return nothing don't.

## HTTP/REST APIs

- Nouns for resources (`/orders/123`), plural, kebab/lower; verbs from the METHOD: GET (read, no side effects, cacheable), POST (create/act), PUT (replace idempotently), PATCH (partial update), DELETE.
- Status codes carry the first level of meaning: 200/201/204 success; 400 caller's request malformed; 401 not authenticated; 403 authenticated but forbidden; 404 no such resource; 409 conflict; 422 semantically invalid; 429 slow down; 5xx OUR fault. Never 200-with-error-in-body.
- Error body: machine-readable code + human message + which field failed: `{"error": {"code": "invalid_email", "message": "...", "field": "email"}}`.
- Paginate anything unbounded (cursor beats offset for changing data). Filter/sort via query params. Version the API (`/v1/`) and version breaking changes only — additive changes (new optional fields) shouldn't break well-behaved clients.
- Idempotency: retries happen; POSTs that charge money accept an idempotency key.

## CLI interfaces

- `tool verb --flag value` shape; long flags spelled out (`--output`), short aliases for the frequent few (`-o`).
- Read from stdin/write to stdout by default so it pipes; errors and progress to stderr; exit 0 on success, nonzero on failure.
- `--help` on every level, `--dry-run` for anything destructive, and prompt-before-destroying unless `--yes`.

## Evolving an interface

- Additive changes are safe; renames/removals/meaning-changes are breaking. To break: introduce the new form, deprecate the old with a warning and a date, migrate callers, then remove. Never repurpose an existing name to mean something different — that's the cruelest break, because nothing errors.

## The design test

Write the CALLING code first — the README example, the curl command — before implementing. If the call site reads awkwardly, redesign now; it's the cheapest moment you'll ever get.
