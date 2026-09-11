# /review-pr: the polish skill as a Bernstein workflow

Status: BUILT 2026-09-11 and locally verified; see `## Delivered` at the end
for what exists, what was proven, and what still needs a paid run. Designed
2026-09-11 from the
[polish skill v3.1.0](https://github.com/tenequm/skills/blob/main/skills/polish/SKILL.md),
the operator at v0.1.21, the knowledge bundle, and the
[2609-02 research overview](../research/2609-02-research-overview.md)
(all paper/blog citations below resolve there). Upstream's own review
machinery, which this tool complements, is documented in
[the upstream-review-automation reference](../knowledge/references/upstream-review-automation.md).
The phase map below is the design; one deviation from it is recorded under
`## Open questions, resolved at implementation`.

**For a fresh agent picking this up:** the workflow is built - read
[the skill](../../skills/review-pr/SKILL.md) and run the fixture before
reading further here. This document remains the design record and the
rationale index; `## Delivered` maps each requirement to the code that
carries it. The two hard requirements it set are met: the four lens briefs,
the polish Rules block and the verdict table are VENDORED under
`skills/review-pr/templates/` (copied from polish v3.1.0, then owned here -
the runtime never fetches tenequm/skills), and every acceptance item is
executable from a clean checkout.

Goal: point a command at one or many Bernstein PRs and get a review at or
above the level `/polish` produces today - faster per weekly batch, more
reliable (no orchestrator drift), with models swappable per stage - and
outputs a level above polish through executable verification. The immediate
consumer is the core-reviewer duty on upstream Bernstein: the
`needs-committer-review` label, batched weekly.

Required scope (Misha, 2026-09-11): all eight quality mechanisms land in
the implementation - (1) executable rubric per finding, (2) PoC-or-demote
with the gold gate, (3) PR-body claim re-execution, (4) dual-family lens
diff, (5) author-family routing with a blinded verifier, (6) the precision
ledger, (7) proven suggestions, (8) the house-rule lint stage. Sequencing
below may stage them; none may be dropped without a spec change.

Non-goals: this is not a `/build-plan` product (the plan shape is static);
it does not replace `/code-review` (business-logic correctness stays there,
as polish itself rules); it never posts a review without Misha's explicit
approval - the charter says an approval means *he* read the diff, so the
tool prepares evidence for that read and stops.

## Why a template plan, not /build-plan

The polish skill is already a DAG with a fixed shape: checks, then four
parallel review lenses, then per-finding validation, then synthesis, then a
gated post. Planning machinery would re-derive the same shape per PR at
planning cost. So `/review-pr` stamps a **template plan** per PR the way
`fixtures/slugify/setup.py` stamps a workspace: a deterministic script
materializes the checkout, pins the facts, and posts the same task graph
every time. Swapping a model is one line in the roles block.

## Phase map (polish -> operator)

| polish phase | review-pr stage | model |
|---|---|---|
| (none) | 0. house-rule lint | none (script) |
| 1 checks | 1. gate: pinned validation command | none (command) |
| 2 diff/context | setup script | none (script) |
| 3 four agents | 2. four parallel reviewer tasks | per-role, swappable |
| 4 validate | 3. verify fan-out, one task per finding | cross-family vs producer |
| 5 report | 4. verdict + payload (scripts) + body prose | small model, prose only |
| 6 post | 5. artifacts; human posts after reading | none |

One engine run per stage, the driver owning the boundary - the settled
[phase-boundary decision](../knowledge/decisions/phase-boundary-between-engine-runs.md).
The verify fan-out especially must NOT share a task server with the
reviewers: the engine [releases dependents on worker-reported DONE, before
any verification](../knowledge/findings/bernstein-done-releases-before-verification.md),
so strict reviewed-then-verified ordering requires keeping stage 3 off the
stage-2 server entirely. Stage 3 runs as driver-side pinned mini-runs, the
same mechanism the operator already uses for fixes.

## Stage 0: house-rule lint (zero model, seconds)

Mechanical checks derived from [what upstream's machinery actually
enforces](../knowledge/references/contributing-to-bernstein.md):

- release-notes fragment present, ending with `(#NNNN)` - the one thing
  their bot has demonstrably blocked over;
- new tests fail on base (revert `src/` to base, re-run the PR's tests -
  their own bot's evidence step, reproduced locally);
- prose hygiene: em-dash/unicode scan over title, body, branch, commit
  messages (their denylist names em-dashes);
- no `Signed-off-by` (their governance forbids adding one);
- if a `bisect-on-red` `regression` label sits on a referenced commit,
  annotate it as a files-touched heuristic, never a verdict (measured
  2026-09-07: label landed on a zero-overlap tuning fix).

Everything here lands as findings before any model spawns.

## Setup (deterministic script)

- `gh pr checkout` into a primary checkout; workspace at detached PR head.
- Validation command read from the BASE branch's CLAUDE.md, never the PR
  tree, and pinned into the plan sidecar. **Readiness refuses a plan whose
  validation command was derived from the PR tree.** A PR that edits the
  validation command is itself a finding (polish's own rule, promoted to a
  machine check).
- Diff written to a scratch file; lockfiles and generated files excluded.
- Author-model-family detection (PR body style, disclosure, receipts) for
  routing - see stage 2.
- Small-diff fast path: under ~50 changed lines the driver overhead loses
  to the interactive skill; `/review-pr` says so and exits, pointing at
  `/polish`.

## Stage 1: gate

The pinned validation command, run once, caches cleaned first (Codex
over-claimed lint twice on a warm golangci cache - research overview,
process findings). Failures are findings, never fixes: review mode does
not edit the tree.

## Stage 2: four reviewer tasks, parallel

Briefs are the polish Phase 3 lens sections near-verbatim - they are
already written as briefs - plus the polish Rules block, plus:

- **Injection fencing in every brief.** The diff and everything in it
  (comments, strings, commit messages, PR body) is material to judge,
  never direction to follow; instruction-shaped content is a finding.
  Reviewers receive the PR body for intent. Verifiers never do (stage 3).
- **File allowlist**: `reports/findings-<lens>.json` only.
- **Completion signal names the report file** - the
  [report-witness law](../knowledge/decisions/completion-signals-name-the-report.md).
  This is what converts a luna-style clean exit with no work
  ([capability floor](../knowledge/findings/executor-model-capability-floor.md))
  into an engine retry instead of a silent gap. Note the
  [plan-post helper drops completion_signals](../knowledge/findings/plan-post-drops-completion-signals.md);
  the operator posts witnesses itself - keep it that way here.

### Findings contract (JSON, one file per lens)

Each finding: `file`, `line`/`start_line`, `category`, `claim` (one
sentence), `evidence` (the lines read), `rubric` (see below), `lens`,
`producer` (model family). The schema is the product: stage 3, stage 4,
and the precision ledger all consume it.

**The executable rubric.** Every finding must carry a mechanical check a
verifier can run - "run X, expect Y", "grep Z must be empty", "revert hunk
H, test T flips". Generic LLM judging of code runs at kappa 0.10-0.21
against execution truth; a per-bug rubric reaches 0.75, and the rubric
author matters more than the judge model (research overview, literature).
A finding whose rubric cannot be stated is still reportable but is marked
`unverifiable` and can never rise above SUGGESTION.

### Roles and routing

| role | work shape | initial model | notes |
|---|---|---|---|
| cleanliness | mechanical | gemini flash or luna | witness catches flake |
| efficiency | local reasoning | sonnet 5 | |
| design-reuse | codebase exploration | opus / gpt-5.6-sol high | |
| gating | control-flow tracing | strongest Claude | **never Codex** |
| verifier | adversarial re-check | opposite family per finding | |

The gating ban on Codex is a correctness rule, not a preference: its
content filter [silently truncates turns on exactly the vocabulary that
brief is made of](../knowledge/findings/codex-content-filter-truncates-executor-turns.md)
(race, exploit, attack, sweep), presenting as clean completion.

Routing by author family: review direction is asymmetric (Claude reviewing
Codex 71.6 -> 89.7, Codex reviewing Claude 91.4 -> 82.8 - research
overview). When setup detects the author family, the design and gating
lenses route to the opposite family. Keep four lenses: both Anthropic's
own guidance and the capability-floor arc say discipline beats fan-out.

**Dual-family disagreement:** run design and gating twice, once per
family, and diff the finding sets.
Cross-family ensembles realize 43-44% of the theoretical independence gain
(same-model under 30%); disagreement alone detects ~2/3 of incorrect
programs at zero false positives (DiffTrust). Agreements auto-confirm
cheaply; disagreements are where stage-3 tokens go.

## Stage 3: verify fan-out (driver-side mini-runs)

One verifier task per surviving finding. The verifier:

1. Is a different model family than the finding's producer (judge
   self-preference: >50% likelier to pass its own model's output).
2. Sees the bare diff and tree ONLY - no PR body, no commit messages, no
   lens or producer identity. A "correct code" comment swings verdicts
   20+ points; the PR body is the author's advocacy and has no place in
   verification.
3. **Executes the rubric** instead of re-reading prose.
4. For correctness and gating findings: **PoC-or-demote.** The verifier
   must produce a failing demonstration on the PR head (test or script).
   Anthropic's security-review result: an adversarial verifier halved
   non-exploitable findings, and requiring a PoC drove false positives to
   near zero. Gold gate: the repro must also behave correctly on base -
   61.9% of decisive generated tests fail on the gold patch, so a repro
   that fails both ways proves nothing.
5. **Re-executes the PR body's own claims** (one dedicated verifier task
   per PR, not per finding): parse the evidence-first body's literal
   before/after outputs, re-run the commands, diff claimed vs actual.
   Squash-merge makes that body the permanent commit message, so an
   over-claim there becomes false history. This mechanizes the
   report_mismatch class and no other reviewer on that repo does it.

Verdicts: CONFIRMED (rubric passed / PoC exists), PLAUSIBLE (holds on
re-read, no mechanical proof), DROPPED (with reason, kept for the report's
"Dropped after validation" section and the ledger).

## Stage 4: synthesis (scripts, model for prose only)

- **Anchor verification is code**: every finding's line must sit inside a
  diff hunk (new files: any line). GitHub rejects the whole review
  atomically on one bad anchor; today the skill eyeballs this.
- **Verdict table is code**: polish's strictest-surviving-finding table
  (SEVERE fix -> request-changes; fix or blocking question -> comment;
  suggestions -> approve-with-comments) computed deterministically from
  the verified findings. Follow-ups and `(pre-existing)`/`(out of diff)`
  never enter the verdict - polish's rule, kept.
- **Proven suggestions:** for few-line fixes, apply the
  suggestion in the worktree, run the pinned gate, attach "compiles,
  tests green" to the `suggestion` block or downgrade it to prose.
  Speculation only for small stageable edits with rollback.
- A small model writes the 1-2 sentence review body. Never process
  narration - polish's rule, kept.
- Artifacts: `report.md` (polish Phase 5 format, correctness first and
  always, substantiated zero) and `pr-review.json` ready for
  `gh api --method POST .../reviews`.

## Stage 5: the human

`/review-pr` ends where polish's review mode ends: verdict line,
"Post it? (y/...)" - after Misha reads. State gate re-checked before
posting (head moved, merged, draft). Nothing in this workflow ever holds
write credentials to GitHub; posting happens in the driver session under
his account, on his word.

## Sandboxing

Reviewer tasks never execute PR code - they read, grep, and write a
report. Process tier plus `env_isolation` (credential allowlist) is
sufficient for them. The two stages that DO execute untrusted code - the
tests-fail-on-base check in stage 0 and any rubric/PoC execution in
stage 3 - run at `capability:sandbox=container`, or on a host with
unprivileged user namespaces enabled so Codex's bubblewrap path works.
That userns sysctl is the exact 2026-09-10 two-hour symptom
(vendor sandbox refusing everything reads as a model that had nothing to
do); readiness checks it before any run.

## Executor sessions land in pond (in scope)

Every executor this workflow spawns - reviewers, verifiers, mini-runs -
is a codex or claude CLI session, the two formats pond already ingests
losslessly. The driver's stage teardown syncs them (`pond sync`, or the
machine-level ingest where it runs), and the run ledger records each
task's session id keyed to the finding ids it produced. What this buys:

