---
name: review-pr
description: "Review a GitHub pull request by handing one free-text review goal to the stock bernstein orchestrator in the target repo's checkout. Use /review-pr <number|url> on public repositories only. Bernstein owns spawning, models, budgets; the goal text carries the five-lens review doctrine and the report lands as review-report.md."
---

# review-pr

Hand the pull request to stock bernstein with this skill's goal text and seed.
Bernstein spawns the agents, routes the models, holds the budget, and writes
its receipts under `.sdd/`; the review doctrine lives entirely in
`templates/review-goal.md`, the model routing in `templates/review-seed.yaml`.

## Fence

Review PUBLIC repositories and the eval corpus only. The lanes run on
personal subscription accounts whose data-use terms are settled at the
account, not per run, and a reviewed tree can still reconfigure its own
reviewer: stock bernstein does not strip a hostile `opencode.json`,
`.agy/` or `.claude/` from the tree it checks out. Never point this at a
private repo, and never hand a model session a credential or a GitHub
token - the two fetch commands below are the only place `gh` runs.

## Invocation

From a checkout of the target repository (clone it under `~/pjv/<owner>/<repo>`
if needed), with the BASE commit of the pull request checked out:

    cd <checkout>
    gh pr diff <N> > .bernstein-pr.diff
    gh pr view <N> --json title,body --template '# {{.title}}

    {{.body}}' > .bernstein-pr.md
    bernstein run --seed <skill>/templates/review-seed.yaml \
      --goal "$(cat <skill>/templates/review-goal.md)" \
      --budget '$3.00' --auto-approve --quiet --wait 3000

The report is `review-report.md` at the checkout root; it ends with a fenced
json block of the findings. Read it, relay it. Nothing is ever posted to
GitHub by this skill.

Notes that cost time to learn:

- `bernstein run` blocks only with `--quiet` and `--wait`; `--headless` on the
  root group is a parsed no-op.
- The seed file must carry a `goal:` string even though `--goal` supplies the
  real one - the detached orchestrator re-parses the seed and refuses one
  without it.
- The two `.bernstein-pr.*` files are untracked, and agents work in worktrees
  cut from the base commit where untracked files are invisible; the seed's
  `worktree_setup.copy_files` is what carries them in.
