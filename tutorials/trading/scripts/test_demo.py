# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.

import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import demo
import exercise


class TutorialContractTests(unittest.TestCase):
    def test_runtime_requires_exact_instance_graph_and_running(self):
        body = {"success": True, "data": {
            "instanceId": "trading-server", "runtime": "computationGraph", "running": True,
        }}
        self.assertTrue(demo.runtime_ready(body))
        for key, value in [("instanceId", "another-instance"), ("runtime", "legacy"), ("running", False)]:
            wrong = copy.deepcopy(body)
            wrong["data"][key] = value
            self.assertFalse(demo.runtime_ready(wrong))
        self.assertFalse(demo.runtime_ready({**body, "success": False}))

    def test_uses_existing_source_application_and_five_matching_plugins(self):
        self.assertTrue((demo.EXAMPLE / "server/trading-native-recipe.json").is_file())
        self.assertEqual(demo.EXAMPLE, demo.LEARNING.parent / "drasi-server/examples/trading")
        self.assertEqual(len(demo.PLUGINS), 5)
        self.assertEqual(len(set(demo.PLUGINS)), 5)
        self.assertIn("drasi-reaction-sse", demo.PLUGINS)

    def test_chain_consumes_projected_result_and_label(self):
        self.assertEqual(exercise.ALERT["inputs"], ["price-ticker-query"])
        self.assertEqual(exercise.COUNT["inputs"], [exercise.ALERT["id"]])
        self.assertIn("p:PriceAlert", exercise.COUNT["query"])
        self.assertEqual(exercise.ALERT["result"], {"label": "PriceAlert"})
        for query in (exercise.ALERT, exercise.COUNT):
            self.assertNotIn("sources", query)
            self.assertEqual(query["queryLanguage"], "Cypher")

    def test_documented_chained_query_matches_the_executed_declaration(self):
        readme = (demo.TUTORIAL / "README.md").read_text()
        declarations = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", readme, re.S)]
        self.assertIn(exercise.ALERT, declarations)
        for script in re.findall(r"python3 (scripts/[a-z_]+\.py)", readme):
            self.assertTrue((demo.TUTORIAL / script).is_file(), script)

    def test_exercise_refuses_unowned_random_or_remote_runs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(exercise, "STATE", Path(directory)):
            work = Path(directory) / "run-owned"
            work.mkdir()
            record = {"instance": demo.INSTANCE, "random_prices": False, "container": "a" * 64,
                      "urls": {"server": "http://127.0.0.1:12345"}}
            path = work / "endpoints.json"
            path.write_text(json.dumps(record))
            with patch.object(exercise, "command", return_value="run-owned") as inspect:
                self.assertEqual(exercise.owned_run(work), record)
                self.assertEqual(inspect.call_args[0][0][0:2], ["podman", "inspect"])
            for change in [
                {"random_prices": True}, {"instance": "unrelated"},
                {"urls": {"server": "https://example.com"}},
            ]:
                path.write_text(json.dumps({**record, **change}))
                with self.assertRaises(ValueError), patch.object(exercise, "command") as inspect:
                    exercise.owned_run(work)
                inspect.assert_not_called()
            path.write_text(json.dumps(record))
            with patch.object(exercise, "command", return_value="another-run"), self.assertRaises(ValueError):
                exercise.owned_run(work)
            with self.assertRaises(ValueError):
                exercise.owned_run(Path(directory))

    def test_dead_child_is_not_reported_as_ready(self):
        process = unittest.mock.Mock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "server exited"):
            demo.wait_for("runtime", lambda: True, [("server", process, None)])

    def run_with_mocked_services(self, *, fail_api=False):
        calls = []
        processes = []
        container = "a" * 64

        def execute(arguments, **kwargs):
            arguments = list(map(str, arguments))
            calls.append((arguments, kwargs))
            if arguments[:2] == ["podman", "run"]:
                return container
            if arguments[:2] == ["podman", "port"]:
                return "127.0.0.1:55123"
            if "inspect" in arguments:
                return json.dumps({"instances": [{"id": demo.INSTANCE}]})
            return "{}"

        def spawn(*args, **kwargs):
            process = unittest.mock.Mock()
            process.poll.return_value = None
            processes.append((process, args, kwargs))
            return process

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            with patch.object(demo, "STATE", state), \
                    patch.object(demo, "verified_build", return_value=(Path("/local/server"), Path("/local/plugins"), Path("/local/generator"))), \
                    patch.object(demo, "command", side_effect=execute), \
                    patch.object(demo, "available_port", side_effect=range(55100, 55105)), \
                    patch.object(demo, "wait_for", side_effect=[None, RuntimeError("API unavailable")] if fail_api else None), \
                    patch.object(demo.subprocess, "Popen", side_effect=spawn), \
                    patch.object(demo.time, "sleep", side_effect=KeyboardInterrupt), \
                    patch("builtins.print"):
                if fail_api:
                    with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                        demo.run(True)
                else:
                    demo.run(True)
                self.assertFalse((state / "server.lock").exists())
                if not fail_api:
                    record = json.loads(next(state.glob("run-*/endpoints.json")).read_text())
                    self.assertEqual(record["container"], container)
                    self.assertFalse(record["random_prices"])
            return calls, processes, container

    def test_foreground_run_uses_owned_resources_and_cleans_up_on_interrupt(self):
        calls, processes, container = self.run_with_mocked_services()
        run = next(arguments for arguments, _ in calls if arguments[:2] == ["podman", "run"])
        self.assertIn("127.0.0.1::5432", run)
        self.assertIn("--tmpfs", run)
        self.assertNotIn("--volume", run)
        self.assertEqual(calls[-1][0], ["podman", "rm", "--force", container])
        self.assertEqual(len(processes), 3)  # API, Server, actual Vite app; no random price process.
        for process, _args, kwargs in processes:
            self.assertTrue(kwargs["start_new_session"])
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=60)
        app_env = processes[-1][2]["env"]
        self.assertEqual(app_env["VITE_TRADING_API_URL"], "http://127.0.0.1:55103")
        self.assertEqual(app_env["VITE_DRASI_SERVER_URL"], "http://127.0.0.1:55100")

    def test_failed_api_is_reported_and_only_owned_database_is_removed(self):
        calls, processes, container = self.run_with_mocked_services(fail_api=True)
        self.assertEqual(calls[-1][0], ["podman", "rm", "--force", container])
        self.assertEqual(len(processes), 1)
        processes[0][0].terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
