# <Tutorial Title>

> One- or two-sentence summary of what the reader will build and learn.

## What you'll build

Briefly describe the pipeline (sources, queries, reactions) and the end result.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- Any other tools or accounts the tutorial requires

## Step 1 — <First step>

Explain the first action. Keep steps small and verifiable.

```bash
# Commands the reader runs
```

## Step 2 — <Next step>

Continue with numbered, sequential steps. Show expected output so readers can confirm progress.

## Clean up

```bash
docker compose down
```

## What's next

Link to related tutorials or documentation.

---

### Authoring checklist

- [ ] `docker compose up` (or the documented command) works from this folder with no manual edits.
- [ ] `config/server.yaml` validates against Drasi Server (`drasi-server validate`).
- [ ] Every step shows the command **and** the expected result.
- [ ] Any custom application images live in sub-folders with their own `Dockerfile`.
- [ ] This folder is listed in [`tutorial/README.md`](../README.md) and the root `README.md`.
