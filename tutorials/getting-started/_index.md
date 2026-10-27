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
| [4. Filter messages](#phase-2) | Add `hello-world-senders` to the running Server |
| [5. Count messages](#phase-3) | Add `message-counts` and stream changes through SSE |
| [6. Detect inactivity](#phase-4) | Watch `inactive-senders` change without new database writes |
| [7. Join locations](#phase-5) | Join the message feed with live HTTP location updates |

**The runtime is ComputationGraph.** Sources, queries, and reactions are connected
components in the same running graph. The convenient `sources`, `queries`, and
`reactions` configuration below uses that runtime directly; it is not a
different engine or an opt-in execution mode.

An `inputs` entry names an upstream component, not just a Source. We will reuse
the `all-messages` query's output for filtering, counting, and joining, instead
of repeating the message projection or introducing another connector.

## Step 1 of 7: Set Up Your Environment {#setup}

Use these existing sibling checkouts, on matching ComputationGraph-capable
branches, in the same parent directory:

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
The [local source setup page](download-binary/) explains the replacement for
the previous binary-download route. A standard single-repository
[Codespace is not sufficient](github-codespace/).

In a terminal, change to `learning-drasi-server/tutorials/getting-started`.
**All commands below run from this directory**, not from `drasi-server/`.

```bash
cp .env.example .env
python3 scripts/demo.py build
python3 scripts/demo.py build-cli
python3 scripts/demo.py verify-build
```

`build` compiles Server and **separately compiles all six dynamic plugins**:
PostgreSQL Source and Bootstrap, Log and SSE Reactions, HTTP Source, and ScriptFile
Bootstrap. It records source/build provenance and copies the exact artifacts to
a private hash-checked bundle. `build-cli` builds this repository's
`tutorials/sse-cli`, installs a private copy, and records its provenance.
Every start verifies the bundle; every `stream` command verifies the CLI.
After editing either checkout or the CLI, rebuild the corresponding artifacts.
Do not share a Cargo target with another simultaneous build.

The `.env` defaults select run `getting-started-cg`, PostgreSQL port `5532`,
Server API `8180`, SSE `8181`, and HTTP Source `8182`. Everything binds to
`127.0.0.1`. For another run, choose a new `DRASI_RUN_ID` **and four free ports**
before starting. Helpers read `.env` in each terminal; the curl examples and
`requests.http` use the defaults, so adjust their URLs if you change ports.
Database credentials in the sample are for this isolated local database only.

Use **Terminal 1** for Server, **Terminal 2** for SQL and REST calls, and
**Terminal 3** for SSE. The helper scripts keep process and container ownership
separate from the query concepts you are learning.

## Step 2 of 7: Set Up the Tutorial Database {#database}

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

## Step 3 of 7: Run Your First Drasi Server {#phase-1}

The initial `configs/getting-started-step-3.yaml` declares an instance named
`getting-started-server`, a PostgreSQL Source `my-postgres`, one query, and
`log-reaction`. The Source reads existing rows with its PostgreSQL Bootstrap
provider and then follows database changes through CDC.

Here is the first query:

```yaml
- id: all-messages
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
contract: query output is always **canonical graph-change v1**.

In **Terminal 1**:

```bash
python3 scripts/demo.py start
```

On first start this copies the step-3 configuration to
`.runtime/getting-started-cg/getting-started.yaml`. Subsequent starts retain
that working copy. REST changes are saved there because `persistConfig: true`;
the checked-in reference configurations are never modified.

Server loads only the local hash-checked plugin directory.
`autoInstallPlugins: false` prevents registry fallback. `--skip-verification`
is used only for this unsigned local development bundle, not arbitrary
downloaded plugins. Missing or changed artifacts are an error, not a reason to
download replacements. The optional Admin UI is disabled; it is not required
for this walkthrough.

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
curl --fail-with-body http://127.0.0.1:8180/api/v1/instances/getting-started-server/queries/all-messages/results
```

There should be four rows, including:

```json
{"MessageId":2,"From":"Brian Kernighan","Message":"Hello World"}
```

Results are current state, not an event history. Ordering is not guaranteed.
The same requests are in `requests.http` for VS Code's REST Client extension.

### Cause an insert, update, and delete

In **Terminal 2**, insert your first message:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('You', 'My first message!');
SQL
```

The Log Reaction prints an `ADD` from `all-messages`:

```text
[log-reaction]   [ADD] {"From":"You","Message":"My first message!","MessageId":5}
```

Now update it:

```bash
python3 scripts/demo.py sql <<'SQL'
UPDATE "Message" SET "Message" = 'My first UPDATED message!' WHERE "From" = 'You';
SQL
```

The Log Reaction prints `UPDATE`, with the old and new message text. Finally:

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

## Step 4 of 7: Add a Continuous Query with Criteria {#phase-2}

Who sent messages containing exactly `Hello World`? Add a query to the running
Server without restarting:

```yaml
- id: hello-world-senders
  autoStart: true
  inputs: [all-messages]
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

Subscribe the Log Reaction to both queries using the current API's `PUT`
operation. It replaces the reaction and resumes it if it was running, without
requiring a separate delete and create:

```bash
curl --fail-with-body -X PUT http://127.0.0.1:8180/api/v1/instances/getting-started-server/reactions/log-reaction \
  -H 'Content-Type: application/json' \
  -d '{"kind":"log","id":"log-reaction","autoStart":true,"queries":["all-messages","hello-world-senders"]}'
python3 scripts/demo.py results hello-world-senders
```

Brian Kernighan is already in the current results: `{"Id":2,"Sender":"Brian Kernighan"}`.
Adding a reaction later is not a promise to replay changes that happened before
it subscribed; use the results endpoint to inspect current state.
Replacing a reaction can replay retained changes, so repeated console messages
are not evidence of duplicate database writes or exactly-once delivery.

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

## Step 5 of 7: Add an Aggregation Query and the SSE Reaction {#phase-3}

`message-counts` counts how many times each message text appears:

```yaml
- id: message-counts
  autoStart: true
  inputs: [all-messages]
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

**Graph data versus reaction payloads:** ComputationGraph transports canonical
graph-change v1 internally. The ordinary `kind: sse` reaction used here is a
query-output adapter and emits `{queryId, results, timestamp}` with typed
result differences. Its `results` are not native graph-change records.
Native graph sinks can consume Source, transformer, or query outputs; ordinary
Log/SSE reaction adapters still require **query output**. No custom sink is
needed for this tutorial.

In Terminal 2:

```bash
python3 scripts/demo.py sql <<'SQL'
INSERT INTO "Message" ("From", "Message") VALUES ('Eve', 'Hello World');
SQL
```

The stream includes an aggregation transition from `2` to `3`:

```json
{
  "queryId": "message-counts",
  "results": [{
    "type": "aggregation",
    "before": {"MessageText": "Hello World", "Count": 2},
    "after": {"MessageText": "Hello World", "Count": 3},
    "row_signature": 2186641145172575182
  }],
  "timestamp": 1771304966308
}
```

The timestamp and opaque `row_signature` are illustrative. Preserve result
identity rather than treating the row's JSON values as its identity; the
signature may exceed JavaScript's safe integer range. Non-aggregate `ADD`,
`UPDATE`, and `DELETE` differences also carry `row_signature`.

Delete Eve's message:

```bash
python3 scripts/demo.py sql <<'SQL'
DELETE FROM "Message" WHERE "From" = 'Eve';
SQL
```

The same group changes from `3` back to `2`. Check `results message-counts`
to confirm. Press **Ctrl+C in Terminal 3** before moving to the next stream.
`configs/getting-started-step-5.yaml` intentionally omits the temporary reaction.

The SSE stream is **live observation, not durable replay**. It does not promise
delivery of bootstrap rows, missed events, or exactly-once external effects.
A fresh REST snapshot and a separate SSE subscription are not an atomic
snapshot-plus-stream handoff. This exercise connects first, then makes a
controlled change; current state is checked independently.

## Step 6 of 7: Add Time-Based Detection {#phase-4}

`inactive-senders` detects people whose latest observed message change was at
least 20 seconds ago. A time condition alone would only be re-evaluated when
data changes. `drasi.trueLater` schedules another evaluation so that a sender
can become inactive even when no further data arrives.

```yaml
- id: inactive-senders
  autoStart: true
  inputs: [my-postgres]
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

Bootstrap can assign load-time change timestamps. Do not assume old database
rows are immediately inactive when a new query starts. Wait at least 20
seconds, then check `python3 scripts/demo.py results inactive-senders` in
Terminal 2; Alice should now be present.

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
  "type": "ADD",
  "data": {"MessageFrom": "Alice", "LastMessageTimestamp": "ZonedDateTime(2026-02-17 05:35:51.703 +00:00)"},
  "row_signature": 12345
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

## Step 7 of 7: Add Cross-Source Joins {#phase-5}

Add an HTTP Source named `location-tracker`. Its ScriptFile Bootstrap provider
loads four initial `UserLocation` nodes from `locations.jsonl`. The file starts
with a `Header` and ends with `Finish`; the HTTP Source accepts subsequent
location changes.

Both plugins were built in Step 1. In Terminal 2:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8180/api/v1/instances/getting-started-server/sources \
  -H 'Content-Type: application/json' -d '{
    "kind":"http", "id":"location-tracker", "autoStart":true,
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
- id: messages-with-location
  autoStart: true
  inputs: [all-messages, location-tracker]
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
Both inputs use the same graph contract, so a derived message node joins just
like a Source node.

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
curl --fail-with-body -X POST http://127.0.0.1:8182/sources/location-tracker/events \
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
curl --fail-with-body -X POST http://127.0.0.1:8182/sources/location-tracker/events \
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
`server-config.yaml` is the completed five-query reference, not a different
three-query demo.

## State, Restarts, and Cleanup {#cleanup}

Stop SSE before Server. A normal CLI exit deletes its temporary reaction.
If the CLI was forcibly killed, inspect the instance's `/reactions` endpoint
and delete only its recorded `sse-cli-...` reaction; don't remove somebody
else's subscription.

Stop Server with **Ctrl+C in Terminal 1**. The helper waits for that child
process only. Run `python3 scripts/demo.py start` again to reuse the working
configuration and rebuild in-memory query state from the inputs.

**Configuration persistence is not data durability.** This tutorial uses
`persistIndex: false`. PostgreSQL rows survive in the owned volume, but the
HTTP location updates are not written back to `locations.jsonl`: after a full
restart Brian starts at the file's original location and Carol has no location
until you send it again. Inactivity timers are rebuilt from observed input
timestamps; they are not a durable alarm-delivery ledger. Neither Log nor SSE
claims exactly-once external effects across restarts.

Remove only this run's database container, keeping its volume:

```bash
python3 scripts/demo.py cleanup
```

Or explicitly remove the owned database volume too:

```bash
python3 scripts/demo.py cleanup --volumes
```

The helper refuses cleanup while its Server lock exists and refuses unowned
containers or volumes. It never kills processes by name. Configuration,
build provenance, and logs remain in `.runtime/`. For a fresh seven-step
walkthrough use a new run ID and free ports instead of resetting old data.

## Optional Viewer and Repeatable Checks

While one SSE CLI is connected, run:

```bash
bash scripts/open-viewer.sh
```

Open `http://127.0.0.1:5173` and click **Connect / refresh**. The viewer fetches
current results for the configured queries and refreshes the subscribed
query's table when an event arrives. Other queries' tables remain snapshots
until refreshed or subscribed. Its event log preserves received payload text,
including large row signatures, without claiming it is a durable history.
Reconnect after adding queries or changing the CLI subscription.

For a self-checking run after building local artifacts:

```bash
bash scripts/run-end-to-end.sh
```

This uses a fresh run name, free loopback ports, and isolated owned data.
It exercises the same incremental five-query sequence, controlled SQL/HTTP
changes, timer transitions, ordinary SSE payloads, and full Server restart,
then cleans only its resources. Its report distinguishes live acceptance from
configuration or compiler checks. It does not invoke Cargo.

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
aggregations, time-based conditions, and a cross-source join. The labeled
`all-messages` output became a reusable input to three other queries in the
same ComputationGraph.

For another scenario, keep the same approach: establish the input data,
project a useful shared result, add focused queries, then attach reactions
appropriate for the effects you need. Explore the other tutorials in this
repository or use `drasi-lib` directly when embedding the runtime in an
application.
