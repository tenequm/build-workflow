<!-- Vendored from the polish skill v3.1.0 (tenequm/skills), then owned here.
     The runtime never fetches that repository: this file IS the brief. -->

# Lens: Side-Effect Gating

Closed-scope correctness check. Finds costly or irreversible side-effects that run before the checks meant to gate them. Does NOT judge whether business logic is correct - that is `/code-review`'s job.

- **Inventory the side-effects**: list every costly or irreversible side-effect introduced or relocated in the diff - charges/payments, DB writes/deletes, mutating external calls, file writes, notifications/emails, irreversible state changes
- **Inventory the gates**: for each side-effect, list the checks that must precede it - input validation (shape/type/range), authentication, authorization, precondition/existence checks, idempotency/dedup
- **Cross-check ordering**: flag any side-effect reachable on a control-flow path where a gate runs after it, or not at all. Trace ACROSS the middleware/handler boundary - middleware that fires a side-effect before calling `next()` is the prime suspect; the validation that should gate it often lives in the downstream handler
- **Missing rollback**: flag a committed side-effect with no compensation when a later step on the same request can still fail (e.g. charged, then the request errors)
- **Out of scope** - route to `/code-review`: whether the business logic is correct, pricing math, algorithmic correctness, anything without a crisp invariant

Every finding must cite the side-effect line, the gate it precedes (or "ungated"), and the control-flow path. No finding without two line references.
