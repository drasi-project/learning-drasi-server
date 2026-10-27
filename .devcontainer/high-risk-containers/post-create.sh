#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ ! -f "$REPO_ROOT/../drasi-server/Cargo.toml" ] || [ ! -f "$REPO_ROOT/../drasi-core/lib/Cargo.toml" ]; then
    echo "Existing sibling drasi-server and drasi-core checkouts are required; no release fallback."
    exit 1
fi

sudo apt-get update
sudo apt-get install -y build-essential cmake clang libclang-dev pkg-config \
    libjq-dev libssl-dev protobuf-compiler python3 postgresql-client

case "$(uname -m)" in
    x86_64) architecture=amd64; checksum=dbaa79a76ace7f4ca230a1ff41dc7d8a5036a8ad0309e9c54f9bf3836dbe853e ;;
    aarch64) architecture=arm64; checksum=0b8110f2229631af7402fb828259330985918b08fefd38b7f1b788a1c8687216 ;;
    *) echo "Unsupported k3d architecture: $(uname -m)"; exit 1 ;;
esac
temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
curl -fL "https://github.com/k3d-io/k3d/releases/download/v5.8.3/k3d-linux-$architecture" -o "$temporary"
echo "$checksum  $temporary" | sha256sum --check
sudo install -m 0755 "$temporary" /usr/local/bin/k3d

cd "$REPO_ROOT/tutorials/high-risk-containers"
python3 scripts/demo.py build
echo "Matching local Server/Core/plugins built. Follow README.md to start the owned demo."
