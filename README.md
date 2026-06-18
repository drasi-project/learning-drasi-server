# Learning Drasi Server

Hands-on tutorials for [Drasi Server](https://github.com/drasi-project/drasi-server).

If you are looking for Drasi Platform (Kubernetes) tutorials, use
[drasi-project/learning](https://github.com/drasi-project/learning).

## Tutorials

| Tutorial | What you learn | How to trigger it |
| --- | --- | --- |
| [getting-started](tutorials/getting-started) | Official Drasi Server getting-started flow (PostgreSQL CDC, queries, log + SSE reactions) | Follow [drasi.io/drasi-server/getting-started](https://drasi.io/drasi-server/getting-started/) and run commands from `drasi-server/examples/getting-started` |
| [building-comfort](tutorials/building-comfort) | Smart-building comfort monitoring (PostgreSQL CDC, six comfort/alert queries with synthetic joins, the dashboard reaction) | Open the **Drasi Server - Building Comfort Tutorial** dev container and follow [tutorials/building-comfort](tutorials/building-comfort) |

See [tutorials](tutorials) for the full list of tutorials.

## Run Locally

For the current getting-started tutorial, use the canonical upstream files in
`drasi-server/examples/getting-started`:

```bash
git clone https://github.com/drasi-project/drasi-server.git
cd drasi-server/examples/getting-started
```

Then follow:

- [drasi.io/drasi-server/getting-started](https://drasi.io/drasi-server/getting-started/)
- [examples/getting-started README](https://github.com/drasi-project/drasi-server/tree/main/examples/getting-started)

## Run in a Dev Container

From the repository root:

1. Open in VS Code.
2. Run Reopen in Container.
3. When prompted, choose a configuration:
	- **Drasi Server - Getting Started Tutorial** — opens [tutorials/getting-started](tutorials/getting-started).
	- **Drasi Server - Building Comfort Tutorial** — installs everything for
	  [tutorials/building-comfort](tutorials/building-comfort) (PostgreSQL client + Drasi Server binary).
4. Follow the README in the matching tutorial folder.

## Run in Codespaces

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/drasi-project/learning-drasi-server)

After the Codespace starts, follow the getting-started guide in
[tutorials/getting-started](tutorials/getting-started).

## Project Links

- [Drasi Server](https://github.com/drasi-project/drasi-server)
- [Drasi Documentation](https://drasi.io/)
- [Org contributing guide](https://github.com/drasi-project/.github/blob/main/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/drasi-project/.github/blob/main/CODE_OF_CONDUCT.md)

## License

[Apache License 2.0](LICENSE)
