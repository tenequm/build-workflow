---
type: Finding
title: A recorded agent that does the right thing for the wrong reason hides a brief defect
description: Every stage-2 session of the first paid review run exited 0 having written nothing, because the brief named an absolute path to a shared tree while each session is validated against its own worktree - a defect the recording-agent fixture could never surface, because that agent resolves its output path from its working directory and never reads the instruction at all.
tags: [testing, fixtures, briefs, review-pr, acceptance]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T09:20:00Z" }
sources:
  - id: run
    resource: "First paid /review-pr run, 2026-09-11, against sipyourdrink-ltd/bernstein#5737: seven stage-2 sessions, seven reports written outside every session's worktree"
    title: The run that surfaced it
  - id: guard
    resource: ../../../skills/review-pr/scripts/review_pr/briefs.py
    title: briefs.guard, which now refuses any brief naming the shared tree
  - id: agent
    resource: ../../../fixtures/review-pr/recording_agent.py
    title: The recording agent whose path handling masked the defect
  - id: acceptance
    resource: ../../operator-acceptance.md
    title: The acceptance map - what each recorded layer does and does not reach
---

# What happened

Each review session gets its own detached worktree and is validated against it: a
session that writes anything but its declared report parks the stage. The reviewer brief
said, in as many words, *"Write exactly one file and no others: `reports/findings-X.json`,
relative to `/abs/path/to/the/shared/tree`"*.

Every model obeyed exactly. Seven sessions read the diff, did the work, wrote a
well-formed report into the shared tree, and exited 0. The driver looked in each
session's own worktree, found nothing, and - correctly - recorded seven failed attempts,
retried once, and reported an honest failure.[^run]

The report-witness law did its job perfectly. The brief was the defect.

# Why the fixture could not catch it

The fixture runs the whole pipeline over the real ACP transport against a recording
agent, and it passed on every run. It passed because the recording agent computes its
output path as `Path(report)` against its own working directory.[^agent] It never reads
"relative to <absolute path>" because it never reads the sentence at all - it extracts
the report path with a regex and writes it where it happens to be standing.

Which is the correct behaviour, by luck. A real model reads the whole sentence and
honours the absolute path in it. So the fixture agreed with the driver for a reason the
driver could not rely on, and the two only disagreed when something arrived that
actually read English.

# The general shape

A recorded agent is a stand-in for a model's *judgment*, and this repository leans on
that heavily - it is what makes the acceptance suite free to run.[^acceptance] But every
recorded agent also stands in for a model's *obedience*, and there it is not a stand-in
at all: it obeys a regex, not a brief. Anything a brief says that the recording agent
does not parse is, for testing purposes, unsaid.

So a recorded fixture proves that the plumbing around an instruction works. It cannot
prove the instruction is right. Three properties fall in that blind spot:

- **where** an agent is told to write, read, or look;
- **what** a brief forbids, since the recorder never tries the forbidden thing;
- **which** of several paths or names the brief picks out, when the recorder derives its
  own.

# What was done about it

A runtime guard rather than another test: `briefs.guard` refuses to build any brief that
names the shared reviewed tree, so the class cannot recur silently even in a brief
nobody re-reads.[^guard] The brief now resolves every write target against the working
directory and says so explicitly.

The reusable rule is narrower than "recorded agents are insufficient": **when a brief
tells an agent where to put something, the test that the brief is right cannot be
written with an agent that derives the location itself.** Either the recorder must honour
the instruction the way a model would, or the constraint belongs in code that runs
before the session, where it can be checked without a model at all.
