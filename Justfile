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
    python3 scripts/review_prompt_boundaries.py
    claude plugin validate . --strict
    just operator-check
    echo "check: clean"

operator_python_paths := "src tests scripts ../scripts/review_prompt_boundaries.py ../skills/build-run/scripts ../skills/build-plan/scripts ../skills/build-close/scripts ../fixtures/review-pr-cases/harness.py"

# Non-mutating Python/operator checks, also run by `just check` and the staged hook.
operator-check:
    cd bernstein_operator && uv run python scripts/sync-skill-code.py --check
    cd bernstein_operator && uv run ty check src ../scripts/review_prompt_boundaries.py ../skills/build-run/scripts ../skills/build-plan/scripts/plan-check.py ../skills/build-close/scripts ../fixtures/review-pr-cases/harness.py
    cd bernstein_operator && uv run ruff check --config pyproject.toml {{operator_python_paths}}
    cd bernstein_operator && uv run ruff format --check --config pyproject.toml {{operator_python_paths}}

# Exercise the installed plugin against an isolated, patched copy of the source engine.
test *ARGS:
    cd bernstein_operator && uv run python scripts/acceptance.py {{ARGS}}

fix:
    cd bernstein_operator && uv run ruff check --fix --config pyproject.toml {{operator_python_paths}}
    cd bernstein_operator && uv run ruff format --config pyproject.toml {{operator_python_paths}}
    cd bernstein_operator && uv run python scripts/sync-skill-code.py

install:
    cd bernstein_operator && uv sync --all-groups

update:
    cd bernstein_operator && uv lock --upgrade
    cd bernstein_operator && uv sync --all-groups

# Score the /review-pr eval corpus. No argument runs all four cases through a stock
# bernstein review, four at a time; `just eval case-01-off-by-one` is the smoke case run
# after an engine or seed change. Any harness flag (--jobs N, --goal <template>,
# --seed <config>, --budget N) passes straight through.
eval *ARGS:
    python3 fixtures/review-pr-cases/harness.py {{ARGS}}

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
