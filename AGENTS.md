# build-workflow - agent instructions

After meaningful skill or template edits, release with `just ship`, not a bare
`git push`. Plugin consumers only receive updates when the manifest version
changes; `ship` bumps both `plugin.json` files in sync, commits, and pushes.
Doc-only or internal changes may push without shipping.

The operator's own machines consume `skills/` via live symlinks from
`~/.claude/skills` (the `bwup` shell function), so local edits are live
immediately and need no install step.

A build occupies only its workspace branch: the plan commits nothing to the
primary (workspace-at-first-write, 2026-09-04), so other sessions may work on
main freely while a build runs; primary drift is resolved by /build-close's
merge. The one shared file is the primary's `.claude/settings.local.json`,
written once at workspace creation.

The three skills are self-contained: a skill never invokes another skill
or slash command and never reads a file from a sibling skill's directory. Each skill carries its own
`templates/`; a template two skills need is copied into both. Consumers
install the skills one at a time, and a skill that reaches outside itself
breaks for them.

A retro item closes only as a check, a template field, or a test - never as
another skill sentence.
