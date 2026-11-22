# Drasi SSE CLI

Watch a continuous query while changing its source data. The CLI has three
modes:

- **Temporary reaction** (default): create an SSE reaction for the query, print
  its JSON notifications, and delete the reaction when you press Ctrl-C.
- **Attach** (`--attach`): read the query through the Server API. The stream
  starts with the query's current rows and continues with every later change.
  Nothing is created on the server.
- **Existing endpoint** (`--sse-url`): observe an SSE endpoint that already
  exists, without changing the server.

This helper is built from this repository and runs against the Server and
plugins built from your local checkouts, not a released binary or Server's
separate `examples/sse-cli`. Each endpoint sends its own JSON format; the CLI
prints whichever JSON the selected endpoint sends.

## Build the local helper

Use the existing sibling checkouts:

```text
computation-graph/
  drasi-core/
  drasi-server/
  learning-drasi-server/
```

Build Server and its matching local `drasi-reaction-sse` plugin using the
[Getting Started tutorial](../getting-started). Do not mix downloaded plugins
with the local Server/Core build. The instance and query must already be
running. The temporary-reaction mode also needs permission to create and delete
reactions through the API (Server must not be read-only).

The helper needs Python 3, `rustup`, Rust `1.95.0`, and the dependencies from its
committed Cargo lockfile in the local Cargo cache. From `learning-drasi-server/`:

```bash
python3 tutorials/sse-cli/scripts/build.py \
  --destination tutorials/sse-cli/bin/drasi-sse-cli \
  --state tutorials/sse-cli/bin/provenance.json

python3 tutorials/sse-cli/scripts/build.py \
  --destination tutorials/sse-cli/bin/drasi-sse-cli \
  --state tutorials/sse-cli/bin/provenance.json \
  --verify-only
```

The builder runs only this tutorial's manifest with `--offline --locked -j 1`.
It defaults to `../drasi-server/target` and the debug profile; `--target-dir`,
`--profile release`, and `--toolchain` are explicit overrides. It does not
download a toolchain, dependencies, released CLI, Server, or plugins. A missing
toolchain/cache is an error: prepare that prerequisite explicitly, then rerun.
Coordinate access to the shared target directory when other builds are running.
Do not inherit a cross-compilation target into a local build.

`--destination` is the exact installed executable path, and `--state` is the
provenance JSON path. For example, Getting Started can choose its own
`tutorials/getting-started/bin/drasi-sse-cli` and adjacent provenance file.
The receipt records the build command, compiler, source/lockfile SHA256 values,
and installed executable SHA256. `--verify-only` checks this checkout and that
installed binary without invoking Cargo. Rebuild after changing CLI sources.
This receipt covers the CLI only, not Server or plugin provenance.

## Trigger and observe a change

Keep the [Getting Started](../getting-started) server running. In another terminal:

```bash
tutorials/sse-cli/bin/drasi-sse-cli \
  --server http://127.0.0.1:8180 \
  --instance getting-started-server \
  --query ac1a10bb-59c8-4572-9bf7-c610f166c19d
```

Wait for `Connected to SSE stream`, then perform the tutorial's next
message insert, update, or delete in its database terminal. The CLI is an
observer, not a replacement source or a row cache. Check the resulting
`results` array on your terminal, then press **Ctrl-C**. Status messages go to
stderr; only JSON data goes to stdout.

The temporary reaction streams **future changes**, not an initial snapshot.
Rows that existed before you connected do not appear. An aggregate can emit an
update rather than an insert, and a row leaving a query is a query result
deletion even if its source row was updated rather than deleted.

## Attach to a query

To start from the current rows, attach instead:

```bash
tutorials/sse-cli/bin/drasi-sse-cli \
  --server http://127.0.0.1:8180 \
  --instance getting-started-server \
  --query message-counts --attach
```

The CLI connects to
`/api/v1/instances/getting-started-server/queries/message-counts/attach`. The
first event is named `snapshot`; its data is the array of current rows. The CLI
prints that array and reports `Snapshot of the query's N current row(s)` on
stderr. Every later event is one result change, with a `sequence` number:

```json
{
  "query_id": "ac1a10bb-59c8-4572-9bf7-c610f166c19d",
  "sequence": 2,
  "timestamp": "2026-11-22T07:05:20.806076Z",
  "results": [
    {
      "type": "aggregation",
      "before": {"Count": 2, "MessageText": "Hello World"},
      "after": {"Count": 3, "MessageText": "Hello World"},
      "row_signature": 2186641145172575182
    }
  ],
  "metadata": {"processed_by": "drasi-core", "result_count": 1}
}
```

