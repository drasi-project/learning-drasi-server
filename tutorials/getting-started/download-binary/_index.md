---
type: "docs"
title: "Setup: Local Source Build"
linkTitle: "Local Source Build"
weight: 5
toc_hide: true
description: "Build matching local Drasi Server, Core plugins, and SSE CLI"
---

This tutorial requires the current local ComputationGraph implementation.
A released binary or a published plugin is not a substitute for your local
Server/Core checkout.

Place the existing `learning-drasi-server`, `drasi-server`, and `drasi-core`
checkouts alongside one another. Keep their matching branches and local edits.
Do not copy a similarly named checkout from another workspace.

Install Rust 1.95.0, Python 3.11+, curl, Podman, and the native build dependencies
documented by the local Server/Core repositories (including a C/C++ toolchain,
libclang, OpenSSL, jq/oniguruma, protobuf, pkg-config, and CMake).
The [Dev Container](../dev-container/) prepares the Linux prerequisites.

From `learning-drasi-server/tutorials/getting-started`:

```bash
cp .env.example .env
python3 scripts/demo.py build
python3 scripts/demo.py build-cli
python3 scripts/demo.py verify-build
```

The build commands create private, verified artifacts and provenance under
`.runtime/build`. Source path dependencies do not rebuild dynamically loaded
plugins automatically, so the build explicitly compiles all six required
plugins. Start and stream helpers reject mismatched artifacts rather than
silently downloading them. `scripts/download.sh` now delegates to the local
Server/plugin build; it no longer downloads releases.

On Windows use WSL2 or the Dev Container with the bash walkthrough. The old
PowerShell downloader exits with setup guidance rather than installing a
different runtime.

[Continue with the tutorial](../#database).
