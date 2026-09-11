<!-- Vendored from the polish skill v3.1.0 (tenequm/skills), then owned here.
     The runtime never fetches that repository: this file IS the brief. -->

# Report format

Synthesize validated findings into a single deduplicated report. If multiple agents flagged the same code, merge into one finding. Group by category:

```
## Review Findings

### Correctness (N issues)
1. `path/to/file.ts:55` - chargeUser() runs before body validation (handler validates at :78, after next()); a malformed request is charged then 400s
2. ...

### Cleanliness (N issues)
1. `path/to/file.ts:42` - console.log("debug response")
2. ...

### Design (N issues)
1. `path/to/file.ts:15-18` - hand-rolled path join, use existing `resolveAssetPath` from shared/utils
2. ...

### Efficiency (N issues)
1. `path/to/file.ts:30-45` - sequential awaits on independent API calls, use Promise.all
2. ...

### Dropped after validation
1. `path/to/view.py:12` - per-mousemove getBoundingClientRect - the element is CSS-fixed, so the rect is cached and there is no layout flush
2. `path/to/file.ts:88` - flock fallback catches all lock errors, not just unsupported-filesystem ones - validated but not actionable; nothing to change

**Total: X issues across Y categories**

**Recommendation:** fix correctness #1, cleanliness #1-2, efficiency #1; skip design #2 (marginal).

**Awaiting approval before proceeding with fixes.**
```

List **Correctness** first, and always - including at `(0 issues)`, since a zero there is a real signal that side-effect ordering was checked. A correctness zero must state what was traced - which side-effects were inventoried and which gates cover them - not just the count. It must never be batch-approved alongside cosmetic items.

There is no non-blocking "observations" section: anything validated and worth acting on is a finding in its category (tagged `(pre-existing)` or `(out of diff)` where applicable); anything not worth acting on goes under **Dropped after validation** with the reason. That section substantiates the counts - omit it when empty.

End the report with a per-finding **Recommendation** line: which findings you'd fix and which you'd skip, so the user can approve by reference. Judge on long-term codebase benefit. Out-of-diff findings default to fix - defer one only when fixing it would bloat the commit beyond what belongs there, force a decision, or add more risk than value, and say which explicitly rather than leaving it open-ended. Scope hygiene loses when the fix is smaller than the explanation for deferring it; a low-risk fix that just eases maintenance is a fix, not a deferral.

If zero issues found, report "Clean - no issues found", substantiate the correctness zero (what was traced and why it's clean), and offer next actions - e.g. commit as-is, or leave for the user's own review - then stop.

The report MUST end with the line "**Awaiting approval before proceeding with fixes.**" (or the clean-case report above). Do not proceed to Phase 6 until the user explicitly approves.
