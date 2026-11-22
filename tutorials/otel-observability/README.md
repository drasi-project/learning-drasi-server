<!-- DO NOT EDIT. Generated from _index.md by scripts/render-tutorials.py. Edit _index.md and run `python3 scripts/render-tutorials.py`. -->

OpenTelemetry collects signals. Operators still need to decide whether a rollout,
a latency spike, and a downstream dependency describe the same incident.

This tutorial builds that correlation layer on **Drasi Server**. Three mock store
services (`frontend`, `checkout`, `payments`) run in Kubernetes and export real
request timings and CLIENT spans through an in-cluster OTel Collector. Drasi
watches their Deployments, live p99 gauges, and a PostgreSQL SLO policy. The
dashboard shows an alert **Added** when a regression persists and **Removed**
when it recovers. You change the originating systems, not Drasi's result data.

**Sources → shared health queries → alert queries → dashboard and log reactions**

The Server and every plugin are built from the sibling `drasi-server/` and
`drasi-core/` checkouts. Server runs the sources, queries and reactions as
connected components of one computation graph, which you can list with
`python3 scripts/demo.py graph`. Server also reports its own metrics, so you
can watch Drasi do the work as well as the services it observes.

| Step | What you do |
| --- | --- |
| [Set up](#step-1-of-4-set-up-your-environment) | Build matching local Server and plugins |
| [Run](#step-2-of-4-run-the-demo) | Start an owned cluster, Collector, store services, and PostgreSQL |
| [Observe](#step-3-of-4-open-the-dashboard) | Open the built-in dashboard and inspect the live graph |
| [Drive change](#step-4-of-4-drive-change) | Roll checkout, edit its SLO policy, and interrupt its heartbeat |
| [How it works](#how-it-works) | Follow shared health and heartbeat results through the query graph, and read Drasi's own metrics |
| [Optional webhook alerts](#optional-webhook-alerts) | Send alert starts and ends to Discord or a local receiver |

> **Before you begin**
>
> Use two terminals in `tutorials/otel-observability/`: Terminal 1 runs Server in the
> foreground; Terminal 2 changes the store. Python **3.11+** is required. Commands
> below use `python3`; in PowerShell use `python` if that is your interpreter name.
> The existing `.sh` and `.ps1` entry points call the same Python helper.
>
> Default ports are API `8380`, dashboard `3000`, PostgreSQL `5732`, Drasi OTLP/gRPC
> `14317`, Drasi OTLP/HTTP `14318`, checkout control `18080`, and Kubernetes API
> `6551`. Copy `.env.example` to `.env` before starting if any are already occupied.
> Each run owns its generated resource names and checks ports before creation.

## Step 1 of 4: Set Up Your Environment
### Local checkouts

Use this layout, with matching checkouts of all three repositories:

```text
workspace/
  drasi-core/
  drasi-server/
  learning-drasi-server/
```

Server's `drasi-lib` dependency must point at the sibling `drasi-core/lib`.
The helper never clones a repository, changes branches, downloads a released
Server, or installs registry plugins. It builds Server and the PostgreSQL,
Kubernetes, OTel, dashboard, log, HTTP and query plugins together. The query
plugin, `drasi-computation-transformer-query`, runs every continuous query and
provides the `promote` middleware used below.

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

The build copies Server and the plugins into a private folder under
`.runtime/` and records their hashes. Every start checks those hashes and
refuses missing, extra or changed plugin files. Plugin signature checks are
skipped only for this local build, and plugins are never downloaded from a
registry. Rebuild after changing Server or Core. A build made on macOS does not
run in the Linux dev container, or the other way round.

### Local dev container

Choose **Drasi Server - OTel Observability Tutorial** in VS Code. It mounts the
**parent directory**, so the same sibling checkouts must already exist. Setup
installs build prerequisites and checksum-verifies k3d, then builds matching
Linux Server/plugin artifacts. It uses its own Docker-in-Docker engine, so it
does not need Docker Desktop; running directly on your host uses Podman.
Container build outputs, selected plugin bundles, kubeconfig, and ownership
records live in the container-local `/home/vscode/.cache/drasi-otel-observability/`
directory, separate from the host's `.runtime/` files. The container also selects
its own Docker API socket rather than inheriting a host Podman socket from `.env`.

A standalone Codespace containing only `learning-drasi-server` is insufficient,
and there is no released-binary fallback for a missing sibling checkout.

## Step 2 of 4: Run the Demo
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
4. Starts the local Server with `server-config.yaml`, checks that the
   `otel-observability-server` instance is running and that every source, query
   and reaction reports `Running`, then checks that the dashboard is served.

The Kubernetes source does not expand `${...}` variables in `kubeconfigPath`
and `namespaces`, so the helper writes this run's private kubeconfig path and
namespace into `.runtime/server-config.generated.yaml`, which Server loads.
Server expands the other `${...}` references itself.

Wait for:

```text
OTel READY. Dashboard: http://localhost:3000
Wait for the next Collector export; readiness is not scenario verification.
```

The message confirms that Server and the dashboard are running, not that
telemetry has arrived. The OTel source has no initial snapshot to load; the
health and dependency views fill in from the next Collector exports, a few
seconds later.

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

## Step 3 of 4: Open the Dashboard
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
curl -fsS http://localhost:8380/api/v1/instances/otel-observability-server/queries/97471d43-3175-45e4-a663-0cbf726b2739/results
```

To see how the sources, queries and reactions are connected, run in
Terminal 2:

```bash
python3 scripts/demo.py graph
```

```text
Graph otel-observability-server (Running)

Components:
  k8s                           Source     Running
  otel                          Source     Running
  slo                           Source     Running
  checkout-heartbeat            Query      Running
  current-health                Query      Running
  service-dependencies          Query      Running
  checkout-health               Query      Running
  missing-heartbeat             Query      Running
  slo-alert                     Query      Running
  slo-alert-notices             Query      Running
  console-log                   Reaction   Running
  otel-observability-dashboard  Reaction   Running
  (19 internal helper components hidden)

Connections:
  k8s -> current-health
  otel -> checkout-heartbeat
  otel -> current-health
  otel -> service-dependencies
  slo -> slo-alert
  checkout-heartbeat -> missing-heartbeat  (data + bootstrap)
  checkout-heartbeat -> otel-observability-dashboard
  current-health -> checkout-health  (data + bootstrap)
  current-health -> slo-alert  (data + bootstrap)
  current-health -> otel-observability-dashboard
  service-dependencies -> console-log
  service-dependencies -> otel-observability-dashboard
  checkout-health -> otel-observability-dashboard
  missing-heartbeat -> console-log
  missing-heartbeat -> otel-observability-dashboard
  slo-alert -> slo-alert-notices  (data + bootstrap)
  slo-alert -> console-log
  slo-alert -> otel-observability-dashboard
```

Queries that read another query's results, such as `slo-alert` reading
`current-health`, get both live changes (`data`) and, when they start, a
snapshot of the current results (`bootstrap`). [How it works](#how-it-works) explains
each query. Server also creates helper components inside each query; the
command hides them.

## Step 4 of 4: Drive Change
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

With Server still running, `python3 scripts/verify_demo.py` repeats the rollout
(including the `slo-alert-notices` start and end), two policy-change cycles,
explicit/absent heartbeat recovery, and dependency expiry against this owned
run. It also checks the dashboard's live WebSocket Added/Removed messages and
stable alert identities. This optional verifier needs **Node 22+** (built-in
WebSocket, no npm packages), changes the store, and writes evidence under
`.runtime/verification/`. It does not exercise the optional webhook reaction.
For fast helper checks without infrastructure, run
`python3 -m unittest discover -s scripts -p test_demo.py`.

## How It Works
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
publishes those rows as `ServiceHealth` nodes that other queries can match:

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

A downstream query matches another query's published nodes directly; no extra
reaction or conversion step sits between them. The dashboard, log and HTTP
reactions subscribe to queries and receive each result change as added,
updated or deleted. The dashboard shows these as rows that appear, change or
disappear, and the log reaction prints one line for each:

```text
DEPENDENCY checkout -> payments
SLO ALERT checkout v42: p99 920.0 ms > 750.0 ms
SLO ALERT checkout v42: p99 1006.9674459955422 ms > 750.0 ms
SLO RECOVERED checkout v42
```

### Notify only when an alert starts or ends
While an SLO alert lasts, every new p99 sample changes `slo-alert`'s
`latencyMs`, so the query reports an update every few seconds, as the second
`SLO ALERT` line above shows. That suits the dashboard, but not a chat
channel. `slo-alert-notices` reads `slo-alert`'s `SloAlert` nodes and returns
only the fields that stay the same while an alert lasts:

```cypher
MATCH (a:SloAlert)
RETURN a.service AS service,
       a.deployVersion AS deployVersion,
       a.thresholdMs AS thresholdMs
```

A new latency sample changes no returned value, so `slo-alert-notices` reports
nothing; it changes only when an alert starts or ends, or when its version or
threshold changes. The optional [webhook reaction](#optional-webhook-alerts) subscribes to this
query instead of `slo-alert`.

### Application telemetry and Drasi's own metrics
The Collector in this scenario delivers the store's **application telemetry**
to Drasi as source data. Separately, the `telemetry` section of
`server-config.yaml` makes Server report **its own** metrics in Prometheus
text format at `http://localhost:8380/metrics`:

```yaml
telemetry:
  profile: basic
  inspection:
    enabled: true
  metrics:
    backend: prometheus
    prometheus:
      path: /metrics
```

Any Prometheus-compatible scraper can read that endpoint. The series are
labeled with component IDs, and `drasi_component_info` maps each ID to its
name. `python3 scripts/demo.py metrics` does that mapping and totals two
counters for each query: the events it processed and the changes it made to
its results:

```text
Query                 Events processed  Result changes
checkout-health                     12               5
checkout-heartbeat                 609              22
current-health                     613              12
missing-heartbeat                   22               0
service-dependencies               609               2
slo-alert                           13               0
slo-alert-notices                    0               0
```

Every OTel export reaches the three queries that read the `otel` source, but
most samples change nothing: `current-health` processed 613 events and changed
its results 12 times. Run the command again after `roll v42` once the alert
appears:

```text
slo-alert                           19               2
slo-alert-notices                    2               1
```

`slo-alert` changed its results twice, when the alert started and when a new
latency sample arrived; `slo-alert-notices` changed once, when the alert
started. `slo-alert` keeps counting as samples arrive during the alert, and
`slo-alert-notices` does not. Your numbers differ from these.

`GET /api/v1/telemetry` (enabled by `inspection`) shows which telemetry
settings are active. Server can also export traces and metrics over OTLP; see
`drasi-server/docs/telemetry-configuration.md`.

### Restarts

Query state is kept in memory. After a Server restart, the PostgreSQL
bootstrap reloads the policy, Kubernetes lists the current Deployments, and
the OTel views fill in again from the next exports. Telemetry sent while
Server was stopped is not replayed, and reactions do not report changes that
happened in the meantime.

## Optional: Webhook Alerts
The dashboard is for watching. The same alert starts and ends can trigger an
**HTTP reaction**. Send them to a Discord channel where you are allowed to
create a webhook, or to a small local receiver that prints them and needs no
account. Do not send private data to an unapproved endpoint.

1. Choose where messages go:
   - **Discord:** create a webhook for the channel and copy its URL. Treat the
     token as a secret.
   - **Local receiver:** open a third terminal in `tutorials/otel-observability/`
     and run `python3 ../../scripts/webhook_receiver.py`. It prints
     `Listening on http://127.0.0.1:8390/ (Ctrl+C to stop)`; use
     `http://127.0.0.1:8390/` as the webhook URL.
2. Uncomment the `discord-alerts` reaction at the bottom of `server-config.yaml`
   (remove the first `# ` on each line), keeping it inside
   `instances[0].reactions`. The local build already includes
   `drasi-reaction-http`; no plugin download is needed.
3. Stop only Server, set `DISCORD_WEBHOOK_URL` to the webhook or receiver URL in
   your shell, and run `python3 scripts/demo.py start`. Leave the cluster and
   database intact.

The reaction subscribes to [`slo-alert-notices`](#notify-only-when-an-alert-starts-or-ends) and
`missing-heartbeat`. Its `added` and `updated` templates read `after.*`, its
`deleted` templates read `before.*`, and each posts a Discord
`{"content": "..."}` body.

Then, in Terminal 2, waiting for each change to appear on the dashboard before
the next command:

```bash
python3 scripts/demo.py roll v42
python3 scripts/demo.py set-slo 800
python3 scripts/demo.py set-slo 750
python3 scripts/demo.py roll v41
python3 scripts/demo.py heartbeat off
python3 scripts/demo.py heartbeat on
```

The local receiver prints one message when the alert starts, one for each
threshold change while it lasts, one when it ends, and one each when the
heartbeat goes missing and returns, however many latency samples arrive in
between:

```text
[01:01:15] POST /
⚠️ **SLO alert**
• **Service:** `checkout`
• **Version:** `v42`
• **p99 above:** 750.0 ms

[01:02:05] POST /
⚠️ **SLO alert changed**
• **Service:** `checkout`
• **Version:** `v42`
• **p99 above:** 800.0 ms

[01:02:20] POST /
⚠️ **SLO alert changed**
• **Service:** `checkout`
• **Version:** `v42`
• **p99 above:** 750.0 ms

[01:02:45] POST /
✅ **SLO recovered**
• **Service:** `checkout`
• **Version:** `v42`

[01:03:23] POST /
💔 **Heartbeat missing**
• **Service:** `checkout`

[01:03:35] POST /
✅ **Heartbeat restored**
• **Service:** `checkout`
```

The HTTP reaction needs a template for every kind of change it can receive. For
a change without one, it sends its own default JSON body to
`<webhook URL>/changes/<query ID>`, which is not a Discord webhook address.
Subscribed to `slo-alert` directly, it would send one such request for each
latency update during an alert. If a delivery fails, the reaction retries and
then stops with an `Error` status until you start it again; the
[High Risk Containers](../high-risk-containers/) webhook step walks through
that recovery.
