---
name: build-plan
description: "Stage 2 of the build workflow: cut docs/spec.md into a Bernstein plan and per-step briefs. Writes .agents/build/plans/<slug>.yaml with stages, steps, owners, cli and model per step, and briefs plus interface contracts for parallel splits in the run dir. Use after /build-design or when a spec exists and a plan does not. Triggers: /build-plan, cut the plan, write briefs."
---

# build-plan

Input: `.agents/build/runs/<slug>` with the spec sha256 in `ledger.md`.
Output, exact paths (`<run>` = that directory, `<T>` = a step's title slug:
lowercase, every non-alphanumeric run replaced by `-`, cut to 48 chars):

    .agents/build/plans/<slug>.yaml         plan, tracked; `name:` MUST equal <slug>
    .agents/build/plans/<slug>.steps.yaml   sidecar, tracked, same directory
    <run>/briefs/<T>.md                     brief; the sidecar's `brief:` is relative to <run>
    <run>/contracts/<seam>.md               driver-written interface contract per seam

Copy the templates from this skill: `TPL=.agents/skills/build-plan/templates`
(project install; `~/.agents/skills/...` for a global one).

1. Decompose by dependency graph, not by file list: independent subtasks run in
   parallel stages; a seam split gets a driver-written interface contract first.
   Phase length target 15-30 min of executor wall; split longer ones.
2. One step per stage, stage name = step name, `depends_on` carries the DAG.
   Bernstein batches concurrently-open same-role tasks into ONE session
   (`max_tasks_per_agent` defaults to 2 and no seed key, `tuning:` section or run
   flag changes it), and a batched session spawns once, so only the first step's
   sidecar `cli` is ever read. What keeps two open siblings apart is a differing
   `cli:` or `model:` **in the plan** (`_groups_can_merge`,
   tick_pipeline.py:113-127); the sidecar `cli` is invisible to Bernstein. So
   declare `cli:` on every step in the plan too, and give two parallel siblings
   different roles if they would otherwise share role, cli and model.
   **The two files spell it differently: the plan takes the adapter name
   (`herdr-claude`, `herdr-codex`, `herdr-agy`, `herdr-fake`), the sidecar takes
   the bare kind (`claude`, `codex`, `agy`, `fake`).** `bernstein plan validate`
   warns "unknown key 'cli'" on every step and exits 0; that warning is expected.
3. Split a phase into parallel sibling steps by disjoint file ownership:
   whenever one step would own more than about 8 files, or two independent
   packages, cut it into `phase-Na`, `phase-Nb`, ... in stages of their own with
   no dependency between them. Siblings must not share a file -- readiness fails
   a plan where two steps own the same path or overlapping globs -- so a file
   both would touch (`go.mod`, a registry, a shared type) belongs to exactly one
   sibling or to a small preceding step that lands it first. `judge-N` depends on
   every sibling stage, so it reviews the whole phase.
4. Assign executors by shape: seam and investigation steps -> herdr-claude /
   claude-opus-5; transfer, exact-line and fix steps -> herdr-codex; Flash only
   as the shadow lane (`shadow: agy`). `herdr-fake` is a plumbing test only.
5. Judge nodes: `judge-N` depends on every `phase-N` sibling stage; `fix-N`
   depends on `judge-N` with condition failed, retry 2; dependents depend on
   `phase-N` only. `polish-N` optional, non-blocking, files restricted to
   phase-N's. Three hard requirements on a judge step, all silent if missed:
   its sidecar entry carries `judges: "<exact phase title>"` (that field, not
   the title, selects the verdict gate); its `report:` is exactly
   `.agents/blind-review.md` (the verdict parser reads that path and nothing
   else); its plan `files:` is `[]`.
6. Write the plan and sidecar from `$TPL/build.yaml` and `$TPL/build.steps.yaml`;
   replace every `<...>` placeholder and delete the sibling/judge/fix/polish
   stanzas the phase does not use. Briefs from `$TPL/brief.md` into
   `<run>/briefs/<T>.md`: allowlist, items whose done-criterion the Validation
   block can decide, exact validation commands, report format. Judge steps use
   `$TPL/judge-brief.md` (paste the phase brief and `$TPL/judge-prompt.md` into
   it), fix steps `$TPL/fix-brief.md`. Length cap 16k. Every brief needs an
   `## Items` heading, a `## Validation` heading with a fenced command block, and
   a `## Report` heading whose text names Deviations; readiness fails without
   them.
7. Set each sidecar step's `brief:` and `report:` explicitly rather than relying
   on the `<T>` default. `report:` is relative to the executor's worktree root
   and is copied to `<run>/reports/<T>/report.md` on settle.
8. Record the plan and brief hashes in `<run>/ledger.md`:

       printf -- "- %s plan=%s briefs=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
         "$(shasum -a 256 .agents/build/plans/<slug>.yaml | cut -d' ' -f1)" \
         "$(shasum -a 256 <run>/briefs/*.md | cut -d' ' -f1 | tr '\n' ' ')" \
         >> <run>/ledger.md
       git add .agents/build/plans && git commit -m "chore(build): plan and sidecar for <slug>"

   Then offer `/build-ready <run>`.
