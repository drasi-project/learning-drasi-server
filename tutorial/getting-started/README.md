# Getting Started with Drasi Server

In this tutorial you will build a complete data pipeline in a few minutes. You will create:

1. A **mock source** that generates simulated sensor readings.
2. A **continuous query** that filters for high temperatures.
3. A **log reaction** that prints matching results as they change.

No database or external service is required — everything runs from a single Docker container.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (Docker Desktop or Docker Engine with the
  Compose plugin).

If you opened this tutorial in a [GitHub Codespace](https://codespaces.new/drasi-project/learning-drasi-server)
or Dev Container, Docker is already installed for you.

## Step 1 — Start Drasi Server

From this folder (`tutorial/getting-started`), start the server:

```bash
docker compose up
```

This launches Drasi Server using the configuration in [`config/server.yaml`](config/server.yaml).
On startup the server loads the source, query, and reaction defined in that file.

Wait until you see a log line indicating the server is listening on port `8080`.

## Step 2 — Watch the pipeline work

The log reaction (`temp-logger`) prints a line every time a sensor reading crosses the
temperature threshold defined by the query. Watch the `docker compose` output — you should see
entries similar to:

```
Added: {"s":{"sensor_id":"sensor_2","temperature":27.4,"humidity":0.51, ...}}
Updated: {"s":{"sensor_id":"sensor_2","temperature":29.1,"humidity":0.48, ...}}
```

Each `Added` line is a sensor reading that newly matched the query (`temperature > 25`), and each
`Updated` line is a previously matched reading whose value changed.

## Step 3 — Explore the Web UI (optional)

Drasi Server includes a visual Web UI. Open it in your browser:

```
http://localhost:8080/ui
```

You will see the pipeline as a graph: the `sensor-feed` source feeding the `high-temp` query,
which feeds the `temp-logger` reaction. Click any node to inspect its status and configuration.

## Step 4 — Inspect via the REST API (optional)

You can also query the server directly:

```bash
# Health check
curl http://localhost:8080/health

# List sources
curl http://localhost:8080/api/v1/sources

# Current results of the high-temp query
curl http://localhost:8080/api/v1/queries/high-temp/results

# Stream live component events
curl -N http://localhost:8080/api/v1/events
```

## Step 5 — Experiment

Try editing [`config/server.yaml`](config/server.yaml):

- Lower the threshold in the query (`temperature > 25`) to match more readings.
- Increase `sensorCount` on the source to simulate more sensors.
- Decrease `intervalMs` to generate readings more frequently.

Restart the server to apply changes:

```bash
docker compose restart
```

## Clean up

Stop and remove the container:

```bash
docker compose down
```

## What's next

- Read the [Drasi Server documentation](https://drasi.io/) to learn about real data sources
  (PostgreSQL CDC, HTTP webhooks, gRPC) and other reactions (HTTP, SSE, gRPC).
- Browse the other [tutorials](../README.md) in this repository.
