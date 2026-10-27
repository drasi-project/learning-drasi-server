#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors. Licensed under Apache-2.0.
"""Run with python3 -m unittest discover -s scripts -p 'test_*.py'."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import demo


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        demo.load_environment()

    def test_default_ports_are_local_and_distinct(self):
        self.assertEqual(os.environ["SERVER_HOST"], "127.0.0.1")
        self.assertEqual(os.environ["POSTGRES_PORT"], os.environ["POSTGRES_HOST_PORT"])
        self.assertEqual(os.environ["MYSQL_PORT"], os.environ["MYSQL_HOST_PORT"])
        self.assertEqual(demo.container("mysql"), "curbside-pickup-cg-mysql")

    def test_rejects_mismatched_database_ports(self):
        os.environ["MYSQL_HOST_PORT"] = "9999"
        with self.assertRaisesRegex(ValueError, "must match"):
            demo.load_environment()

    def test_rejects_overlapping_ports(self):
        os.environ["WEBUI_PORT"] = os.environ["DASHBOARD_PORT"]
        with self.assertRaisesRegex(ValueError, "distinct"):
            demo.load_environment()

    def test_rejects_external_database(self):
        os.environ["MYSQL_HOST"] = "example.com"
        with self.assertRaisesRegex(ValueError, "local database"):
            demo.load_environment()

    def test_rejects_unowned_container_before_compose(self):
        with patch.object(demo, "engine", return_value="podman"), \
                patch.object(demo, "run", side_effect=[
                    demo.container("postgres") + "\n",
                    json.dumps([{"Config": {"Labels": {}}}]),
                ]), patch.object(demo, "compose") as compose:
            with self.assertRaisesRegex(RuntimeError, "unowned container"):
                demo.database()
            compose.assert_not_called()

    def test_rejects_different_run_owner(self):
        labels = {"io.drasi.curbside-pickup.path": str(demo.TUTORIAL),
                  "io.drasi.curbside-pickup.run": "/different/run"}
        with patch.object(demo, "engine", return_value="podman"), \
                patch.object(demo, "run", side_effect=[
                    demo.container("mysql") + "\n",
                    json.dumps([{"Config": {"Labels": labels}}]),
                ]):
            with self.assertRaisesRegex(RuntimeError, "unowned container"):
                demo.check_ownership()

    def test_cleanup_preserves_volumes_by_default(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(demo, "state_dir", return_value=Path(directory)), \
                patch.object(demo, "check_ownership"), patch.object(demo, "compose") as compose:
            demo.cleanup()
            compose.assert_called_once_with("down")

    def test_cleanup_requires_explicit_volume_flag(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(demo, "state_dir", return_value=Path(directory)), \
                patch.object(demo, "check_ownership"), patch.object(demo, "compose") as compose:
            demo.cleanup(True)
            compose.assert_called_once_with("down", "--volumes")

    def test_cleanup_refuses_running_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "server.lock").write_text("123\n")
            with patch.object(demo, "state_dir", return_value=path), \
                    patch.object(demo, "compose") as compose:
                with self.assertRaisesRegex(RuntimeError, "Stop this demo"):
                    demo.cleanup(True)
                compose.assert_not_called()

    def test_existing_database_is_never_reseeded(self):
        with patch.object(demo, "check_ownership"), \
                patch.object(demo, "engine", return_value="podman"), \
                patch.object(demo.subprocess, "run"), \
                patch.object(demo, "compose"), \
                patch.object(demo, "postgres", return_value="1") as postgres, \
                patch.object(demo, "mysql", return_value="1") as mysql:
            demo.database()
            for call in (*postgres.call_args_list, *mysql.call_args_list):
                self.assertNotIn("DROP TABLE", call.args[0])
                self.assertNotIn("INSERT INTO", call.args[0])

    def test_wrong_runtime_is_not_ready(self):
        with patch.object(demo, "get_json", return_value={
            "success": True, "data": {
                "instanceId": "another-instance", "runtime": "computationGraph", "running": True,
            },
        }):
            with self.assertRaisesRegex(RuntimeError, "this instance"):
                demo.check()

    def test_all_components_and_console_must_be_ready(self):
        proof = {"success": True, "data": {
            "instanceId": demo.INSTANCE, "runtime": "computationGraph", "running": True,
        }}
        responses = [proof]
        for identifiers in (("retail-ops", "physical-ops"), demo.QUERIES, ("curbside-dashboard",)):
            responses.append({"success": True, "data": [
                {"id": name, "status": "Running"} for name in identifiers
            ]})
        responses.extend([[{"id": "curbside-pickup"}], {"connecting": True}])
        with patch.object(demo, "get_json", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "not connected"):
                demo.check()

    def test_join_fans_out_and_timer_can_cancel(self):
        config = (demo.TUTORIAL / "server-config.yaml").read_text()
        self.assertEqual(config.count("        joins:"), 1)
        self.assertEqual(config.count("component: pickup-state"), 2)
        self.assertIn("label: Pickup", config)
        self.assertNotIn("nodes: [Pickup]", config)
        self.assertIn("p.orderStatus <> 'ready' AND p.vehicleLocation = 'Curbside'", config)
        self.assertIn("autoInstallPlugins: false", config)
        self.assertNotIn("ref: source/", config)


if __name__ == "__main__":
    unittest.main()
