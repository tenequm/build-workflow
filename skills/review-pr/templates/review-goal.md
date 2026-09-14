# Review this pull request

This file contains only the five independent review lenses. Each `## Lens` section is
the complete lens-specific task text. Copy sections verbatim into separate tasks; the
coordinator and reviewer templates own orchestration, inputs, outputs and shared rules.

## Lens 1: Claim vs implementation

Every other lens is scoped to the diff. **This one is not.** Two coequal duties: is
this statement true of this repository right now, and does this changed code do what it
is plainly meant to do? A change that adds or edits a rule, threshold, filename, role,
label, guarantee or description of what a script does is asserting something about the
implementation. Find the thing that decides it and check.

A claim is anything added or changed that a reader would act on and could be wrong:

- **A rule with a mechanism**: "two approvals, one from a core reviewer", "after seven
  days the thread gets `needs-maintainer`". Something enforces that, or nothing does.
- **A named artifact**: a path, config key, label, workflow, role name, environment
  variable. It exists under that exact name, or it does not.
- **A threshold or a number**: "over 400 lines", "a 72 hour hold". Some code compares
  against it, or the number is decorative.
- **A description of behaviour**: "the checker compares content", "the bot reverts
  `src/` and re-runs the tests".
- **A statement of where truth lives**: two documents that each defer to the other are a
  loop; a document claiming to derive from a source it contradicts is a finding on one
  of the two.

Where the repository has authority files - a charter, governance, ownership, a
contributing document, a schema other files copy - read each one end to end on the BASE
branch before judging any hunk against it. Reading them whole rather than grepping is
the recall lever: a hunk judged before you have read the rule is judged against the
author's framing of the rule. This pull request's own edits to an authority file are
hunks to audit, never ground truth. Record for each: quorums and numeric floors and
exactly whom they apply to; role permissions; any roster presented as complete; which
artifact it names as normative versus the downstream copy; carve-outs and invariants. A
category the file is silent on is recorded as silent - never invent a claim to fill one.

Then take each hunk and ask: does it **contradict** a claim outright; **generalize** one
stated for a single role, tier or path as if it applied to all; **drop a carve-out**
something still enforces; **invert a direction**, naming as normative the artifact the
authority calls the copy; **omit a member** of a list it claims to reproduce in full?

The second duty is plain correctness inside the hunks: a logic error, an inverted
condition, an off-by-one, a mishandled empty, zero or exact-multiple case. No other lens
hunts those, so a defect you can demonstrate is a finding whether or not any document
speaks to it. Name the input that breaks it and what the code returns for it.

How to check one: grep the whole repository for the name, threshold or label; read the
script, workflow, schema or document that implements it; follow imports. The deciding
file is usually not in the diff - that is the point. Be specific about which side is
wrong: "the doc says X, `path/to.py:88` does Y" is a finding, "this seems inconsistent"
is not. When nothing implements a claim, prefer an absence proof: a repository-wide
search whose only hit is the claim itself. Report a rule the change silently drops, too:
if the diff removes or rewrites a statement, check whether the thing it described still
happens - a rule still enforced but no longer written down is as much a defect as one
written down and not enforced.

Do not report: taste decided purely inside the diff; the style, wording or structure of
prose - only whether it is TRUE; or a claim you could not check. Say nothing rather than
guessing. A wrong finding here is expensive because it reads as authoritative.

## Lens 2: Side-effect gating

A closed-scope correctness check: costly or irreversible side-effects that run before
the checks meant to gate them. It does not judge whether business logic is correct.

1. **Inventory the side-effects** introduced or relocated by the diff - charges and
   payments, DB writes and deletes, mutating external calls, file writes, notifications,
   irreversible state changes.
2. **Inventory the gates** each one needs - input validation of shape, type and range;
   authentication; authorization; precondition and existence checks; idempotency.
3. **Cross-check ordering.** Flag any side-effect reachable on a control-flow path where
   a gate runs after it, or not at all. Trace ACROSS the middleware/handler boundary -
   middleware that fires a side-effect before calling `next()` is the prime suspect, and
   the validation that should gate it often lives in the downstream handler.
4. **Missing rollback**: a committed side-effect with no compensation when a later step
   on the same request can still fail (charged, then the request errors).

Every finding cites the side-effect line, the gate it precedes or "ungated", and the
control-flow path. No finding here without two line references.

