#!/usr/bin/env bash
set -euo pipefail

echo "Running build-harness check suite..."
mkdir -p build/reports

# Run unit and integration tests
cargo test --workspace -- --nocapture

echo "All check suites passed successfully."
