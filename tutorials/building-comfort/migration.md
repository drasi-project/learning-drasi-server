---
type: docs
title: Migrating Building Comfort to ComputationGraph
description: What changed to run this tutorial on the matching local Drasi Server and DrasiLib.
weight: 50
---

# Migrating Building Comfort to ComputationGraph

Building Comfort now builds and runs the ComputationGraph version of Drasi
Server from the existing sibling repositories. It still uses PostgreSQL,
the same six continuous queries, and the dashboard and log reactions. There
was no need to convert those plugins to native graph interfaces or replace
the tutorial with a different application.

These notes cover this tutorial's setup and walkthrough, not the qualification
of other tutorials.
For the runnable instructions, see the [Building Comfort tutorial](README.md).

## What had to change

| Area | Previous setup | Current setup |
| --- | --- | --- |
| Server selection | Downloaded `0.2.0-preview`; startup could also find an unrelated Server on `PATH` | Build the existing sibling `drasi-server` checkout, whose `drasi-lib` dependency points into sibling `drasi-core/lib` |
| Plugins | Automatically downloaded registry releases into a shared cache | Build the four required libraries from the same Core checkout, with `dynamic-plugin` enabled |
| Artifact selection | A binary's presence was enough | Keep a private matching bundle; verify Server and plugin hashes before every start; reject missing, changed or extra plugin files |
| Runtime selection | A setup could accidentally run the old downloaded Server | Require the live named instance to report `computationGraph`; there is no runtime-selection flag |
| HTTP examples | `requests.http` still used removed unscoped component routes | Address `/api/v1/instances/building-comfort-server/...` consistently |
| Readiness | A Server API startup log was treated as demo readiness | Require the instance, configured source, all six queries, both reactions, and predefined dashboard to be available |
| Database setup | Every start stopped the old database and removed its volume | Use a separate owned Compose project, seed only an empty database, and preserve existing readings on subsequent starts |
| Helpers | Separate Bash and PowerShell scripts, with differing behavior | One Python command implementation for build, startup, database changes, simulation and cleanup |
| Documentation | Release-download and one-click environment instructions | Existing-checkout build instructions, explicit state boundaries, actual expected results, and repeatable acceptance commands |

### Build Server and its plugins together

The required libraries are:

```text
drasi-source-postgres
drasi-bootstrap-postgres
drasi-reaction-dashboard
drasi-reaction-log
```

Changing only the Server executable is not sufficient. The old downloaded
plugins were built for a different SDK/ABI. The new helper builds the four
libraries from the same Core source used by Server rather than assuming that
a similarly named registry package will be compatible.

`python3 scripts/demo.py build` uses the existing Server Cargo target directory
unless `CARGO_TARGET_DIR` is set. It uses locked dependency resolution and writes
a private bundle under `.runtime/builds/<content-hash>/`. Build and verification
delegate to the repository's shared `scripts/local_build.py`. Plugins build
individually, and each artifact is copied before a later build can replace it
in the Cargo target directory. Database ownership, startup and cleanup remain
specific to this tutorial. The build record contains
the compiler version, Core/Server revisions, working-tree status and SHA256 of
each executable/library. Rebuild after changing either checkout. The old
`bin/drasi-server` and global plugin cache are not fallback locations.

Core's workspace lockfile is not tracked. On a checkout that has never resolved
its workspace dependencies, generate that lockfile once before the locked build:

```bash
# From tutorials/building-comfort/
RUSTUP_TOOLCHAIN=1.95.0 cargo generate-lockfile --manifest-path ../../../drasi-core/Cargo.toml
RUSTUP_TOOLCHAIN=1.95.0 python3 scripts/demo.py build
```

Locally compiled libraries do not have registry signatures. The launcher uses
`--skip-verification` only with its private, hash-checked bundle. This is a
local-development arrangement, not a recommendation to disable signature
verification for downloaded production plugins.

### Keep the ordinary source/query/reaction configuration

The configuration already had an explicit `building-comfort-server` instance.
The six queries use `inputs` to name their upstream components. `room-comfort`
reads the PostgreSQL source and declares the synthetic `joins`; floor, building
and alert queries consume the relevant upstream query outputs. Explicit result
labels name the nodes carried by their common graph-change format. The dashboard
and log reactions subscribe by query ID.

These interfaces create graph-owned components inside that instance's
ComputationGraph. An application does not need explicit native graph YAML,
an `executionMode` field, or a new query language just to use the new runtime.
`autoInstallPlugins` is now false because startup loads the prepared libraries
instead of downloading unrelated releases.

The source list also contains the library's internal `__component_graph__`
source. Its name does not indicate an old execution engine. Readiness accepts
that known internal source while still requiring every configured component.

### Treat source data and query state separately

The new Compose project defaults to `building-comfort-cg`; its container and
volume carry the tutorial's ownership label. It does not reuse or remove the
older `building-comfort` project's volume. Existing Server files under the
tutorial's former `data/` directory are also left alone.