- **Forensics without spelunking.** A failed or suspicious review stage
  is a `pond_get_session` / `pond_sql` query, not a crawl through
  `.sdd/runtime` logs - the 2026-09-10 lesson, applied.
- **Findings with provenance.** Every posted finding links to the
  transcript that produced and the one that verified it; a disputed
  review thread can be answered with evidence.
- **The eval corpus for free.** The precision ledger's (lens, model)
  rows point at real transcripts, which is exactly the substrate the
  future claim-vs-tool-call verifier and the routing brain need.

Boundaries: transcripts are stored and queried, never fed back into
briefs (they are a prompt-injection surface and the corpus provably
carries credentials - evidence, not instructions). All three executor
families are covered: pond v0.17.2 (2026-09-11) ingests agy sessions,
including those its ACP server writes - both lanes under `~/.gemini`.
Readiness therefore pins `pond >= 0.17.2` on the operator host, and
setup runs `pond adapters enable agy` once on hosts that synced before
that release.

## The precision ledger (the level-above loop)

Append-only, `runs.jsonl` pattern: per finding - lens, producer model,
verifier verdict, and fate (posted / author fixed / Misha dropped). After
~20 PRs this yields measured precision per (lens, model): the routing
table stops being priors. OpenAI's precision-tuned reviewer gets 46% of
comments acted on; that ratio, per lens, is this tool's quality metric.
The ledger is also the eval corpus the pond-evidence direction wants -
collected as a side effect, spent later.