The real payload also includes `query_name`, `input_alias`, more `metadata`,
and a `profiling` object with processing timestamps. The snapshot and the
changes come from one subscription, so no change falls between them. Attaching
creates nothing on the server: no reaction, no port, and nothing to clean up.
If the stream ends, attach again; the new stream starts with a fresh snapshot.

## Command-line contract

```text
drasi-sse-cli --server URL --instance ID --query ID [OPTIONS]
drasi-sse-cli --server URL --instance ID --query ID --attach [--debug] [--log-file FILE]
drasi-sse-cli --sse-url URL [--debug] [--log-file FILE]
```

| Option | Meaning |
| --- | --- |
| `-s`, `--server` | Server API base URL; alternatively `DRASI_SERVER_URL` |
| `-i`, `--instance` | Explicit instance; alternatively `DRASI_INSTANCE_ID` |
| `-q`, `--query` | Existing query name or UUID; alternatively `DRASI_QUERY` |
| `--attach` | Read the query's snapshot and changes through the Server API; creates no reaction |
| `-p`, `--sse-port` | Temporary reaction's HTTP port, default `8090`; choose an unused nonzero port |
| `--sse-host` | Reaction bind IP, default **`127.0.0.1`** |
| `--sse-url` | Connect to an existing endpoint; no creation or deletion |
| `-d`, `--debug` | Show heartbeat timestamps and SSE protocol lines on stderr |
| `-l`, `--log-file` | Append the same pretty-printed JSON as stdout to a file |
| `-h`, `--help` | Show full usage |

`--attach` cannot be combined with `--sse-port`, `--sse-host`, or `--sse-url`.
`--sse-url` is a separate mode and cannot be combined with `--server`,
`--instance`, `--query` (including their environment variables), `--sse-port`,
or `--sse-host`.

The reaction binds loopback by default rather than exposing query results to the
network. The CLI connects to `http://<server-host>:<sse-port>/events`; this
listener is separate from the API port and serves HTTP even if the API uses
HTTPS. If Server is remote, prefer an authenticated tunnel/proxy to an existing
endpoint with `--sse-url`. Explicit `--sse-host 0.0.0.0` enables a remote
reaction listener only when intended: secure that port yourself. The reaction
does not add authentication or TLS. For IPv6 loopback, use `--sse-host ::1`
and an appropriate `[::1]` Server URL.

To watch two queries, run two terminals with different unused `--sse-port`
values. Creation and deletion both address the selected instance; the CLI
never chooses the first instance or removes a pre-existing reaction.

## Know which stream you selected

| Endpoint | JSON data contract |
| --- | --- |
| Temporary ordinary `kind: sse` reaction, `/events` | `queryId`, `results`, `timestamp` |
| Existing native `drasi.network/sse-sink`, configured SSE path | `output`, `sequence`, `publishedAt`, `changes` |
| Server API `/api/v1/instances/<instance>/queries/<query>/attach` (`--attach`) | Named `snapshot` event with a row array, then result changes using `query_id`, `sequence`, `timestamp`, `results`, `metadata` |

These are **not interchangeable formats**. The CLI displays their JSON data
without converting one to another. SSE `event:`, `id:`, comments, and retry
fields are protocol metadata, shown only with `--debug`; they are not injected
into stdout or the log. The one exception is a `snapshot` event, which the CLI
announces on stderr. This is a JSON observer, not a protocol replay file.
Custom endpoint templates must produce valid JSON; plain-text templates fail
explicitly. JSON is parsed for formatting, not application-schema validation.

### Ordinary reaction: query result diffs

The `kind: sse` reaction sends each batch of row differences as one event. An
insert into Getting Started's `all-messages` query looks like this:

```json
{
  "queryId": "67ff1d64-e938-4a9b-b80e-074666bdef95",
  "results": [
    {
      "data": {"From": "Bob", "Message": "Goodbye World", "MessageId": 7},
      "row_signature": 12345,
      "type": "ADD"
    }
  ],
  "timestamp": 1795330145558
}
```

`queryId` is the query's ID, even when you selected the query by name.
`row_signature` identifies the result row; it comes from the query engine and is
not a source primary key or a value generated by this CLI. Actual signatures
and timestamps vary.

| `type` | Fields carried by the adapter |
| --- | --- |
| `ADD` | `data`, `row_signature` |
| `UPDATE` | `data`, `before`, `after`, `row_signature`, optional `grouping_keys` |
| `DELETE` | `data`, `row_signature` |
| `aggregation` | `before` (may be null), `after`, `row_signature` |
| `noop` | No row change |

For example, an update's `before` and `after` are siblings of `data`, not nested
under it. All records in the received batch, including aggregation/noop records
if emitted, are retained. The millisecond `timestamp` is when the reaction
published the change; the reaction does not send the query's sequence number.
Use `--attach` when you need it.

