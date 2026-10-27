# Learning Drasi Server

Hands-on tutorials for [Drasi Server](https://github.com/drasi-project/drasi-server).

## Tutorials

| Tutorial | Scenario |
| --- | --- |
| [Getting started](tutorials/getting-started) | PostgreSQL messages, continuous queries, joins, inactivity and Log/SSE reactions |
| [Building Comfort](tutorials/building-comfort) | Shared room, floor and building calculations with live comfort alerts and a dashboard |
| [Curbside Pickup](tutorials/curbside-pickup) | Correlate orders and arriving vehicles, show pickup readiness and delays |
| [High-risk Containers](tutorials/high-risk-containers) | Join running Kubernetes container images to a risk catalogue and react to risk changes |
| [OTel Observability](tutorials/otel-observability) | Correlate Kubernetes rollouts, OpenTelemetry health and PostgreSQL SLO policy |
| [Trading](tutorials/trading) | Run the local Server trading application with prices, portfolio views and chained calculations |
| [SSE CLI](tutorials/sse-cli) | Inspect live Server reaction streams or an explicitly selected existing SSE endpoint |

Follow the README in each tutorial for its exact build, run and exercise
sequence. The scenarios use the current local ComputationGraph implementation,
not unrelated released Drasi binaries or automatically downloaded plugins.

## Local source layout

Keep the complete repositories beside one another:

```text
workspace/
  drasi-core/
  drasi-server/
  learning-drasi-server/
```

Use matching `agentofreality-parallel-computation-graph` branches for the current
development tutorials. Server must use the sibling `drasi-core/lib` dependency.
The helpers never clone, switch branches, or substitute a release build.
Tutorial folders are not standalone ZIP distributions: keep repository-level
`scripts/` and the matching sibling checkouts available.

Most tutorial helpers share [`scripts/local_build.py`](scripts/local_build.py).
It builds Server and the tutorial's exact Core plugin packages, copies them
into a private content-addressed bundle, and records their hashes and source
revisions. Startup verifies that bundle rather than choosing an arbitrary
library from the shared Cargo target. Rebuild after changing Core or Server.
The SSE CLI has its own [source-build and verification helper](tutorials/sse-cli)
so callers use this repository's CLI, not a similarly named Server example.

Use the documented Rust toolchain (currently 1.95.0), Python 3.11 or newer, and
the native dependencies listed by the tutorial. Before a locked build, generate
Core's untracked workspace lockfile if it is absent:

```bash
# From learning-drasi-server/
RUSTUP_TOOLCHAIN=1.95.0 cargo generate-lockfile --manifest-path ../drasi-core/Cargo.toml
```

Tutorials use Podman for local infrastructure. Kubernetes scenarios also need
the documented `kubectl` and `k3d` tools; a dev container is not proof that its
container engine or Kubernetes prerequisites work on every host. If sharing
`drasi-server/target`, run Rust/plugin builds one at a time.

## Run in a Dev Container

From the repository root:

1. Open in VS Code.
2. Run Reopen in Container.
3. When prompted, choose a configuration:
	- **Drasi Server - Getting Started Tutorial**
	- **Drasi Server - Building Comfort Tutorial**
	- **Drasi Server - Curbside Pickup Tutorial**
	- **Drasi Server - High Risk Containers Tutorial**
	- **Drasi Server - OTel Observability Tutorial**
4. Follow the README in the matching tutorial folder.

The source-based configurations require the sibling repositories above. A
Codespace containing only `learning-drasi-server` is not the complete setup;
prepare the matching source layout and infrastructure rather than falling
back to release downloads.

## Documentation Site

The tutorials also render as a [Docsy](https://www.docsy.dev/)/[Hugo](https://gohugo.io/)
documentation site. Site-published tutorials are authored in
`tutorials/<name>/_index.md` and mounted into the Hugo content tree; their sibling
`README.md` files are generated. Trading and SSE CLI have standalone README
entry points rather than generated `_index.md` pages.

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

Use each tutorial's current helper and verification commands. They own their
scenario-specific database, service and Kubernetes setup rather than relying on
one script to guess all tutorial layouts. The older `scripts/tutorial-runtime.py`
targets prior configuration layouts; it is not the shared runner for these
source-based walkthroughs.

For an independent check, select an unused run name, private state directory and
free loopback ports using the tutorial's documented options. Preserve existing
user data. Do not reuse a cluster by name alone or switch the global Kubernetes
context. Stop only the processes you started and use ownership-checked cleanup;
deleting volumes must be an explicit choice.

ComputationGraph is the only Server runtime. Readiness must identify the correct
instance and required components, not merely a healthy HTTP listener. Retain
the exact build record and runtime evidence, then exercise the actual scenario:
database changes, query results, timer behavior, browser updates and restart
where documented. Infrastructure setup or a successful build alone does not
establish that a tutorial passed.

Signature verification is bypassed only for the locally built, hash-checked
development bundle. This is not a recommendation to disable verification for
downloaded plugins. Report unavailable services, untested platforms and
unexercised failure modes explicitly.

## Project Links

- [Drasi Server](https://github.com/drasi-project/drasi-server)
- [Drasi Documentation](https://drasi.io/)
- [Org contributing guide](https://github.com/drasi-project/.github/blob/main/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/drasi-project/.github/blob/main/CODE_OF_CONDUCT.md)

## License

[Apache License 2.0](LICENSE)