## Lens 3: Design and reuse

Requires exploring the codebase beyond the diff.

- **Reuse**: search for existing utilities, helpers and shared modules that replace the
  new code - utility directories, shared modules, files adjacent to the changed ones.
  Hand-rolled string manipulation, path handling, type guards and env checks are the
  usual hits.
- **Over-engineering**: a helper used exactly once; an abstraction wrapping a single
  call; try/catch that re-throws the same error or catches an impossibility; validation
  of internal data already validated at the boundary; a flag or config for something
  that could just be code; a backwards-compat shim for code just written.
- **Redundant state**: state duplicating existing state, cached values that could be
  derived, observers or effects that could be direct calls.
- **Parameter sprawl**: new parameters bolted onto a function instead of generalizing or
  restructuring what is there.
- **Copy-paste with slight variation** that should be unified.
- **Leaky abstractions**: internals exposed, or an existing boundary broken.
- **Stringly-typed code** where constants, enums or branded types already exist here.
- **Structure**: functions that grew past roughly 50 lines during the change; naming
  inconsistent with this codebase's conventions.
- **Behaviour drift in relocated code**: when the diff moves or rewrites an existing
  path, compare it against what it replaced. Dropped input validation, removed guards or
  early returns, changed error semantics (status codes, return shapes). A refactor that
  changes behaviour is a regression even when every line looks clean.

## Lens 4: Efficiency

Runtime performance and resource use.

- **Redundant work**: repeated computations, repeated file reads, duplicate network
  calls, N+1 patterns.
- **Missed concurrency**: independent operations awaited sequentially.
- **Hot-path bloat**: new blocking work in startup or a per-request/per-render path.
- **No-op updates**: state or store updates inside polling loops, intervals or handlers
  that fire unconditionally with no change detection; wrappers taking updater callbacks
  that do not honor same-reference returns.
- **TOCTOU anti-patterns**: pre-checking that a file or resource exists before operating.
  Operate directly and handle the error.
- **Memory**: unbounded structures, missing cleanup, listener leaks.
- **Overly broad operations**: reading a whole file for a portion, loading every item to
  filter for one.
- **Unchecked system boundaries**: HTTP calls with no response status check, unhandled
  rejections on external calls, missing error handling at I/O boundaries.

## Lens 5: Cleanliness

Fast, mechanical, high-confidence. Junk that should be removed.

- **Debug leftovers**: `console.log`, `console.debug`, `console.warn` added during
  development; temporary debug variables; hardcoded test values. NOT structured logger
  calls (`logger.info`, `logger.error`).
- **AI slop**: comments explaining obvious code ("// increment counter") - flag each one
  individually, even when the code it describes is flagged elsewhere; JSDoc on internal
  functions that are not public API; verbose docstrings on simple helpers; `TODO`,
  `FIXME`, `HACK` markers left by a tool rather than a person; type annotations a
  language infers correctly; emoji in code or comments unless the project uses them.
- **Non-ASCII punctuation** introduced in changed lines - em dashes, smart quotes -
  unless the project uses them. A plain-text grep misses multi-byte characters; scan
  byte-aware, e.g. `rg -n '[\x{2010}-\x{2015}\x{2018}-\x{201F}]'`.
- **Dead code**: unreferenced functions, variables and types; commented-out blocks (git
  has the history); unused parameters not required by an interface or callback signature.
- **Unused imports**, including ones left behind by a refactor.
- **Hardcoded values**: magic numbers or strings that belong in constants; URLs, prices
  and limits that belong in config. NOT `0`, `1`, `true`, or HTTP status codes.

## Hard constraints

- **Review workers: never commit and never push.** Not a branch, not a tag, not a stash
  left behind.
- **Across the workers, write exactly one file in the checkout: `review-report.md`, at
  the checkout the run started in**
  (`$(dirname "$(git rev-parse --git-common-dir)")`, not your worktree). Modify no other
  file in the checkout. Scratch work, lens findings included, goes in the one scratch
  directory the coordinator named, outside every repository.
- **Workers do not fix anything.** This review ends at a recommendation.
- If a worker runs a validation, lint or test command, take it from the **BASE branch's**
  documentation or config - never from the pull request's own tree. Run nothing whose
  definition the diff supplies.
- No credential value reaches the report or a worker prompt.