```bash
tutorials/sse-cli/bin/drasi-sse-cli \
  -s http://127.0.0.1:8180 -i getting-started-server -q message-counts \
  --log-file events.json | jq '.results[]'
```

The log is a sequence of pretty-printed JSON values, not a single JSON array or
one-line NDJSON. Tools such as `jq` can read that sequence. Take care when passing
64-bit row signatures to tools that round JSON numbers.

### Existing native sink: producer-neutral graph changes

For an already-configured, owned native sink:

```bash
tutorials/sse-cli/bin/drasi-sse-cli --sse-url http://127.0.0.1:9010/events
```

No instance or query is invented. A native output can come from a source,
transformer, or query. For example, this is a patch followed by an identity-only
delete (illustrative, not a promised emission from Getting Started):

```json
{
  "output": {"alias": "items", "component": "inventory-source", "port": "out"},
  "sequence": 42,
  "publishedAt": 1793127600000,
  "changes": [
    {
      "operation": "PATCH",
      "identity": {"namespace": "inventory", "id": "item-1"},
      "after": {"note": null},
      "removedProperties": ["oldNote"]
    },
    {
      "operation": "DELETE",
      "identity": {"namespace": "inventory", "id": "item-2"}
    }
  ]
}
```

Native operations are `ADD`, `REPLACE`, `PATCH`, and `DELETE`. `ADD`/`REPLACE`
carry full after images; a `PATCH` after image contains only properties being
set. Setting a property to null is different from removing it using
`removedProperties`. Identity-only deletion has no manufactured row or before
image. `element`, `before`, `after`, and `effectiveFrom` appear only if supplied.
`publishedAt` is the sink's wall clock, not business/event time.

The CLI preserves nested objects, lists, nulls, strings representing temporal
values, large numbers, and all supplied change metadata. It does not apply
patches, merge a row cache, infer missing images, or add `queryId` or row
signatures to native data.

## Transport, cleanup, and limits

In temporary mode the CLI posts to
`/api/v1/instances/<instance>/reactions` with `kind: "sse"`, a unique
`sse-cli-<uuid>` ID, `queries: [<query>]`, `autoStart: true`, and the chosen
host/port plus `ssePath: "/events"`. Server acknowledges the reaction before its
listener accepts connections, so the CLI retries refused connections for up to
10 seconds. In attach mode the CLI only reads
`/api/v1/instances/<instance>/queries/<query>/attach`.

The parser assembles complete SSE events across HTTP chunks, handles UTF-8
characters split between chunks, LF/CRLF/CR line endings, and joins multiple
`data:` lines. Heartbeats of the form `{"type":"heartbeat","ts":123}` are
excluded from stdout/logs; debug mode shows their real timestamp.

Ctrl-C after creation closes the connection and deletes **only this CLI's**
reaction. Stream, JSON, UTF-8, stdout/log write, and cleanup failures produce
diagnostics and a nonzero exit status. Opening a bad log path fails before
creating a reaction. A failed create request reports the generated reaction ID
to inspect if the remote server completed an ambiguous request. Forced
termination or an unreachable server can prevent cleanup; do not assume a
reaction was deleted unless deletion was confirmed.

The CLI does **not** silently reconnect on EOF: a server close or lag
disconnection may mean missing notifications, so it reports failure. Native
and ordinary SSE sinks provide volatile notifications, not retained history,
replay, or exactly-once delivery. Reconnect explicitly, and obtain a fresh
snapshot if your downstream consumer maintains state. The native sink's
`/snapshot/<alias>` is a separate point-in-time read; an `--attach` stream
includes its own snapshot, so a new attachment is the simplest way to start
again from current rows.

## Contributor checks

From `learning-drasi-server/`, with exclusive access to the shared Rust target:

```bash
rustup run 1.95.0 cargo fmt --manifest-path tutorials/sse-cli/Cargo.toml --check
rustup run 1.95.0 cargo test --manifest-path tutorials/sse-cli/Cargo.toml \
  --target-dir ../drasi-server/target --offline --locked -j 1

DRASI_SSE_CLI="$PWD/tutorials/sse-cli/bin/drasi-sse-cli" \
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tutorials/sse-cli/tests -v
```

Rust tests cover framing, event names, mode selection, binding, and payload
preservation. Python tests cover provenance and a locally owned mock HTTP
server's lifecycle, errors, Ctrl-C cleanup, logging, attach, and connect-only
behavior. These are regression checks, **not live Drasi proof**. For live
validation, run Getting Started's `bash scripts/run-end-to-end.sh`: it drives
the CLI's temporary-reaction and attach modes against real source changes and
confirms the temporary reactions disappear. A native sink needs its own live
check; ordinary reaction evidence does not establish the native sink's format.
