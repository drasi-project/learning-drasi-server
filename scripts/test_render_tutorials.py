#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
"""Checks for composing generated tutorial variant pages."""

import importlib.util
from pathlib import Path
import unittest


_SPEC = importlib.util.spec_from_file_location(
    "render_tutorials", Path(__file__).resolve().with_name("render-tutorials.py"))
rt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rt)

MAIN = "---\ntitle: Main\n---\nIntro [d](dev-container/).\n\n## A {#a}\ntext a\n\n## B {#b}\ntext b\n"
FRONT = "---\ntitle: V\n---\n"


def compose(additions, main=MAIN):
    return rt.compose_variant(main, additions)


class ComposeVariantTests(unittest.TestCase):
    def test_after_inserts_at_end_of_section(self):
        out = compose(FRONT + "<!-- telemetry: after #a -->\nADD\n")
        self.assertLess(out.index("text a"), out.index("ADD"))
        self.assertLess(out.index("ADD"), out.index("## B {#b}"))

    def test_before_inserts_ahead_of_heading(self):
        out = compose(FRONT + "<!-- telemetry: before #a -->\nADD\n")
        self.assertLess(out.index("Intro"), out.index("ADD"))
        self.assertLess(out.index("ADD"), out.index("## A {#a}"))

    def test_top_text_goes_first(self):
        out = compose(FRONT + "TOP\n\n<!-- telemetry: after #b -->\nEND\n")
        self.assertLess(out.index(rt.VARIANT_BANNER), out.index("TOP"))
        self.assertLess(out.index("TOP"), out.index("Intro"))
        self.assertLess(out.index("text b"), out.index("END"))

    def test_front_matter_comes_from_additions(self):
        out = compose(FRONT)
        self.assertTrue(out.startswith(FRONT + rt.VARIANT_BANNER))
        self.assertNotIn("title: Main", out)

    def test_unknown_anchor_fails(self):
        with self.assertRaisesRegex(ValueError, "#missing"):
            compose(FRONT + "<!-- telemetry: after #missing -->\nX\n")

    def test_blocks_at_same_anchor_keep_file_order(self):
        out = compose(FRONT + "<!-- telemetry: after #a -->\nX\n<!-- telemetry: after #a -->\nY\n")
        self.assertLess(out.index("text a"), out.index("X"))
        self.assertLess(out.index("X"), out.index("Y"))
        self.assertLess(out.index("Y"), out.index("## B {#b}"))

    def test_inserted_headings_do_not_move_later_anchors(self):
        out = compose(FRONT + "<!-- telemetry: after #a -->\n## New\nN\n"
                      "<!-- telemetry: after #a -->\nY\n"
                      "<!-- telemetry: after #b -->\nM\n")
        self.assertLess(out.index("N\n"), out.index("Y"))
        self.assertLess(out.index("Y"), out.index("## B {#b}"))
        self.assertLess(out.index("## New"), out.index("## B {#b}"))
        self.assertLess(out.index("text b"), out.index("M"))

    def test_omit_marker_tolerates_trailing_whitespace(self):
        main = MAIN.replace("Intro", "<!-- telemetry-variant: omit --> \nHIDE\n"
                                     "<!-- /telemetry-variant: omit -->\t\nIntro")
        out = compose(FRONT, main)
        self.assertNotIn("HIDE", out)
        self.assertIn("Intro", out)

    def test_unmatched_omit_marker_fails(self):
        for marker in ("<!-- telemetry-variant: omit -->\n", "<!-- /telemetry-variant: omit -->\n"):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, "omit"):
                compose(FRONT, MAIN.replace("Intro", marker + "Intro"))

    def test_omit_markers_drop_main_content(self):
        main = MAIN.replace("Intro", "<!-- telemetry-variant: omit -->\nHIDE\n"
                                     "<!-- /telemetry-variant: omit -->\nIntro")
        out = compose(FRONT, main)
        self.assertNotIn("HIDE", out)
        self.assertNotIn("telemetry-variant", out)
        self.assertIn("Intro", out)

    def test_only_main_text_links_are_rewritten(self):
        main = ("---\ntitle: Main\n---\n[d](dev-container/) [s](#a) [u](https://x) "
                "[p](../p/) [r](/r)\n\n```text\n[c](code/)\n```\n\n## A {#a}\ntext a\n")
        out = compose(FRONT + "<!-- telemetry: after #a -->\n[t](../#a) [l](local/)\n", main)
        for expected in ("[d](../dev-container/)", "[s](#a)", "[u](https://x)",
                         "[p](../p/)", "[r](/r)", "[c](code/)", "[t](../#a)", "[l](local/)"):
            self.assertIn(expected, out)

    def test_committed_variant_pages_are_current(self):
        variants = rt.iter_variants()
        self.assertTrue(variants)
        for additions in variants:
            main = (additions.parent.parent / "_index.md").read_text(encoding="utf-8")
            self.assertEqual(
                additions.with_name("_index.md").read_text(encoding="utf-8"),
                rt.compose_variant(main, additions.read_text(encoding="utf-8")),
                f"{additions.with_name('_index.md')} is stale; run scripts/render-tutorials.py")


if __name__ == "__main__":
    unittest.main()
