# Learning Drasi Server

Hands-on tutorials for [Drasi Server](https://github.com/drasi-project/drasi-server).

## Tutorials

| Tutorial | What you learn | How to trigger it |
| --- | --- | --- |
| [getting-started](tutorials/getting-started) | Official Drasi Server getting-started flow (PostgreSQL CDC, queries, log + SSE reactions) | Open the **Drasi Server - Getting Started Tutorial** dev container (or a Codespace) and follow [tutorials/getting-started](tutorials/getting-started) |
| [building-comfort](tutorials/building-comfort) | Smart-building comfort monitoring (PostgreSQL CDC, six comfort/alert queries with synthetic joins, the dashboard reaction) | Open the **Drasi Server - Building Comfort Tutorial** dev container and follow [tutorials/building-comfort](tutorials/building-comfort) |

See [tutorials](tutorials) for the full list of tutorials.

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

## Documentation Site

The tutorials also render as a [Docsy](https://www.docsy.dev/)/[Hugo](https://gohugo.io/)
documentation site. Each tutorial is authored once in `tutorials/<name>/_index.md`
(the single source of truth) and mounted into the Hugo content tree, so the doc
site and the GitHub `README.md` files stay in sync.

### Prerequisites

- [Hugo Extended](https://gohugo.io/installation/) `0.152.2` or newer
- [Go](https://go.dev/dl/) `1.24` or newer (for Hugo Modules)
- [Node.js](https://nodejs.org/) `18` or newer with npm (for the PostCSS pipeline)

### Build

```bash
# 1. Install the PostCSS dependencies used by Docsy's SCSS pipeline
npm install

# 2. Build the static site into ./public
hugo --gc --minify
```

### Preview locally

```bash
hugo server
```

Then open <http://localhost:1313>.

> Hugo writes the `public/webfonts/*` files as read-only, which can make a later
> rebuild fail with a "permission denied" error. If that happens, remove the
> generated output before rebuilding: `rm -rf public resources`.

### Regenerate the GitHub READMEs

After editing any `tutorials/<name>/_index.md`, regenerate the plain-Markdown
`README.md` files so they match:

```bash
python3 scripts/render-tutorials.py          # write README.md files
python3 scripts/render-tutorials.py --check   # fail if any are stale (CI check)
```

## Isolated Runtime Evaluation

`scripts/tutorial-runtime.py` runs the published tutorial infrastructure without
reusing the normal tutorial container names, volumes, ports, or Kubernetes
context. It is an optional development path; the normal tutorial commands and
downloaded releases remain unchanged. It requires Python 3, working Docker
Compose, and a **ComputationGraph-only** Drasi Server build with matching local plugin
artifacts. High Risk Containers additionally needs `kubectl` and `k3d`.

From this repository's root, choose an unused run ID and an evidence directory:

```bash
python3 scripts/tutorial-runtime.py prepare building-comfort \
  --run-id my-native-evaluation --output /path/to/evidence
```

The `prepare` action uses that tutorial's real Compose configuration and seed SQL.
It generates isolated `compose.json`, `server-config.yaml`, `environment.sh`, an
ownership manifest, and command logs under `/path/to/evidence/building-comfort`.
It refuses to overwrite an existing evaluation or reuse existing data volumes.
The default loopback ports for PostgreSQL, API, and dashboard are respectively
`49110`, `49112`, and `49113` for Building Comfort. The other tutorial blocks start
at `49100` (Getting Started), `49120` (High Risk Containers), and `49130` (Curbside
Pickup). Override the range with `--base-port`.

Start the exact server build under evaluation, supplying its SHA256:

```bash
python3 scripts/tutorial-runtime.py serve building-comfort \
  --run-id my-native-evaluation --output /path/to/evidence \
  --server /path/to/drasi-server --server-sha256 <sha256> \
  --plugins /path/to/local-plugins
```

ComputationGraph is the server's only runtime; no engine flag or feature opt-in
is needed. Removed `--execution-mode` and `executionMode` configuration selectors
are not supported. The script requires the live instance's
`/api/v1/instances/<id>/runtime` endpoint to report exactly that `instanceId`,
`runtime: "computationGraph"`, and `running: true` inside a successful response.
A different instance or a healthy API alone does not satisfy readiness
verification. The server hash, plugin hashes, process ID, arguments, runtime
response, and server log are recorded. Provenance also includes the fixed
informational `runtime: "computationGraph"` label; it is not a selectable mode or
a replacement for the live identity/readiness check. Signature verification is
skipped only for these explicitly supplied local development plugins, not for
normal published tutorial downloads.

Use the generated environment with the tutorial's data-changing commands and
compare all published observations, including result identities, aggregates,
timers, reaction events, dashboard changes, and stop/restart behavior. Getting
Started starts from `configs/getting-started-step-3.yaml`; its five queries must
still be added and exercised in the published sequence, not replaced by the
older `server-config.yaml` smoke demo. Helpers with fixed container names must be
adapted to the exact names recorded in the ownership manifest.

For High Risk Containers, after `prepare`, use the same run ID with:

```bash
python3 scripts/tutorial-runtime.py cluster high-risk-containers \
  --run-id my-native-evaluation --output /path/to/evidence \
  --k3d /path/to/k3d --kube-port 49650
```

This deploys the actual tutorial Pods into a dedicated namespace, writes a private
kubeconfig, and updates only the generated server configuration. It does not
update or switch the global Kubernetes context.

After stopping the server, simulator, SSE CLI, and any operations console you
started, remove only the recorded infrastructure:

```bash
python3 scripts/tutorial-runtime.py cleanup building-comfort \
  --run-id my-native-evaluation --output /path/to/evidence
```

For High Risk Containers, also pass `--k3d` if it is not on `PATH`; cleanup removes
the owned cluster as well. The evidence is retained. **These commands establish
infrastructure and runtime provenance, not that a tutorial passed.** Report
unexecuted or failed workflow steps separately.

## Project Links

- [Drasi Server](https://github.com/drasi-project/drasi-server)
- [Drasi Documentation](https://drasi.io/)
- [Org contributing guide](https://github.com/drasi-project/.github/blob/main/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/drasi-project/.github/blob/main/CODE_OF_CONDUCT.md)

## License

[Apache License 2.0](LICENSE)
