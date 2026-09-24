# Copyright 2026 The Drasi Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Run: python3 -B -m unittest discover -s tutorials/getting-started/tests -v."""

from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile
import unittest


TUTORIAL = Path(__file__).resolve().parents[1]
ROOT = TUTORIAL.parents[1]
PINS = {
    "source/postgres": "0.2.10",
    "bootstrap/postgres": "0.2.13",
    "reaction/log": "0.2.7",
    "reaction/sse": "0.3.6",
    "source/http": "0.2.11",
    "bootstrap/scriptfile": "0.2.13",
}


class PluginVersionTests(unittest.TestCase):
    def test_all_config_refs_are_pinned(self):
        configs = sorted((TUTORIAL / "configs").glob("*.yaml"))
        self.assertEqual(len(configs), 4)
        for path in [*configs, TUTORIAL / "server-config.yaml"]:
            with self.subTest(path=path.name):
                refs = re.findall(r"^\s*- ref: (\S+)", path.read_text(), re.M)
                expected = {f"{kind}:{PINS[kind]}" for kind in
                            ("source/postgres", "bootstrap/postgres", "reaction/log")}
                if path.name == "server-config.yaml":
                    expected.add("reaction/sse:0.3.6")
                self.assertEqual(set(refs), expected)
                self.assertEqual(len(refs), len(expected))

    def test_both_installers_use_the_same_release(self):
        release = "https://github.com/drasi-project/drasi-server/releases/download/0.2.3"
        for name in ("download.sh", "download.ps1"):
            with self.subTest(name=name):
                source = (TUTORIAL / "scripts" / name).read_text()
                self.assertIn(f'"{release}"', source)
                self.assertNotIn("releases/latest", source)

    def test_documented_rest_installs_match_pins(self):
        source = (TUTORIAL / "_index.md").read_text()
        refs = re.findall(r'"ref": "([^"]+)"', source)
        expected = [f"{kind}:{PINS[kind]}" for kind in
                    ("reaction/sse", "source/http", "bootstrap/scriptfile")]
        self.assertCountEqual(refs, expected * 2)
        for kind, version in PINS.items():
            self.assertIn(f"| `{kind}` | `{version}` |", source)
        render = runpy.run_path(str(ROOT / "scripts/render-tutorials.py"))["render"]
        self.assertEqual((TUTORIAL / "README.md").read_text(), render(source))

    def test_setup_paths_use_current_tutorial_assets(self):
        for setup in ("download-binary", "dev-container", "github-codespace"):
            with self.subTest(setup=setup):
                source = (TUTORIAL / setup / "_index.md").read_text()
                self.assertIn("drasi-project/learning-drasi-server", source)
                self.assertNotIn("drasi-server/releases/latest", source)
        post_create = (ROOT / ".devcontainer/getting-started/post-create.sh").read_text()
        self.assertIn("cp -R tutorials/getting-started examples/", post_create)

    def test_examples_copy_preserves_pinned_configs_on_repeat_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            shutil.copytree(TUTORIAL, workspace / "tutorials/getting-started")
            for _ in range(2):
                subprocess.run(
                    ["bash", "-c", "mkdir -p examples && cp -R tutorials/getting-started examples/"],
                    cwd=workspace, check=True,
                )
                for source in (TUTORIAL / "configs").glob("*.yaml"):
                    copied = workspace / "examples/getting-started/configs" / source.name
                    self.assertEqual(copied.read_bytes(), source.read_bytes())
                self.assertFalse((workspace / "examples/getting-started/getting-started").exists())


if __name__ == "__main__":
    unittest.main()
