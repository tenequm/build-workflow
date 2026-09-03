# build-workflow - agent instructions

After meaningful skill or template edits, release with `just ship`, not a bare
`git push`. Plugin consumers only receive updates when the manifest version
changes; `ship` bumps both `plugin.json` files in sync, commits, and pushes.
Doc-only or internal changes may push without shipping.

The operator's own machines consume `skills/` via live symlinks from
`~/.claude/skills` (the `bwup` shell function), so local edits are live
immediately and need no install step.
