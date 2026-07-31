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

## Project Links

- [Drasi Server](https://github.com/drasi-project/drasi-server)
- [Drasi Documentation](https://drasi.io/)
- [Org contributing guide](https://github.com/drasi-project/.github/blob/main/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/drasi-project/.github/blob/main/CODE_OF_CONDUCT.md)

## License

[Apache License 2.0](LICENSE)
