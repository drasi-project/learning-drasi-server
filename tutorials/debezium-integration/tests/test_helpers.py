# Copyright 2026 The Drasi Authors.
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

"""Isolated shell regressions: no Docker daemon, network, or real Drasi process."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


TUTORIAL = Path(__file__).resolve().parents[1]


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.tutorial = self.repo / "tutorials/debezium-integration"
        self.scripts = self.tutorial / "scripts"
        self.scripts.mkdir(parents=True)
        for name in ("start-server.sh", "start-demo-http.sh",
                     "start-debezium-server.sh", "setup-database.sh"):
            shutil.copyfile(TUTORIAL / "scripts" / name, self.scripts / name)
        database = self.tutorial / "database"
        database.mkdir()
        (database / "init.sql").write_text("")
        (self.tutorial / "server-config-http.yaml").write_text("")
        self.cwd = self.root / "caller"
        self.cwd.mkdir()
        self.mock_bin = self.root / "commands"
        self.mock_bin.mkdir()
        self.calls = self.root / "calls"
        self.calls.touch()
        # Do not inherit another installation or the caller's tutorial settings.
        self.env = {
            "PATH": f"{self.mock_bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "MOCK_DIR": str(self.root),
            "MOCK_SCENARIO": "running",
        }
        self.mock("sleep", "exit 0")
        self.mock("ps", "exit 0")
        self.mock("tail", "exit 0")
        self.mock("jq", """
case "$*" in *FAILED*) exit 1 ;; esac
cat >/dev/null
""")
        self.mock("curl", """
echo 'curl|'"$*"'|'"$HTTP_SOURCE_PORT" >> "$MOCK_DIR/calls"
[ "$MOCK_SCENARIO" != health-error ] || exit 1
echo '{"connector":{"state":"RUNNING"},"tasks":[{"state":"RUNNING"}]}'
""")
        self.mock("docker-compose", """
echo 'compose|'"$*"'|'"$KAFKA_HOST_PORT"'|'"$CONNECT_HOST_PORT"'|'"$DEBEZIUM_SINK_HTTP_URL" >> "$MOCK_DIR/calls"
case "$*" in
  *"up -d"*) [ "$MOCK_SCENARIO" != up-error ] || exit 1 ;;
  *"ps -a -q debezium-server")
    [ "$MOCK_SCENARIO" != ps-error ] || exit 1
    [ "$MOCK_SCENARIO" = missing ] || echo exact-service-id ;;
  *"logs --no-color --tail 40 debezium-server")
    [ "$MOCK_SCENARIO" != logs-error ] || exit 1
    echo "recent service log evidence" ;;
esac
exit 0
""")
        self.mock("docker", """
echo 'docker|'"$*" >> "$MOCK_DIR/calls"
case "$1" in
  inspect)
    [ "$MOCK_SCENARIO" != inspect-error ] || exit 1
    case "$MOCK_SCENARIO" in
      recover)
        if [ -f "$MOCK_DIR/restarted" ]; then echo running
        else touch "$MOCK_DIR/restarted"; echo restarting; fi ;;
      logs-error) echo exited ;;
      *) echo "$MOCK_SCENARIO" ;;
    esac ;;
