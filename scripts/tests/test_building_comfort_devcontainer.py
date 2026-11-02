# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
CARGO = shutil.which("cargo")
COMMAND_STUB = """#!/bin/bash
set -eu
printf '%s' "${0##*/}" >> "$TEST_COMMAND_LOG"
printf '\\t%s' "$@" >> "$TEST_COMMAND_LOG"
printf '\\n' >> "$TEST_COMMAND_LOG"
if [ "${0##*/}" = "${TEST_FAIL:-}" ]; then
    echo "Test failure: ${0##*/}" >&2
    exit 42
fi
"""


class BuildingComfortDevcontainerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "learning drasi-server"
        self.server = self.root / "drasi-server"
        self.core = self.root / "drasi-core"
        self.tutorial = self.repo / "tutorials/building-comfort"
        self.tutorial.mkdir(parents=True)
        self.hook = self.repo / ".devcontainer/building-comfort/post-create.sh"
        self.hook.parent.mkdir(parents=True)
        shutil.copy2(REPOSITORY / ".devcontainer/building-comfort/post-create.sh", self.hook)
        self.server.mkdir()
        (self.server / "Cargo.toml").touch()
        (self.core / "lib").mkdir(parents=True)
        (self.core / "lib/Cargo.toml").touch()
        (self.core / "Cargo.lock").write_text("# fixture\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "commands.log"
        self.jq_log = self.root / "jq-env.log"
        self.command("sudo")
        for name in ("cargo", "python3"):
            suffix = 'printf "%s\\n" "${JQ_LIB_DIR:-}" >> "$TEST_JQ_LOG"\n'
            if name == "cargo":
                suffix += (
                    'if [ "$1" = "generate-lockfile" ]; then\n'
                    '    printf "# generated fixture\\n" > "$TEST_CORE_LOCK"\n'
                    'fi\n'
                )
            self.command(name, suffix)
        self.command("dpkg-architecture", 'printf "%s\\n" "$TEST_MULTIARCH"\n')

    def command(self, name, suffix=""):
        executable = self.bin / name
        executable.write_text(COMMAND_STUB + suffix)
        executable.chmod(0o755)

    def run_hook(self, **overrides):
        result = subprocess.run(
            ["/bin/bash", str(self.hook)],
            cwd=self.root,
            env={
                **os.environ,
                "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                "TEST_COMMAND_LOG": str(self.log),
                "TEST_JQ_LOG": str(self.jq_log),
                "TEST_CORE_LOCK": str(self.core / "Cargo.lock"),
                "TEST_MULTIARCH": "aarch64-linux-gnu",
                "TEST_FAIL": "",
                "JQ_LIB_DIR": "",
                **overrides,
            },
            capture_output=True,
            text=True,
        )
        calls = [line.split("\t") for line in self.log.read_text().splitlines()]
        return result, calls

    def test_synchronizes_only_server_lockfile_before_build(self):
        result, calls = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [call for call in calls if call[0] in ("cargo", "python3")],
            [
                ["cargo", "update", "--manifest-path",
                 str(self.repo / "../drasi-server/Cargo.toml"), "--workspace"],
                ["python3", "scripts/demo.py", "build"],
            ],
        )
        self.assertEqual((self.core / "Cargo.lock").read_text(), "# fixture\n")

    def test_native_libraries_are_installed_and_selected_for_each_architecture(self):
        for architecture in ("aarch64-linux-gnu", "x86_64-linux-gnu"):
            with self.subTest(architecture=architecture):
                self.log.write_text("")
                self.jq_log.write_text("")
                result, calls = self.run_hook(TEST_MULTIARCH=architecture)
                self.assertEqual(result.returncode, 0, result.stderr)
                install = next(call for call in calls if call[:3] == ["sudo", "apt-get", "install"])
                self.assertIn("libjq-dev", install)
                self.assertIn("libonig-dev", install)
                self.assertIn(["dpkg-architecture", "-qDEB_HOST_MULTIARCH"], calls)
                self.assertEqual(
                    self.jq_log.read_text().splitlines(),
                    [f"/usr/lib/{architecture}", f"/usr/lib/{architecture}"],
                )

    def test_explicit_jq_library_directory_is_preserved(self):
        result, calls = self.run_hook(JQ_LIB_DIR="/custom/jq/lib")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call[0] == "dpkg-architecture" for call in calls))
        self.assertEqual(
            self.jq_log.read_text().splitlines(), ["/custom/jq/lib", "/custom/jq/lib"]
        )

    def test_native_architecture_lookup_failure_stops_before_cargo(self):
        result, calls = self.run_hook(TEST_FAIL="dpkg-architecture")
        self.assertEqual(result.returncode, 42)
        self.assertIn("Test failure: dpkg-architecture", result.stderr)
        self.assertFalse(any(call[0] in ("cargo", "python3") for call in calls))
        self.assertNotIn("environment is ready", result.stdout)

    def test_lockfile_update_failure_stops_before_build(self):
        result, calls = self.run_hook(TEST_FAIL="cargo")
        self.assertEqual(result.returncode, 42)
        self.assertIn("Test failure: cargo", result.stderr)
        self.assertFalse(any(call[0] == "python3" for call in calls))
        self.assertNotIn("environment is ready", result.stdout)

    def test_missing_core_lockfile_is_generated_before_server_update_and_build(self):
        (self.core / "Cargo.lock").unlink()
        result, calls = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [call for call in calls if call[0] in ("cargo", "python3")],
            [
                ["cargo", "generate-lockfile", "--manifest-path",
                 str(self.repo / "../drasi-core/Cargo.toml")],
                ["cargo", "update", "--manifest-path",
                 str(self.repo / "../drasi-server/Cargo.toml"), "--workspace"],
                ["python3", "scripts/demo.py", "build"],
            ],
        )
        self.assertEqual((self.core / "Cargo.lock").read_text(), "# generated fixture\n")

    def test_core_lockfile_generation_failure_stops_before_server_update_and_build(self):
        (self.core / "Cargo.lock").unlink()
        result, calls = self.run_hook(TEST_FAIL="cargo")
        self.assertEqual(result.returncode, 42)
        self.assertIn("Test failure: cargo", result.stderr)
        self.assertEqual(
            [call for call in calls if call[0] == "cargo"],
            [["cargo", "generate-lockfile", "--manifest-path",
              str(self.repo / "../drasi-core/Cargo.toml")]],
        )
        self.assertFalse(any(call[0] == "python3" for call in calls))
        self.assertFalse((self.core / "Cargo.lock").exists())
        self.assertNotIn("environment is ready", result.stdout)

    def real_cargo(self, *arguments):
        return subprocess.run(
            [CARGO, *arguments, "--offline"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    @unittest.skipUnless(CARGO, "Cargo is required for the stale-lockfile regression test")
    def test_stale_server_lockfile_is_repaired_for_a_locked_command(self):
        lib_manifest = "[package]\nname = 'drasi-lib'\nversion = '0.1.0'\nedition = '2021'\n"
        files = {
            self.server / "Cargo.toml":
                "[package]\nname = 'drasi-server'\nversion = '0.1.0'\nedition = '2021'\n"
                "[dependencies]\ndrasi-lib = { path = '../drasi-core/lib' }\n",
            self.server / "src/main.rs": "fn main() {}\n",
            self.core / "Cargo.toml": "[workspace]\nmembers = ['lib', 'helper']\nresolver = '2'\n",
            self.core / "lib/Cargo.toml": lib_manifest,
            self.core / "lib/src/lib.rs": "",
            self.core / "helper/Cargo.toml":
                "[package]\nname = 'drasi-test-helper'\nversion = '0.1.0'\nedition = '2021'\n",
            self.core / "helper/src/lib.rs": "",
        }
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        server_manifest = str(self.server / "Cargo.toml")
        generated = self.real_cargo("generate-lockfile", "--manifest-path", server_manifest)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        (self.core / "lib/Cargo.toml").write_text(
            lib_manifest + "[dependencies]\ndrasi-test-helper = { path = '../helper' }\n"
        )
        generated = self.real_cargo(
            "generate-lockfile", "--manifest-path", str(self.core / "Cargo.toml")
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)
        core_lock = (self.core / "Cargo.lock").read_bytes()
        locked = self.real_cargo(
            "metadata", "--manifest-path", server_manifest, "--locked", "--format-version", "1"
        )
        self.assertNotEqual(locked.returncode, 0)
        self.assertIn("cannot update the lock file", locked.stderr)

        self.command("cargo", 'exec "$TEST_REAL_CARGO" "$@" --offline\n')
        self.command(
            "python3",
            'exec "$TEST_REAL_CARGO" metadata --manifest-path "$TEST_SERVER_MANIFEST" '
            '--locked --offline --format-version 1 > /dev/null\n',
        )
        result, _ = self.run_hook(
            TEST_REAL_CARGO=CARGO, TEST_SERVER_MANIFEST=server_manifest
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        packages = tomllib.loads((self.server / "Cargo.lock").read_text())["package"]
        self.assertIn("drasi-test-helper", {package["name"] for package in packages})
        self.assertEqual((self.core / "Cargo.lock").read_bytes(), core_lock)

        (self.core / "Cargo.lock").unlink()
        result, _ = self.run_hook(
            TEST_REAL_CARGO=CARGO, TEST_SERVER_MANIFEST=server_manifest
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            tomllib.loads((self.core / "Cargo.lock").read_text()),
            tomllib.loads(core_lock.decode()),
        )


if __name__ == "__main__":
    unittest.main()
