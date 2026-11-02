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

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


CONFIG_DIR = Path(__file__).resolve().parents[2] / ".devcontainer/getting-started"

DOCKER_STUB = """#!/bin/bash
set -eu
printf '%s\\n' "$*" >> "$TEST_DOCKER_LOG"
if [ "$1 $2" = "${TEST_FAIL:-}" ]; then
    echo "Engine error: $1 $2" >&2
    exit 42
fi
case "$1 $2" in
    "container inspect") printf '%s\\n' "${TEST_CONNECTED:-}" ;;
    "network ls") printf '%s\\n' "${TEST_NETWORKS:-}" ;;
    "network create"|"network connect") ;;
    *) echo "Unexpected command: $*" >&2; exit 43 ;;
esac
"""


class DevcontainerNetworkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.log = self.path / "docker.log"
        for name, content in (
            ("docker", DOCKER_STUB),
            ("hostname", "#!/bin/sh\nprintf 'test-container\\n'\n"),
        ):
            executable = self.path / name
            executable.write_text(content)
            executable.chmod(0o755)

    def run_hook(self, **overrides):
        environment = {
            **os.environ,
            "PATH": f"{self.path}{os.pathsep}{os.environ['PATH']}",
            "TEST_DOCKER_LOG": str(self.log),
            "TEST_CONNECTED": "",
            "TEST_NETWORKS": "",
            "TEST_FAIL": "",
            **overrides,
        }
        result = subprocess.run(
            ["bash", str(CONFIG_DIR / "post-start.sh")],
            env=environment,
            capture_output=True,
            text=True,
        )
        calls = self.log.read_text().splitlines()
        return result, calls

    def test_creates_and_connects_missing_network(self):
        result, calls = self.run_hook(TEST_NETWORKS="bridge\npodman\ndrasi-network-other")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-2:], [
            "network create drasi-network",
            "network connect drasi-network test-container",
        ])

    def test_reuses_existing_network(self):
        result, calls = self.run_hook(TEST_NETWORKS="bridge\ndrasi-network")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("network create drasi-network", calls)
        self.assertEqual(calls[-1], "network connect drasi-network test-container")

    def test_already_connected_is_a_noop(self):
        result, calls = self.run_hook(TEST_CONNECTED="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("container inspect "))
        self.assertIn("already connected", result.stdout)

    def test_engine_errors_stop_setup(self):
        for command in ("container inspect", "network ls", "network create", "network connect"):
            with self.subTest(command=command):
                self.log.write_text("")
                result, calls = self.run_hook(TEST_FAIL=command)
                self.assertEqual(result.returncode, 42)
                self.assertIn(f"Engine error: {command}", result.stderr)
                self.assertTrue(calls[-1].startswith(command))
                self.assertNotIn("Dev container connected", result.stdout)

    def test_network_setup_runs_inside_container_before_attach(self):
        config = json.loads((CONFIG_DIR / "devcontainer.json").read_text())
        self.assertNotIn("initializeCommand", config)
        self.assertNotIn("--network=drasi-network", config.get("runArgs", []))
        self.assertEqual(config["postStartCommand"], "bash .devcontainer/getting-started/post-start.sh")
        self.assertEqual(config["waitFor"], "postStartCommand")
        self.assertIn("ghcr.io/devcontainers/features/docker-outside-of-docker:1", config["features"])

    def test_tmp_permissions_are_set_before_lifecycle_commands(self):
        config = json.loads((CONFIG_DIR / "devcontainer.json").read_text())
        self.assertIn("--tmpfs=/tmp:rw,exec,mode=1777", config["runArgs"])

    def test_post_create_stops_on_apt_errors(self):
        sudo = self.path / "sudo"
        sudo.write_text("""#!/bin/bash
set -eu
printf '%s\\n' "$*" >> "$TEST_SUDO_LOG"
if [ "$*" = "$TEST_FAIL" ]; then
    echo "Package installation failed: $*" >&2
    exit 42
fi
case "$*" in
    "apt-get update") ;;
    *) echo "Unexpected sudo command: $*" >&2; exit 43 ;;
esac
""")
        sudo.chmod(0o755)
        downstream = self.path / "bash"
        downstream.write_text("#!/bin/sh\necho 'Unexpected downstream script' >&2\nexit 43\n")
        downstream.chmod(0o755)

        for command in ("apt-get update", "apt-get install -y postgresql-client"):
            with self.subTest(command=command):
                self.log.write_text("")
                result = subprocess.run(
                    ["/bin/bash", str(CONFIG_DIR / "post-create.sh")],
                    env={
                        **os.environ,
                        "PATH": f"{self.path}{os.pathsep}{os.environ['PATH']}",
                        "TEST_SUDO_LOG": str(self.log),
                        "TEST_FAIL": command,
                    },
                    capture_output=True,
                    text=True,
                )
                calls = self.log.read_text().splitlines()
                self.assertEqual(result.returncode, 42)
                self.assertEqual(calls[0], "apt-get update")
                self.assertEqual(calls[-1], command)
                self.assertIn("Package installation failed", result.stderr)
                self.assertNotIn("environment is ready", result.stdout)


if __name__ == "__main__":
    unittest.main()
