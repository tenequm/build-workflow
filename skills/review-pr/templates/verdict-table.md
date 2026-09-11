<!-- Vendored from the polish skill v3.1.0 (tenequm/skills), then owned here.
     The runtime never fetches that repository: this file IS the brief. -->

# Severity classes and the verdict table

Split the findings into **Pre-merge asks** and **Follow-ups** (candidate tickets) before
deciding anything. Findings tagged `(pre-existing)` or `(out of diff)` are always follow-ups.

**State gate first.** A draft PR, a closed or merged PR, or an ask the requester withdrew ->
**skip**: post nothing, name the state that caused it, and still report every finding so the
work is not lost. `skip` is reached only from PR state, never from finding severity. Close a skip
with the same two lines below - `y` confirms posting nothing, and naming an action overrides the
gate.

**Otherwise** classify every surviving pre-merge finding as exactly one of:

- **SUGGESTION** - the author may ignore it and the PR is still fine to merge (nits,
  alternatives, questions where any answer is acceptable)
- **BLOCKING QUESTION** - the verdict depends on the answer (intent or a contract that cannot
  be verified from the diff alone)
- **BLOCKING FIX** - a commit on this PR is required. SEVERE if it involves security, data
  loss, an irreversible change, or a broken deploy path

Follow-ups never enter the verdict. The verdict is the strictest match:

| Strictest surviving finding | Verdict |
| --- | --- |
| any SEVERE blocking fix | request-changes |
| any blocking fix or blocking question | comment-only |
| suggestions only | approve-with-comments |
| none | approve |