## Acceptance evidence before this is called working

1. **Ground-truth replay**: run against
   [PR #5737](https://github.com/sipyourdrink-ltd/bernstein/pull/5737),
   where the hand review produced 14 findings with known maintainer
   fates. The tool must recover the correctness findings and the applied
   design findings; every miss is analyzed, not excused.
2. **Seeded fixture** `fixtures/review-pr/` (slugify pattern): a fixture
   repo plus a PR with planted defects covering all four lenses, one
   instruction-shaped injection in a comment, and one over-claimed PR
   body. One command materializes it; the pipeline must catch the plants,
   report the injection as a finding without acting on it, and flag the
   claim mismatch.
3. **A real weekly batch**: the current `needs-committer-review` set,
   wall time and dollars recorded against the interactive-polish
   baseline. Target: under 8 min and predictable cost per mid-size PR;
   the batch unattended.
4. Anchor check proven: a deliberately mis-anchored finding is caught by
   the script, not by GitHub's 422.

## Order of work

1. Deterministic spine: setup script, stage-0 lint, anchor check, verdict
   table, payload assembly. No engine, no models - testable cold.
2. Findings schema + the four lens briefs extracted from polish SKILL.md.
3. Template plan + roles + witnesses; first end-to-end run against a
   small already-reviewed PR; then the #5737 replay.
4. Stage 3: rubric execution, PoC-or-demote, PR-body claim re-execution,
   cross-family routing.
5. Dual-family lens diff, author-family routing, proven suggestions -
   all three are committed scope (Misha, 2026-09-11), sequenced after
   stage 3 works because they compose on top of it.
6. The fixture, seeded (its plants must now also cover a dual-family
   disagreement case and a provable suggestion).
7. Batch driver + precision ledger.
8. Pond session capture wires in with the batch driver (7): teardown
   sync + session ids in the ledger. Future, not in this scope: the
   claim-vs-tool-call verifier over those stored transcripts - but its
   substrate is being collected from the first run.

## Open questions, resolved at implementation

Answered 2026-09-11 while building. Each answer is in code, and the two that
carry real rationale have decision records.

- **Verify fan-out cost ceiling.** Capped at `bounds.max_verifier_sessions`
  (12), correctness and gating claims first; past the cap a finding settles on
  its driver-executed rubric. Findings are NOT batched into a shared session:
  a verifier that sees four claims reads each in the context of the others,
  which destroys the blinding stage 3 exists to buy. Rationale in
  [the decision record](../knowledge/decisions/verification-is-capped-never-batched.md).
- **Does tests-fail-on-base run on every PR?** Only when the pull request
  touches test files, matching their bot's own selectivity - and the skip is
  recorded with its reason, because an unrecorded skip cannot be told from a
  pass. `houserules.tests_fail_on_base`.
- **Ledger location.** In-repo at `docs/review-ledger/runs.jsonl`, as
  proposed: the repo is public by design, the ledger is evidence, and an
  `.agents/` ledger dies with the worktree that wrote it.
- **Non-Bernstein repos day one.** Yes. Stage 0 loads a rule set per
  repository: `bernstein` adds the release-notes fragment and the bisect
  annotation, every other repo gets `generic` (prose hygiene, no sign-off,
  injection scan, validation-command provenance, tests-fail-on-base). The set
  is chosen from the remote slug and overridable with `--rules`.
- **Author-family detection.** Disclosure lines and trailers score 2, unicode
  punctuation in the body scores 1, and a tie or a zero score returns
  `unknown`, which leaves the default routing table untouched. The confidence
  is recorded in the sidecar, so a review never hides which table it used.

One further deviation, recorded because it changes the phase map above: the
model stages run as driver-owned one-shot ACP sessions rather than Bernstein
task-server runs. All eight quality mechanisms are preserved; the reasoning,
and what it costs, is in
[the decision record](../knowledge/decisions/review-sessions-are-driver-owned-ceremonies.md).

## Delivered

| requirement | where |
|---|---|
| 1. executable rubric per finding | `review_pr/findings.py` (schema, `unverifiable` demotion), `review_pr/rubric.py` (execution) |
| 2. PoC-or-demote with the gold gate | `review_pr/verify.py:settle`, `review_pr/rubric.py:gold_gate` |
| 3. PR-body claim re-execution | `review_pr/claims.py`, `templates/claims-brief.md` |
| 4. dual-family lens diff | `review_pr/dualfamily.py`, `templates/stages.yaml:dual_family` |
| 5. author-family routing, blinded verifier | `review_pr/checkout.py:author_family`, `pipeline.py:lens_families`, `briefs.py:verifier` |
| 6. the precision ledger | `review_pr/ledger.py`, `review-pr.py ledger` |
| 7. proven suggestions | `review_pr/suggestions.py`, `synthesize.py:comment_body` |
| 8. house-rule lint stage | `review_pr/houserules.py` |
| the deterministic spine | `checkout.py`, `diffindex.py`, `anchors.py`, `verdictcalc.py`, `synthesize.py` |
| the vendored briefs | `skills/review-pr/templates/` |
| pond session capture | `review_pr/pondsync.py`, wired in `pipeline.py:pond_capture` |
| the batch driver | `review-pr.py batch` |

### Acceptance evidence, as it stands

- **Seeded fixture (item 2): done and executable.**
  `python3 fixtures/review-pr/setup.py /tmp/fx --recorded` materialises the
  repository and the pull request; `test_review_fixture.py` runs the whole
  pipeline over the real `acpx` transport against a recording agent and
  asserts each plant, the injection reported-and-not-obeyed, the claim
  mismatch, the dual-family agreement, the proven and the downgraded
  suggestion, and the ledger rows. 33 assertions, no provider spend.
- **Anchor check proven (item 4): done.** `test_review_contract.py` puts a
  finding outside a hunk, one on a file absent from the diff and one on a
  deleted file, and requires the script to catch all three before a payload
  is assembled.
- **Ground-truth replay against PR #5737 (item 1): RUN 2026-09-11, and it
  fails its own bar.** Replayed against commit `2512a7e3ea67`, the tree the
  hand review's second round actually saw - reviewing today's head would score
  a tree whose 14 findings were already applied. Result: 4 recovered exactly,
  1 partially, 9 missed, 3 found that the human did not raise. Against the bar
  above (`recover the correctness findings and the applied design findings`):
  **0 of 3 correctness, 1 of 7 design**. Precision held - 7 of 8 pre-merge
  findings were CONFIRMED by an executed rubric or a cross-family verifier -
  but recall did not. Every miss has one shape, and the analysis is in
  [its own finding](../knowledge/findings/review-lenses-miss-claim-vs-implementation.md):
  the four lenses are polish's code-review lenses, and the missed findings all
  check a claim the diff adds against an implementation the diff does not
  touch. Closing it needs a fifth lens, not a better model.
- **A real weekly batch (item 3): still not run.** `review-pr batch --label
  needs-committer-review` is the entry point and records wall time and charged
  spend per pull request into `batch.json`. The replay gives the per-pull-request
  shape it would multiply: 11 sessions, 169s of wall time once stage 2 was warm,
  and roughly $15 of measured provider cost at the shipped budgets - which is
  above the plan's "predictable cost" target and is the number to attack first.

### What the paid replay cost, and what it bought

About $29 of provider spend across two attempts. It found four defects that no
recorded-agent test could have found, all fixed in this change:

1. **Every stage-2 session wrote its report where nothing collects it.** The brief
   named an absolute path to the shared reviewed tree; each session is validated
   against its own worktree. All seven sessions obeyed the brief, exited 0, and
   produced nothing - and the report-witness law caught it exactly as designed,
   retried once, and recorded an honest failure. The fixture had masked it because
   the recording agent writes relative to its working directory and never read the
   instruction. Briefs now resolve every write target against the working directory,
   and `briefs.guard` refuses any brief that names the shared tree.
2. **One invented tag parked a run with seven good sessions behind it.** A model
   tagged a finding `docs-drift`. Tags are decorative; only four of them decide
   anything. Unknown tags are now dropped and kept as `dropped_tags`, while every
   field that decides something stays strict.
3. **A claim that could not be executed was reported as the author over-claiming.**
   The body listed the tests it had run, the extractor turned that into `pytest ...`,
   and the sandbox has no `pytest` - exit 127 became "the body's own evidence does
   not reproduce". A check that cannot run refutes nothing; such claims are now
   counted as `unchecked` and raise no finding. This is the same control the
   tests-fail-on-base rule already gained from the first real run.
4. **Claude-family sessions were invisible to pond.** Codex and agy write their own
   rollouts and were captured; the Claude bridge sets `persistSession: False`, which
   is right for a blind judge and wrong for a review whose transcript is the
   provenance a posted finding points at. It is now a flag, off by default, and the
   review template turns it on - verified end to end: the session file lands keyed by
   its ACP session id and pond ingests it as `claude-code`.

### Environment

`review-pr ready` is green on the operator host as of 2026-09-11, with pond
0.17.2 installed to `~/.local/bin` (ahead of the Home Manager copy) and the `agy`
adapter enabled. Folding 0.17.2 into the Home Manager pin is the operator's own
change; until then the binary in `~/.local/bin` is what satisfies the check, and
removing it restores 0.17.1 and the refusal.
