---
name: build-close
description: "Land a validated three-stage build and run its release ceremonies. Use /build-close <path_to_plan_doc> after /build-run, whether the workspace branch has a PR or remains local."
---

# build-close

Input: `<path_to_plan_doc>`. Never edit application code. Send every code fix
to a fresh executor with a brief and allowlist. Never merge on your own
judgment; merge only after the user answers.

The moment a skill instruction proves wrong, ambiguous, or is deviated
from - or the user has to intervene where the skill should have sufficed -
append `- workflow: <what and why>` to `<run>/ledger.md`. These lines are
the retro's input for improving the workflow after the run.

Every commit anywhere in this workflow - driver, executor, judge, fix - uses
Conventional Commits: `type(scope): description` with type in feat, fix,
chore, refactor, docs, test, ci, perf. Branch names follow the same shape:
`type/short-description`. No attribution lines or trailers.

## Preflight

Run inside the workspace `/build-plan` created. Resolve the checkout with
`git rev-parse --git-dir`, `git rev-parse --git-common-dir`, and
`git rev-parse --show-superproject-working-tree`. Refuse when git dir equals
common dir, the superproject result is non-empty, or HEAD is detached.

Resolve the sidecar whose `defaults.doc` equals the input plan document. Fall
back to `.agents/build/plans/ACTIVE` only when exactly that ACTIVE plan pins the
same document. Refuse disagreement. Derive `<slug>` and `<run>` from the selected
machine plan.

Read `<run>/workspace.json`, `<run>/ledger.md`, and `<run>/runs.jsonl` before
anything else. Require workspace.json to contain exactly `path`, `branch`,
`base`, `base_branch`, and `primary`. Require the current absolute root and
checked-out branch to equal `path` and `branch`. Read every attempt report and
judge result named by runs.jsonl; a blocked row is unresolved evidence.

Discover what release means. Check CLAUDE.md (or the equivalent project
instructions) for release and deploy ceremonies - commonly versioning,
changelog, release notes, tags, package publication, migrations, deployment,
and smoke checks. If none is documented, ask. Also read `## Release
requirements` and every `owner: user` row in the plan document.

## PR path

When a PR exists for the workspace branch:

1. Watch CI until terminal. Do not merge red or pending checks.
2. Read review feedback and unresolved threads. Turn every requested code
   change into a committed brief and dispatch a fresh fix executor. Never edit
   the code in the driver session.
3. Re-run the affected checks, push executor commits to the existing branch,
   reply, and resolve threads according to repo convention.
4. Require green checks and all required threads resolved.
5. Ask the user whether to merge. On explicit yes, use the repo's merge method,
   squash where the repo squashes. Otherwise keep the PR, branch, and worktree.

## Local path

When no PR exists, ask the user whether to land the validated branch locally.
On explicit yes, operate from the primary checkout recorded in workspace.json:

1. Read its current branch. Require it to equal `base_branch`. If it moved,
   stop and ask; do not switch or merge.
2. Run `git -C <primary> checkout <base_branch>` only if needed after the check.
3. Run `git -C <primary> merge --no-ff <branch>`.
4. Run the sidecar's `defaults.gate_cmd` on the merged primary tree.

If the merged-tree check is red, stop. Leave the merge, workspace, and branch
in place for diagnosis. Send any code repair to a fresh executor; do not hide
the failed integration with cleanup.

## Ceremonies

After a completed merge, assemble one release list from the discovered repo
instructions, the plan document's `## Release requirements`, and all
`owner: user` phase rows. Execute only driver-safe, authorized items. Hand every
credentialed, infrastructure, destructive, or manual `owner: user` item to the
user explicitly. Do not claim a release step that was not measured.

## Evidence and cleanup

Before removing anything, preserve evidence:

    rsync -a <workspace>/<run>/ <primary>/.agents/build/runs/<slug>/

Run `git config --unset core.hooksPath`; tolerate only the exit that means the
key was absent.

After either merge path has completed:

1. Run `git status --porcelain` in the workspace.
2. If dirty, list every path and ask. Keep the worktree and branch.
3. If clean, remove the worktree without `--force` from the primary checkout.
4. Delete the merged branch with `git branch -d <branch>`.

The build allowlist in `<primary>/.claude/settings.local.json` stays; tell the
user it is there and removable by hand.

Keep the worktree while a PR remains open or when the user chooses to keep it.
Discard only on the user's explicit request and only after they type
`discard`. Confirm exact paths before any discard action.

## Handoff

Finish by writing `<run>/handoff.md` in ASCII with these headings exactly and
no others:

    ## Outcome
    ## Phases
    ## Defects
    ## Open
    ## Integration

Under Integration, record what the user chose and every exact command run.
Under Phases, include executor, wall time, files, gate, and judge verdict.
Under Defects, separate caught-before-merge from post-run findings with
file:line evidence. Under Open, list uncompleted release and `owner: user`
items. Ensure the evidence copy in the primary checkout contains this handoff.