This configuration uses memory-backed query indexes. On restart, queries
bootstrap from current PostgreSQL rows. `persistConfig: false` means imperative
API edits are not saved back into YAML, and this tutorial does not configure a
persistent dashboard state store. Restart therefore restores the declared
configuration and dashboard layout, not arbitrary in-memory edits.

Starting the demo no longer implies permission to reset its database.
`cleanup` preserves the volume; only `cleanup --volumes` requests deletion.
Cleanup refuses unowned resources and requires the foreground Server to have
stopped. It never kills all processes matching a name.

If a hard crash leaves `.runtime/server.lock`, inspect the recorded helper PID
and confirm that this demo is no longer running before removing that one lock
file. Do not delete runtime data or database volumes to get past a lock.

## Tutorial corrections found during the migration

These were mistakes or workarounds in the tutorial, not requirements imposed
by ComputationGraph:

1. **The building rollup dropped the floor before averaging.** The calculation
   now computes each floor's average from `RoomComfort` results, then computes
   the building average from `FloorComfort` results. An extra room on one floor
   makes this distinguishable from averaging all rooms directly.
2. **The KPI and gauge bypassed that rollup.** They now read
   `building-comfort-level-calc` directly instead of averaging the per-room
   view as a workaround. Both display the same building value as the query.
3. **One alert explanation was wrong.** Setting one room to `82 / 40 / 10`
   gives room comfort 58, but its floor average is exactly 50. Only the room
   alerts. The tutorial now has a separate two-cold-room exercise that really
   produces a building alert.
4. **Reset-all worked around old multi-row behavior.** It now issues one
   PostgreSQL update affecting all rooms. The acceptance check requires every
   query and dashboard snapshot to reflect every changed row.

The temperature/humidity/CO2 formula, table schema, synthetic relationships and
six calculation/alert roles remain the same. The shared room calculation is
named `room-comfort` rather than the UI-specific `building-comfort-ui`; the other
five query IDs are unchanged. The dashboard still receives real query changes;
the helper never fabricates results or sends sensor updates directly to Server.

## How to check the migrated tutorial

Run these commands from `tutorials/building-comfort/`.

```bash
# Helper and comparison regressions; no containers or Server needed:
python3 -m unittest discover -s scripts -p 'test_*.py' -v

# Terminal 1:
python3 scripts/demo.py start-demo

# Terminal 2: compare the current state without changing it:
python3 scripts/verify_demo.py

# Exercise the seeded demo, then restore its original sensor readings:
# Stop the simulator/other writers first. Requires the nine seeded rooms.
python3 scripts/verify_demo.py --exercise --output .runtime/acceptance.json
```

The exercise compares **all six Server result sets and all six dashboard
snapshots** against values calculated independently from PostgreSQL. It checks:

| Scenario | Required observation |
| --- | --- |
| Initial bootstrap | Nine rooms, three floors, one building; all comfort values 46; no alerts |
| One cold room | Room 4, floor 32, building approximately 41.3333; room/floor alerts only |
| Single-room reset | The room and its affected aggregates return to their expected values |
| One hot room | Room 58, floor exactly 50; no floor alert |
| Two cold rooms | Floor 18, building approximately 36.6667; building alert present |
| Multi-row reset | Every room and aggregate restored; every alert removed |
| Insert on one floor | Ten rooms; correct averages despite unequal floor sizes |
| Delete that room | Nine rooms again; no leftover result or dashboard row |
| Simulator | Three actual database changes reflected correctly |
| Identity | Updating a room does not create a new dashboard row identity |

The comparison rejects missing/extra rows, duplicate dashboard identities,
incorrect fields and wrong values. Floating-point averages permit absolute
error up to `1e-7`; row identities are read as strings, not rounded JavaScript
numbers. A healthy HTTP endpoint or a quiet period is not a result assertion.

For restart, change a room, record the results, stop Server normally, and run
`start-demo` again without deleting the database. Re-run the read-only check and
confirm the same values. Also open the dashboard and verify its live updates:
snapshot comparisons alone do not demonstrate browser rendering.

## Verified scope and limits

The local qualification used macOS arm64, Rust 1.95.0, PostgreSQL 14 in Podman,
Core `317c99e0` and Server `006b038`, with the Learning changes in this document.
The six-query exercises passed against real PostgreSQL CDC and the actual
dashboard plugin. The browser displayed live room, floor and building changes.
A separate unequal-floor browser check displayed building comfort `43.50`,
matching the floor rollup rather than the room-weighted value `43.00`.
A normal Server stop/reconstruction retained the changed source readings and
recreated the matching query and dashboard values.

The local dev-container definition mounts the sibling checkouts, installs
build prerequisites and builds the same source; its Rust feature is locked.
It reports a missing Core workspace lockfile before attempting the locked build.
That definition is updated, but a complete Linux dev-container runtime run
and native Windows execution are not part of this local qualification.
The documentation site is built separately with Hugo Extended 0.152.2.

This tutorial does **not** establish durable query-index recovery, recovery of
undelivered native pipe frames, crash-safe browser notifications, exactly-once
external effects, or in-place migration of old persisted formats. Nor does it
qualify every plugin, Server feature, or other tutorial.
