# Everything the pre-commit hooks check, on demand.
check:
    #!/usr/bin/env bash
    set -euo pipefail
    gitleaks git --redact -v
    test "$(jq -r '.name,.version' plugin.json)" = "$(jq -r '.name,.version' .claude-plugin/plugin.json)"
    sh skills/build-plan/scripts/plan-lint.sh --templates
    cmp -s skills/build-plan/templates/bernstein.yaml skills/build-run/templates/bernstein.yaml || (echo "bernstein.yaml template copies diverged" && exit 1)
    cmp -s skills/build-plan/templates/judge-prompt.md skills/build-run/templates/judge-prompt.md || (echo "judge-prompt.md template copies diverged" && exit 1)
    shellcheck skills/build-plan/scripts/*.sh
    claude plugin validate . --strict
    echo "check: clean"

# Bump the patch version in both plugin manifests, commit, and push.
# Plugin consumers only receive updates when the version changes.
ship:
    #!/usr/bin/env bash
    set -euo pipefail
    v=$(jq -r .version plugin.json)
    new="${v%.*}.$(( ${v##*.} + 1 ))"
    for f in plugin.json .claude-plugin/plugin.json; do
        jq --arg v "$new" '.version = $v' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    done
    git add plugin.json .claude-plugin/plugin.json
    git commit -m "chore: release v$new"
    git push
    echo "shipped v$new"
