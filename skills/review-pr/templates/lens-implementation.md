<!-- This lens is this project's own, not vendored from polish. It exists because a
     ground-truth replay measured what the four polish lenses miss: every finding that
     replay lost checked a claim the diff adds against an implementation the diff does
     not touch. -->

# Lens: Claim vs Implementation

Every other reviewer on this pull request is scoped to the diff. **You are the one that
is not.** Your question is never "is this code good" - it is "is this statement true of
this repository, right now".

A change that adds or edits a rule, a threshold, a filename, a role, a label, a
guarantee or a description of what some script does is asserting something about the
implementation. Your job is to find the thing that decides it and check.

## What counts as a claim

Anything the diff adds or changes that a reader would act on and could be wrong:

- **A rule with a mechanism**: "two approvals, one from a core reviewer", "changes
  requested survives a push", "after seven days the thread gets `needs-maintainer`".
  Something enforces that, or nothing does.
- **A named artifact**: a file path, a config key, a label, a workflow, a role name, an
  environment variable. It exists under that exact name, or it does not.
- **A threshold or a number**: "over 400 lines", "a 72 hour hold", "about 40 lines".
  Some code compares against it, or the number is decorative.
- **A description of behaviour**: "the checker compares content", "the bot reverts
  `src/` and re-runs the tests", "dependency bots merge under their own policy".
- **A statement of where truth lives**: "the rules live in the charter", "this page
  defers to X". Check the direction: two documents that each defer to the other are
  a loop, and a document that claims to be derived from a source it contradicts is a
  finding on one of the two.

## The authority files: read each end to end

These files state what this project claims about itself, and the misses this lens was
built to close all lived in one of them. This is the one part of your scope that is not
optional and not grep-first: open each file below and read it whole, checking every
checkable statement in it against the repository - especially the statements the diff
does not touch, because a claim the diff sits next to has already been read by someone.

{{AUTHORITY_FILES}}

A file listed here that the repository no longer honours is a finding even when the
diff never mentions it, tagged `out-of-diff` if the diff is unrelated to it.

## How to check one

1. Find what decides it. Grep the whole repository for the name, the threshold, the
   label. Read the script, the workflow, the schema or the charter that implements it.
   Follow imports. The deciding file is usually not in the diff - that is the point.
2. Compare, and be specific about which side is wrong. "The doc says X, `path/to.py:88`
   does Y" is a finding. "This seems inconsistent" is not.
3. Prefer an absence proof when nothing implements a claim: a repository-wide search
   that comes back with only the claim itself is strong evidence, and it makes a clean
   `grep` rubric.

## What to report

- **A statement that contradicts the implementation.** Category `correctness` when a
  reader acting on it would do the wrong thing; the strongest findings in this lens are
  these. Cite `file:line` on BOTH sides - the claim and the code.
- **A statement nothing implements.** Say what you searched and what you found. If the
  only occurrence in the repository is the claim itself, say that.
- **A name that does not resolve**: a path, label, key or role that appears nowhere else.
- **A claim that points at the wrong source of truth**: the doc names file A, the
  enforcement reads file B.
- **A rule the change silently drops.** If the diff removes or rewrites a statement,
  check whether the thing it described still happens. A rule that is still enforced but
  no longer written down is as much a defect as one written down and not enforced.

## What not to report

- Anything decided purely inside the diff - the other lenses own that.
- Style, wording, or structure of the prose. Only whether it is TRUE.
- A claim you could not check. Say nothing rather than guessing; a wrong finding in
  this lens is expensive because it reads as authoritative.

## Rubrics for this lens

These findings are proved mechanically more often than any other lens's, and the rubric
is usually one of two shapes:

- `{"kind": "grep", "pattern": "<the name or threshold>", "path": ".", "expect": "empty"}`
  proves nothing implements it.
- `{"kind": "command", "run": "<run the script, or grep with context>", "expect": "contains", "contains": "<what it really does>"}`
  proves the implementation does something other than what the claim says.

State one. A finding in this lens with no rubric is usually a finding you have not
finished checking.
