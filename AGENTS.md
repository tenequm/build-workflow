# build-workflow - agent instructions

After meaningful skill or template edits, release with `just ship`, not a bare
`git push`. Plugin consumers only receive updates when the manifest version
changes; `ship` bumps both `plugin.json` files in sync, commits, and pushes.
Doc-only or internal changes may push without shipping.

The operator's own machines consume `skills/` via live symlinks from
`~/.claude/skills` (the `bwup` shell function), so local edits are live
immediately and need no install step.

A build occupies only its workspace branch: the plan commits nothing to the
primary (workspace-at-first-write, 2026-09-04; rationale in
[the decision record](docs/knowledge/decisions/workspace-at-first-write.md)),
so other sessions may work on main freely while a build runs; primary drift
is resolved by /build-close's merge. The one shared file is the primary's `.claude/settings.local.json`,
written once at workspace creation.

The four skills are self-contained: a skill never invokes another skill
or slash command and never reads a file from a sibling skill's directory. Each skill carries its own
`templates/`; a template two skills need is copied into both. Consumers
install the skills one at a time, and a skill that reaches outside itself
breaks for them. `scripts/skill_isolation.py` enforces this (pre-commit); shared
Python is vendored by `bernstein_operator/scripts/sync-skill-code.py`, whose
`--check` requires the copies to stay byte-identical.

`/review-pr` reviews someone else's pull request and runs no task engine: its model
stages are driver-owned one-shot ACP sessions, for the reasons in
[the decision record](docs/knowledge/decisions/review-sessions-are-driver-owned-ceremonies.md).
Two rules there are load-bearing and easy to weaken by accident - the validation
command is read from the BASE branch and never from the pull request tree, and no
model session ever receives a credential or a GitHub token.

Three rules apply to anything added to it, each learned by being burned:

- A new boundary that parses model output is strict only on fields a later stage reads
  to decide something; a purely descriptive field is dropped and recorded, never fatal
  ([why](docs/knowledge/decisions/strict-on-deciding-fields-tolerant-on-describing-ones.md)).
- A new executable check runs a control leg first and reports inconclusive when the
  command could not run. An exit code alone is an observation, not a finding
  ([why](docs/knowledge/findings/a-check-that-cannot-run-refutes-nothing.md)).
- The fixture (`fixtures/review-pr/setup.py --recorded`) runs the whole pipeline over
  the real acpx transport for no provider spend, but it stands in for a model's
  judgment and NOT for its obedience: a recording agent derives its own output path and
  never reads the brief, so nothing a brief says about where to write, what to avoid or
  which of several names to pick is covered by it
  ([why](docs/knowledge/findings/recorded-agents-hide-brief-defects.md)). Put that class
  of constraint in code that runs before the session.

- Cost figures are observability, never control flow: no new bound may read a dollar
  amount, and every dollar figure is derived from pond after the run and labeled a
  floor ([why](docs/knowledge/decisions/cost-is-observability-never-control-flow.md)).
- Session capture goes through the run's own pond store with the pinned binary; the
  host corpus is only ever a fold target
  ([why](docs/knowledge/decisions/per-run-pond-store-for-capture.md)).

A retro item closes only as a check, a template field, or a test - never as
another skill sentence.

Durable project knowledge lives in `docs/knowledge/` (an OKF bundle; read its
`index.md` first). Load the okf-project-knowledge-base skill before reading or
writing it, and after substantial work review whether a durable decision or
finding should be captured there. The index listing is generated: after any
concept change run `python3 scripts/kb_index.py` (pre-commit enforces
`--check`). There is no update log - git history is the log.
