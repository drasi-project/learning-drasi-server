#!/bin/bash
# Copyright 2025 The Drasi Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Drasi Server Install Script
# Auto-detects platform and downloads the correct drasi-server binary.

set -e

# TEMPORARY: pinned to the 0.2.0-preview pre-release (plugin-sdk 0.9.0) so the
# reaction/dashboard plugin loads on Linux. Revert to
# ".../releases/latest/download" once a stable sdk-0.9.0 drasi-server is released.
REPO_URL="https://github.com/drasi-project/drasi-server/releases/download/0.2.0-preview"
INSTALL_DIR="bin"

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Darwin)
        case "$ARCH" in
            arm64)  PLATFORM_SUFFIX="aarch64-apple-darwin" ;;
            x86_64) PLATFORM_SUFFIX="x86_64-apple-darwin" ;;
            *) echo "Error: Unsupported macOS architecture: $ARCH"; exit 1 ;;
        esac
        ;;
    Linux)
        if ldd --version 2>&1 | grep -q musl; then
            LIBC="musl"
        else
            LIBC="gnu"
        fi
        case "$ARCH" in
            x86_64)        PLATFORM_SUFFIX="x86_64-linux-$LIBC" ;;
            aarch64|arm64) PLATFORM_SUFFIX="aarch64-linux-$LIBC" ;;
            *) echo "Error: Unsupported Linux architecture: $ARCH"; exit 1 ;;
        esac
        if [ "$LIBC" = "musl" ]; then
            echo "Note: musl libc detected. Ensure libstdc++ and libgcc are installed:"
            echo "  apk add --no-cache libstdc++ libgcc"
        fi
        ;;
    *)
        echo "Error: Unsupported operating system: $OS"
        echo "For Windows, use download.ps1 instead."
        exit 1
        ;;
esac

echo "Detected: $OS ($ARCH)"

mkdir -p "$INSTALL_DIR"

SERVER_BINARY="drasi-server-$PLATFORM_SUFFIX"
echo "Downloading: $SERVER_BINARY"
curl -fsSL "$REPO_URL/$SERVER_BINARY" -o "$INSTALL_DIR/drasi-server"
chmod +x "$INSTALL_DIR/drasi-server"

echo
echo "Verifying installation..."
"$INSTALL_DIR/drasi-server" --version

echo
echo "✅ Drasi Server installed to $INSTALL_DIR/drasi-server"
