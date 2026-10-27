#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
"""Small checks that do not build Rust or start any services."""

import json
import io
import os
from pathlib import Path
import socket
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import yaml

import demo


class TutorialTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "DRASI_RUN_ID": "getting-started-unit",
            "POSTGRES_PORT": "5532", "SERVER_PORT": "8180",
            "SSE_PORT": "8181", "HTTP_PORT": "8182",
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_config_sequence_matches_request_bodies(self):
        previous = {}
        expected = ["all-messages", "hello-world-senders", "message-counts", "inactive-senders"]
        for step in range(3, 7):
            path = demo.TUTORIAL / f"configs/getting-started-step-{step}.yaml"
            config = yaml.safe_load(path.read_text())
            self.assertFalse(config["autoInstallPlugins"])
            self.assertEqual(config["host"], "127.0.0.1")
            self.assertNotIn("plugins", config)
            self.assertNotIn("pluginRegistry", config)
            instance, = config["instances"]
            self.assertEqual(instance["id"], demo.INSTANCE)
            queries = {item["id"]: item for item in instance["queries"]}
            self.assertEqual(list(queries), expected[:step - 2])
            for name, query in previous.items():
                self.assertEqual(queries[name], query)
            for name, query in queries.items():
                self.assertTrue(query["result"]["label"])
                if name != "all-messages":
                    fixture = json.loads((demo.TUTORIAL / f"configs/{name}.json").read_text())
                    self.assertEqual(query | {"query": " ".join(query["query"].split())},
                                     fixture | {"query": " ".join(fixture["query"].split())})
            previous = queries
        complete = yaml.safe_load((demo.TUTORIAL / "server-config.yaml").read_text())["instances"][0]
        self.assertEqual([q["id"] for q in complete["queries"]], expected + ["messages-with-location"])
        for query in complete["queries"]:
            if query["id"] in previous:
                self.assertEqual(query, previous[query["id"]])
        self.assertEqual(complete["queries"][-1]["inputs"], ["all-messages", "location-tracker"])
        location_source = next(s for s in complete["sources"] if s["id"] == "location-tracker")
        path = location_source["bootstrapProvider"]["filePaths"][0]
        self.assertEqual((demo.state() / path).resolve(), demo.TUTORIAL / "locations.jsonl")
        self.assertEqual(previous["all-messages"]["result"]["label"], "Message")
        self.assertEqual(previous["inactive-senders"]["inputs"], ["my-postgres"])
        for name in ("message-counts", "hello-world-senders"):
            self.assertEqual(previous[name]["inputs"], ["all-messages"])

    def test_database_initialization_never_drops_existing_data(self):
        sql = (demo.TUTORIAL / "database/init.sql").read_text().upper()
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("PG_DROP_REPLICATION_SLOT", sql)
        self.assertNotIn("PG_CREATE_LOGICAL_REPLICATION_SLOT", sql)
        self.assertIn('CREATE TABLE "MESSAGE"', sql)

    def test_generated_reference_uses_absolute_scriptfile_path(self):
        content = (demo.TUTORIAL / "server-config.yaml").read_text()
        config = yaml.safe_load(demo.working_config(content))
        source = next(s for s in config["instances"][0]["sources"] if s["id"] == "location-tracker")
        self.assertEqual(source["bootstrapProvider"]["filePaths"],
                         [str(demo.TUTORIAL / "locations.jsonl")])

    def test_environment_rejects_unsafe_names_and_conflicting_ports(self):
        with patch.dict(os.environ, {"DRASI_RUN_ID": "../someone-else"}):
            with self.assertRaisesRegex(ValueError, "DRASI_RUN_ID"):
                demo.environment()
        with patch.dict(os.environ, {"HTTP_PORT": "8180"}):
            with self.assertRaisesRegex(ValueError, "distinct"):
                demo.environment()
        with patch.dict(os.environ, {"HTTP_PORT": "08180"}):
            with self.assertRaisesRegex(ValueError, "distinct"):
                demo.environment()
        with patch.dict(os.environ, {"HTTP_PORT": "70000"}):
            with self.assertRaisesRegex(ValueError, "TCP port"):
                demo.environment()

    def test_refuses_unowned_containers_and_volumes(self):
        for kind, name, record in (
            ("container", demo.container(), {"Config": {"Labels": {}}}),
            ("volume", demo.volume(), {"Labels": {demo.LABEL: "/another/run"}}),
        ):
            with self.subTest(kind=kind), patch.object(
                demo, "run", side_effect=[name + "\n", json.dumps([record])]
            ):
                with self.assertRaisesRegex(RuntimeError, "unowned"):
                    demo.owned(kind, name)

    def test_cleanup_checks_both_owners_before_removing_anything(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            demo, "state", return_value=Path(directory)
        ), patch.object(demo, "owned", side_effect=[True, RuntimeError("unowned volume")]), patch.object(
            demo, "run"
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "unowned volume"):
                demo.cleanup(True)
            run.assert_not_called()

    def test_cleanup_preserves_volume_by_default(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            demo, "state", return_value=Path(directory)
        ), patch.object(demo, "owned", return_value=True), patch.object(demo, "run") as run:
            demo.cleanup()
            self.assertEqual([call.args[0] for call in run.call_args_list],
                             [["podman", "stop", demo.container()], ["podman", "rm", demo.container()]])

    def test_cleanup_refuses_an_active_server_lock(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            demo, "state", return_value=Path(directory)
        ), patch.object(demo, "owned") as owned:
            (Path(directory) / "server.lock").write_text("12345\n")
            with self.assertRaisesRegex(RuntimeError, "foreground Server"):
                demo.cleanup(True)
            owned.assert_not_called()

    def test_existing_working_configuration_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            demo, "state", return_value=Path(directory)
        ), patch.object(demo, "local_build") as helper:
            helper.return_value.verified_build.return_value = (Path("server"), Path("plugins"))
            config = Path(directory) / "getting-started.yaml"
            config.write_text("user configuration\n")
            with self.assertRaisesRegex(RuntimeError, "do not overwrite API changes"):
                demo.start(demo.TUTORIAL / "configs/getting-started-step-3.yaml")
            self.assertEqual(config.read_text(), "user configuration\n")

    def test_environment_does_not_execute_dotenv_content(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            demo, "TUTORIAL", Path(directory)
        ):
            (Path(directory) / ".env").write_text("source ~/.profile\n")
            with self.assertRaisesRegex(ValueError, "NAME=value"):
                demo.environment()

    def test_port_probe_still_rejects_a_live_listener(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            with self.assertRaises(OSError):
                demo.free_port(listener.getsockname()[1])

    def test_sql_values_are_passed_as_psql_variables(self):
        with patch.object(demo, "owned", return_value=True), patch.object(
            demo, "run", return_value="8\nINSERT 0 1"
        ) as run:
            demo.sql("SELECT :'sender';", variables={"sender": "O'Brien; DROP TABLE Message;"})
            argv = run.call_args.args[0]
            self.assertIn("sender=O'Brien; DROP TABLE Message;", argv)
            self.assertEqual(run.call_args.kwargs["stdin"], "SELECT :'sender';")
            self.assertIn("ON_ERROR_STOP=1", argv)

    def test_runtime_check_requires_exact_instance_and_running_graph(self):
        for runtime in (
            {"instanceId": "other", "runtime": "computationGraph", "running": True},
            {"instanceId": demo.INSTANCE, "runtime": "computationGraph", "running": False},
            {"instanceId": demo.INSTANCE, "runtime": "legacy", "running": True},
        ):
            with patch.object(demo, "api", return_value=runtime):
                with self.assertRaisesRegex(RuntimeError, "runtime"):
                    demo.check()

    def test_api_preserves_applied_but_not_persisted_error_without_retry(self):
        error = urllib.error.HTTPError(
            "http://127.0.0.1", 500, "Internal Server Error", {},
            io.BytesIO(b'{"code":"PERSISTENCE_FAILED","message":"change applied in memory"}'),
        )
        with patch.object(demo.urllib.request, "urlopen", side_effect=error) as request:
            with self.assertRaisesRegex(RuntimeError, "PERSISTENCE_FAILED"):
                demo.api("reactions", method="POST", body={"kind": "log"})
            self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
