#!/usr/bin/env bash
# Provision the pinned pond binary into the operator venv, like the bernstein dep:
# the workflow never depends on whatever pond the host happens to carry. The pin
# lives in skills/review-pr/scripts/review_pr/pondsync.py (PINNED) and here.
set -euo pipefail

VERSION="${1:-0.17.2}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/bernstein_operator/.venv/bin"
ARCH="$(uname -m)-unknown-linux-gnu"
ASSET="pond-$ARCH.tar.xz"
URL="https://github.com/tenequm/pond/releases/download/v$VERSION/$ASSET"

if [ ! -d "$DEST" ]; then
    echo "no operator venv at $DEST - run uv sync in bernstein_operator first" >&2
    exit 1
fi
if [ -x "$DEST/pond" ] && "$DEST/pond" --version 2>/dev/null | grep -q " $VERSION\$"; then
    echo "pond $VERSION already provisioned at $DEST/pond"
    exit 0
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
curl -fsSL "$URL" -o "$work/$ASSET"
curl -fsSL "https://github.com/tenequm/pond/releases/download/v$VERSION/checksums.txt" \
    -o "$work/checksums.txt"
(cd "$work" && grep " $ASSET\$" checksums.txt | sha256sum -c -)
tar -xJf "$work/$ASSET" -C "$work"
found="$(find "$work" -type f -name pond | head -1)"
install -m 0755 "$found" "$DEST/pond"
"$DEST/pond" --version
echo "pond $VERSION provisioned at $DEST/pond"
