---
type: "docs"
title: "Debezium Integration"
linkTitle: "Debezium Integration"
weight: 25
description: >
  Feed your existing Debezium change stream into Drasi Server through an HTTP sink or directly from Kafka, with an optional disposable Building Comfort lab.
---

If you already use **Debezium** for change data capture, you can keep it as your CDC reader and use **Drasi Server** to continuously evaluate queries over its events. This tutorial connects an existing Debezium deployment to Drasi; it does not replace your database connector or introduce another CDC reader.

Choose the route that matches your deployment. **Each route stands alone**: you do not need to run both.

| Route | Pipeline | Use it when |
| ----- | -------- | ----------- |
| **[Debezium Server over HTTP](#path-http)** | Database → Debezium Server HTTP sink → Drasi HTTP source | You use Debezium Server and can direct its sink to Drasi |
| **[Debezium on Kafka Connect](#path-kafka)** | Database → Debezium Connect → existing Kafka topic → Drasi Kafka source | You already publish Debezium events to Kafka |

Drasi consumes Kafka directly. **There is no Kafka sink connector to install.**

<div class="flow-diagram">
  <div class="flow-step">
    <div class="flow-step__icon"><i class="fas fa-database"></i></div>
    <div class="flow-step__label">Your database</div>
    <div class="flow-step__description">Existing captured tables</div>
  </div>
  <div class="flow-arrow"><i class="fas fa-arrow-right"></i></div>
  <div class="flow-step">
    <div class="flow-step__icon"><i class="fas fa-exchange-alt"></i></div>
    <div class="flow-step__label">Debezium</div>
    <div class="flow-step__description">Server HTTP sink or Connect + Kafka</div>
  </div>
  <div class="flow-arrow"><i class="fas fa-arrow-right"></i></div>
  <div class="flow-step">
    <div class="flow-step__icon"><i class="fas fa-filter"></i></div>
    <div class="flow-step__label">Drasi source</div>
    <div class="flow-step__description">Map row events to graph changes</div>
  </div>
  <div class="flow-arrow"><i class="fas fa-arrow-right"></i></div>
  <div class="flow-step">
    <div class="flow-step__icon"><i class="fas fa-bolt"></i></div>
    <div class="flow-step__label">Queries and reactions</div>
    <div class="flow-step__description">Use your existing Drasi configuration</div>
  </div>
</div>

The examples use the `Room` table from [Building Comfort](../building-comfort/) to make the mapping concrete. Adapt the table, key, labels, and query properties to your own captured table. The full six-query/dashboard example remains in the bundled [HTTP configuration](server-config-http.yaml) and [Kafka configuration](server-config-kafka.yaml); this tutorial focuses on the integration.

| Step | What You'll Do |
| ---- | -------------- |
| **[Step 1: Prepare your event and mapping](#prepare)** | Inspect a real event, choose identities, and plan initial state |
| **[Step 2: Connect your change feed](#connect)** | Follow either the [HTTP](#path-http) or [Kafka](#path-kafka) instructions |
| **[Step 3: Verify database changes](#verify)** | Trace an insert, update, and delete through a query and reaction |
| **[How It Works](#how)** | Check envelope paths, deletion behavior, and important settings |
| **[Optional disposable lab](#lab)** | Try both routes locally or in a dev container without an existing environment |

{{% alert title="Before you begin" color="info" %}}
- **Drasi familiarity:** you should already know how to configure sources, queries, and reactions. Start with [Getting Started](../getting-started/) and [Building Comfort](../building-comfort/) if these are new to you.
- **Access:** use a nonproduction Debezium deployment, its configuration/logs, and a captured table where you can safely change a test row. For Server, you need a distribution with the native HTTP sink; for Connect, Kafka read/metadata permissions and broker addresses reachable from Drasi.
- **Format:** these examples consume Debezium row envelopes as JSON, with `op`, `before`, `after`, and `source`. Inspect the actual value first. Schema-wrapped JSON needs different paths; flattened SMT records, Avro, and Protobuf are not interchangeable with this format.
- **Drasi runtime:** use a server and compatible source/reaction plugins. The examples pin Drasi Server **0.2.3**; see [compatibility](#compatibility) before changing versions.
- **Tools:** the commands use bash, `curl`, and `jq`; Kafka inspection uses `kcat` or your existing topic browser. SQL uses your database client. Docker is needed **only for the optional lab**, not for connecting existing services.
{{% /alert %}}

## Step 1 of 3: Prepare Your Event and Mapping {#prepare}

Capture a representative event through your existing Debezium diagnostics or Kafka topic browser. Keep sample data local and redact credentials or sensitive row values before sharing it. For Kafka, the [read-only inspection commands](#path-kafka) below show how to read without joining an application consumer group.

For example, an update to a Building Comfort room has this **value/body**, not a Drasi API change object:

```json
{
  "before": {"id":"room_01_01_01","name":"Room 01","temperature":70,"humidity":40,"co2":10,"floor_id":"floor_01_01"},
  "after": {"id":"room_01_01_01","name":"Room 01","temperature":40,"humidity":20,"co2":700,"floor_id":"floor_01_01"},
  "source": {"db":"building_comfort","schema":"public","table":"Room"},
  "op": "u"
}
```

Check these prerequisites before configuring either source:

| Check | Why it matters |
| ----- | -------------- |
| **Stable row key** | Inserts/updates need the key in `after`; deletes need it in `before`. Include **all** components of a composite key. These examples assume an immutable `id`, not a mutable business attribute. |
| **Unambiguous graph identity** | IDs must be unique across all tables within a Drasi source, not just within each table. The examples prefix the row ID with database, schema, and table. |
| **Table and schema scope** | Inspect `source.db`, `source.schema`, and `source.table`. The mapping's table-name filter is not a database/schema authorization filter. Scope the upstream feed or use separate sources/labels when schemas contain identically named tables. |
| **Complete update image** | `after` becomes the complete node properties, not a partial patch. Check connector row-image settings and unavailable/unchanged large-column values. The PostgreSQL lab uses `REPLICA IDENTITY FULL`; that is not a universal fix for every database or TOAST-value case. |
| **Query contract** | Labels and property names are case-sensitive. The sample maps `Room` to label `Room` and leaves `id` and `floor_id` properties unchanged, so the Building Comfort property-based joins still work. |
| **Initial state and recovery** | A new Drasi query needs existing rows as well as future changes. Agree on a supported snapshot/bootstrap/replay procedure and a restart strategy before switching delivery. |

The ID template tests **`after`**, not `after.id`, to choose the row image. A truthiness test on the key would treat numeric `0` as false and can lose valid inserts. For a composite key such as `(tenant_id, id)`, include both in the same branch:

```handlebars
{{payload.source.db}}:{{payload.source.schema}}:{{payload.source.table}}:{{#if payload.after}}{{payload.after.tenant_id}}:{{payload.after.id}}{{else}}{{payload.before.tenant_id}}:{{payload.before.id}}{{/if}}
```

This delimiter pattern assumes the components cannot contain `:` and exist on every row event. For arbitrary strings, normalize/encode keys upstream into a collision-free identifier. If your queries use graph element IDs rather than row properties, adapt those queries and any explicit relation endpoints to the prefixed IDs too.

{{% alert title="Existing rows do not automatically reappear" color="warning" %}}
Changing an HTTP sink URL does not request a new snapshot. `snapshot.mode=initial` depends on the connector's saved state; it does not re-snapshot on every restart. Kafka can replay only retained records, which might not include unchanged old rows or a complete snapshot. Use a connector-supported snapshot/signaling procedure or a separately planned Drasi bootstrap/rebuild. **Do not delete production offsets, replication slots, or consumer groups to follow this tutorial.**
{{% /alert %}}

## Step 2 of 3: Connect Your Change Feed {#connect}

### Route A: Debezium Server → Drasi HTTP Source {#path-http}

```text
Your database → existing Debezium Server → HTTP POST /debezium → Drasi queries
```

#### Configure the Drasi listener

Keep your existing Debezium source connector settings, database credentials, offset storage, and replication slot. First prepare Drasi. Save this as `drasi-http.yaml` in your integration working directory, or merge its plugin/source entries into your own Drasi configuration. The small query and log reaction let you observe row changes without installing the full dashboard.

```yaml
apiVersion: drasi.io/v1
id: debezium-http-server
host: "127.0.0.1"
port: 8380
persistConfig: false
autoInstallPlugins: true
plugins:
  - ref: source/http:0.2.11
  - ref: reaction/log:0.2.7
sources:
  - kind: http
    id: debezium-rooms
    autoStart: true
    host: "0.0.0.0"
    port: 9080
    webhooks:
      errorBehavior: reject
      routes:
        - path: /debezium
          methods: [POST]
          mappings:
            - when:
                field: source.table
                equals: Room
              operationFrom: payload.op
              operationMap: {c: insert, r: insert, u: update, d: delete}
              elementType: node
              template:
                id: "{{payload.source.db}}:{{payload.source.schema}}:{{payload.source.table}}:{{#if payload.after}}{{payload.after.id}}{{else}}{{payload.before.id}}{{/if}}"
                labels: ["{{payload.source.table}}"]
                properties: "{{payload.after}}"
queries:
  - id: room-readings
    autoStart: true
    queryLanguage: Cypher
    query: "MATCH (r:Room) RETURN r.id AS RoomId, r.temperature AS Temperature"
    sources:
      - sourceId: debezium-rooms
        nodes: [Room]
reactions:
  - kind: log
    id: room-changes
    autoStart: true
    queries: [room-readings]
```

Replace `Room`, `id`, and `temperature` if using a different table. For several captured tables, use a table allowlist such as `regex: "^(Building|Floor|Room)$"` instead of `equals`; subscribe your queries to the appropriate labels. See [envelope variants](#envelopes) if the sample event contains an outer `schema`/`payload` wrapper.

`9080` is the **source listener**; `8380` is the **management API**, not the CDC destination. Change conflicting ports before starting. The webhook binds to all interfaces for remote delivery; restrict network access and configure appropriate authentication/TLS before exposing it beyond a trusted test network. Consult the [pinned HTTP source documentation](https://github.com/drasi-project/drasi-core/blob/drasi-source-http-v0.2.11/components/sources/http/README.md) for the supported options.

#### Start Drasi before redirecting delivery

With a compatible `drasi-server` on your path, run the following in Terminal 1. The dedicated plugin directory avoids changing another Drasi installation's cache.

{{< tabpane persist="header" >}}
{{< tab header="bash / zsh" lang="bash" >}}
mkdir -p .drasi-plugins
drasi-server --config drasi-http.yaml --plugins-dir "$PWD/.drasi-plugins"
{{< /tab >}}
{{< tab header="PowerShell" lang="powershell" >}}
New-Item -ItemType Directory -Force .drasi-plugins | Out-Null
drasi-server --config drasi-http.yaml --plugins-dir "$PWD/.drasi-plugins"
{{< /tab >}}
{{< /tabpane >}}

In Terminal 2, check the listener and inspect the source and query status:

```bash
curl --fail-with-body http://127.0.0.1:9080/health
curl --fail-with-body http://127.0.0.1:8380/api/v1/instances/debezium-http-server/sources/debezium-rooms
curl --fail-with-body http://127.0.0.1:8380/api/v1/instances/debezium-http-server/queries/room-readings
```

Expect healthy HTTP responses and a running source/query, without plugin-load or mapping errors in Drasi's logs. **Readiness is not evidence that existing rows have been ingested.** Complete [Step 3](#verify) after connecting Debezium.

#### Point the existing Server HTTP sink at Drasi

Back up your Debezium Server configuration. In its `application.properties`, set the following sink/format properties, using an address reachable **from the Debezium Server process**. `drasi-host` below is a placeholder for that host or service DNS name.

```properties
debezium.sink.type=http
debezium.sink.http.url=http://drasi-host:9080/debezium
debezium.sink.http.timeout.ms=10000
debezium.sink.http.retries=10
debezium.sink.http.retry.interval.ms=2000
debezium.format.key=json
debezium.format.value=json
debezium.format.key.schemas.enable=false
debezium.format.value.schemas.enable=false
```

These are settings for the native sink shipped with Debezium Server 2.7; check the [Server documentation](https://debezium.io/documentation/reference/2.7/operations/debezium-server.html) for your distribution/version. If you retain schemaful JSON, keep your format settings and adapt Drasi's mapping instead.

Debezium Server has one selected sink. **Switching it redirects delivery; it does not multicast to the old destination and Drasi.** If another consumer needs the current sink, arrange a separate feed/deployment with its own connector identity and offset storage rather than redirecting it.

Test `/health` from the Server's network namespace using your usual diagnostics before restarting Server through your deployment's normal procedure. For containers, `localhost` means that container. `host.docker.internal` can reach a Docker host when configured, but does not universally address a sibling dev container; use shared-network service DNS or an explicitly reachable host address. Preserve the existing offsets and confirm streaming resumes in Server logs.

The example uses `errorBehavior: reject` so parse/mapping failures are not acknowledged as success. Unmatched heartbeat, schema-change, transaction, or other-table events are rejected too: arrange row-only delivery for this endpoint or normalize/filter a dedicated feed upstream. The pinned Server sink skips null values, but an `op: d` envelope is **not null** and must still be delivered. Do not remove deletes while filtering noise.

The sink has bounded retry settings, not a durable queue or an exactly-once guarantee. Drasi's sample listener/query state is not configured for durable recovery. A successful POST or a healthy source does not prove every event affected every query. Watch both sets of logs, plan recovery, then continue with [database verification](#verify).

### Route B: Debezium on Kafka Connect → Drasi Kafka Source {#path-kafka}

```text
Your database → existing Debezium Connect → existing Kafka topic → Drasi queries
```

#### Inspect the existing topic without changing it

Keep your connector, topic names, and existing consumers. With your deployment's addresses and connector name, inspect status and metadata:

```bash
CONNECT_URL=http://connect-host:8083
CONNECTOR=your-existing-connector
BROKERS=broker-host:9092
TOPIC=building.public.Room

curl --fail-with-body "$CONNECT_URL/connectors/$CONNECTOR/status" | jq .
kcat -b "$BROKERS" -L -t "$TOPIC"
kcat -b "$BROKERS" -C -t "$TOPIC" -o beginning -c 3 -e \
  -f 'key=%k\nvalue=%s\n'
```

Supply authentication using your existing client configuration if required. `kcat -C` here reads directly without `-G`: it does not join/reset a production group; `-e` exits at the end of the topic. Check both the **key bytes** and **value**: is the value raw JSON, schema-wrapped JSON, a flattened row, or a binary format? Inspect the connector's `value.converter` and effective worker defaults locally if needed; connector configurations may contain credentials.

Do not change a shared connector's converters or add the lab's `RegexRouter` just to use Drasi. If the topic is Avro/Protobuf or its deletion format is incompatible, provide an isolated Drasi-specific JSON feed via an upstream adapter or a separately managed connector with appropriate serialization/tombstone settings. A separate connector must have its own offset/replication identity. See [envelopes and tombstones](#envelopes) before choosing.

#### Configure a Drasi consumer for that topic

Save this as `drasi-kafka.yaml`, or merge the entries into your own configuration. Replace the brokers/topic with the ones you inspected and adapt the table/key/query as in Step 1. No Connect REST mutation or sink connector is needed.

```yaml
apiVersion: drasi.io/v1
id: debezium-kafka-server
host: "127.0.0.1"
port: 8380
persistConfig: false
autoInstallPlugins: true
plugins:
  - ref: source/kafka:0.1.7
  - ref: reaction/log:0.2.7
sources:
  - kind: kafka
    id: debezium-rooms
    autoStart: true
    bootstrapServers: "broker-host:9092"
    topic: building.public.Room
    groupId: drasi-room-integration
    nodeLabel: Room
    autoOffsetReset: earliest
    mappings:
      - when:
          field: source.table
          equals: Room
        operationFrom: payload.op
        operationMap: {c: insert, r: insert, u: update, d: delete}
        elementType: node
        template:
          id: "{{payload.source.db}}:{{payload.source.schema}}:{{payload.source.table}}:{{#if payload.after}}{{payload.after.id}}{{else}}{{payload.before.id}}{{/if}}"
          labels: ["{{payload.source.table}}"]
          properties: "{{payload.after}}"
queries:
  - id: room-readings
    autoStart: true
    queryLanguage: Cypher
    query: "MATCH (r:Room) RETURN r.id AS RoomId, r.temperature AS Temperature"
    sources:
      - sourceId: debezium-rooms
        nodes: [Room]
reactions:
  - kind: log
    id: room-changes
    autoStart: true
    queries: [room-readings]
```

`bootstrapServers` is only the initial connection. All broker addresses returned through Kafka's **advertised listeners** must also be reachable from Drasi. Keep your existing Kafka-compatible broker, including Redpanda if that is what you use.

The pinned plugin accepts a singular `topic`, not a topic list or regex subscription. For existing per-table topics, add one source per topic with distinct source IDs and dedicated Drasi group IDs. Each query must subscribe to **all** relevant source IDs, for example:

```yaml
sources:
  - sourceId: debezium-rooms
    nodes: [Room]
  - sourceId: debezium-floors
    nodes: [Floor]
  - sourceId: debezium-buildings
    nodes: [Building]
```

This fragment belongs under a query, not at the top-level `sources`. Apply it to the bundled Building Comfort queries that require those labels; keep their joins, query text, and reactions unchanged.

For secured clusters, `source/kafka:0.1.7` exposes `securityProtocol`, `saslMechanism`, `saslUsername`, `saslPassword`, and an `additionalProperties` map passed to librdkafka. For example, merge these fields into the source for SASL/SCRAM with TLS and supply the credentials through your normal secret/environment mechanism:

```yaml
securityProtocol: SASL_SSL
saslMechanism: SCRAM-SHA-512
saslUsername: "${KAFKA_USERNAME}"
saslPassword: "${KAFKA_PASSWORD}"
additionalProperties:
  ssl.ca.location: /path/to/broker-ca.pem
```

Use your actual broker authentication method and a CA file accessible to Drasi. See the [pinned plugin configuration](https://github.com/drasi-project/drasi-core/blob/drasi-source-kafka-v0.1.7/components/sources/kafka/src/descriptor.rs) and [librdkafka settings](https://github.com/confluentinc/librdkafka/blob/master/CONFIGURATION.md) for version-dependent options. Do not disable certificate verification or override offset/commit controls as a shortcut.

#### Start and check Drasi

Run in Terminal 1 (use a separate working directory/plugin directory from other installations):

{{< tabpane persist="header" >}}
{{< tab header="bash / zsh" lang="bash" >}}
mkdir -p .drasi-plugins
drasi-server --config drasi-kafka.yaml --plugins-dir "$PWD/.drasi-plugins"
{{< /tab >}}
{{< tab header="PowerShell" lang="powershell" >}}
New-Item -ItemType Directory -Force .drasi-plugins | Out-Null
drasi-server --config drasi-kafka.yaml --plugins-dir "$PWD/.drasi-plugins"
{{< /tab >}}
{{< /tabpane >}}

In Terminal 2:

```bash
curl --fail-with-body http://127.0.0.1:8380/api/v1/instances/debezium-kafka-server/sources/debezium-rooms
curl --fail-with-body http://127.0.0.1:8380/api/v1/instances/debezium-kafka-server/queries/room-readings
curl --fail-with-body http://127.0.0.1:8380/api/v1/instances/debezium-kafka-server/queries/room-readings/results
```

Check for a running source/query, successful partition assignment in the logs, and no JSON/mapping errors. Empty results can mean no retained rows match; source status alone cannot distinguish that from an incomplete initial state. Continue with [Step 3](#verify).

{{% alert title="Replay behavior: source/kafka 0.1.7" color="warning" %}}
This version **manually assigns all topic partitions** and disables automatic commits. It first uses Drasi query resume positions (or a configured bootstrap boundary); without those, `earliest` explicitly selects the beginning and `latest` the end. It does **not** restore from Kafka group committed offsets in this path. A dedicated `groupId` avoids reusing another application's identity, but does not provide partition load balancing between Drasi instances.

This differs from the usual Kafka consumer-group rule, where `auto.offset.reset` applies only when no valid committed offset exists. Do not use a production group reset to initialize Drasi. Replaying the beginning still means **retained** history, not every row that ever existed. These sample configurations keep query state in memory; restarting without restored query state/positions can replay retained events and repeat reactions. Running multiple instances can duplicate processing. Plan coordinated state restoration or a complete rebuild/snapshot before relying on restart behavior, and recheck semantics when changing plugin versions.
{{% /alert %}}

## Step 3 of 3: Verify Database Changes {#verify}

Use your database client to perform **three separate committed operations** on a test row in a table already captured by Debezium: insert, update, then delete. Wait for each stage to reach Drasi before proceeding; do not place all three in a transaction that leaves no observable row.

For your own schema, choose a unique test key, fill required columns/foreign keys, and adapt the `room-readings` query and mapping to that table. **Do not run the lab's schema/reset scripts against an existing database.** If the Building Comfort schema is already installed and `floor_01_01` exists, these are concrete SQL statements you can use:

```sql
-- First confirm this test ID is unused; do not overwrite an existing row.
SELECT * FROM "Room" WHERE id = 'room_drasi_probe';

INSERT INTO "Room" (id, name, temperature, humidity, co2, floor_id)
VALUES ('room_drasi_probe', 'Drasi probe', 70, 40, 10, 'floor_01_01');
```

Inspect the query results (set `INSTANCE` to the route you chose):

```bash
API=http://127.0.0.1:8380
INSTANCE=debezium-http-server
# For Kafka: INSTANCE=debezium-kafka-server
curl --fail-with-body "$API/api/v1/instances/$INSTANCE/queries/room-readings/results" | jq .
```

Expect `RoomId: room_drasi_probe` with `Temperature: 70` and an added result in the log reaction. Then execute and verify:

```sql
UPDATE "Room" SET temperature = 40 WHERE id = 'room_drasi_probe';
```

The same query row should now report `Temperature: 40`, with an update in the reaction. Finally:

```sql
DELETE FROM "Room" WHERE id = 'room_drasi_probe';
```

The query row must disappear, with a removed result in the reaction. Inspect the corresponding Debezium `c`, `u`, and `d` events in your diagnostics/topic browser if any stage fails. A delete envelope must retain the key in `before`. Check serialization, mapping paths, labels, source subscriptions, and logs before changing offsets.

If you run the **bundled** six-query configuration instead of the small probe config, its source is `building-facilities` and its per-room query is `building-comfort-ui`. Use:

```bash
curl --fail-with-body "$API/api/v1/instances/$INSTANCE/queries/building-comfort-ui/results" | jq .
```

Its dashboard is at `http://localhost:3000`. Only the freshly seeded lab has the expected **9 rooms at comfort 46**; after `break-room.sh room_01_01_01`, that room is **4** and its floor is **32**. Arbitrary existing datasets have different counts/values.

`building-comfort-level-calc` weights each floor equally, even when floors have different room counts. The dashboard KPI/gauge instead averages the per-room results to avoid stale aggregate materialization; these room-weighted values match the floor-weighted query for equal-sized floors, but not in general.

{{% alert title="Known aggregate/result-state limitation with the pinned runtime" color="warning" %}}
The reader walkthrough verified real CDC into the per-room query on both routes, but did **not** establish a fully correct six-query/dashboard demo. After insert/update/delete activity, the management API retained duplicate or stale floor/building aggregate rows on both routes. After Kafka simulation and reset, all nine database and per-room query rows were back at comfort 46, yet `floor-alert` still contained an old 51.6667 alert in both the API and dashboard snapshot. The expected state is three floor rows at 46, one building row at 46, and no alerts.

This pinned-runtime query/result-state discrepancy is tracked in [drasi-project/drasi-core#935](https://github.com/drasi-project/drasi-core/issues/935); it is not evidence that the database changes failed to reach Drasi. The floor-weighting correction in this tutorial is a separate query fix and does not resolve that runtime limitation. Restarting to clear the display is not a correctness fix. Use the small `room-readings` query to verify the integration separately; do not rely on the bundled aggregate/alert state until a compatible runtime release is verified.
{{% /alert %}}

A synthetic POST from [`requests.http`](https://github.com/drasi-project/learning-drasi-server/blob/main/tutorials/debezium-integration/requests.http) is a **mapping smoke test only**. It bypasses both the database and Debezium and changes Drasi's view without changing the database. Use it only with an isolated test source; it is not evidence that CDC works.

## How It Works {#how}

### Debezium Envelope → Drasi Changes {#envelopes}

The sources construct a template context around the incoming value/body: **Drasi's `payload` is the whole incoming JSON document**. It is not a requirement to wrap the HTTP body in another `payload`.

| Debezium `op` | Drasi operation | Row image |
| ------------- | --------------- | --------- |
| `c` (create), `r` (snapshot read) | `insert` | ID and properties from `after` |
| `u` | `update` | Same stable ID, complete properties from `after` |
| `d` | `delete` | ID from `before`; `after` is null |

The pinned mapping engine supports deletes: it builds the element metadata and emits a delete containing that metadata. A properties template resolving to null produces no properties, which is valid for this delete path. It does not need a fabricated `after` row.

For schema-enabled JSON, the **wire document** instead looks like:

```json
{
  "schema": {"type":"struct","fields":[]},
  "payload": {
    "op":"d",
    "before":{"id":0},
    "after":null,
    "source":{"db":"building_comfort","schema":"public","table":"Room"}
  }
}
```

The abbreviated `schema` illustrates nesting; Drasi maps the JSON value and does not interpret the Connect schema. Use these exact paths:

| Setting | Raw envelope (both sources) | Schema-wrapped envelope (both sources) |
| ------- | --------------------------- | ------------------------------------- |
| `when.field` | `source.table` | `payload.payload.source.table` |
| `operationFrom` | `payload.op` | `payload.payload.op` |
| `template.labels` entry | `{{payload.source.table}}` | `{{payload.payload.source.table}}` |
| `template.properties` | `{{payload.after}}` | `{{payload.payload.after}}` |

For the wrapped ID use:

```handlebars
{{payload.payload.source.db}}:{{payload.payload.source.schema}}:{{payload.payload.source.table}}:{{#if payload.payload.after}}{{payload.payload.after.id}}{{else}}{{payload.payload.before.id}}{{/if}}
```

**Why the double prefix in the condition?** For raw input, HTTP conditions resolve against the incoming body and strip one optional `payload.` prefix; Kafka conditions resolve against the context, adding `payload.` unless already explicit. Thus `source.table` works for both raw inputs, while `payload.payload.source.table` correctly reaches the inner envelope in both wrapped inputs. `payload.source.table` alone still refers to the raw-envelope location, not to the inner wrapped envelope.

The mappings shown exclude records without a matching `source.table`; `operationMap` has no fallback for unknown operations. HTTP rejects unmatched events with the chosen error policy; Kafka logs unmatched/malformed messages without producing the mapped row change. Heartbeat, schema, and transaction metadata are not row changes. Use row-data topics or an upstream dedicated filter, and investigate warnings rather than assuming all non-row messages were safely ingested. HTTP can apply multiple matching mappings; Kafka uses the first matching mapping, so avoid overlapping rules.

An `ExtractNewRecordState`/unwrap SMT removes the envelope fields these snippets need. Inspect its exact output and deletion behavior before designing a different mapping; if deletes/keys have been discarded, a field-path change cannot recover them. The Kafka source parses JSON values, not Schema Registry Avro/Protobuf. Use a decoding/normalizing adapter or an isolated compatible feed, rather than adding invented converter fields to the Drasi source. Changing a shared Connect `JsonConverter` setting changes the format for every consumer of its output.

#### Kafka tombstones are a separate path

A Kafka **null value** is a tombstone, distinct from a non-null JSON `op: d` envelope with `after: null`. In `source/kafka:0.1.7`, tombstones **bypass mappings**: the plugin emits a delete using the raw UTF-8 Kafka key as the element ID and `nodeLabel` as the label. A key such as `{"id":"room_01_01_01"}` does not equal the mapped ID `building_comfort:public:Room:room_01_01_01`.

The preceding `op: d` envelope still deletes the correct mapped node. The tombstone does not replace that envelope, and a `when` filter cannot repair or discard the tombstone bypass. Verify the key/ID contract and do not depend on the raw-key delete for these row-derived IDs. If your feed contains only tombstones for deletion, or raw keys could collide with mapped IDs, provide an isolated Drasi-specific feed that retains delete envelopes and either normalizes keys consistently or omits tombstones. **Do not disable tombstones globally on an existing shared connector/topic.** The disposable lab disables them on its own connector only.

These version-specific details come from the pinned [Kafka consumer](https://github.com/drasi-project/drasi-core/blob/drasi-source-kafka-v0.1.7/components/sources/kafka/src/consumer.rs), [HTTP condition matcher](https://github.com/drasi-project/drasi-core/blob/drasi-source-http-v0.2.11/components/sources/http/src/route_matcher.rs), and [shared mapping engine](https://github.com/drasi-project/drasi-core/blob/drasi-source-kafka-v0.1.7/components/sources/mapping/src/engine.rs).

### Important Configuration Reference

| Setting | Integration decision |
| ------- | -------------------- |
| HTTP `host`, `port`, `webhooks.routes[].path` | Where Debezium posts. This is separate from the server's management `port`. Confirm network reachability from the sender. |
| HTTP `webhooks.errorBehavior` | `reject` surfaces mapping failures to the sender. `accept_and_log` acknowledges even rejected/unmatched input; do not treat a 2xx response under that policy as successful ingestion. |
| Server `debezium.sink.http.url` | Destination for the selected sink. Preserve connector offsets and coordinate the effect on the previous destination. |
| Server `timeout.ms`, `retries`, `retry.interval.ms` under `debezium.sink.http.` | Native sink request/retry controls. They are not a replay store or a delivery guarantee. |
| `debezium.format.value` / `debezium.format.value.schemas.enable` | Server value encoding and optional schema wrapper; match Drasi paths to the observed body. |
| Connect `value.converter` / `value.converter.schemas.enable` | Effective connector or worker serialization. Inspect before changing; other consumers share the output. |
| Kafka `bootstrapServers`, `topic` | Reachable bootstrap and advertised brokers; one topic per source in the pinned version. |
| Kafka `groupId`, `autoOffsetReset` | Dedicated identity and initial/replay policy. See the version-specific manual-assignment behavior above, not generic group assumptions. |
| Kafka security fields / `additionalProperties` | Match the broker's SASL/TLS requirements; keep credentials out of committed files. |
| `when`, `operationFrom`, `operationMap`, `template` | Table selection, operation codes, stable namespaced identity, label and complete properties. Conditions expose a single field/header test, not a compound database/schema/table predicate. |
| Debezium `table.include.list`, snapshot settings | Scope the captured feed and establish initial state with the connector owner; do not reconfigure shared capture casually. Server source settings use the `debezium.source.` prefix. |
| `plugins[].ref`, `--plugins-dir` | Keep a matched server/plugin set isolated from other installations. |

### Compatibility and Verification Scope {#compatibility}

The bundled downloads pin **Drasi Server 0.2.3**, with **`source/http:0.2.11`**, **`source/kafka:0.1.7`**, **`reaction/dashboard:0.1.5`**, and **`reaction/log:0.2.7`**. Its runtime loader expects ABI **0.13**, even though its `--version` output reports a different plugin SDK crate version. The next plugin releases (HTTP 0.2.12, Kafka 0.1.8, dashboard 0.1.6, log 0.2.8) were rejected for ABI 0.14. Do not infer compatibility from SDK crate labels or automatically select `latest`.

A native Apple Silicon macOS reader walkthrough exercised both raw-JSON routes with this matched set: initial data, separately committed database inserts/updates/deletes, query results and log reactions, and the bundled six-query room/floor change from 46 to 4/32 and back. Dashboard HTTP snapshots and live WebSocket reactions were checked, not visual rendering. The optional simulation was also exercised with macOS Bash 3.2. **Full Linux/Codespaces and Windows end-to-end behavior has not been verified.**

The original Kafka lab encountered broker stalls and Connect worker reassignment on a shared Docker host under memory/IO pressure. One run recovered automatically after a five-minute rebalance delay; another left Drasi's consumer stopped after a topic-metadata timeout. The lab now bounds Redpanda's memory allocation and waits for the connector, its task, and the topic before launching Drasi. These are disposable-lab safeguards, not production sizing or a guarantee against host resource pressure. A healthy container or a task marked `RUNNING` alone is not sufficient; verify the connector too and repeat the database-change checks.

Isolated HTTP mapping checks with Server 0.2.3 cover raw and schema-wrapped JSON, create/snapshot/update/delete operations, numeric-zero keys, namespaced IDs, and query/log-reaction changes. These synthetic checks do not exercise Debezium or the database.

Use an isolated plugin directory as shown above (the lab scripts default to `tutorials/debezium-integration/.drasi-plugins`). Never delete `~/.drasi/plugins` to repair this tutorial. Check actual loader errors and the installed plugin versions when diagnosing compatibility.

## Optional Appendix: Disposable Building Comfort Lab {#lab}

Use this appendix if you do not have a Debezium environment. It supplies PostgreSQL, Debezium Server or Connect, and optionally Redpanda. Return to [preparation](#prepare), [HTTP integration](#path-http), or [Kafka integration](#path-kafka) to understand/adapt the running configuration.

{{% alert title="Disposable infrastructure only" color="warning" %}}
`setup-database.sh` and both `start-demo-*` scripts destroy/recreate this Compose project's data: setup runs `down -v`, drops/reseeds the lab tables, and the Kafka route deletes/re-registers its demo connector. The HTTP demo also resets its own offset volume. **Never point these scripts at existing infrastructure.** They use fixed `debezium-integration-*` container/network names; run only one copy of the lab on a Docker daemon. Check for existing lab containers and port conflicts first.
{{% /alert %}}

### Prepare the lab

Choose **Drasi Server - Debezium Integration Tutorial** when reopening the repository in a VS Code dev container or creating a Codespace. The setup installs the Drasi binary, PostgreSQL client, curl, and jq; Docker-in-Docker provides the disposable services. Network reachability still needs checking, and the end-to-end limitation above applies.

For a local run, install Docker with Compose, bash (macOS Bash 3.2 is supported), curl, and jq, then download the pinned binary from the repository root:

{{< tabpane persist="header" >}}
{{< tab header="bash / zsh" lang="bash" >}}
cd tutorials/debezium-integration
bash scripts/download.sh
{{< /tab >}}
{{< tab header="PowerShell" lang="powershell" >}}
cd tutorials/debezium-integration
powershell -ExecutionPolicy Bypass -File scripts/download.ps1
# Run the remaining bash helper scripts in Git Bash.
{{< /tab >}}
{{< /tabpane >}}

On Windows, use the PowerShell download with **Git Bash**; the launchers recognize `bin/drasi-server.exe`. If using **WSL**, run `bash scripts/download.sh` inside WSL to download the Linux binary, then run the helpers there. Do not reuse the Windows download as the WSL installation.

Alternatively follow [Build from Source](https://drasi.io/drasi-server/how-to-guides/installation/build-from-source/) and place a compatible binary in this tutorial's `bin/`. The launchers prefer that binary over a repository-root installation.

If using this binary for the main-route commands rather than the lab launchers, add it to the current bash/zsh terminal's path with `export PATH="$PWD/bin:$PATH"` from the tutorial directory.

Run all remaining lab commands from `tutorials/debezium-integration/`. Use Terminal 1 for Drasi/demo startup and Terminal 2 for database writes. Defaults are API `8380`, dashboard `3000`, PostgreSQL `5752`, HTTP CDC `9080`, Kafka `19092`, and Connect `8083` (Redpanda also publishes `18081`/`18082`). Copy `.env.example` to `.env` for overrides. If changing ports, update both endpoints, such as `HTTP_SOURCE_PORT` and `DEBEZIUM_SINK_HTTP_URL`, or `KAFKA_HOST_PORT` and `KAFKA_BOOTSTRAP_SERVERS`.

### Start with Server over HTTP

In Terminal 1:

```bash
bash scripts/start-demo-http.sh
```

The script recreates PostgreSQL, starts Drasi, waits for its HTTP health endpoint, and only then starts Debezium Server with fresh **lab** offsets. It fails with recent service logs if the exact Compose container cannot reach a running state within the startup checks. This establishes listener/container startup only; neither check verifies network reachability from Debezium, database health, or snapshot/streaming delivery. Verify actual data below before treating the integration as working.

The manual equivalent, useful for inspecting each stage, is:

```bash
bash scripts/setup-database.sh          # Destructive lab reset: PostgreSQL only
bash scripts/start-server.sh http       # Terminal 1: leave running
# Terminal 2, after the listener is healthy:
bash scripts/start-debezium-server.sh --reset-offsets
docker logs -f debezium-integration-server
```

Do not run both the automatic and manual sequences. Compose defaults the sink to `http://host.docker.internal:9080/debezium`; override it with an address reachable from the Debezium container if needed. The local health check cannot prove that container-to-listener route works.

Open `http://localhost:3000` (or the forwarded **Comfort Dashboard** port), wait for nine rooms, and inspect the instance-scoped `building-comfort-ui` results as in [Step 3](#verify). In Terminal 2:

```bash
bash scripts/break-room.sh room_01_01_01
bash scripts/reset-room.sh room_01_01_01
```

These helpers only execute SQL updates; they do not send synthetic CDC. Wait for the room/floor values to change before resetting. For insert/delete verification, use the SQL probe in Step 3 against the lab database, via `docker exec -i debezium-integration-postgres psql -v ON_ERROR_STOP=1 -U drasi_user -d building_comfort`.

### Try Connect and Kafka independently

Stop Drasi with Ctrl+C, then remove the previous **lab** stack if present:

```bash
bash scripts/cleanup.sh --volumes
bash scripts/start-demo-kafka.sh
```

This recreates the lab database, starts Redpanda and Debezium Connect, registers the demo connector, then waits for both the connector and at least one task to be `RUNNING` and for `building.changes` to be available before starting Drasi. The readiness checks are bounded and fail with diagnostics instead of launching Drasi against an unavailable topic. The fresh retained Kafka history includes the snapshot for Drasi to replay. Check:

```bash
curl --fail-with-body http://localhost:8083/connectors/building-comfort-connector/status
curl --fail-with-body http://localhost:8380/api/v1/instances/debezium-kafka-server/sources/building-facilities
curl --fail-with-body http://localhost:8380/api/v1/instances/debezium-kafka-server/queries/building-comfort-ui/results
```

Use your overridden ports if different. Open the same dashboard and drive the same database writes. Optional helpers are `bash scripts/set-room.sh room_01_02_03 82 40 10` and `bash scripts/simulate.sh`; stop the simulation with Ctrl+C.

The single-core demo broker uses `--memory 512M` to bound its allocation on shared development hosts. Docker still needs headroom for PostgreSQL, Connect, and other workloads. If setup times out, the connector becomes `UNASSIGNED`, or Drasi logs `Failed to fetch topic metadata`, inspect the Connect and broker logs and host resources; do not treat an empty dashboard as a successful snapshot. Once the lab feed is ready again, restart only this tutorial's Drasi process with `bash scripts/start-server.sh kafka` to replay retained history. Do not repeatedly reset the lab or modify unrelated Docker workloads to hide a delivery failure.

### What the lab provisions

| File | Purpose |
| ---- | ------- |
| `database/docker-compose.yml` | PostgreSQL 16 with logical replication; profile `http` adds Debezium Server 2.7, profile `kafka` adds Redpanda and Debezium Connect 2.7 |
| `database/init.sql` | Disposable Building/Floor/Room schema, replication user, full replica identity, and nine seeded rooms |
| `database/debezium-server/application.properties` | PostgreSQL connector plus native HTTP sink, schema-free JSON and the lab's own file offset store |
| `database/connect/register-postgres.json` | Connector registered by `POST /connectors`; JSON converters and a **lab-only** RegexRouter combine per-table events into `building.changes` |
| `server-config-http.yaml`, `server-config-kafka.yaml` | Transport-specific source plus the unchanged six-query/dashboard/log bundle |

The lab's row IDs already include table-specific prefixes; the Drasi mapping additionally namespaces graph IDs by database/schema/table. If you copy the single-topic routing elsewhere, consider **Kafka key collisions too**: topic compaction happens before Drasi and cannot be repaired by prefixing only Drasi IDs. Existing per-table topics are usually the simpler integration.

Compared with native [Building Comfort](../building-comfort/), Debezium owns the replication slot/publication and provides snapshot `r` events instead of a Drasi PostgreSQL source/bootstrap. The query and reaction definitions do not teach anything new here; see that tutorial for their explanation.

## Clean Up {#cleanup}

For an **existing environment**, remove only the test row/configuration you added, stop the dedicated Drasi test process, and coordinate any HTTP sink restoration with its owner. Do not reset connectors, groups, slots, topics, or shared plugins. If your test fails before the delete, remove the test row using your normal database client.

For the **disposable lab only**, stop any simulation and press Ctrl+C in the terminal running Drasi before running:

{{< tabpane persist="header" >}}
{{< tab header="bash / zsh" lang="bash" >}}
bash scripts/cleanup.sh             # Remove lab containers, keep volumes
bash scripts/cleanup.sh --volumes   # Also delete lab data and offsets
{{< /tab >}}
{{< tab header="PowerShell" lang="powershell" >}}
# After stopping Drasi, use Git Bash (or your Linux installation inside WSL):
bash scripts/cleanup.sh --volumes
{{< /tab >}}
{{< /tabpane >}}

## Next Steps

- Apply the verified mapping to your existing queries and reactions; preserve their label/property contracts.
- Use [Building Comfort](../building-comfort/) for the complete query/dashboard explanation, or [Getting Started](../getting-started/) for Drasi configuration basics.
- Before production use, design and exercise authentication, initial-state loading, state recovery, replay, and duplicate-reaction handling for your chosen route.

For changes to the lab helpers, run the dependency-free regression checks from the repository root with `python3 -m unittest discover -s tutorials/debezium-integration/tests`. These use mocked commands and do not replace native-platform or end-to-end CDC verification.
