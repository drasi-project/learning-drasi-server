#!/usr/bin/env python3
"""Render Docsy/Hugo tutorial sources into plain Markdown READMEs.

Each tutorial is authored once in an ``index.md`` that may use Docsy/Hugo
shortcodes (``{{< tabpane >}}``, ``{{% alert %}}``, ...). The doc site consumes
``index.md`` directly so the tab widgets and styled alerts render. GitHub and
plain Markdown viewers cannot process shortcodes, so this script generates a
sibling ``README.md`` with the shortcodes converted to equivalent plain
Markdown.

Source of truth:   tutorials/<name>/index.md   (shortcodes, used by doc site)
Generated output:  tutorials/<name>/README.md  (plain Markdown, shown on GitHub)

Usage:
    python3 scripts/render-tutorials.py          # write README.md files
    python3 scripts/render-tutorials.py --check   # fail if any are stale
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TUTORIALS_DIR = REPO_ROOT / "tutorials"

GENERATED_BANNER = (
    "<!-- DO NOT EDIT. Generated from index.md by scripts/render-tutorials.py. "
    "Edit index.md and run `python3 scripts/render-tutorials.py`. -->\n\n"
)

_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')

_TABPANE_RE = re.compile(
    r"\{\{<\s*tabpane[^}]*>\}\}(?P<body>.*?)\{\{<\s*/\s*tabpane\s*>\}\}",
    re.DOTALL,
)
_CODE_TAB_RE = re.compile(
    r"\{\{<\s*tab\s+(?P<attrs>[^}]*?)>\}\}(?P<body>.*?)\{\{<\s*/\s*tab\s*>\}\}",
    re.DOTALL,
)
_MD_TAB_RE = re.compile(
    r"\{\{%\s*tab\s+(?P<attrs>[^}]*?)%\}\}(?P<body>.*?)\{\{%\s*/\s*tab\s*%\}\}",
    re.DOTALL,
)
_ALERT_RE = re.compile(
    r"\{\{%\s*alert\s+(?P<attrs>[^}]*?)%\}\}(?P<body>.*?)\{\{%\s*/\s*alert\s*%\}\}",
    re.DOTALL,
)


def _parse_attrs(raw: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _ATTR_RE.finditer(raw)}


def _render_tabpane(match: re.Match[str]) -> str:
    body = match.group("body")

    rendered: list[tuple[int, str]] = []

    for m in _CODE_TAB_RE.finditer(body):
        attrs = _parse_attrs(m.group("attrs"))
        header = attrs.get("header", "").strip()
        lang = attrs.get("lang", "").strip()
        code = m.group("body").strip("\n")
        block = f"**{header}**\n\n```{lang}\n{code}\n```"
        rendered.append((m.start(), block))

    for m in _MD_TAB_RE.finditer(body):
        attrs = _parse_attrs(m.group("attrs"))
        header = attrs.get("header", "").strip()
        content = m.group("body").strip("\n")
        block = f"**{header}**\n\n{content}"
        rendered.append((m.start(), block))

    rendered.sort(key=lambda item: item[0])
    return "\n\n".join(block for _, block in rendered)


def _render_alert(match: re.Match[str]) -> str:
    attrs = _parse_attrs(match.group("attrs"))
    title = attrs.get("title", "").strip()
    body = match.group("body").strip("\n")

    lines: list[str] = []
    if title:
        lines.append(f"> **{title}**")
        lines.append(">")
    for line in body.splitlines():
        lines.append(">" if not line.strip() else f"> {line}")
    return "\n".join(lines)


def render(source: str) -> str:
    out = _TABPANE_RE.sub(_render_tabpane, source)
    out = _ALERT_RE.sub(_render_alert, out)
    # Collapse 3+ blank lines that conversions can introduce.
    out = re.sub(r"\n{4,}", "\n\n\n", out)
    return GENERATED_BANNER + out.lstrip("\n")


def iter_sources() -> list[Path]:
    if not TUTORIALS_DIR.is_dir():
        return []
    return sorted(TUTORIALS_DIR.glob("*/index.md"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated READMEs are up to date; do not write.",
    )
    args = parser.parse_args()

    sources = iter_sources()
    if not sources:
        print("No tutorials/*/index.md sources found.", file=sys.stderr)
        return 0

    stale: list[Path] = []
    for source in sources:
        target = source.with_name("README.md")
        expected = render(source.read_text(encoding="utf-8"))
        current = target.read_text(encoding="utf-8") if target.exists() else None

        if args.check:
            if current != expected:
                stale.append(target)
            continue

        if current != expected:
            target.write_text(expected, encoding="utf-8")
            print(f"rendered {target.relative_to(REPO_ROOT)}")
        else:
            print(f"unchanged {target.relative_to(REPO_ROOT)}")

    if args.check and stale:
        print(
            "The following generated READMEs are out of date:\n"
            + "\n".join(f"  - {p.relative_to(REPO_ROOT)}" for p in stale)
            + "\n\nRun `python3 scripts/render-tutorials.py` and commit the result.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
