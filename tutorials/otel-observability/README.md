<!-- DO NOT EDIT. Generated from _index.md by scripts/render-tutorials.py. Edit _index.md and run `python3 scripts/render-tutorials.py`. -->

OpenTelemetry collects signals. Observability backends store and visualize them. Operators still have to decide whether a deployment, a latency spike, and a downstream dependency are *the same incident*.

This tutorial builds that correlation layer on **Drasi Server**. Three mock store services (`frontend`, `checkout`, `payments`) run in a local Kubernetes cluster and export OTLP through an in-cluster Collector. Drasi watches the checkout Deployment, the live p99 gauge, and a PostgreSQL SLO policy — and emits **Added** / **Removed** when a sustained regression becomes true or false. There is no application code in the loop, and **no bespoke web UI**: the built-in **dashboard reaction** is the demo.

**What you'll build:** a running Drasi Server assembled from Drasi's three core building blocks:

**Sources** → **Continuous Queries** → **Reactions**

- **Sources**: Kubernetes, OTel, and PostgreSQL
- **Continuous Queries**: Correlate rollout, health, and policy
- **Reactions**: Dashboard and console log

| Step | What You'll Do | Time |
| ---- | ------------- | ---- |
| **[Step 1: Set Up Your Environment](#step-1-of-4-set-up-your-environment)** | Open the dev container (or install the tools locally) | 5 min |
| **[Step 2: Run the Demo](#step-2-of-4-run-the-demo)** | One command starts Kubernetes, PostgreSQL, and Drasi Server | 5 min |
| **[Step 3: Open the Dashboard](#step-3-of-4-open-the-dashboard)** | Watch checkout v41 stay healthy | 2 min |
| **[Step 4: Drive Change](#step-4-of-4-drive-change)** | `kubectl` a rollout, `UPDATE` the SLO, stop heartbeats | 8 min |
| **[How It Works](#how-it-works)** | Understand the three sources, the virtual joins, and the queries | 5 min |

> **Before you begin**
>
> - **Terminals:** you'll use two. **Terminal 1** runs the demo (it stays in the foreground). Use **Terminal 2** to change Kubernetes, PostgreSQL, and the mock services with `kubectl`, SQL, and `curl`.
> - **Working directory:** run every command from the tutorial directory (`tutorials/otel-observability/`). The dev container opens there automatically; if you're running locally, `cd tutorials/otel-observability` first.
> - **Command tabs:** commands are shown in tabs (*bash / zsh* and *PowerShell*). Use the one for your shell. The dev container and Codespaces use *bash*.
> - **Ports:** the Drasi Server API is on `8380`, the dashboard is on `3000`, PostgreSQL is on `5732`, the OTel source is on `14317`, the checkout control API is on `18080`, and the k3d Kubernetes API is on `6551`.
> - **What this is not:** Drasi is not replacing Prometheus, Grafana, Loki, or a tracing backend. It keeps a bounded live graph for correlation.

## Step 1 of 4: Set Up Your Environment
This tutorial needs **Docker** (it runs PostgreSQL, builds three mock service images, and starts a local Kubernetes cluster), plus **k3d** and **kubectl**. The easiest way to get everything is the **dev container**.

### Option A: Dev Container or GitHub Codespaces (recommended)

1. Open this repository in VS Code and run **Reopen in Container** (or create a **Codespace** from the repo's **Code** menu).
2. When prompted for a configuration, choose **Drasi Server - OTel Observability Tutorial**.
3. Wait for the container to finish. Its setup script installs the PostgreSQL client, `kubectl`, and `k3d`, and downloads the Drasi Server binary.

That's it. Skip ahead to [Step 2](#step-2-of-4-run-the-demo).

### Option B: Run Locally

You'll need **Docker** (for PostgreSQL, image builds, and k3d), [**k3d**](https://k3d.io/#installation), [**kubectl**](https://kubernetes.io/docs/tasks/tools/), and **bash** (the helper scripts use it; on Windows use Git Bash or WSL, or use the PowerShell tabs). From the repository root, move into the tutorial directory and download the Drasi Server binary:

**bash / zsh**

```bash
cd tutorials/otel-observability
bash scripts/download.sh
```

**PowerShell**

```powershell
cd tutorials/otel-observability
powershell -ExecutionPolicy Bypass -File scripts/download.ps1
```

This places the binary at `bin/drasi-server` (or `bin\drasi-server.exe` on Windows) inside the tutorial directory.

> **Pinned versions**
>
> This tutorial pins **Drasi Server 0.2.2** and the published **`source/otel:0.1.0`** plugin (plugin-sdk 0.11, signed).

## Step 2 of 4: Run the Demo
Everything runs from a single configuration file, `server-config.yaml`. In **Terminal 1**, start the demo:

**bash / zsh**

```bash
bash scripts/start-demo.sh
```

**PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-demo.ps1
```

The `start-demo` script does four things:

1. **Builds three mock store images** (`frontend:v1`, `checkout:v41` / `:v42`, `payments:v1`) and imports them into a k3d cluster.
2. **Deploys an in-cluster OTel Collector** plus the three services. Apps export OTLP/HTTP to `otel-collector:4318`; the Collector forwards to Drasi on the host at `:14317`.
3. **Starts PostgreSQL** and seeds `service_slo_policy` (checkout / `latency_p99_ms` / 750 ms).
4. **Runs Drasi Server** in the foreground with the full configuration.

On first start, Drasi Server downloads the signed registry plugins it needs (`source/postgres`, `bootstrap/postgres`, `source/kubernetes`, `bootstrap/kubernetes`, `source/otel:0.1.0`, `reaction/dashboard`, `reaction/log`) from `ghcr.io/drasi-project`. When you see a line like the following, it's ready:

```text
Drasi Server started successfully with API on port 8380
```

Leave this running. Everything else happens from **Terminal 2** (or your browser).

> **Stopping and resetting**
>
> Press **Ctrl+C** in Terminal 1 to stop the server. To remove the database container *and* the k3d cluster when you're completely done, run `bash scripts/cleanup.sh` (bash) or `powershell -ExecutionPolicy Bypass -File scripts/cleanup.ps1` (PowerShell). Add `--volumes` (bash) or `-RemoveVolumes` (PowerShell) to also delete the database data.

## Step 3 of 4: Open the Dashboard
Drasi Server's dashboard reaction hosts a live web dashboard; there's no separate app to build or run. **Wait until Terminal 1 prints `Drasi Server started successfully`** (on the first run this takes a little longer while the plugins download), then open it in your browser:

```text
http://localhost:3000
```

In the dev container or Codespaces, port `3000` is forwarded automatically. If you open the page before the server has finished starting, just refresh once it's ready.

The OTel source has **no bootstrap dump** — it waits for the next export. Wait until **Current Health** shows all three services (usually a few seconds after `Drasi Server started successfully`). Then you should see:

- **Active SLO Alerts** — empty. Checkout is healthy.
- **Checkout p99** and the gauge — about **400 ms**, under the 750 ms policy.
- **Current Health** — checkout at deploy version **v41**.
- **Service Dependencies** — `frontend → checkout` and `checkout → payments`, derived from CLIENT spans.
- **Checkout heartbeat** — a `lastSeen` timestamp. Empty means no pulse has arrived yet, not that the signal is healthy.

The dashboard updates the instant the data changes, with no refreshing. Let's make something change.

## Step 4 of 4: Drive Change
With Terminal 1 running the demo and the dashboard open, use **Terminal 2** to change the same systems Drasi is watching. None of these commands talk to Drasi. Kubernetes, PostgreSQL, and checkout's control API are the origins; Drasi only observes.

Set the kubeconfig once for this terminal (the cluster script wrote it):

**bash / zsh**

```bash
export KUBECONFIG=bin/kubeconfig.yaml
```

**PowerShell**

```powershell
$env:KUBECONFIG = "bin/kubeconfig.yaml"
```

List what the cluster is running before you change anything:

```bash
kubectl get deploy,pods,svc
```

You should see `frontend`, `checkout` (image tag `v41`), `payments`, and `otel-collector`.

### Roll checkout to v42

This is a real Deployment change. **v41** starts at 400 ms; **v42** starts at 920 ms (above the 750 ms policy). The image change is the latency change.

```bash
kubectl set image deployment/checkout app=otel-observability-checkout:v42
kubectl rollout status deployment/checkout
kubectl label deployment/checkout version=v42 --overwrite
```

`set image` starts a v42 replica that **actually sleeps ~920 ms** on each `/work` request (v41 sleeps ~400 ms). Frontend keeps calling checkout; checkout calls payments; the exported `latency_p99_ms` is the p99 of those real timings. After `rollout status`, **Current Health** shows **v42** at ~920 ms. Five seconds later **slo-alert** emits **Added**.

### Recover, then change the policy

Roll back to v41 — 400 ms, under the SLO. The same alert row is **Removed**; there is no separate resolution query.

```bash
kubectl set image deployment/checkout app=otel-observability-checkout:v41
kubectl rollout status deployment/checkout
kubectl label deployment/checkout version=v41 --overwrite
```

The threshold lives in PostgreSQL, not in the query. Checkout v41 is already ~400 ms, so dropping the policy to 100 ms is enough to fire the alert — no latency change required.

Read the current row. You should see `750`:

```bash
docker exec otel-observability-postgres psql -U drasi_user -d otel_observability -c \
  "SELECT service_name, metric_name, threshold_ms FROM service_slo_policy;"
```

Tighten the policy below the live p99. After five seconds (`trueFor`) **slo-alert** emits **Added**:

```bash
docker exec otel-observability-postgres psql -U drasi_user -d otel_observability -c \
  "UPDATE service_slo_policy SET threshold_ms = 100 WHERE service_name = 'checkout' AND metric_name = 'latency_p99_ms';"
```

Put the policy back above the live p99. The same alert row is **Removed**:

```bash
docker exec otel-observability-postgres psql -U drasi_user -d otel_observability -c \
  "UPDATE service_slo_policy SET threshold_ms = 750 WHERE service_name = 'checkout' AND metric_name = 'latency_p99_ms';"
```

Drasi never sees these commands — it only sees the row change through logical replication.

### Missing heartbeat

Stop checkout's health metric:

**bash / zsh**

```bash
curl -fsS -X POST http://127.0.0.1:18080/heartbeat/off
```

**PowerShell**

```powershell
curl.exe -fsS -X POST http://127.0.0.1:18080/heartbeat/off
```

Checkout keeps exporting `health.heartbeat`, but the value is **0**. **Checkout heartbeat** flips to disabled and **missing-heartbeat** emits **Added**. Resume the signal:

**bash / zsh**

```bash
curl -fsS -X POST http://127.0.0.1:18080/heartbeat/on
```

**PowerShell**

```powershell
curl.exe -fsS -X POST http://127.0.0.1:18080/heartbeat/on
```

The same row is **Removed**.

### Reset

Return everything to the starting state (checkout `v41`, 400 ms, heartbeat on, SLO 750):

**bash / zsh**

```bash
bash scripts/reset.sh
```

**PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/reset.ps1
```

## How It Works
Everything you just ran is described by the single `server-config.yaml`. Here's what each part does.

### Three sources

**Kubernetes** watches the store Deployments. Drasi Server runs *outside* the cluster and connects with the kubeconfig written by `scripts/setup-cluster.sh`:

```yaml
  - kind: kubernetes
    id: k8s
    resources:
      - apiVersion: apps/v1
        kind: Deployment
    namespaces:
      - default
    authMode: kubeconfig
    kubeconfigPath: bin/kubeconfig.yaml
```

Each Deployment becomes a node with `name` (from `metadata.name`) and a nested `labels` map. A **promote** middleware copies `labels.version` to a top-level `version` property so the validated queries can return `d.version`.

**OpenTelemetry** is the native `source/otel` plugin. It listens for OTLP/gRPC on `:14317` and projects an allowlisted subset into a bounded graph — it is not a telemetry backend. The in-cluster Collector forwards to that port; `setup-cluster` rewrites `host.k3d.internal` to the node gateway when the alias is missing (common in the Docker-in-Docker dev container):

```text
(:Service {name: 'checkout'})-[:REPORTS]->(:Metric {name: 'latency_p99_ms', value: 400})
(:Service {name: 'checkout'})-[:REPORTS]->(:Metric {name: 'health.heartbeat', receivedAt: ...})
(:Service {name: 'checkout'})-[:DEPENDS_ON]->(:Service {name: 'payments'})
(:Service {name: 'checkout'})-[:HEARTBEAT]->(:Heartbeat {lastSeen: ...})
```

The metric identity is `(service.name, metric.name)`, so the next gauge **updates** the same node. `health.heartbeat` is allowlisted so the query can use `Metric.receivedAt` (server receive time). The mock sends a changing gauge value so each export is a real Update. `DEPENDS_ON` edges refresh on each CLIENT span and expire after 60 seconds. There is no bootstrap: late subscribers wait for the next export.

**PostgreSQL** holds the SLO policy and streams changes via logical replication. The table name is unquoted `service_slo_policy` so the node label matches the Cypher (`(p:service_slo_policy)`).

### Virtual joins

The OTel source does not invent Kubernetes or policy relationships. The query declares them:

```yaml
joins:
  - id: RUNS
    keys:
      - label: Deployment
        property: name
      - label: Service
        property: name
  - id: GOVERNED_BY
    keys:
      - label: Service
        property: name
      - label: service_slo_policy
        property: service_name
```

### The queries

**current-health** is the always-on path, so the dashboard has a live latency even when no alert is firing:

```cypher
MATCH (d:Deployment)-[:RUNS]->(s:Service)-[:REPORTS]->(m:Metric)
WHERE m.name = 'latency_p99_ms'
RETURN
  s.version AS deployVersion,
  s.name AS service,
  m.value AS latencyMs
```

**slo-alert** is the flagship query. Neither the sample 920 ms nor the 750 ms threshold is embedded in the Cypher — both are changing data. The result fires only after the condition holds for five seconds:

```cypher
MATCH (d:Deployment)-[:RUNS]->(s:Service)-[:REPORTS]->(m:Metric),
      (s)-[:GOVERNED_BY]->(p:service_slo_policy)
WHERE m.name = p.metric_name
  AND s.version = d.version
  AND m.value > p.threshold_ms
  AND drasi.trueFor(
    m.value > p.threshold_ms,
    duration({ seconds: 5 })
  )
RETURN
  d.version AS deployVersion,
  s.name AS service,
  m.value AS latencyMs,
  p.threshold_ms AS thresholdMs
```

**service-dependencies** is the live `DEPENDS_ON` map. **missing-heartbeat** watches checkout's `health.heartbeat` gauge: `POST /heartbeat/off` exports **0** (immediate **Added**); a process that stops exporting ages `receivedAt` for 10 seconds.

```cypher
MATCH (svc:Service)-[:REPORTS]->(m:Metric)
WHERE svc.name = 'checkout'
  AND m.name = 'health.heartbeat'
  AND (
        m.value <= 0
        OR drasi.trueNowOrLater(
             datetime(m.receivedAt) <= (datetime.realtime() - duration({ seconds: 10 })),
             datetime(m.receivedAt) + duration({ seconds: 10 })
           )
      )
RETURN svc.name AS service
```

### The mock services

The cluster runs three small images that share `services/app.py` and differ only by `SERVICE_NAME` / `PEER_SERVICE`:

| Image | Emits |
| --- | --- |
| `otel-observability-frontend:v1` | Calls `http://checkout:8080/work` every 2s; exports client p99 + CLIENT span |
| `otel-observability-checkout:v41` | `/work` sleeps **400 ms**, then calls payments |
| `otel-observability-checkout:v42` | `/work` sleeps **920 ms**, then calls payments |
| `otel-observability-payments:v1` | `/work` sleeps **80 ms** |

Same `app.py`; v41/v42 differ by `WORK_MS`. Each request is timed; the process exports a p99 gauge of recent samples (the OTel source accepts gauges, not histograms). Checkout's control API is `http://127.0.0.1:18080` (`POST /delay/<ms>` changes the sleep, `POST /heartbeat/on|off` toggles the heartbeat).

### Plugin and server versions
This tutorial pins **Drasi Server 0.2.2** (`scripts/download.sh`, override with `DRASI_SERVER_VERSION`) and **`source/otel:0.1.0`** from `ghcr.io/drasi-project`. First start downloads the signed cdylib into `bin/<os>-<arch>/plugins` (host and the Linux dev container keep separate trees so a Mac bind-mount cannot exec a Darwin binary).

`0.2.0-preview` is plugin-sdk 0.9 and cannot load this plugin. Re-run `bash scripts/download.sh` if you still have that binary.

## Claims this demo does not make

- Drasi replaces Prometheus, Grafana, Loki, or a tracing backend.
- Arbitrary raw OTLP volume can be retained safely.
- Results have exactly-once delivery.
- Cross-source events have a global order.
- A correlated condition proves causation.

The defensible claim is that Drasi continuously maintains a declarative correlation and exposes its changing result set.
