#!/usr/bin/env bash
# Runs once after the dev container / Codespace is created.
set -euo pipefail

echo "Pre-pulling the Drasi Server image so the tutorial starts quickly..."
docker pull ghcr.io/drasi-project/drasi-server:latest || \
  echo "Could not pre-pull the image; it will be pulled on first 'docker compose up'."

echo ""
echo "Dev container ready."
echo "To start the Getting Started tutorial:"
echo "  cd tutorial/getting-started && docker compose up"
