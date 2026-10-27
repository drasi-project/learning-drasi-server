---
type: "docs"
title: "OTel Observability"
linkTitle: "OTel Observability"
weight: 40
description: >
  Correlate Kubernetes rollouts, OpenTelemetry health, and a PostgreSQL SLO policy using shared continuous-query results and a live dashboard.
---

OpenTelemetry collects signals. Operators still need to decide whether a rollout,
a latency spike, and a downstream dependency describe the same incident.

This tutorial builds that correlation layer on **Drasi Server**. Three mock store
services (`frontend`, `checkout`, `payments`) run in Kubernetes and export real
request timings and CLIENT spans through an in-cluster OTel Collector. Drasi
watches their Deployments, live p99 gauges, and a PostgreSQL SLO policy. The
dashboard shows an alert **Added** when a regression persists and **Removed**
when it recovers. You change the originating systems, not Drasi's result data.

**Sources → shared health queries → alert queries → dashboard and log reactions**

The Server and every plugin are built from the existing sibling `drasi-server/`
and `drasi-core/` checkouts. The only runtime is ComputationGraph. It connects the
existing source and reaction interfaces as well as query-to-query graph data;
there is no execution-mode flag or separate compatibility runtime.

| Step | What you do |
| --- | --- |
| [Set up](#setup) | Build matching local Server and plugins |
| [Run](#run) | Start an owned cluster, Collector, store services, and PostgreSQL |
| [Observe](#dashboard) | Open the built-in dashboard and inspect the live graph |
| [Drive change](#drive) | Roll checkout, edit its SLO policy, and interrupt its heartbeat |
| [How it works](#how) | Follow shared health and heartbeat results through the query graph |
| [Optional Discord alerts](#discord) | Deliver the same alert changes to a webhook |

{{% alert title="Before you begin" color="info" %}}
Use two terminals in `tutorials/otel-observability/`: Terminal 1 runs Server in the
foreground; Terminal 2 changes the store. Python **3.11+** is required. Commands
below use `python3`; in PowerShell use `python` if that is your interpreter name.
The existing `.sh` and `.ps1` entry points call the same Python helper.

Default ports are API `8380`, dashboard `3000`, PostgreSQL `5732`, Drasi OTLP/gRPC
`14317`, Drasi OTLP/HTTP `14318`, checkout control `18080`, and Kubernetes API
`6551`. Copy `.env.example` to `.env` before starting if any are already occupied.
Each run owns its generated resource names and checks ports before creation.
{{% /alert %}}

## Step 1 of 4: Set Up Your Environment {#setup}

### Local checkouts

Use this layout, with the current matching ComputationGraph branches already
checked out:

```text
workspace/
  drasi-core/
  drasi-server/
  learning-drasi-server/
```

Server's `drasi-lib` dependency must point at the sibling `drasi-core/lib`.
The helper never clones a repository, changes branches, downloads a released
Server, or installs registry plugins. It rebuilds the Server and the PostgreSQL,
Kubernetes, OTel, dashboard, log, and optional HTTP plugin libraries together.

Install the Server/Core build prerequisites documented in those repositories
(Rust **1.95**, C/C++ tools, CMake, Clang/libclang, libjq, OpenSSL, pkg-config,
and protoc), plus **Podman**, **kubectl**, and **k3d 5.8+**. Podman must be running.
k3d uses Podman's Docker-compatible API, not just the Podman CLI connection.

On macOS, get the socket path without changing any global settings:

```bash
podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}'
```

Put `DOCKER_HOST=unix:///the/returned/socket/path` in this tutorial's `.env`.
On Linux, use the socket of your running Podman API service. k3d's Podman support
is experimental: this tutorial requires a functioning privileged k3d cluster,
not merely a working `podman ps`. If networking cannot reach the host, set
`COLLECTOR_DRASI_ENDPOINT` to the host address reachable **from the cluster**.
Do not use `localhost` there; that would refer to the Collector itself.

From the learning repository:

```bash
cd tutorials/otel-observability
python3 scripts/demo.py build
python3 scripts/demo.py verify-build
```

Builds copy the complete matched artifact set into a private, hash-checked bundle
under `.runtime/`. Startup verifies those hashes and rejects extra/missing plugin
files. Unsigned **local development artifacts only** bypass signature checks;
automatic registry fallback is disabled. Rebuild after changing Server or Core.
Do not reuse a Darwin bundle inside Linux (or vice versa).

### Local dev container

Choose **Drasi Server - OTel Observability Tutorial** in VS Code. It mounts the
**parent directory**, so the same sibling checkouts must already exist. Setup
installs build prerequisites and checksum-verifies k3d, then builds matching
Linux Server/plugin artifacts. Its isolated Docker-in-Docker engine is selected
explicitly; it does not need Docker Desktop. Native local execution defaults to
Podman. Container build outputs, selected plugin bundles, kubeconfig, and ownership
records live in the container-local `/home/vscode/.cache/drasi-otel-observability/`
directory, separate from native host `.runtime/` files. The container also selects
its own Docker API socket rather than inheriting a host Podman socket from `.env`.

A standalone Codespace containing only `learning-drasi-server` is insufficient.
There is deliberately no released-binary fallback for a missing sibling checkout.

## Step 2 of 4: Run the Demo {#run}

In **Terminal 1**:

```bash
python3 scripts/demo.py start-demo
```

The helper:

1. Creates a uniquely named k3d cluster with a **private kubeconfig**, without
   updating the user's kubeconfig or changing its current context.
2. Builds checkout **v41** and **v42**, frontend, and payments from `services/`,
   imports those images, and deploys them with the actual in-cluster Collector.
3. Starts a uniquely named, ownership-labeled PostgreSQL container and volume.
   It seeds the checkout / `latency_p99_ms` / **750 ms** policy only in a new
   database. Existing policy values and replication state are not reset.
4. Starts the local Server with `server-config.yaml`, verifies the exact
   `otel-observability-server` instance reports `runtime: "computationGraph"`
   and `running: true`, then checks component and dashboard readiness.

The helper renders the owned kubeconfig path and namespace into
`.runtime/server-config.generated.yaml`: the Kubernetes plugin exposes those
fields as plain strings, not environment-aware `ConfigValue` fields. Other
supported environment references are resolved by Server and its plugin DTOs.

Wait for **OTel READY**. This confirms the runtime and dashboard, not that all
telemetry has arrived. OTLP has no bootstrap dump; allow the next Collector
exports to populate the health and dependency views.

The Collector receives app OTLP/HTTP at `otel-collector:4318` and forwards
OTLP/gRPC to Drasi. Its generated endpoint is printed during setup. If data
does not arrive, inspect it and the Collector logs:

```bash
python3 scripts/demo.py kubectl logs deployment/otel-collector --tail=50
python3 scripts/demo.py kubectl get deploy,pods,svc
```

The `kubectl` helper supplies the owned cluster's private kubeconfig and namespace
on every call. It prints the underlying command, so you can also run equivalent
`kubectl --kubeconfig ... --namespace ...` commands directly.

Press **Ctrl+C** to stop Server. Infrastructure and PostgreSQL data remain.
Restart only Server with `python3 scripts/demo.py start`. No process-name killing
or database reset is performed.

## Step 3 of 4: Open the Dashboard {#dashboard}

Open **http://localhost:3000** (or your configured dashboard port), then choose
**Open** on the **OTel Observability** dashboard card. The dashboard
reaction serves the UI directly; there is no separate frontend application.

After telemetry arrives, expect:

- **Active SLO Alerts:** zero at healthy checkout v41.
- **Checkout p99:** below the 750 ms policy. v41 sleeps 400 ms locally and calls
  payments (80 ms), so real end-to-end samples are normally roughly **480 ms plus
  overhead**, not an exact 400 ms.
- **Current Health:** frontend, checkout v41, and payments.
- **Service Dependencies:** `frontend → checkout` and `checkout → payments`,
  derived from actual CLIENT spans.
- **Checkout heartbeat:** a live receive timestamp. An empty view means no
  heartbeat has been observed yet, not that a service is proven healthy.

Updates arrive automatically. `requests.http` contains instance-scoped source,
query, reaction, and runtime requests, plus the checkout control calls.
For example:

```bash
curl -fsS http://localhost:8380/api/v1/instances/otel-observability-server/runtime
curl -fsS http://localhost:8380/api/v1/instances/otel-observability-server/queries/current-health/results
```

## Step 4 of 4: Drive Change {#drive}

Use **Terminal 2**. The following commands act on Kubernetes, PostgreSQL, and the
mock checkout service. Drasi only observes their changes.

### Roll checkout to v42

```bash
python3 scripts/demo.py roll v42
```

This prints and runs `kubectl set image`, waits for `rollout status`, then sets
the Deployment's `version=v42` label. It uses this run's locally built image.
The helper verifies and reimports that image first, since Kubernetes can
garbage-collect an inactive image during a long session; no registry pull is used.
The v42 process really sleeps **920 ms**, then calls payments, so its p99 exceeds
750 ms. **Current Health** changes to v42. Once that version matches Kubernetes
and remains over the policy for five seconds, **slo-alert** emits **Added**.
The alert row and active count update on the dashboard.

Recover:

```bash
python3 scripts/demo.py roll v41
```

After fresh v41 telemetry arrives, the same alert row is **Removed**. There is
no separate resolution query. Startup, scheduling, Collector batching and export
intervals add time to the five-second sustained-condition window.

### Change the policy without changing the workload

Read the live row:

```bash
python3 scripts/demo.py sql "SELECT service_name, metric_name, threshold_ms FROM service_slo_policy;"
```

Tighten it below healthy v41's observed p99:

```bash
python3 scripts/demo.py set-slo 100
```

The helper executes the following SQL against **only this run's PostgreSQL**:

```sql
UPDATE service_slo_policy
SET threshold_ms = 100
WHERE service_name = 'checkout' AND metric_name = 'latency_p99_ms';
```

The shared health row has not been redefined. Logical replication changes the
policy input and **slo-alert** becomes **Added** after five seconds. Restore:

```bash
python3 scripts/demo.py set-slo 750
```

The alert is **Removed**. Repeating the tighten/restore exercise starts a fresh
sustained-condition window.

### Explicitly disable and restore heartbeat

```bash
python3 scripts/demo.py heartbeat off
```

Checkout continues exporting `health.heartbeat`, now with value **0**.
**Checkout heartbeat** shows disabled and **missing-heartbeat** emits **Added**
on the next export; it does not need to wait ten seconds for this explicit signal.

```bash
python3 scripts/demo.py heartbeat on
```

A fresh positive pulse removes the alert. These are the same
`POST /heartbeat/off` and `/heartbeat/on` control endpoints on
`http://127.0.0.1:18080` used by `requests.http`.

### Observe a truly absent exporter

Keep the positive heartbeat enabled, then stop checkout's only replica:

```bash
python3 scripts/demo.py kubectl scale deployment/checkout --replicas=0
```

After the last received heartbeat is ten seconds old, the timer emits
**missing-heartbeat Added** without a new source event. Restart:

```bash
python3 scripts/demo.py kubectl scale deployment/checkout --replicas=1
python3 scripts/demo.py roll v41
```

`roll v41` reimports the owned image if Kubernetes discarded it while no replica
was running, then waits for the restored Deployment. The next positive export
removes the alert. Dependency edges expire after 60 seconds
without another CLIENT span. A source that has never seen checkout cannot invent
a missing heartbeat row; this exercise requires the initially observed pulse.

### Reset and stop

```bash
python3 scripts/demo.py reset
```

This restores checkout v41's 400 ms local delay, heartbeat on, and SLO 750; it
does not destroy or recreate the database. If you scaled a Deployment to zero,
restore its replicas first.

Stop Server with Ctrl+C, then remove only the recorded owned infrastructure:

```bash
python3 scripts/demo.py cleanup
```

The database volume is retained. Use `cleanup --volumes` only when you also want
to delete **this run's** PostgreSQL data. The helper verifies ownership labels
and recorded cluster container IDs before removal. It refuses foreign resources
and refuses cleanup while its foreground Server lock is present. Never delete a
lock without first verifying that its recorded process has stopped.

### Repeat the exercises automatically

With Server still running, `python3 scripts/verify_demo.py` repeats the rollout,
two policy-change cycles, explicit/absent heartbeat recovery, and dependency
expiry against this owned run. It also checks the dashboard's live WebSocket
Added/Removed messages and stable alert identities. This optional verifier needs
**Node 22+** (built-in WebSocket, no npm packages), changes the store, and writes
evidence under `.runtime/verification/`. It does not exercise Discord.
For fast helper checks without infrastructure, run
`python3 -m unittest discover -s scripts -p test_demo.py`.

## How It Works {#how}

### Three sources, one computation graph

**Kubernetes** watches Deployments in the owned namespace. A `promote` middleware
copies `labels.version` into a top-level `version` property. **PostgreSQL** streams
the composite-key `service_slo_policy` table via logical replication. **OTel**
projects only the allowlisted gauges and CLIENT-span relationships into a bounded
live graph:

```text
(:Service)-[:REPORTS]->(:Metric {name: 'latency_p99_ms', value: ...})
(:Service)-[:REPORTS]->(:Metric {name: 'health.heartbeat', receivedAt: ...})
(:Service)-[:DEPENDS_ON]->(:Service)
```

Each gauge updates the same `(service.name, metric.name)` identity.
`receivedAt` is Drasi receive time. Dependency relationships refresh on CLIENT
spans and expire after 60 seconds. The source can also project Heartbeat nodes,
but this scenario uses the explicit gauge value and receive timestamp so it can
distinguish disabled pulses from absent exports.

### Reuse the correlation, not copied query text

`current-health` joins Deployment names to OTel Service names with the synthetic
`RUNS` relation. It returns both the live service version and Kubernetes rollout
version, service name, metric name, and latency. `result.label: ServiceHealth`
exposes those rows as standard graph-change nodes:

```yaml
result:
  label: ServiceHealth
```

`checkout-health` selects checkout from that result for the KPI and gauge.
`slo-alert` consumes the same producer plus the PostgreSQL policy:

```yaml
inputs:
  - current-health
  - component: slo
    nodes: [service_slo_policy]
```

Its `GOVERNED_BY` synthetic join matches `ServiceHealth.service` to
`service_slo_policy.service_name`. The query is:

```cypher
MATCH (h:ServiceHealth)-[:GOVERNED_BY]->(p:service_slo_policy)
WHERE h.metricName = p.metric_name
  AND drasi.trueFor(
    h.deployVersion = h.rolloutVersion AND h.latencyMs > p.threshold_ms,
    duration({ seconds: 5 })
  )
RETURN h.deployVersion AS deployVersion,
       h.service AS service,
       h.latencyMs AS latencyMs,
       p.threshold_ms AS thresholdMs
```

Both version agreement and threshold comparison are inside `trueFor`, including
their false transitions. A mismatching rollout or recovery cancels the pending
condition instead of filtering out the event before the timer can observe it.

Similarly, `checkout-heartbeat` emits `CheckoutHeartbeat` nodes with `service`,
`pulse`, and `lastSeen`. `missing-heartbeat` subscribes to that query, tests an
explicit zero immediately, or schedules a `drasi.trueNowOrLater` check for ten
seconds after the last receive time. The same live heartbeat result drives the
dashboard and the timer.

Query outputs carry standard graph changes, without a remap reaction or
query-specific envelope in downstream Cypher. This graph representation can
also connect native source/transformer/query producers and native sinks. The
ordinary dashboard, log, and HTTP reactions used **here** still subscribe to
query IDs and use their query-aware Added/Updated/Removed template contracts.

### Data-plane telemetry versus runtime observability

The Collector in this scenario delivers **application telemetry as source data**.
It is not collecting all Drasi component telemetry. The instance `/runtime`
endpoint proves the selected instance is running ComputationGraph, not that
every export arrived, that alerts are correct, or that data is durably committed.
Query-progress metrics likewise do not prove exactly-once processing, durable
replay, or all-component OTel coverage.

This tutorial deliberately keeps in-memory query state. PostgreSQL survives a
Server restart and bootstraps its policy; Kubernetes supplies current objects;
OTel views refill from subsequent exports. It does not promise replay of telemetry
sent while Server was unavailable.

## Optional: Discord Alerts {#discord}

The dashboard is for watching. The same **Added/Removed** transitions can trigger
an HTTP reaction. Use a Discord channel where you are allowed to create a webhook,
or your own webhook endpoint. Do not send private data to an unapproved endpoint.

1. In Discord, create a webhook and copy its URL. Treat the token as a secret.
2. Uncomment the `discord-alerts` reaction at the bottom of `server-config.yaml`.
   Preserve its indentation inside `instances[0].reactions`. The local build
   already includes `drasi-reaction-http`; no plugin download is needed.
3. Stop only Server, provide `DISCORD_WEBHOOK_URL` in your shell environment, and
   run `python3 scripts/demo.py start`. Leave the cluster and database intact.

The reaction subscribes to `slo-alert` and `missing-heartbeat`. Its `added`
templates read `after.*`; its `deleted` templates read `before.*`, posting a
Discord `{"content": "..."}` body. Updated latency rows intentionally have no
webhook template, avoiding a message for each new sample.

Roll v42 then v41 to observe **SLO alert** and **SLO recovered**, or toggle
heartbeat off/on for **Heartbeat missing** and **Heartbeat restored**. A valid
webhook and permission to post are required to exercise this optional step;
local dashboard success does not verify external delivery.
