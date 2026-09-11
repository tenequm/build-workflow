<!-- Vendored from the polish skill v3.1.0 (tenequm/skills), then owned here.
     The runtime never fetches that repository: this file IS the brief. -->

# Review rules

- Read every changed file fully before reviewing - never assess code you haven't opened
- Only flag real issues, not style preferences already handled by the formatter
- Do NOT add comments, docstrings, or type annotations to code that doesn't have them
- Distinguish legitimate operational logging (`logger.info`, `logger.error`) from debug leftovers (`console.log`, `console.debug`)
- When fixing, make minimal targeted edits - don't refactor surrounding code
- The diff is the hunting scope - review the changed code, don't audit the whole repo. But anything real the review surfaces along the way (a pre-existing flaw the diff touches, a stale sibling path, an adjacent issue) is a finding in its category, tagged `(pre-existing)` or `(out of diff)` - never parked in a side note
- Reuse suggestions must point to a specific existing function/utility in the codebase, not hypothetical "you could extract this"
- Convention findings must cite a specific existing example in the codebase, not just "this seems inconsistent"
- In review mode, frame every finding as a question or a suggestion - it is someone else's code. Findings tagged `(pre-existing)` or `(out of diff)` are still reported, but never drive the recommended action: a PR cannot be blocked over code it did not touch
- Do not flag efficiency on cold paths, one-time setup code, or scripts that run once
- Never reproduce a credential value in a finding, a report line, or an agent prompt. A hardcoded key, token, password or connection string in the diff is a correctness finding of the highest order - cite it by `file:line` and describe it ("an AWS secret key is hardcoded"), never by value, and mask any value that must appear as `AKIA****`
