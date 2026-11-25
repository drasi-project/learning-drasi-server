---
type: "docs"
title: "Getting Started"
linkTitle: "Getting Started"
weight: 10
description: >
  Connect a locally built Drasi Server to PostgreSQL and build five Continuous Queries step by step.
---

Drasi Server keeps query results up to date as data changes. You describe what
matters with a Continuous Query, then connect a Reaction to act on changes to
its results. This tutorial builds a live message monitor: first show every
message, then filter, count, detect inactivity, and join messages to locations
received from a different system.

You will insert, update, and delete database rows yourself and watch the result
changes in the console and an SSE terminal. The scenario uses five queries,
two Sources, a Log Reaction, and temporary SSE Reactions. There is no application
code to write.

| Step | What you do |
| --- | --- |
| [1. Set up](#setup) | Build the current local Server, Core plugins, and SSE CLI |
| [2. Start the database](#database) | Load four sample messages into PostgreSQL |
| [3. Run the first query](#phase-1) | See inserts, updates, and deletes through `all-messages` |
| [4. Filter messages](#phase-2) | Add `hello-world-senders` and see it in the running graph |
| [5. Count messages](#phase-3) | Add `message-counts` and stream changes through SSE |
| [6. Detect inactivity](#phase-4) | Watch `inactive-senders` change without new database writes |
| [7. Join locations](#phase-5) | Join the message feed with live HTTP location updates |
| [8. Keep query state](#phase-6) | Store query indexes on disk so a restart resumes instead of rebuilding |

**Drasi Server runs your solution as one computation graph.** Each Source,
query, and reaction is a component in that graph, and the graph connects them:
a connection carries changes from one component's output to another
component's input. You describe the components with the `sources`, `queries`,
and `reactions` configuration below; Server builds the graph from it.

An `inputs` entry names an upstream component, not just a Source. You will
reuse the `all-messages` query's output for filtering, counting, and joining,
instead of repeating the message projection or introducing another connector.

<!-- telemetry-variant: omit -->
{{% alert title="Optional: Follow this tutorial with telemetry enabled" color="info" %}}
Prefer to watch Drasi Server's traces in Jaeger and its metrics in Grafana as you
go? Follow [Getting Started with Telemetry Enabled](telemetry/) instead: it is
this tutorial with the telemetry steps added.
{{% /alert %}}
<!-- /telemetry-variant: omit -->

## Step 1 of 8: Set Up Your Environment {#setup}

Use these existing sibling checkouts, on matching branches, in the same parent
directory:

```text
workspace/
  drasi-core/
  drasi-server/
  learning-drasi-server/
    tutorials/getting-started/
    tutorials/sse-cli/
```

This tutorial uses **the current contents** of those checkouts, including local
edits. It does not download a released Drasi binary, fetch published plugins,
clone another checkout, or change branches. Server's `drasi-lib` dependency must
point to the sibling `drasi-core/lib`.

You need Python 3.11+, Rust 1.95.0, the Server/Core native build prerequisites,
curl, and a running **Podman**. On macOS start your Podman machine first. On
Windows, follow the bash commands in WSL2 or use the
[local Dev Container](dev-container/). The first build can take much longer
than the walkthrough; reserve enough disk space for Rust build artifacts.
The [local source build page](download-binary/) lists the native build
prerequisites. A standard single-repository
[Codespace is not sufficient](github-codespace/).

In a terminal, change to `learning-drasi-server/tutorials/getting-started`.
**All commands below run from this directory**, not from `drasi-server/`.

```bash
cp .env.example .env
python3 scripts/demo.py build
python3 scripts/demo.py build-cli
python3 scripts/demo.py verify-build
```

`build` compiles Server and seven plugins: the PostgreSQL Source and its
Bootstrap Provider, the HTTP Source, the ScriptFile Bootstrap Provider, the Log
and SSE Reactions, and `drasi-computation-transformer-query`, which runs
continuous queries. Server loads the query plugin before it creates any query;
without it, query creation fails. The query plugin includes the standard
middleware and JQ support. The build records source/build provenance and copies
the exact artifacts to a private hash-checked bundle. `build-cli` builds this
repository's `tutorials/sse-cli`, installs a private copy, and records its
provenance. Every start verifies the bundle; every `stream` and `watch` command
verifies the CLI. After editing either checkout or the CLI, rebuild the
corresponding artifacts.

Both commands use `../../../drasi-server/target` for Cargo output unless you set
`CARGO_TARGET_DIR`. Do not share a Cargo target with another simultaneous
build. The helper compiles one crate at a time (`CARGO_BUILD_JOBS=1`) to limit
memory use; export a larger `CARGO_BUILD_JOBS` value to build faster when your
machine has the memory.

The `.env` defaults select run `getting-started-cg`, PostgreSQL port `5532`,
Server API `8180`, SSE `8181`, and HTTP Source `8182`. Everything binds to
`127.0.0.1`. For another run, choose a new `DRASI_RUN_ID` **and four free ports**
before starting. Helpers read `.env` in each terminal; the curl examples and
`requests.http` use the defaults, so adjust their URLs if you change ports.
Database credentials in the sample are for this isolated local database only.

Use **Terminal 1** for Server, **Terminal 2** for SQL and REST calls, and
**Terminal 3** for SSE. The helper scripts keep process and container ownership
separate from the query concepts you are learning.

## Step 2 of 8: Set Up the Tutorial Database {#database}

Start the database:

```bash
python3 scripts/demo.py database
```

The helper creates a labeled Podman container and volume owned by this run,
enables PostgreSQL logical replication, loads `database/init.sql` into an empty
database, then creates `drasi_slot` in a separate session. It refuses resources
owned by another run and **never resets or reseeds an existing database**.
It needs no shared container network or Compose provider.

The `Message` table contains:

| Field | Type | Purpose |
| --- | --- | --- |
| MessageId | integer | Unique message identifier |
| From | varchar(50) | Sender |
| Message | varchar(200) | Message text |
| CreatedAt | timestamp | Database insertion time |

Verify the data:

```bash
python3 scripts/demo.py sql 'SELECT "MessageId", "From", "Message" FROM "Message" ORDER BY "MessageId";'
```

```text
1|Buzz Lightyear|To infinity and beyond!
2|Brian Kernighan|Hello World
3|Antoninus|I am Spartacus
4|David|I am Spartacus
```

The `sql` helper sends your SQL to `psql` inside the **owned** container with
`ON_ERROR_STOP=1`. It also accepts SQL on stdin, which avoids shell quoting
problems in the exercises below.

## Step 3 of 8: Run Your First Drasi Server {#phase-1}

The initial `configs/getting-started-step-3.yaml` declares an instance named
`getting-started-server`, a PostgreSQL Source `my-postgres`, one query, and
`log-reaction`. The Source reads existing rows with its PostgreSQL Bootstrap
provider and then follows database changes through CDC.

Here is the first query:

```yaml
- id: 67ff1d64-e938-4a9b-b80e-074666bdef95
  name: all-messages
  autoStart: true
  inputs: [my-postgres]
  result:
    label: Message
  query: |
    MATCH (m:Message)
    RETURN m.MessageId AS MessageId, m.From AS From, m.Message AS Message
  queryLanguage: GQL
```

`MATCH` selects every `Message` node and `RETURN` projects three fields. There
is no filter, so its result set is every message, kept current. A relational row
is represented as a graph node; you can use GQL or openCypher to query it.

**`result.label` names the result nodes published by this query.** Each result
node has the returned fields, a stable runtime identity, and label `Message`.
It is a new result node, not the original PostgreSQL node with all of its
properties and timestamps. Later queries can match this label by naming
`all-messages` in `inputs`. Setting the label does not change the output
format: every Source and query publishes the same kind of graph changes.

In **Terminal 1**:

```bash
python3 scripts/demo.py start
```

On first start this copies the step-3 configuration to
`.runtime/getting-started-cg/getting-started.yaml`. Subsequent starts retain
that working copy. REST changes are saved there because `persistConfig: true`;
the checked-in reference configurations are never modified.

Server loads only the local hash-checked plugin directory.
`autoInstallPlugins: false` stops Server from downloading plugins. `--skip-verification`
is used only for this unsigned local development bundle, not arbitrary
downloaded plugins. Missing or changed artifacts are an error, not a reason to
download replacements. The optional Web UI is disabled (`enableUi: false`); it
is not required for this walkthrough.

Wait for `READY: getting-started-server, computationGraph`, then verify in
**Terminal 2**:

```bash
python3 scripts/demo.py check
curl --fail-with-body http://127.0.0.1:8180/api/v1/instances/getting-started-server/runtime
```

The successful runtime response must contain exactly:

```json
{"instanceId":"getting-started-server","runtime":"computationGraph","running":true}
```

This is the `data` inside the API's `{success, data, error}` response envelope.
`/health` alone does not establish that this instance and its components are
running. If startup fails, read the Server error; do not stop unrelated
processes to free a port or use a released binary as a substitute.

If a later REST command returns `PERSISTENCE_FAILED`, stop the walkthrough and
inspect the response, live component state, and working configuration. The
operation may have been applied in memory even though saving it failed.
Do not blindly repeat a `POST`, assume it rolled back, or disable persistence
to turn the failure into a success.

### View the current results

```bash
python3 scripts/demo.py results all-messages
```

Equivalent REST request:

```bash
curl --fail-with-body http://127.0.0.1:8180/api/v1/instances/getting-started-server/queries/67ff1d64-e938-4a9b-b80e-074666bdef95/results
```

There should be four rows, including:

```json
{"From":"Brian Kernighan","Message":"Hello World","MessageId":2}
```

Results are current state, not an event history. Ordering is not guaranteed.
The same requests are in `requests.http` for VS Code's REST Client extension.

### Cause an insert, update, and delete

In **Terminal 2**, from `learning-drasi-server/tutorials/getting-started` (like
every command in this tutorial), insert your first message:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('You', 'My first message!');
SQL
```

In Terminal 1, the Log Reaction prints an `ADD` from `all-messages`:

```text
[92e8fa7a-bd91-46a3-95ff-8c364677f077] Query '67ff1d64-e938-4a9b-b80e-074666bdef95' (1 items):
[92e8fa7a-bd91-46a3-95ff-8c364677f077]   [ADD] {"From":"You","Message":"My first message!","MessageId":5}
```

Each line starts with the ID of `log-reaction`, and the first line names the
query by its ID: `67ff1d64-…` is `all-messages`.

Now update it:

```bash
python3 scripts/demo.py sql <<'SQL'
UPDATE "Message" SET "Message" = 'My first UPDATED message!' WHERE "From" = 'You';
SQL
```

The Log Reaction prints `UPDATE`, with the old row, `->`, and the new row.
Finally:

```bash
python3 scripts/demo.py sql <<'SQL'
DELETE FROM "Message" WHERE "From" = 'You';
SQL
```

It prints `DELETE`. After each operation, run `results all-messages` again
to see the matching current state. IDs and log ordering can vary. These
examples assume the fresh database; using a sender name avoids depending on
the next serial ID.

**Checkpoint:** you caused all three changes and observed both current query
results and reaction notifications. A change to the Source generates a
notification only when it changes the query's result.

## Step 4 of 8: Add a Continuous Query with Criteria {#phase-2}

Who sent messages containing exactly `Hello World`? Add a query to the running
Server without restarting:

```yaml
- id: 420bc6f5-d87a-4f99-9c79-7f88a7f0a88e
  name: hello-world-senders
  autoStart: true
  inputs: [{id: 67ff1d64-e938-4a9b-b80e-074666bdef95}]
  result: {label: HelloWorldSender}
  query: |
    MATCH (m:Message)
    WHERE m.Message = 'Hello World'
    RETURN m.MessageId AS Id, m.From AS Sender
  queryLanguage: Cypher
```

This is **direct query chaining**. The input is `all-messages`, not
`my-postgres`. The new query starts from the upstream output's current snapshot
and then consumes its live changes. It needs neither a second PostgreSQL
connection nor an intermediate re-ingestion Source.

`WHERE` filters the result; `RETURN` renames the fields to `Id` and `Sender`.
The complete request body is `configs/hello-world-senders.json`. In Terminal 2:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8180/api/v1/instances/getting-started-server/queries \
  -H 'Content-Type: application/json' --data-binary @configs/hello-world-senders.json
```

The response confirms that Server **accepted** the change:

```json
{"success":true,"data":{"message":"query 'hello-world-senders' change accepted",
 "configuration":{"requestId":"…","revision":2,"durable":false,
  "componentId":"420bc6f5-d87a-4f99-9c79-7f88a7f0a88e","status":"reconciling"}},"error":null}
```

Accepting a change and running it are separate events. `revision` counts the
accepted changes to this instance's configuration, and `status: reconciling`
means Server is now creating and starting the query. `durable: false` means
the accepted configuration is held in memory and the YAML file, not in a
separate configuration store. The query is ready when `results` answers.

Subscribe the Log Reaction to both queries with a `PUT`. It replaces the
reaction's configuration and restarts it, without a separate delete and create:

```bash
curl --fail-with-body -X PUT http://127.0.0.1:8180/api/v1/instances/getting-started-server/reactions/92e8fa7a-bd91-46a3-95ff-8c364677f077 \
  -H 'Content-Type: application/json' \
  -d '{"kind":"log","id":"92e8fa7a-bd91-46a3-95ff-8c364677f077","name":"log-reaction","autoStart":true,"queries":[{"id":"67ff1d64-e938-4a9b-b80e-074666bdef95"},{"id":"420bc6f5-d87a-4f99-9c79-7f88a7f0a88e"}]}'
python3 scripts/demo.py results hello-world-senders
```

The `PUT` response includes `"plan":{"mode":"recreate","data":"preserve"}`:
Server rebuilds the reaction with its new settings and keeps the queries' data.

Brian Kernighan is already in the current results: `{"Id":2,"Sender":"Brian Kernighan"}`.
Adding a reaction later is not a promise to replay changes that happened before
it subscribed; use the results endpoint to inspect current state.
Replacing a reaction can replay retained changes, so repeated console messages
are not evidence of duplicate database writes or exactly-once delivery.

### See the graph

Server built a graph from these declarations. Print it:

```bash
python3 scripts/demo.py graph
```

```text
Graph getting-started-server (Running)

Components:
  my-postgres          Source     Running
  all-messages         Query      Running
  hello-world-senders  Query      Running
  log-reaction         Reaction   Running
  (5 internal helper components hidden)

Connections:
  my-postgres -> all-messages
  all-messages -> hello-world-senders  (data + bootstrap)
  all-messages -> log-reaction
  hello-world-senders -> log-reaction
```

The helper reads `GET /api/v1/instances/getting-started-server/computation`,
which reports every component's lifecycle state and, when one fails, why. It
hides the helper components that Server adds inside each query.

`all-messages -> hello-world-senders` is two connections. The **bootstrap**
connection delivered the current `all-messages` rows to the new query when it
started; the **data** connection carries every later change. That is how a
query added to a running graph starts from the upstream query's current results
instead of an empty state.

Now insert Alice's matching message and Bob's non-matching message:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('Alice', 'Hello World');
INSERT INTO "Message" ("From", "Message") VALUES ('Bob', 'Goodbye World');
SQL
```

Alice generates an `ADD` for both queries. Bob generates an `ADD` only for
`all-messages`. Check the filtered results again: Brian and Alice appear; Bob
does not. `configs/getting-started-step-4.yaml` is the reference after this step.

**Checkpoint:** one graph output now feeds both a reaction and another query,
and the same database changes drive both result sets.

## Step 5 of 8: Add an Aggregation Query and the SSE Reaction {#phase-3}

`message-counts` counts how many times each message text appears:

```yaml
- id: ac1a10bb-59c8-4572-9bf7-c610f166c19d
  name: message-counts
  autoStart: true
  inputs: [{id: 67ff1d64-e938-4a9b-b80e-074666bdef95}]
  result: {label: MessageCount}
  query: |
    MATCH (m:Message)
    RETURN m.Message AS MessageText, count(m) AS Count
  queryLanguage: Cypher
```

The non-aggregate field `MessageText` defines each group. Drasi maintains
`Count` incrementally as messages enter, leave, or change groups. This query
reuses the same labeled message projection as the filter.

```bash
curl --fail-with-body -X POST http://127.0.0.1:8180/api/v1/instances/getting-started-server/queries \
  -H 'Content-Type: application/json' --data-binary @configs/message-counts.json
python3 scripts/demo.py results message-counts
```

At this point `Hello World` has count `2` (Brian and Alice), and `I am Spartacus`
has count `2`. No repeated database scans are needed for subsequent updates.

### Stream result changes

An SSE Reaction sends result changes to connected clients. Its plugin was
already built and loaded in Step 1; **do not install a registry plugin** now.
The local SSE CLI creates a temporary reaction, streams events, and deletes
its own reaction when you stop it normally.

In **Terminal 3**:

```bash
python3 scripts/demo.py stream message-counts
```

This verifies and runs the locally built CLI with:
`--server http://127.0.0.1:8180 --instance getting-started-server
--query message-counts --sse-port 8181 --sse-host 127.0.0.1`.
The instance argument matters: component APIs are instance-scoped.
Wait for the connection message before changing data.

**Graph data versus reaction payloads:** inside the graph, every connection
carries graph changes: nodes and relations being added, replaced, or deleted.
The `kind: sse` reaction used here subscribes to query results and sends each
change as `{queryId, results, timestamp}`, where `results` lists the row
differences. Reactions of this kind consume query outputs only.

In Terminal 2:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('Eve', 'Hello World');
SQL
```

The stream includes an aggregation transition from `2` to `3`:

```json
{
  "queryId": "ac1a10bb-59c8-4572-9bf7-c610f166c19d",
  "results": [{
    "type": "aggregation",
    "before": {"MessageText": "Hello World", "Count": 2},
    "after": {"MessageText": "Hello World", "Count": 3},
    "row_signature": 2186641145172575182
  }],
  "timestamp": 1771304966308
}
```

`queryId` is the query's ID (`ac1a10bb-…` is `message-counts`). The timestamp is
when the reaction published the change. `row_signature` is the result row's
identity: use it, not the row's values, to match a change to a row you already
have. It can exceed JavaScript's safe integer range, so read it as text or as a
64-bit integer. `ADD`, `UPDATE`, and `DELETE` differences also carry
`row_signature`.

Delete Eve's message:

```bash
python3 scripts/demo.py sql <<'SQL'
DELETE FROM "Message" WHERE "From" = 'Eve';
SQL
```

The same group changes from `3` back to `2`. Check `results message-counts`
to confirm. Press **Ctrl+C in Terminal 3** before moving to the next stream.
`configs/getting-started-step-5.yaml` intentionally omits the temporary reaction.

The SSE stream is **live observation, not durable replay**. It does not deliver
the rows that existed before you connected, changes made while you were
disconnected, or exactly-once external effects.

### Watch a query from its current results

To see the current rows *and* every change that follows, without creating a
reaction, attach to the query through the Server API. In Terminal 3:

```bash
python3 scripts/demo.py watch message-counts
```

The CLI connects to
`GET /api/v1/instances/getting-started-server/queries/message-counts/attach`.
That stream begins with a `snapshot` event holding the current rows, then sends
each result change that happened after that snapshot, with a `sequence` number:

```text
Attaching to query 'message-counts'; no reaction is created.
Connected to SSE stream at http://127.0.0.1:8180/api/v1/instances/getting-started-server/queries/message-counts/attach
Snapshot of the query's 4 current row(s):
[
  {
    "Count": 2,
    "MessageText": "I am Spartacus"
  },
  …
]
Live changes follow (Ctrl-C to stop).
```

Insert and delete Eve's message again and compare: each change arrives as a
`results` list with the same `before`, `after`, and `row_signature` fields,
plus `query_id`, `sequence`, and `timestamp`. Because the snapshot and the
changes come from one subscription, no change can fall between them. If the
connection drops, reconnect: a new attachment starts with a fresh snapshot.
Press **Ctrl+C** to stop watching.

Use a reaction to deliver changes to another system; use `watch` (or the
`attach` endpoint) to inspect a query.

## Step 6 of 8: Add Time-Based Detection {#phase-4}

`inactive-senders` detects people whose latest observed message change was at
least 20 seconds ago. A time condition alone would only be re-evaluated when
data changes. `drasi.trueLater` schedules another evaluation so that a sender
can become inactive even when no further data arrives.

```yaml
- id: 193fae0b-7cc9-4cfc-bc87-1672662fa02c
  name: inactive-senders
  autoStart: true
  inputs: [{id: 7d38f9ea-27f0-4a2d-830c-da910ed68b6b}]
  result: {label: InactiveSender}
  query: |
    MATCH (m:Message)
    WITH m.From AS MessageFrom, max(drasi.changeDateTime(m)) AS LastMessageTimestamp
    WHERE LastMessageTimestamp <= datetime.realtime() - duration({ seconds: 20 })
      OR drasi.trueLater(LastMessageTimestamp <= datetime.realtime() - duration({ seconds: 20 }),
                         LastMessageTimestamp + duration({ seconds: 20 }))
    RETURN MessageFrom, LastMessageTimestamp
  queryLanguage: Cypher
```

This query deliberately reads **`my-postgres` directly**.
`drasi.changeDateTime(m)` measures the Source node's change timestamp, not
`CreatedAt` or the publication time of a projected query result. Chaining this
query through `all-messages` would change those semantics. Editing an existing
message also counts as activity; this is not a durable record of when somebody
last sent a message, and deleting rows removes them from the calculation.

```bash
curl --fail-with-body -X POST http://127.0.0.1:8180/api/v1/instances/getting-started-server/queries \
  -H 'Content-Type: application/json' --data-binary @configs/inactive-senders.json
```

In Terminal 3:

```bash
python3 scripts/demo.py stream inactive-senders
```

When the query starts, it loads the existing rows (bootstrap) and records the
load time as each row's change time. So no sender is inactive yet. About 20
seconds after you created the query, the stream shows an `ADD` for every
sender, and `python3 scripts/demo.py results inactive-senders` in Terminal 2
lists all of them, including Alice. Every row shows the same
`LastMessageTimestamp`: the load time.

Make Alice active:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('Alice', 'About to go inactive');
SQL
```

Alice leaves the inactive set (`DELETE`). **Wait 20 seconds without another
write**. Alice enters it again (`ADD`) with the new `LastMessageTimestamp`.
An illustrative result difference is:

```json
{
  "data": {
    "LastMessageTimestamp": "2026-11-22T06:50:06.810+00:00",
    "MessageFrom": "Alice"
  },
  "row_signature": 10285043417284617156,
  "type": "ADD"
}
```

Now send another message:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('Alice', 'Active again');
SQL
```

Alice leaves immediately and returns after another idle interval. The `DELETE`
difference carries the previous row in `data`; actual timestamps and signatures
will differ. It is the timer, not a polling loop or another database change,
that adds Alice back.

Stop the SSE CLI with Ctrl+C. The reference is
`configs/getting-started-step-6.yaml`.

## Step 7 of 8: Add Cross-Source Joins {#phase-5}

Add an HTTP Source named `location-tracker`. Its ScriptFile Bootstrap provider
loads four initial `UserLocation` nodes from `locations.jsonl`. The file starts
with a `Header` and ends with `Finish`; the HTTP Source accepts subsequent
location changes.

Both plugins were built in Step 1. In Terminal 2:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8180/api/v1/instances/getting-started-server/sources \
  -H 'Content-Type: application/json' -d '{
    "kind":"http", "id":"9b42f663-9f3d-4655-9843-47120021c01d",
    "name":"location-tracker", "autoStart":true,
    "host":"127.0.0.1", "port":8182,
    "bootstrapProvider":{"kind":"scriptfile","filePaths":["../../locations.jsonl"]}
  }'
```

The helper runs Server in `.runtime/<run-id>/`, so `../../locations.jsonl`
resolves to this tutorial's file. ScriptFile paths are literal filesystem
paths, not environment-variable templates. They are resolved on the Server
host, not in the REST client's current directory.
The automated verifier supplies an absolute path, and when starting from the
completed reference with `start --config server-config.yaml`, the helper writes
the actual absolute tutorial path into its new working configuration.

The join query reads the message **query output** and the new **Source output**:

```yaml
- id: 1261cc70-9cbe-47b9-8ab3-eada717ac2b3
  name: messages-with-location
  autoStart: true
  inputs:
    - {id: 67ff1d64-e938-4a9b-b80e-074666bdef95}
    - {id: 9b42f663-9f3d-4655-9843-47120021c01d}
  result: {label: LocatedMessage}
  query: |
    MATCH (m:Message)-[:FROM_USER]->(u:UserLocation)
    RETURN m.MessageId AS Id, m.Message AS Message,
           m.From AS Sender, u.location AS Location, u.status AS Status
  queryLanguage: Cypher
  joins:
    - id: FROM_USER
      keys:
        - {label: Message, property: From}
        - {label: UserLocation, property: name}
```

`FROM_USER` is a virtual relationship between equal `Message.From` and
`UserLocation.name` values. No relationship is written back to either system.
Both inputs publish the same kind of graph changes, so a result node from
`all-messages` joins just like a node from a Source.

```bash
curl --fail-with-body -X POST http://127.0.0.1:8180/api/v1/instances/getting-started-server/queries \
  -H 'Content-Type: application/json' --data-binary @configs/messages-with-location.json
python3 scripts/demo.py results messages-with-location
```

Brian's existing message should be joined with location `Building A, Floor 3`
and status `online`. In Terminal 3:

```bash
python3 scripts/demo.py stream messages-with-location
```

### Move Brian

In Terminal 2:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8182/sources/9b42f663-9f3d-4655-9843-47120021c01d/events \
  -H 'Content-Type: application/json' -d '{
    "operation":"update",
    "element":{"type":"node","id":"brian","labels":["UserLocation"],
      "properties":{"name":"Brian Kernighan","location":"Conference Room B","status":"away"}}
  }'
```

Brian's joined row changes from `Building A, Floor 3` / `online` to
`Conference Room B` / `away`. The SSE `UPDATE` includes `before`, `after`,
`data` (the new row), and `row_signature`. `Id`, `Message`, and `Sender`
are unchanged.

### Complete a missing join

First insert Carol's message:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('Carol', 'Good morning!');
SQL
python3 scripts/demo.py results messages-with-location
```

Carol is **not** in the joined result yet, although she is in `all-messages`:
there is no matching location. Add it:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8182/sources/9b42f663-9f3d-4655-9843-47120021c01d/events \
  -H 'Content-Type: application/json' -d '{
    "operation":"insert",
    "element":{"type":"node","id":"carol","labels":["UserLocation"],
      "properties":{"name":"Carol","location":"Home Office","status":"online"}}
  }'
```

The SSE stream shows an `ADD` for Carol with `Message: Good morning!`,
`Location: Home Office`, and `Status: online`. This notification was caused by
HTTP data, not another database write.

To observe the other input drive an existing join, update Carol's message:

```bash
python3 scripts/demo.py sql <<'SQL'
UPDATE "Message" SET "Message" = 'Good afternoon!' WHERE "From" = 'Carol';
SQL
```

Now the joined row updates through PostgreSQL, `all-messages`, and the join,
while retaining Carol's location. Stop the CLI with Ctrl+C.

Print the graph again with `python3 scripts/demo.py graph`. It now has two
Sources and five queries. A connection from a Source shows only `data`: the
Source sends a new query its existing rows, read by its Bootstrap Provider, and
then its changes over the same subscription. That is how the join received the
four locations from `locations.jsonl`. Connections between queries show
`data + bootstrap`.

## Step 8 of 8: Keep Query State Across Restarts {#phase-6}

So far every query keeps its indexes, the data it needs to update its results,
in memory. Stopping Server discards them, and the next start rebuilds every
query by reading all of its input rows again (bootstrap). With **durable
indexes**, each query stores its indexes, its current results, and its
position in each input's change stream on disk, using RocksDB. A restart then
resumes from that position: the query applies only the changes it has not seen.

### Turn on durable indexes

Stop the SSE CLI if it is running, then stop Server with **Ctrl+C in
Terminal 1**. Server saved every change you made through the API in its
working configuration, `.runtime/getting-started-cg/getting-started.yaml` (the
directory name is your `DRASI_RUN_ID`). Open that file and change the instance
setting `persistIndex` to `true`:

```yaml
instances:
- id: getting-started-server
  persistIndex: true
```

Start Server:

```bash
python3 scripts/demo.py start
```

Server refuses to start. The error ends with:

```text
IncompatibleSource: sources that do not support replay cannot feed persistent query '1261cc70-9cbe-47b9-8ab3-eada717ac2b3' (source '9b42f663-9f3d-4655-9843-47120021c01d', supports_replay=false)
ERROR: Server exited during startup: 1
```

Before Server starts a query, it checks that every input can provide what the
query needs. A durable query must be able to ask its inputs to replay the
changes it missed while Server was stopped. PostgreSQL can: the replication
slot keeps each change until Drasi confirms it, and the queries that read
`all-messages` can ask that query. The HTTP Source `location-tracker`
(`9b42f663-…`) cannot: it only sees the requests sent to it while it runs. So
`messages-with-location` (`1261cc70-…`) cannot be durable.

### Keep the join in memory

Each query can choose its own index storage. In the same file, find the
`messages-with-location` query and add `storageBackend` below its `result`:

```yaml
  - id: 1261cc70-9cbe-47b9-8ab3-eada717ac2b3
    name: messages-with-location
    # ... keep the existing settings ...
    result:
      label: LocatedMessage
    storageBackend:
      kind: memory
```

Run `python3 scripts/demo.py start` again. Server reaches `READY`. The four
queries that do not depend on the HTTP Source now keep their indexes under
`.runtime/<run-id>/data/`; the join keeps its indexes in memory.

### Change data while Server is stopped

Stop Server with Ctrl+C. While it is stopped, insert a message in Terminal 2:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('Dana', 'Hello World');
SQL
```

Start Server again with `python3 scripts/demo.py start`, then check the
filtered query in Terminal 2:

```bash
python3 scripts/demo.py results hello-world-senders
```

Dana is listed. Look at Terminal 1's startup output. It has no
`Bootstrapped ... rows from table 'Message'` lines this time: the durable
queries did not read the table again. They resumed from their saved positions
in the replication slot (`Replication started from read LSN ...`) and processed
only Dana's insert. `message-counts` counts one more `Hello World` message, and
Dana joins `inactive-senders` 20 seconds after Server processed her message.

Only the in-memory join bootstrapped again:
`Bootstrap completed successfully for query '1261cc70-…', sent 4 events`.
Brian is back at `Building A, Floor 3`, and Carol has no location until you send
it again, because no component stored the HTTP location updates.

`server-config.yaml` is the reference configuration for the end of this step:
two Sources, five queries with durable indexes except the in-memory join, and
the Log Reaction.

## Stop and Clean Up {#cleanup}

Stop SSE before Server. A normal CLI exit deletes its temporary reaction.
If the CLI was forcibly killed, inspect the instance's `/reactions` endpoint
and delete only its recorded `sse-cli-...` reaction; don't remove somebody
else's subscription.

Stop Server with **Ctrl+C in Terminal 1**. The helper waits for that child
process only. Run `python3 scripts/demo.py start` again to reuse the working
configuration. Here is what each restart keeps:

| State | Where it lives | After a restart |
| --- | --- | --- |
| Sources, queries, reactions | Working configuration (`persistConfig: true`) | Recreated as you last changed them |
| Messages | The owned PostgreSQL volume | Unchanged; changes made while Server was stopped wait in the replication slot |
| Durable query indexes and results | `.runtime/<run-id>/data/` | Restored; queries resume from their saved positions |
| In-memory query indexes | Server memory | Rebuilt from the inputs (bootstrap) |
| HTTP location updates | Nowhere | Lost; the join starts again from `locations.jsonl` |

Neither the Log nor the SSE Reaction records what it delivered, so neither
promises exactly-once effects across restarts.

Remove only this run's database container, keeping its volume:

```bash
python3 scripts/demo.py cleanup
```

Or explicitly remove the owned database volume too:

```bash
python3 scripts/demo.py cleanup --volumes
```

`--volumes` also deletes the run's saved query state in `.runtime/<run-id>/data/`.
That state records positions in the deleted database's change stream, so the
next start must bootstrap from the new database instead of resuming.

The helper refuses cleanup while its Server lock exists and refuses unowned
containers or volumes. It never kills processes by name. Configuration, build
provenance, and logs remain in `.runtime/`. For a fresh walkthrough, use a new
run ID and free ports instead of resetting old data.

## Optional Viewer and Repeatable Checks

While Server is running, start the viewer:

```bash
bash scripts/open-viewer.sh
```

Open `http://127.0.0.1:5173` and click **Connect / refresh**. The viewer attaches
to each tutorial query that exists, the same way `watch` does: each table starts
from the query's snapshot and applies every change that follows. If the
connection drops, the browser reconnects and the next snapshot replaces the
table. Click **Connect / refresh** after adding queries. The event log keeps
the received text, including large row signatures; it is not a durable history.

For a self-checking run after building local artifacts:

```bash
bash scripts/run-end-to-end.sh
```

This uses a fresh run name, free loopback ports, and isolated owned data.
It exercises the same eight-step sequence: the incremental five-query graph,
controlled SQL/HTTP changes, timer transitions, ordinary SSE payloads, the
snapshot-first `attach` stream, and the durable-index restart, including the
rejected HTTP-fed durable query. It then cleans only its resources and writes
`acceptance.json` in its run directory. It does not invoke Cargo.

Lightweight configuration/helper tests use a separate test-only environment:

```bash
python3 -m venv .runtime/test-venv
.runtime/test-venv/bin/pip install -r scripts/requirements-test.txt
.runtime/test-venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
node --test scripts/test_viewer.cjs
```

The viewer checks use Node.js's built-in test runner and need no npm packages.

## What You've Learned {#summary}

You built a message monitor using Sources, five Continuous Queries, and
Reactions. You caused changes and watched them propagate through filters,
aggregations, time-based conditions, and a cross-source join. Along the way:

- Server runs the Sources, queries, and Reactions as one graph. The labeled
  `all-messages` output became a reusable input to three other queries, and
  `graph` showed each connection, including the bootstrap connections that
  give a new query the current upstream results.
- An API change is accepted first and then applied; check the component, not
  only the response, to know when it is running.
- A Reaction delivers changes to other systems; `watch` (the query `attach`
  endpoint) shows a query's current rows followed by its changes.
- Durable indexes let queries resume after a restart. Server checks that every
  input of a durable query can replay what it missed, and each query can choose
  in-memory storage instead.

For another scenario, keep the same approach: establish the input data,
project a useful shared result, add focused queries, then attach reactions
appropriate for the effects you need. Explore the other tutorials in this
repository or use `drasi-lib` directly when embedding the runtime in an
application.
