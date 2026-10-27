#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Build and verify a tutorial's matching local Server and Core plugin bundle.

Tutorial helpers call build(state, plugins, server_repo=None) and
verified_build(state, plugins). They retain ownership of their own configuration,
databases, ports and processes. This module never starts services, downloads
released Drasi artifacts, switches branches, or manages database state.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib


REPOSITORY = Path(__file__).resolve().parent.parent


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _plugins(plugins):
    plugins = tuple(plugins)
    if not plugins or len(set(plugins)) != len(plugins):
        raise ValueError("Supply a nonempty list of distinct Core plugin package names")
    if any(not re.fullmatch(r"drasi-[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in plugins):
        raise ValueError("Invalid Core plugin package name")
    return plugins


def _run(argv, *, cwd, capture=False):
    print("+", " ".join(map(str, argv)), flush=True)
    result = subprocess.run(
        list(map(str, argv)), cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout


def _roots(server_repo):
    server = Path(server_repo or os.environ.get(
        "DRASI_SERVER_REPO", REPOSITORY.parent / "drasi-server")).resolve()
    core = server.parent / "drasi-core"
    manifest = server / "Cargo.toml"
    if not manifest.is_file() or not (core / "lib/Cargo.toml").is_file():
        raise RuntimeError(
            "Build requires existing sibling drasi-server/ and drasi-core/ checkouts; "
            "this helper does not clone or switch branches."
        )
    dependency = tomllib.loads(manifest.read_text())["dependencies"]["drasi-lib"]
    if not isinstance(dependency, dict) or "path" not in dependency \
            or (server / dependency["path"]).resolve() != core / "lib":
        raise RuntimeError("Server must use the sibling drasi-core/lib path dependency")
    if not (core / "Cargo.lock").is_file():
        raise RuntimeError(
            "The Core workspace Cargo.lock is missing. Before this locked build, run: "
            f"cargo generate-lockfile --manifest-path {core / 'Cargo.toml'}"
        )
    if os.environ.get("CARGO_BUILD_TARGET"):
        raise RuntimeError(
            "This helper builds host-local artifacts; unset CARGO_BUILD_TARGET "
            "instead of selecting a cross-compiled or stale native library."
        )
    return server, core


def build(state, plugins, server_repo=None):
    """Build only the requested local artifacts and atomically select their bundle.

    Stop the tutorial first. Concurrent builds sharing one Cargo target must be
    serialized by the caller. Packages are built individually so dynamic-plugin
    features from unrelated plugin packages are not unified.
    """
    plugins = _plugins(plugins)
    state = Path(state).resolve()
    if (state / "server.lock").exists():
        raise RuntimeError("Stop this demo before rebuilding; server.lock is present")
    server, core = _roots(server_repo)
    target = Path(os.environ.get("CARGO_TARGET_DIR", server / "target")).resolve()
    common = ["--locked", "--target-dir", target]
    state.mkdir(parents=True, exist_ok=True)
    extension = ".dll" if sys.platform == "win32" else ".dylib" if sys.platform == "darwin" else ".so"
    prefix = "" if sys.platform == "win32" else "lib"
    binary = "drasi-server.exe" if sys.platform == "win32" else "drasi-server"

    # Copy each artifact before a later package build can replace shared outputs.
    with tempfile.TemporaryDirectory(prefix="build-", dir=state) as directory:
        staging = Path(directory)
        (staging / "plugins").mkdir()
        files = {}
        _run(["cargo", "build", "--manifest-path", server / "Cargo.toml", *common,
              "--bin", "drasi-server"], cwd=server)
        files["server"] = staging / binary
        shutil.copy2(target / "debug" / binary, files["server"])
        for package in plugins:
            _run(["cargo", "build", "--manifest-path", core / "Cargo.toml", *common,
                  "-p", package, "--lib", "--features", "dynamic-plugin"], cwd=core)
            name = prefix + package.replace("-", "_") + extension
            files[package] = staging / "plugins" / name
            shutil.copy2(target / "debug" / name, files[package])
        hashes = {name: sha256(path) for name, path in files.items()}
        identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        bundle = state / "builds" / identity
        (bundle / "plugins").mkdir(parents=True, exist_ok=True)
        artifacts = {}
        for name, source in files.items():
            destination = (bundle if name == "server" else bundle / "plugins") / source.name
            if not destination.exists():
                shutil.copy2(source, destination)
            if sha256(destination) != hashes[name]:
                raise RuntimeError(f"Artifact copy/hash mismatch: {destination}")
            artifacts[name] = {"path": str(destination), "sha256": hashes[name]}
        record = {
            "runtime": "computationGraph",
            "artifacts": artifacts,
            "rustc": _run(["rustc", "--version"], cwd=server, capture=True).strip(),
            "repositories": {
                name: {
                    "revision": _run(["git", "-C", path, "rev-parse", "HEAD"],
                                     cwd=server, capture=True).strip(),
                    "status": _run(["git", "-C", path, "status", "--short"],
                                   cwd=server, capture=True),
                } for name, path in (("drasi-server", server), ("drasi-core", core))
            },
        }
        temporary = state / "build.json.tmp"
        temporary.write_text(json.dumps(record, indent=2) + "\n")
        temporary.replace(state / "build.json")
    verified_build(state, plugins)
    print(f"Built local Server and {len(plugins)} matching plugins: {state / 'build.json'}")


def verified_build(state, plugins):
    """Return the verified Server executable and exact requested plugin directory.

    The record describes a specific build, not automatic freshness after source
    edits. Rebuild after changing Core or Server. No global cache or PATH fallback
    is used when an artifact is missing or has changed.
    """
    plugins = _plugins(plugins)
    path = Path(state).resolve() / "build.json"
    if not path.is_file():
        raise RuntimeError("No local build record. Run this tutorial's local build command first.")
    record = json.loads(path.read_text())
    if record["runtime"] != "computationGraph":
        raise RuntimeError("Build record does not identify the ComputationGraph runtime")
    artifacts = record["artifacts"]
    if set(artifacts) != {"server", *plugins}:
        raise RuntimeError("Build record must contain Server and exactly the required plugins")
    for artifact in artifacts.values():
        file = Path(artifact["path"])
        if not file.is_file() or sha256(file) != artifact["sha256"]:
            raise RuntimeError(f"Missing or changed local artifact: {file}; rebuild the demo")
    directory = Path(artifacts[plugins[0]]["path"]).parent
    expected = {Path(artifacts[name]["path"]) for name in plugins}
    if any(file.parent != directory for file in expected):
        raise RuntimeError("Build record plugins must share one private directory")
    if set(directory.iterdir()) != expected:
        raise RuntimeError(f"Unexpected files in the private plugin directory: {directory}")
    return Path(artifacts["server"]["path"]), directory
