# Learning Drasi Server

Hands-on tutorials for [Drasi Server](https://github.com/drasi-project/drasi-server).

## Tutorials

| Tutorial | What you learn | How to trigger it |
| --- | --- | --- |
| [getting-started](tutorials/getting-started) | Official Drasi Server getting-started flow (PostgreSQL CDC, queries, log + SSE reactions) | Open the **Drasi Server - Getting Started Tutorial** dev container (or a Codespace) and follow [tutorials/getting-started](tutorials/getting-started) |
| [building-comfort](tutorials/building-comfort) | Smart-building comfort monitoring (PostgreSQL CDC, six comfort/alert queries with synthetic joins, the dashboard reaction) | Open the **Drasi Server - Building Comfort Tutorial** dev container and follow [tutorials/building-comfort](tutorials/building-comfort) |
| [otel-observability](tutorials/otel-observability) | Correlate Kubernetes rollouts, OTel health, and a PostgreSQL SLO policy (native OTel source, Collector, dashboard) | Open the **Drasi Server - OTel Observability Tutorial** dev container and follow [tutorials/otel-observability](tutorials/otel-observability) |

See [tutorials](tutorials) for the full list of tutorials.

## Run in a Dev Container

From the repository root:

1. Open in VS Code.
2. Run Reopen in Container.
3. When prompted, choose a configuration:
	- **Drasi Server - Getting Started Tutorial** — opens [tutorials/getting-started](tutorials/getting-started).
	- **Drasi Server - Building Comfort Tutorial** — installs everything for
	  [tutorials/building-comfort](tutorials/building-comfort) (PostgreSQL client + Drasi Server binary).
	- **Drasi Server - OTel Observability Tutorial** — installs everything for
	  [tutorials/otel-observability](tutorials/otel-observability) (k3d, kubectl, PostgreSQL client, mock store images).
4. Follow the README in the matching tutorial folder.

## Run in Codespaces

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/drasi-project/learning-drasi-server)

After the Codespace starts, follow the getting-started guide in
[tutorials/getting-started](tutorials/getting-started).

## Automated Tutorial Evaluation

The scheduled/PR evaluation workflow uses the configured GPT model for attempts
1 and 2. If both fail, attempt 3 uses the Copilot CLI default model by omitting
`--model`. Each attempt retains its 20-minute timeout and report-based checks.

The preferred model defaults to `gpt-6.1-sol`. Change it without editing a
workflow by setting the repository Actions variable `TUTORIAL_EVALUATION_MODEL`
under **Settings > Secrets and variables > Actions > Variables**, or with:

```bash
gh variable set TUTORIAL_EVALUATION_MODEL --repo drasi-project/learning-drasi-server --body gpt-6.1-sol
```

The separate **Agentic Tutorial Evaluation** manual workflow runs once. Its
optional `model` input overrides the repository variable; leaving it blank uses
the variable or the built-in default.

For scheduled runs, passing on attempt 1 or 2 creates no issue. Passing on attempt
3 keeps the evaluation green and creates a warning issue with the `automated`
label, not `tutorial-failure`. An unsuccessful evaluation still creates a failure
issue. PR and manually triggered runs do not create issues.

A warning records recovery with the default model, not proof of model
deprecation. The default may change provider, cost, or behavior and is not
necessarily the latest GPT model. Model access depends on the workflow account's
plan and policies; see [supported models](https://docs.github.com/en/copilot/reference/ai-models/supported-models)
and [CLI model selection](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference#choosing-a-model).

Run the workflow regression checks locally with
`node --test scripts/test-tutorial-evaluation.cjs` (Node.js 18 or newer).

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

## Project Links

- [Drasi Server](https://github.com/drasi-project/drasi-server)
- [Drasi Documentation](https://drasi.io/)
- [Org contributing guide](https://github.com/drasi-project/.github/blob/main/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/drasi-project/.github/blob/main/CODE_OF_CONDUCT.md)

## License

[Apache License 2.0](LICENSE)
