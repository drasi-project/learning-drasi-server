#!/bin/bash
# Copyright 2026 The Drasi Authors.
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

# Install the source/otel plugin.
#
# source/otel is not on ghcr.io/drasi-project until drasi-core PR 750 is
# published. This script builds libdrasi_source_otel from that PR and copies
# it into the tutorial plugin directory so Drasi Server can load kind: otel.
#
# First run clones drasi-core and compiles the crate (several minutes).
# Later runs are no-ops if the plugin file is already present.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUTORIAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLATFORM_DIR="$TUTORIAL_DIR/bin/$(uname -s)-$(uname -m)"
PLUGINS_DIR="${DRASI_PLUGINS_DIR:-$PLATFORM_DIR/plugins}"
SRC_DIR="${OTEL_PLUGIN_SRC:-$TUTORIAL_DIR/bin/otel-plugin-src}"
PR_REF="${OTEL_PLUGIN_PR:-750}"
RUST_IMAGE="${OTEL_PLUGIN_RUST_IMAGE:-rust:1.95.0-bookworm}"

mkdir -p "$PLUGINS_DIR"

plugin_artifact() {
    case "$(uname -s)" in
        Linux) echo "libdrasi_source_otel.so" ;;
        Darwin) echo "libdrasi_source_otel.dylib" ;;
        MINGW*|MSYS*|CYGWIN*) echo "drasi_source_otel.dll" ;;
        *) echo "libdrasi_source_otel.so" ;;
    esac
}

plugin_exists() {
    local name
    name="$(plugin_artifact)"
    if [ -f "$PLUGINS_DIR/$name" ]; then
        echo "$PLUGINS_DIR/$name"
        return 0
    fi
    return 1
}

if EXISTING="$(plugin_exists)"; then
    echo "source/otel already present: $EXISTING"
    exit 0
fi

echo "=== Installing source/otel from drasi-core PR #${PR_REF} ==="
echo "  Plugins: $PLUGINS_DIR"
echo "  Source:  $SRC_DIR"
echo

if [ ! -d "$SRC_DIR/.git" ]; then
    echo "Cloning drasi-core PR #${PR_REF} (shallow)..."
    rm -rf "$SRC_DIR"
    mkdir -p "$SRC_DIR"
    git clone --filter=blob:none --depth 1 https://github.com/drasi-project/drasi-core.git "$SRC_DIR"
    git -C "$SRC_DIR" fetch --depth 1 origin "pull/${PR_REF}/head"
    git -C "$SRC_DIR" checkout --detach FETCH_HEAD
else
    echo "Reusing existing checkout at $SRC_DIR"
fi

if command -v cargo >/dev/null 2>&1 && { [ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ]; }; then
    echo "Building drasi-source-otel with host cargo..."
    (cd "$SRC_DIR" && cargo build --lib -p drasi-source-otel --features dynamic-plugin --release)
    ARTIFACT=""
    for name in libdrasi_source_otel.dylib libdrasi_source_otel.so; do
        if [ -f "$SRC_DIR/target/release/$name" ]; then
            ARTIFACT="$name"
            break
        fi
    done
    if [ -z "$ARTIFACT" ]; then
        echo "Error: cargo build did not produce a source/otel cdylib"
        exit 1
    fi
    cp "$SRC_DIR/target/release/$ARTIFACT" "$PLUGINS_DIR/"
else
    if ! command -v docker >/dev/null 2>&1; then
        echo "Error: Docker is required to build source/otel on this platform."
        echo "Install Docker, or set DRASI_PLUGINS_DIR to a directory that already"
        echo "contains libdrasi_source_otel.so built from drasi-core PR #${PR_REF}."
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        echo "Error: Docker daemon is not running."
        exit 1
    fi

    echo "Building drasi-source-otel in $RUST_IMAGE (linux)..."
    docker pull "$RUST_IMAGE"
    docker run --rm \
        -v "$SRC_DIR":/src \
        -v drasi-otel-plugin-cargo:/usr/local/cargo/registry \
        -v drasi-otel-plugin-git:/usr/local/cargo/git \
        -v drasi-otel-plugin-target:/src/target \
        -w /src \
        "$RUST_IMAGE" \
        cargo build --lib -p drasi-source-otel --features dynamic-plugin --release

    docker run --rm \
        -v drasi-otel-plugin-target:/src/target \
        -v "$PLUGINS_DIR":/out \
        "$RUST_IMAGE" \
        bash -lc 'cp -v /src/target/release/libdrasi_source_otel.so /out/'
fi

if ! EXISTING="$(plugin_exists)"; then
    echo "Error: plugin was built but not found in $PLUGINS_DIR"
    exit 1
fi

echo
echo "✅ Installed source/otel → $EXISTING"
echo "   (unsigned local build; server-config.yaml sets verifyPlugins: false)"
