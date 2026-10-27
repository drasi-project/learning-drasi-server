#!/usr/bin/env python3
"""Build and verify this tutorial's SSE CLI without downloading an alternative."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT.parents[2] / "drasi-server" / "target"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    paths = [ROOT / "Cargo.toml", ROOT / "Cargo.lock", ROOT / "scripts/build.py"]
    paths.extend(sorted((ROOT / "src").rglob("*.rs")))
    return {str(path.relative_to(ROOT)): sha256(path) for path in paths}


def atomic_write(path, data, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.flush()
            if executable:
                temporary.chmod(0o755)
            output.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def verify(destination, state):
    provenance = json.loads(state.read_text())
    if provenance.get("schema") != 1:
        raise ValueError("Unsupported SSE CLI provenance schema; rebuild with this script")
    if provenance.get("sourceRoot") != str(ROOT):
        raise ValueError("SSE CLI provenance names a different source checkout; rebuild here")
    if provenance.get("sources") != source_hashes():
        raise ValueError("SSE CLI source files changed; rebuild before running the tutorial")
    if provenance.get("destination") != str(destination):
        raise ValueError("SSE CLI provenance names a different installed destination")
    if provenance.get("sha256") != sha256(destination):
        raise ValueError("Installed SSE CLI does not match its recorded SHA256; rebuild")
    return provenance


def build(args):
    before = source_hashes()
    environment = os.environ.copy()
    if environment.get("CARGO_BUILD_TARGET"):
        raise ValueError("Unset CARGO_BUILD_TARGET before building the local SSE CLI")
    environment.update(CARGO_BUILD_JOBS="1", CARGO_NET_OFFLINE="true")
    prefix = ["rustup", "run", args.toolchain]
    command = prefix + [
        "cargo", "build", "--manifest-path", str(ROOT / "Cargo.toml"),
        "--target-dir", str(args.target_dir), "--offline", "--locked", "-j", "1",
        "--bin", "drasi-sse-cli",
    ]
    if args.profile == "release":
        command.append("--release")
    rustc = subprocess.check_output(
        prefix + ["rustc", "--version", "--verbose"], text=True, env=environment
    ).strip()
    print("Building tutorial SSE CLI: " + " ".join(command), flush=True)
    subprocess.run(command, check=True, env=environment)
    if source_hashes() != before:
        raise ValueError("SSE CLI sources changed during the build; rerun before installing")
    filename = "drasi-sse-cli.exe" if os.name == "nt" else "drasi-sse-cli"
    artifact = args.target_dir / args.profile / filename
    binary = artifact.read_bytes()
    atomic_write(args.destination, binary, executable=True)
    provenance = {
        "schema": 1,
        "sourceRoot": str(ROOT),
        "sources": before,
        "destination": str(args.destination),
        "sha256": hashlib.sha256(binary).hexdigest(),
        "artifact": str(artifact),
        "command": command,
        "rustc": rustc,
        "environment": {
            key: environment[key] for key in (
                "CARGO_BUILD_JOBS", "CARGO_NET_OFFLINE", "CARGO_INCREMENTAL",
                "CARGO_PROFILE_DEV_DEBUG", "CARGO_PROFILE_DEV_STRIP",
                "CARGO_PROFILE_TEST_DEBUG", "RUSTFLAGS",
            ) if key in environment
        },
    }
    atomic_write(args.state, (json.dumps(provenance, indent=2) + "\n").encode())
    verify(args.destination, args.state)
    print(f"Installed {args.destination}\nSHA256 {provenance['sha256']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True, help="Exact installed binary path")
    parser.add_argument("--state", type=Path, required=True, help="Provenance JSON file")
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--profile", choices=("debug", "release"), default="debug")
    parser.add_argument("--toolchain", default="1.95.0")
    parser.add_argument("--verify-only", action="store_true", help="Verify without building or running Cargo")
    args = parser.parse_args()
    args.destination = args.destination.expanduser().resolve()
    args.state = args.state.expanduser().resolve()
    args.target_dir = args.target_dir.expanduser().resolve()
    try:
        if args.destination == args.state:
            raise ValueError("Binary destination and provenance file must be different")
        if args.verify_only:
            provenance = verify(args.destination, args.state)
            print(f"Verified {args.destination}\nSHA256 {provenance['sha256']}")
        else:
            if not shutil.which("rustup"):
                raise ValueError("rustup is required; install the requested toolchain before building")
            build(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"SSE CLI build/verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
