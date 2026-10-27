---
type: "docs"
title: "Setup: Dev Container"
linkTitle: "Dev Container"
weight: 20
toc_hide: true
description: "Use existing sibling checkouts in a local development container"
---

Use VS Code with the Dev Containers extension and a working local container
engine. When using Podman to launch the Dev Container, configure VS Code's
Dev Containers Docker Path setting to `podman`.

Before opening the container, ensure the **existing** `learning-drasi-server`,
`drasi-server`, and `drasi-core` checkouts share a parent directory. Open
`learning-drasi-server` in VS Code, choose **Reopen in Container**, then
**Drasi Server - Getting Started Tutorial**.

The configuration mounts that parent at `/workspaces`, opens
`tutorials/getting-started`, and installs Rust 1.95 plus native build
prerequisites. It uses Podman **inside** the privileged development container
for the tutorial's database; it does not mount a host Docker socket or join a
shared tutorial network. Use this privileged development environment only
with trusted local source. The Rust target lives inside the development
container, not in the host's macOS/Windows target directory.

Post-create checks the sibling paths and Podman readiness. It does not clone,
download a released Server, fetch published plugins, or start Cargo implicitly.
Follow the main tutorial's explicit build commands:

```bash
cp .env.example .env
python3 scripts/demo.py build
python3 scripts/demo.py build-cli
python3 scripts/demo.py verify-build
```

The first Rust build can take considerable time and disk space. If you share
the target with other sessions, serialize builds. A missing prerequisite or
inaccessible sibling checkout must be fixed; there is no registry fallback.

Ports `8180` (API), `8181` (SSE), `8182` (HTTP Source), `5532` (PostgreSQL), and
`5173` (optional viewer) are forwarded. Keep them private. Run CLI and SQL
commands inside the Dev Container so loopback refers to the same environment
as Server and its PostgreSQL container.

[Continue with the tutorial](../#database).
