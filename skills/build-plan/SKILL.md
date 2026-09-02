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
    .agents/build/plans/<slug>/<step>.md    brief, TRACKED; <step> is the stage name
    <run>/contracts/<seam>.md               driver-written interface contract per seam

BRIEFS ARE TRACKED FILES, not run-directory files. The step's plan
`description:` tells the agent to read its brief by path, and only tracked files
exist inside the agent's worktree: the run directory is untracked and outside
every worktree. The sidecar's `brief:` therefore starts with `.agents/` and
resolves against the REPO ROOT; anything else resolves against `<run>` and is
driver-side only. A brief edit is a commit.

Copy the templates from this skill: `TPL=.agents/skills/build-plan/templates`
(project install; `~/.agents/skills/...` for a global one).

1. Decompose by dependency graph, not by file list: independent subtasks run in
   parallel stages; a seam split gets a driver-written interface contract first.
   Phase length target 15-30 min of executor wall; split longer ones.
2. One step per stage, stage name = step name, `depends_on` carries the DAG.
   Bernstein batches concurrently-open same-role tasks into ONE session
   (`max_tasks_per_agent` defaults to 2 and no seed key, `tuning:` section or run
   flag changes it), and a batched session spawns once. What keeps two open
   siblings apart is a differing cli or model (`_groups_can_merge`,
   tick_pipeline.py:113-127), and both are resolved from the step's `role:`
   through `role_model_policy` in `bernstein.yaml`. **Do not write a per-step
   `cli:`**: it is not in Bernstein's plan schema, it won the first spawn and was
   LOST on the retry (measured 2026-09-02). Give two parallel siblings different
   ROLES that resolve to different clis -- `resolver` (codex) and `analyst`
   (claude). Readiness fails any role with no policy entry. The four roles are
   `resolver`, `analyst`, `adversary` (judge) and `visionary` (shadow): the
   obvious names (`backend`, `reviewer`) each pull a 10 KB irrelevant catalog
   persona onto the front of the prompt with no way to switch it off, and
   anything outside Bernstein's role enum fails `plan validate`. Do not rename
   them; see `docs/2609-02-persona-prefix.md`.
3. Split a phase into parallel sibling steps by disjoint file ownership:
   whenever one step would own more than about 8 files, or two independent
   packages, cut it into `phase-Na`, `phase-Nb`, ... in stages of their own with
   no dependency between them. Siblings must not share a file -- readiness fails
   a plan where two steps own the same path or overlapping globs -- so a file
   both would touch (`go.mod`, a registry, a shared type) belongs to exactly one
   sibling or to a small preceding step that lands it first. `judge-N` depends on
   every sibling stage, so it reviews the whole phase.
4. Assign executors by shape, through the role: seam and investigation steps ->
   `analyst` (claude, claude-opus-5); transfer, exact-line and fix steps ->
   `resolver` (codex, gpt-5.6-sol); Flash only as the `visionary` role, out of
   the chain. Every judge step is `adversary` (claude, claude-opus-5). Unlike
   Bernstein's built-in `reviewer`, `adversary` is NOT in the role tool
   allowlist, so the judge does have Write and Edit and nothing stops it
   touching code: its brief must forbid editing anything but its review file.
5. Judge nodes: `judge-N` depends on every `phase-N` sibling stage; `fix-N`
   depends on `judge-N` (plain `depends_on` -- Bernstein's plan schema has no
   per-stage condition or retry field, so a clean verdict makes fix-N a no-op,
   which its brief must say); dependents depend on `phase-N` only. `polish-N` optional, non-blocking, files restricted to
   phase-N's. Three hard requirements on a judge step, all silent if missed:
   its sidecar entry carries `judges: "<exact phase title>"` (that field, not
   the title, selects the verdict gate); its `report:` is exactly
   `.agents/blind-review.md` (the verdict parser reads that path and nothing
   else); its plan `files:` is `[]`.
6. Write the plan and sidecar from `$TPL/build.yaml` and `$TPL/build.steps.yaml`;
   replace every `<...>` placeholder and delete the sibling/judge/fix/polish
   stanzas the phase does not use. Briefs from `$TPL/brief.md` into
   `.agents/build/plans/<slug>/<step>.md`: allowlist, items whose done-criterion the Validation
   block can decide, exact validation commands, report format. Judge steps use
   `$TPL/judge-brief.md` (paste the phase brief and `$TPL/judge-prompt.md` into
   it), fix steps `$TPL/fix-brief.md`. Length cap 16k. Every brief needs an
   `## Items` heading, a `## Validation` heading with a fenced command block, and
   a `## Report` heading whose text names Deviations; readiness fails without
   them.
7. Set each sidecar step's `brief:` and `report:` explicitly rather than relying
   on the `<T>` default. `report:` is relative to the executor's worktree root
   and is copied to `<run>/reports/<T>/report.md` by the gate. Codex has twice
   exited without writing its report (`report_mismatch: ["no report file"]`,
   non-blocking): keep the Report section short and make it the last item.
8. Record the plan and brief hashes in `<run>/ledger.md`:

       printf -- "- %s plan=%s briefs=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
         "$(shasum -a 256 .agents/build/plans/<slug>.yaml | cut -d' ' -f1)" \
         "$(shasum -a 256 .agents/build/plans/<slug>/*.md | cut -d' ' -f1 | tr '\n' ' ')" \
         >> <run>/ledger.md
       git add .agents/build/plans && git commit -m "chore(build): plan and sidecar for <slug>"

   Then offer `/build-ready <run>`.
