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
import os
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
        post_create = (ROOT / ".devcontainer/getting-started/post-create.sh").read_text()
        copy_commands = re.search(r"^mkdir -p examples\ncp .+$", post_create, re.M).group()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            shutil.copytree(TUTORIAL, workspace / "tutorials/getting-started")
            for _ in range(2):
                subprocess.run(
                    ["bash", "-ec", copy_commands],
                    cwd=workspace, check=True,
                )
                for source in (TUTORIAL / "configs").glob("*.yaml"):
                    copied = workspace / "examples/getting-started/configs" / source.name
                    self.assertEqual(copied.read_bytes(), source.read_bytes())
                self.assertFalse((workspace / "examples/getting-started/getting-started").exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_asset_copy_refreshes_existing_examples(self):
        source = (TUTORIAL / "download-binary/_index.md").read_text()
        commands = re.search(
            r'lang="powershell" >}}\n(.*?){{< /tab >}}', source, re.S,
        ).group(1)
        copy_commands = "\n".join(
            line for line in commands.splitlines()
            if line.startswith(("New-Item ", "Copy-Item "))
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            shutil.copytree(
                TUTORIAL, workspace / "learning-drasi-server-main/tutorials/getting-started",
            )
            for _ in range(2):
                subprocess.run(
                    ["pwsh", "-NoProfile", "-NonInteractive", "-Command",
                     '$ErrorActionPreference = "Stop"\n' + copy_commands],
                    cwd=workspace, check=True, capture_output=True, text=True,
                )
                for source in (TUTORIAL / "configs").glob("*.yaml"):
                    copied = workspace / "examples/getting-started/configs" / source.name
                    self.assertEqual(copied.read_bytes(), source.read_bytes())
                    copied.write_text("stale unversioned config\n")
                self.assertFalse((workspace / "examples/getting-started/getting-started").exists())


@unittest.skipUnless(os.name == "posix", "Native executable fixtures use POSIX shell scripts")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.mocks = self.workspace / "mocks"
        self.mocks.mkdir()
        self.fixtures = self.workspace / "fixtures"
        self.fixtures.mkdir()
        self.requests = self.workspace / "requests.txt"
        self.requests.touch()
        self.env = {
            **os.environ,
            "PATH": f"{self.mocks}{os.pathsep}{os.environ['PATH']}",
            "MOCK_REQUESTS": str(self.requests),
            "MOCK_BINARIES": str(self.fixtures),
            "MOCK_OS": "Linux",
            "MOCK_ARCH": "x86_64",
            "MOCK_LIBC": "gnu",
            "MOCK_DOWNLOAD_FAILURE": "none",
            "MOCK_SERVER_STATUS": "0",
            "MOCK_SSE_STATUS": "0",
        }
        for name, status in (("drasi-server", "MOCK_SERVER_STATUS"),
                             ("drasi-sse-cli", "MOCK_SSE_STATUS")):
            for suffix in ("", ".exe"):
                self.write_executable(
                    self.fixtures / (name + suffix),
                    f'#!/bin/sh\n[ "$1" = "--version" ] || exit 99\nexit "${status}"\n',
                )
        self.write_executable(self.mocks / "uname", """#!/bin/sh
case "$1" in
  -s) echo "$MOCK_OS" ;;
  -m) echo "$MOCK_ARCH" ;;
  *) exit 99 ;;
esac
""")
        self.write_executable(
            self.mocks / "ldd", '#!/bin/sh\necho "$MOCK_LIBC"\n',
        )
        self.write_executable(self.mocks / "curl", """#!/bin/sh
[ "$1" = "-fsSL" ] && [ "$3" = "-o" ] || exit 99
echo "$2" >> "$MOCK_REQUESTS"
case "$2" in *"$MOCK_DOWNLOAD_FAILURE"*) echo "Download failed" >&2; exit 22 ;; esac
cp "$MOCK_BINARIES/$(basename "$4")" "$4"
""")

    @staticmethod
    def write_executable(path, content):
        path.write_text(content)
        path.chmod(0o755)

    def run_installer(self, powershell=False, **environment):
        self.requests.write_text("")
        env = {**self.env, **environment}
        if powershell:
            env["INSTALLER"] = str(TUTORIAL / "scripts/download.ps1")
            command = ["pwsh", "-NoProfile", "-NonInteractive", "-Command", """
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    Add-Content -Path $env:MOCK_REQUESTS -Value $Uri
    if ($Uri.Contains($env:MOCK_DOWNLOAD_FAILURE)) { throw "Download failed" }
    Copy-Item (Join-Path $env:MOCK_BINARIES (Split-Path $OutFile -Leaf)) $OutFile
}
function Unblock-File { param($Path) }
& $env:INSTALLER
exit $LASTEXITCODE
"""]
        else:
            command = ["bash", str(TUTORIAL / "scripts/download.sh")]
        return subprocess.run(
            command, cwd=self.workspace, env=env,
            capture_output=True, text=True, timeout=30,
        )

    def test_bash_platforms_download_exact_release_assets(self):
        platforms = [
            ("Darwin", "arm64", "gnu", "aarch64-apple-darwin"),
            ("Darwin", "x86_64", "gnu", "x86_64-apple-darwin"),
            ("Linux", "x86_64", "gnu", "x86_64-linux-gnu"),
            ("Linux", "aarch64", "gnu", "aarch64-linux-gnu"),
            ("Linux", "arm64", "gnu", "aarch64-linux-gnu"),
            ("Linux", "x86_64", "musl", "x86_64-linux-musl"),
            ("Linux", "aarch64", "musl", "aarch64-linux-musl"),
            ("Linux", "arm64", "musl", "aarch64-linux-musl"),
        ]
        for system, arch, libc, suffix in platforms:
            with self.subTest(system=system, arch=arch, libc=libc):
                result = self.run_installer(MOCK_OS=system, MOCK_ARCH=arch, MOCK_LIBC=libc)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.requests.read_text().splitlines(), [
                    f"https://github.com/drasi-project/drasi-server/releases/download/0.2.3/{name}-{suffix}"
                    for name in ("drasi-server", "drasi-sse-cli")
                ])
                for name in ("drasi-server", "drasi-sse-cli"):
                    self.assertTrue(os.access(self.workspace / "bin" / name, os.X_OK))

    def test_bash_rejects_unsupported_platforms_before_download(self):
        for system, arch in (("FreeBSD", "x86_64"), ("Linux", "riscv64"), ("Darwin", "ppc")):
            with self.subTest(system=system, arch=arch):
                result = self.run_installer(MOCK_OS=system, MOCK_ARCH=arch)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unsupported", result.stdout)
                self.assertEqual(self.requests.read_text(), "")

    def assert_failures_are_reported(self, powershell=False):
        for environment in (
            {"MOCK_DOWNLOAD_FAILURE": "drasi-server-"},
            {"MOCK_DOWNLOAD_FAILURE": "drasi-sse-cli-"},
            {"MOCK_SERVER_STATUS": "17"},
            {"MOCK_SSE_STATUS": "23"},
        ):
            with self.subTest(environment=environment):
                result = self.run_installer(powershell=powershell, **environment)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("installed to", result.stdout)

    def test_bash_stops_on_download_or_verification_failure(self):
        self.assert_failures_are_reported()

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_downloads_exact_release_assets(self):
        result = self.run_installer(powershell=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.requests.read_text().splitlines(), [
            "https://github.com/drasi-project/drasi-server/releases/download/0.2.3/" + name
            for name in ("drasi-server-x86_64-windows-msvc.exe", "drasi-sse-cli-x86_64-windows.exe")
        ])
        self.assertIn("Drasi Server installed to", result.stdout)
        self.assertIn("Drasi SSE CLI installed to", result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_stops_on_download_or_verification_failure(self):
        self.assert_failures_are_reported(powershell=True)


if __name__ == "__main__":
    unittest.main()
