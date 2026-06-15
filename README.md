# Learning Drasi Server

Tutorials and learning resources for [Drasi Server](https://github.com/drasi-project/drasi-server) — a
standalone server for real-time data change processing.

Drasi Server monitors your data sources, runs continuous queries, and triggers automated
reactions when results change — all through a simple YAML configuration or visual Web UI.
This repository contains hands-on tutorials that show you how to build change-driven
solutions with Drasi Server.

> Looking for Drasi on Kubernetes (the Drasi Platform)? See the
> [`drasi-project/learning`](https://github.com/drasi-project/learning) repository instead.

## Getting Started

The fastest way to try a tutorial is in the browser with GitHub Codespaces — no local setup
required.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/drasi-project/learning-drasi-server)

Or run a tutorial locally. All you need is [Docker](https://docs.docker.com/get-docker/):

```bash
git clone https://github.com/drasi-project/learning-drasi-server.git
cd learning-drasi-server/tutorial/getting-started
docker compose up
```

## Tutorials

| Tutorial | Description |
| --- | --- |
| [Getting Started](tutorial/getting-started) | Create your first Drasi Server pipeline: a mock source, a continuous query, and a log reaction. |

More tutorials will be added over time. See [tutorial/](tutorial) for the full list and the
[tutorial template](tutorial/TEMPLATE) for authoring guidance.

## Repository Layout

```
tutorial/                 # One folder per tutorial
  getting-started/        # First tutorial
  TEMPLATE/               # Starting point for new tutorials
.devcontainer/            # Codespaces / Dev Container configuration
.github/                  # Workflows, issue templates, labels, CODEOWNERS
```

## Contributing

Contributions are welcome! See the org-wide
[CONTRIBUTING.md](https://github.com/drasi-project/.github/blob/main/CONTRIBUTING.md) and
[Code of Conduct](https://github.com/drasi-project/.github/blob/main/CODE_OF_CONDUCT.md)
for how to contribute.

## Related Projects

- [Drasi Server](https://github.com/drasi-project/drasi-server) — the standalone change-processing server
- [Drasi Platform](https://github.com/drasi-project) — the full Drasi project
- [Drasi Documentation](https://drasi.io/) — complete documentation

## License

Licensed under the [Apache License 2.0](LICENSE).
