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
    python3 scripts/kb_index.py --check
    python3 scripts/skill_isolation.py
    claude plugin validate . --strict
    just --justfile bernstein_operator/Justfile check
    echo "check: clean"

# Review one GitHub pull request end to end, into ~/pj/reviews/<owner>-<repo>-pr<n>.
# Re-running against an existing workspace resumes it: stage products and session
# receipts on disk are re-read, never re-executed.
review url:
    #!/usr/bin/env bash
    set -euo pipefail
    url='{{url}}'
    slug=$(printf '%s\n' "$url" | sed -nE 's#^(https?://github\.com/)?([^/]+/[^/]+)/pull/([0-9]+).*#\2#p')
    number=$(printf '%s\n' "$url" | sed -nE 's#^(https?://github\.com/)?([^/]+/[^/]+)/pull/([0-9]+).*#\3#p')
    if [ -z "$slug" ] || [ -z "$number" ]; then
        echo "not a pull request URL: {{url}}" >&2
        exit 1
    fi
    repo="${INVOCATION_DIRECTORY:-$PWD}"
    if ! git -C "$repo" remote get-url origin 2>/dev/null | grep -qiF "$slug"; then
        repo="$HOME/pjv/$(printf '%s' "$slug" | tr '[:upper:]' '[:lower:]')"
    fi
    if [ ! -d "$repo/.git" ]; then
        echo "no local checkout of $slug: clone it to $repo first (setup reads the base branch from it)" >&2
        exit 1
    fi
    workspace="$HOME/pj/reviews/$(printf '%s' "$slug" | tr '/' '-')-pr$number"
    mkdir -p "$(dirname "$workspace")"
    python="$(pwd)/bernstein_operator/.venv/bin/python"
    cli="$(pwd)/skills/review-pr/scripts/review-pr.py"
    "$python" "$cli" ready
    code=0
    "$python" "$cli" setup --dest "$workspace" --pr "$number" -R "$slug" --repo-path "$repo" || code=$?
    # Exit 2 is setup's small-diff refusal, and it is advice for the operator, not an
    # error to override: the driver overhead loses to an interactive review down there.
    if [ "$code" -ne 0 ]; then
        exit "$code"
    fi
    "$python" "$cli" run --dest "$workspace"

# Score the /review-pr eval corpus. No argument runs every floor and bar case on the
# fast-loop template, four at a time; pass case or tier names and any harness flag
# (--jobs N, --stages <template>) to narrow or re-route it.
eval *ARGS:
    python3 fixtures/review-pr-cases/harness.py {{ARGS}}

# Provision the pinned pond into the operator venv (see review_pr/pondsync.py PINNED).
install-pond version="0.17.2":
    sh scripts/install-pond.sh {{version}}

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