esac
exit 0
""")

    def executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(0o755)

    def mock(self, name, body):
        self.executable(self.mock_bin / name, body)

    def run_script(self, name, *args, scenario="running"):
        self.calls.write_text("")
        return subprocess.run(
            ["/bin/bash", str(self.scripts / name), *args],
            cwd=self.cwd, env=dict(self.env, MOCK_SCENARIO=scenario),
            capture_output=True, text=True, timeout=20,
        )

    def test_debezium_starts_exact_service_and_bounds_health_request(self):
        result = self.run_script("start-debezium-server.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls.read_text()
        self.assertIn("ps -a -q debezium-server", calls)
        self.assertIn("inspect --format {{.State.Status}} exact-service-id", calls)
        self.assertIn("--connect-timeout 2 --max-time 5", calls)
        self.assertNotIn("docker|ps", calls)
        self.assertIn("verify snapshot/streaming", result.stdout)

    def test_debezium_retries_transient_restart(self):
        result = self.run_script("start-debezium-server.sh", scenario="recover")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls.read_text().count("docker|inspect"), 2)

    def test_debezium_timeouts_fail_with_logs(self):
        for state in ("missing", "created", "restarting"):
            with self.subTest(state=state):
                result = self.run_script("start-debezium-server.sh", scenario=state)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Timed out", result.stderr)
                self.assertIn("recent service log evidence", result.stderr)
                self.assertNotIn("container is running", result.stdout)
                self.assertEqual(
                    self.calls.read_text().count("ps -a -q debezium-server"), 30,
                )

    def test_debezium_terminal_states_and_command_failures(self):
        for state in ("exited", "dead", "paused", "removing", "inspect-error",
                      "ps-error", "up-error", "logs-error"):
            with self.subTest(state=state):
                result = self.run_script("start-debezium-server.sh", scenario=state)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Error:", result.stderr)
                self.assertNotIn("container is running", result.stdout)
                if state == "logs-error":
                    self.assertIn("Unable to retrieve", result.stderr)
                else:
                    self.assertIn("recent service log evidence", result.stderr)

    def test_unhealthy_listener_does_not_start_debezium(self):
        result = self.run_script("start-debezium-server.sh", scenario="health-error")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not reachable", result.stdout)
        self.assertNotIn("up -d", self.calls.read_text())

    def test_env_overrides_reach_health_check_compose_and_connect(self):
        (self.tutorial / ".env").write_text(
            "HTTP_SOURCE_PORT=19080\n"
            "DEBEZIUM_SINK_HTTP_URL=http://host.docker.internal:19080/debezium\n"
            "KAFKA_HOST_PORT=29092\nCONNECT_HOST_PORT=18083\n"
        )
        result = self.run_script("start-debezium-server.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls.read_text()
        self.assertIn("http://127.0.0.1:19080/health", calls)
        self.assertIn("|29092|18083|http://host.docker.internal:19080/debezium", calls)
        result = self.run_script("setup-database.sh", "kafka")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls.read_text()
        self.assertIn("|29092|18083|", calls)
        self.assertIn("http://localhost:18083/connectors", calls)
        self.assertNotIn("localhost:8083", calls)

    def stub_demo_dependencies(self, debezium_exit=0):
        self.executable(self.scripts / "setup-database.sh", "exit 0")
        self.executable(
            self.scripts / "start-debezium-server.sh", f"exit {debezium_exit}",
        )

    def test_both_resolvers_preserve_per_location_precedence_and_exe_fallback(self):
        self.stub_demo_dependencies()
        candidates = [
            directory / name
            for directory in (self.tutorial / "bin", self.repo / "bin",
                              self.cwd / "bin", self.mock_bin)
            for name in ("drasi-server", "drasi-server.exe")
        ]
        for path in candidates:
            self.executable(path, 'echo "$0" > "$MOCK_DIR/selected"')
        for candidate in candidates:
            for script in ("start-server.sh", "start-demo-http.sh"):
                with self.subTest(candidate=candidate, script=script):
                    result = self.run_script(script)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    selected = Path((self.root / "selected").read_text().strip())
                    self.assertEqual((self.cwd / selected).resolve(), candidate.resolve())
            candidate.unlink()
        for script in ("start-server.sh", "start-demo-http.sh"):
            result = self.run_script(script)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("binary not found", result.stdout)

    def test_demo_stops_when_debezium_fails_without_claiming_delivery(self):
        self.stub_demo_dependencies(debezium_exit=1)
        self.executable(self.tutorial / "bin/drasi-server", "exit 0")
        result = self.run_script("start-demo-http.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("snapshotting into Drasi", result.stdout)
        self.assertNotIn("Streaming Drasi logs", result.stdout)
        self.assertIn("--connect-timeout 2 --max-time 5", self.calls.read_text())


class QueryContractTests(unittest.TestCase):
    def test_both_routes_keep_floor_identity_until_building_aggregation(self):
        queries = []
        for route in ("http", "kafka"):
            text = (TUTORIAL / f"server-config-{route}.yaml").read_text()
            query = text.split("  - id: building-comfort-level-calc\n", 1)[1]
            query = query.split("    query: |\n", 1)[1].split("    sources:", 1)[0]
            groups = query.split("      WITH\n")[1:]
            self.assertEqual(len(groups), 3)
            self.assertTrue(groups[0].startswith("        f, b,\n"))
            self.assertTrue(groups[1].startswith("        f, b,\n"))
            self.assertIn("avg(RoomComfortLevel) AS FloorComfortLevel", groups[1])
            self.assertTrue(groups[2].startswith("        b,\n"))
            self.assertIn("avg(FloorComfortLevel) AS ComfortLevel", groups[2])
            queries.append(query)
        self.assertEqual(*queries)


if __name__ == "__main__":
    unittest.main()
