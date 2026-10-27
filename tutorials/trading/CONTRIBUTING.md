# Contributing to the Trading tutorial

Follow [the tutorial](README.md) using the existing sibling
`drasi-server/examples/trading` application. The copied application files in this
directory are not the current entry point. Update the actual source example
when changing app behavior; keep tutorial instructions and launch/check helpers
here. Do not create another application copy or regenerate unrelated tutorials.

## Hands-on extensions

1. **Change a watchlist:** add and remove a simulated symbol using the dashboard.
   Explain why PostgreSQL CDC, not a browser refetch, updates the table.
2. **Inspect portfolio calculations:** change a demo position's quantity,
   observe its value and the singleton portfolio summary, then restore it.
3. **Reuse projected results:** complete the README's chained alert exercise.
   Change the downstream threshold while retaining the original upstream ticker
   and verify both initial and live results, including rows leaving the result.
4. **Inspect aggregation:** compare a sector's count/volume/min/max before and
   after one controlled simulated price change.
5. **Observe connection recovery:** reload the actual dashboard after a change
   and verify current snapshots, not accumulated historical totals. Treat a
   failed upstream service as a failure, not a fixture-driven passing result.

All holdings and orders are local simulations. Do not add real financial
transactions, brokerage accounts or unrelated external integrations.

## Query and transport contracts

Use `inputs` with component names or `{ component, port? }` objects, explicit
`queryLanguage: 'Cypher'`, and `result.label` when a downstream query needs a
specific result-node label. Preserve the same graph-change schema. Do not
reintroduce `sources`, `sourceId`, runtime-selection flags or a second execution
graph. Native sinks may consume sources, queries and transformers; the existing
ordinary SSE adapter has its own documented browser envelope.

Keep real PostgreSQL query-owner membership and the complete native bundle
consistent. Export from the actual `app/src/services/queries.ts`, preserving
joins, input order and result options. A changed native member set requires a
new isolated run, not silent late-consumer setup on an existing slot.

## Checks

From this tutorial directory:

```bash
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/demo.py build
python3 scripts/demo.py run --no-prices
```

In another terminal, using the printed run directory:

```bash
python3 scripts/demo.py verify .runtime/run-YOUR-RUN
python3 scripts/exercise.py .runtime/run-YOUR-RUN
```

From the actual Server example's `app/` directory, run its `npm run typecheck`
and the relevant existing Vitest integration tests. Rebuild the local
`dev-tools/react` package first after package changes. Keep mocked transport
checks distinct from real Server/Core/plugin execution and browser observations.

Use Podman and only newly owned loopback ports, containers and disposable data.
Stop the foreground launcher with Ctrl+C; do not invoke broad cleanup scripts.
