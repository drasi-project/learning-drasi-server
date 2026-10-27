#!/usr/bin/env bash
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
set -euo pipefail
cd "$(dirname "$0")/../../tutorials/getting-started"
test -f ../../../drasi-server/Cargo.toml && test -f ../../../drasi-core/Cargo.toml || {
    echo "Existing sibling drasi-server and drasi-core checkouts are required." >&2
    exit 1
}

packages=(podman uidmap slirp4netns fuse-overlayfs python3 curl ca-certificates
          build-essential pkg-config clang libclang-dev libssl-dev libjq-dev
          libonig-dev protobuf-compiler cmake)
missing=()
for package in "${packages[@]}"; do
    dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -qx 'install ok installed' ||
        missing+=("$package")
done
if ((${#missing[@]})); then
    sudo apt-get update
    sudo apt-get install -y "${missing[@]}"
fi
if ! grep -q '^vscode:' /etc/subuid; then
    sudo usermod --add-subuids 100000-165535 vscode
fi
if ! grep -q '^vscode:' /etc/subgid; then
    sudo usermod --add-subgids 100000-165535 vscode
fi
podman info >/dev/null
bash ../../.devcontainer/getting-started/install-evaluation-tools.sh
echo "Build prerequisites ready. Follow README.md to build matching local Server/Core and SSE CLI."
echo "Setup does not start Cargo automatically; coordinate builds when sharing a target directory."
