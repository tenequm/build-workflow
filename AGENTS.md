# build-workflow - agent instructions

After meaningful skill or template edits, release with `just ship`, not a bare
`git push`. Plugin consumers only receive updates when the manifest version
changes; `ship` bumps both `plugin.json` files in sync, commits, and pushes.
Doc-only or internal changes may push without shipping.

The operator's own machines consume `skills/` via live symlinks from
`~/.claude/skills` (the `bwup` shell function), so local edits are live
immediately and need no install step.

While a build session (`/build-plan` or `/build-run`) is active in a target
repo, no other session may commit or push to that repo's primary checkout:
the build's driver reads the primary's HEAD and settings, and a moving
primary caused a stop-and-verify incident on 2026-09-03. Land unrelated work
before the build starts or after it ends.

The three skills are self-contained: a skill never invokes another skill
(no `/polish`, `/grill-me`, or any other slash command) and never reads a
file from a sibling skill's directory. Each skill carries its own
`templates/`; a template two skills need is copied into both. Consumers
install the skills one at a time, and a skill that reaches outside itself
breaks for them.
