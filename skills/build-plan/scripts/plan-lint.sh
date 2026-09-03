#!/bin/sh
# Fast pre-readiness lint. Catches in seconds the mechanical defects that
# otherwise cost a full readiness pass: briefs over the 16,000-char cap,
# executor/fix briefs whose ## Validation is not a fenced block, and active
# git hooks that readiness will refuse. Judge briefs (blind review) carry no
# Validation block by design and are size-checked only.
# Usage: plan-lint.sh <briefs-dir>   (run from the workspace root)
set -eu

# --templates: check this repo's own brief templates still carry a fenced
# Validation block, so generated briefs cannot fail readiness. Used by lefthook.
if [ "${1:-}" = "--templates" ]; then
  fail=0
  for f in skills/build-plan/templates/brief.md skills/build-plan/templates/fix-brief.md; do
    awk '/^## Validation/{v=1} v&&/^```/{f=1} END{exit !f}' "$f" || {
      echo "FAIL $f: lost its fenced Validation block"
      fail=1
    }
  done
  [ "$fail" -eq 0 ] && echo "plan-lint: templates clean"
  exit "$fail"
fi

dir=${1:?usage: plan-lint.sh <briefs-dir> | --templates}
fail=0
for f in "$dir"/*.md; do
  [ -e "$f" ] || continue
  chars=$(wc -m < "$f")
  if [ "$chars" -gt 16000 ]; then
    echo "FAIL $f: $chars chars, over the 16000 cap"
    fail=1
  fi
  if ! grep -qi "blind review" "$f"; then
    if ! perl -0777 -ne 'exit(/##\s*Validation[^\n]*\n(?:[^\n]*\n)*?```/ ? 0 : 1)' "$f"; then
      echo "FAIL $f: no fenced \`## Validation\` block"
      fail=1
    fi
  fi
done
# --git-common-dir, not .git: in a linked worktree .git is a file and the hooks
# live in the main checkout, which is exactly where this script is documented to run.
hooks_dir="$(git rev-parse --git-common-dir 2>/dev/null || echo .git)/hooks"
if [ -z "$(git config core.hooksPath || true)" ] && ls "$hooks_dir/pre-commit" "$hooks_dir/pre-push" >/dev/null 2>&1; then
  echo "FAIL: active git hooks; point core.hooksPath at an empty repo-local directory before readiness"
  fail=1
fi
[ "$fail" -eq 0 ] && echo "plan-lint: clean"
exit "$fail"
