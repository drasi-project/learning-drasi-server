# Drasi SSE CLI

Watch a continuous query while changing its source data. The CLI creates a
temporary SSE reaction, prints the JSON notifications to your terminal, and
deletes its reaction when you press Ctrl-C. It can also observe an existing SSE
endpoint without changing the server.

This helper uses the **current local ComputationGraph-based Server and matching
Core plugins**, not a released binary or Server's separate `examples/sse-cli`.
Ordinary query reactions and native graph sinks expose different payloads; the
CLI preserves whichever JSON the selected endpoint actually sends.

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
with the local Server/Core build. ComputationGraph is always enabled; there is
no execution-mode flag. The instance and query must already be running and
must permit imperative reaction creation.

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
  --server http://127.0.0.1:8080 \
  --instance getting-started-server \
  --query message-counts
```

Wait for `Connected to SSE stream`, then perform the tutorial's next
message insert, update, or delete in its database terminal. The same queries,
SQL changes, and observation sequence still apply; the CLI is an observer,
not a replacement source or a row cache. Check the resulting `results` array
on your terminal, then press **Ctrl-C**. Status messages go to stderr; only JSON
data goes to stdout.

The temporary reaction streams **future changes**, not an initial snapshot.
Rows that existed before you connected do not automatically appear. An aggregate
can emit an update rather than an insert, and a row leaving a query is a query
result deletion even if its source row was updated rather than deleted.

## Command-line contract

```text
drasi-sse-cli --server URL --instance ID --query ID [OPTIONS]
drasi-sse-cli --sse-url URL [--debug] [--log-file FILE]
```

| Option | Meaning |
| --- | --- |
| `-s`, `--server` | Server API base URL; alternatively `DRASI_SERVER_URL` |
| `-i`, `--instance` | Explicit instance; alternatively `DRASI_INSTANCE_ID` |
| `-q`, `--query` | Existing query ID; alternatively `DRASI_QUERY` |
| `-p`, `--sse-port` | Temporary reaction's HTTP port, default `8090`; choose an unused nonzero port |
| `--sse-host` | Reaction bind IP, default **`127.0.0.1`** |
| `--sse-url` | Connect to an existing endpoint; no creation or deletion |
| `-d`, `--debug` | Show heartbeat timestamps and SSE protocol lines on stderr |
| `-l`, `--log-file` | Append the same pretty-printed JSON as stdout to a file |
| `-h`, `--help` | Show full usage |

Existing tutorial `--server` / `--instance` / `--query` commands remain supported.
`--sse-url` is a separate mode and cannot be combined with those options
(including their environment variables), `--sse-port`, or `--sse-host`.

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
| Server API `/api/v1/instances/<instance>/queries/<query>/attach` | Named `snapshot` event with a row array, then `QueryResult` payloads using `query_id`, `sequence`, `timestamp`, `results`, `metadata` |

These are **not interchangeable envelopes**. `--sse-url` displays their JSON
data without converting one to another. SSE `event:`, `id:`, comments, and retry
fields are protocol metadata, shown only with `--debug`; they are not injected
into stdout or the log. This is a JSON observer, not a protocol replay file.
Custom endpoint templates must produce valid JSON; plain-text templates fail
explicitly. JSON is parsed for formatting, not application-schema validation.

### Ordinary reaction: query result diffs

The current default reaction sends `ResultDiff` records, not the old
`{"op":"i"}` / `{"op":"u"}` / `{"op":"d"}` examples. An illustrative insert:

```json
{
  "queryId": "all-messages",
  "results": [
    {
      "type": "ADD",
      "data": {"Id": 6, "Sender": "Bob", "Message": "Hello"},
      "row_signature": 12345
    }
  ],
  "timestamp": 1793127600000
}
```

`row_signature` comes from the query engine; it is not a source primary key or
a value generated by this CLI. Actual signatures and timestamps vary.

| `type` | Fields carried by the adapter |
| --- | --- |
| `ADD` | `data`, `row_signature` |
| `UPDATE` | `data`, `before`, `after`, `row_signature`, optional `grouping_keys` |
| `DELETE` | `data`, `row_signature` |
| `aggregation` | `before` (may be null), `after`, `row_signature` |
| `noop` | No row change |

For example, an update's `before` and `after` are siblings of `data`, not nested
under it. All records in the received batch, including aggregation/noop records
if emitted, are retained. This renderer's millisecond `timestamp` is its
publication time; it does not expose the underlying `QueryResult` sequence.

```bash
tutorials/sse-cli/bin/drasi-sse-cli \
  -s http://127.0.0.1:8080 -i getting-started-server -q message-counts \
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
host/port plus `ssePath: "/events"`. Current reaction startup binds its listener
before reporting readiness, so no arbitrary one-second sleep is required.

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
`/snapshot/<alias>` is a point-in-time read; the Server query `/attach` endpoint
has its own snapshot-first subscription contract.

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

Rust tests cover framing, mode selection, binding, and payload preservation.
Python tests cover provenance and a locally owned mock HTTP server's lifecycle,
errors, Ctrl-C cleanup, logging, and connect-only behavior. These are regression
checks, **not live Drasi proof**. For live validation, build matching local
Server/Core plugins, start an isolated owned tutorial instance, run the CLI,
perform real source changes, compare observed query notifications, and confirm
its temporary reaction disappeared. A native sink needs its own live check;
ordinary reaction evidence does not establish the native wire contract.
