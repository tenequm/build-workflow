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
