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
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import demo
import verify_demo


POST_CREATE = demo.TUTORIAL.parents[1] / ".devcontainer/building-comfort/post-create.sh"


class DemoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        environment = patch.dict(os.environ, {"DRASI_DEMO_DIR": str(self.directory)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        tutorial = patch.object(demo, "TUTORIAL", self.directory)
        tutorial.start()
        self.addCleanup(tutorial.stop)
        demo.load_environment()

    def build_record(self):
        plugins = self.directory / "plugins"
        plugins.mkdir()
        artifacts = {}
        for name in ("server", *demo.PLUGINS):
            path = (self.directory if name == "server" else plugins) / name
            path.write_text(name)
            artifacts[name] = {"path": str(path), "sha256": demo.sha256(path)}
        record = {"runtime": "computationGraph", "artifacts": artifacts}
        (self.directory / "build.json").write_text(json.dumps(record))
        return record

    def test_requires_build_no_path_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "No local build"):
            demo.verified_build()

    def test_build_delegates_private_state_and_exact_plugins(self):
        with patch.object(demo.local_build, "build") as build:
            demo.build()
            build.assert_called_once_with(self.directory.resolve(), demo.PLUGINS)

    def test_exact_matching_build(self):
        self.build_record()
        server, plugins = demo.verified_build()
        self.assertEqual(server, self.directory / "server")
        self.assertEqual(plugins, self.directory / "plugins")

    def test_changed_plugin_rejected(self):
        record = self.build_record()
        Path(record["artifacts"][demo.PLUGINS[0]]["path"]).write_text("different")
        with self.assertRaisesRegex(RuntimeError, "changed local artifact"):
            demo.verified_build()

    def test_extra_plugin_rejected(self):
        self.build_record()
        (self.directory / "plugins/old-plugin.so").write_text("old")
        with self.assertRaisesRegex(RuntimeError, "Unexpected files"):
            demo.verified_build()

    def test_missing_plugin_rejected(self):
        record = self.build_record()
        Path(record["artifacts"][demo.PLUGINS[0]]["path"]).unlink()
        with self.assertRaisesRegex(RuntimeError, "Missing or changed"):
            demo.verified_build()

    def test_exported_environment_wins(self):
        (self.directory / ".env").write_text("SERVER_PORT=9000\n")
        with patch.dict(os.environ, {"SERVER_PORT": "8381"}):
            demo.load_environment()
            self.assertEqual(os.environ["SERVER_PORT"], "8381")

    def test_invalid_environment_rejected(self):
        (self.directory / ".env").write_text("export SERVER_PORT=9000\n")
        with self.assertRaisesRegex(ValueError, "expected NAME=value"):
            demo.load_environment()

    def test_mismatched_database_ports_rejected(self):
        with patch.dict(os.environ, {"POSTGRES_PORT": "9000"}):
            with self.assertRaisesRegex(ValueError, "must match"):
                demo.load_environment()

    def test_foreign_container_not_reused_or_deleted(self):
        with patch.object(demo, "engine", return_value="podman"), patch.object(
            demo, "run", side_effect=[demo.container(), json.dumps([{"Config": {"Labels": {}}}])]
        ):
            with self.assertRaisesRegex(RuntimeError, "unowned container"):
                demo.check_database_ownership()

    def test_foreign_volume_not_reused_or_deleted(self):
        volume = os.environ["COMPOSE_PROJECT_NAME"] + "_building_comfort_postgres_data"
        with patch.object(demo, "engine", return_value="podman"), patch.object(
            demo, "run", side_effect=["", volume, json.dumps([{"Labels": {}}])]
        ):
            with self.assertRaisesRegex(RuntimeError, "unowned volume"):
                demo.check_database_ownership()

    def test_cleanup_requires_server_stopped(self):
        (self.directory / "server.lock").touch()
        with patch.object(demo, "compose") as compose:
            with self.assertRaisesRegex(RuntimeError, "Ctrl.C"):
                demo.cleanup(True)
            compose.assert_not_called()

    def test_start_rejects_another_listener_without_launching(self):
        (self.directory / "server-config.yaml").write_text("apiVersion: drasi.io/v1\n")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            with patch.dict(os.environ, {"SERVER_PORT": str(listener.getsockname()[1])}), \
                    patch.object(demo, "verified_build", return_value=(Path("/unused"), self.directory)), \
                    patch.object(demo.subprocess, "Popen") as process:
                with self.assertRaises(OSError):
                    demo.start()
                process.assert_not_called()
        self.assertFalse((self.directory / "server.lock").exists())

    def test_cleanup_preserves_volume_by_default(self):
        with patch.object(demo, "check_database_ownership"), patch.object(demo, "compose") as compose:
            demo.cleanup()
            compose.assert_called_once_with("down")

    def test_existing_database_is_not_reseeded(self):
        with patch.object(demo, "check_database_ownership"), patch.object(demo, "compose"), \
                patch.object(demo, "engine", return_value="podman"), \
                patch.object(demo.subprocess, "run") as process, \
                patch.object(demo, "sql", side_effect=["3", "3", "1", "readings"]) as sql:
            process.return_value.returncode = 0
            demo.database()
            self.assertFalse(any("DROP TABLE" in call.args[0] for call in sql.call_args_list))
            self.assertFalse(any("INSERT INTO" in call.args[0] for call in sql.call_args_list))

    def test_reset_all_is_one_transaction(self):
        with patch.object(demo, "sql", return_value="UPDATE 9") as sql:
            demo.reset_room()
            sql.assert_called_once_with('UPDATE "Room" SET temperature=70, humidity=40, co2=10;')

    def test_invalid_room_fails_before_sql(self):
        with patch.object(demo, "sql") as sql:
            with self.assertRaises(ValueError):
                demo.set_room("room'; DROP TABLE x", 70, 40, 10)
            sql.assert_not_called()

    def test_nonexistent_room_is_not_success(self):
        with patch.object(demo, "sql", return_value="UPDATE 0"):
            with self.assertRaisesRegex(RuntimeError, "exactly room"):
                demo.set_room("missing", 70, 40, 10)

    def test_wrong_runtime_instance_rejected(self):
        with patch.object(demo, "get_json", return_value={
            "success": True, "data": {"instanceId": "wrong", "runtime": "computationGraph", "running": True},
        }):
            with self.assertRaisesRegex(RuntimeError, "Expected this instance"):
                demo.check()

    def test_readiness_includes_internal_source(self):
        def components(names):
            return {"success": True, "data": [{"id": name, "status": "Running"} for name in names]}
        responses = [
            {"success": True, "data": {"instanceId": demo.INSTANCE, "runtime": "computationGraph", "running": True}},
            components(["building-facilities", "__component_graph__"]),
            components(demo.QUERIES),
            components(["building-comfort-dashboard", "console-log"]),
            [{"id": "building-comfort"}],
        ]
        with patch.object(demo, "get_json", side_effect=responses):
            self.assertTrue(demo.check()["success"])

    def test_result_check_rejects_missing_duplicate_and_wrong_rows(self):
        expected = [{"RoomId": "r", "ComfortLevel": 46}]
        for actual in ([], expected * 2, [{"RoomId": "r", "ComfortLevel": 47}]):
            with self.assertRaises(AssertionError):
                verify_demo.assert_rows(actual, expected, "test")

    def test_reference_uses_floor_average_not_room_weighting(self):
        rooms = [
            {"id": name, "name": name, "floor_id": floor, "floor_name": floor,
             "building_id": "b", "building_name": "b", "temperature": temperature,
             "humidity": 40, "co2": 10}
            for name, floor, temperature in (("a", "f1", 70), ("b", "f1", 70), ("c", "f2", 82))
        ]
        result = verify_demo.expected_results(rooms)
        self.assertEqual(
            result["building-comfort-level-calc"],
            [{"BuildingId": "b", "BuildingName": "b", "ComfortLevel": 52}],
        )
        self.assertEqual(len(result["building-alert"]), 1)
        self.assertEqual(
            result["floor-comfort-level-calc"][0],
            {"FloorId": "f1", "FloorName": "f1", "BuildingId": "b",
             "BuildingName": "b", "ComfortLevel": 46},
        )
        self.assertEqual(
            result["floor-alert"],
            [{"FloorId": "f2", "FloorName": "f2", "ComfortLevel": 58}],
        )

    def test_reference_keeps_names_through_the_shared_aggregation_chain(self):
        rooms = [{"id": "r", "name": "Office", "floor_id": "f", "floor_name": "Ground",
                  "building_id": "b", "building_name": "HQ", "temperature": 28,
                  "humidity": 40, "co2": 10}]
        result = verify_demo.expected_results(rooms)
        self.assertEqual(result["room-comfort"], [
            {"RoomId": "r", "RoomName": "Office", "FloorId": "f", "FloorName": "Ground",
             "BuildingId": "b", "BuildingName": "HQ", "Temperature": 28,
             "Humidity": 40, "CO2": 10, "ComfortLevel": 4},
        ])
        self.assertEqual(result["room-alert"], [
            {"RoomId": "r", "RoomName": "Office", "ComfortLevel": 4},
        ])
        self.assertEqual(result["floor-alert"], [
            {"FloorId": "f", "FloorName": "Ground", "ComfortLevel": 4},
        ])
        self.assertEqual(result["building-alert"], [
            {"BuildingId": "b", "BuildingName": "HQ", "ComfortLevel": 4},
        ])
        self.assertTrue(all(not rows for rows in verify_demo.expected_results([]).values()))

    def test_tutorial_tenth_room_keeps_equal_floor_weight(self):
        rooms = [
            {"id": f"{floor}-{room}", "name": str(room),
             "floor_id": floor, "floor_name": floor,
             "building_id": "b", "building_name": "Building",
             "temperature": 70, "humidity": 40, "co2": 10}
            for floor in ("f1", "f2", "f3") for room in range(3)
        ]
        rooms.append(dict(rooms[0], id="extra", name="Extra", temperature=82))
        result = verify_demo.expected_results(rooms)
        self.assertEqual(len(result["room-comfort"]), 10)
        self.assertEqual(
            [row["ComfortLevel"] for row in result["floor-comfort-level-calc"]],
            [49, 46, 46],
        )
        self.assertEqual(result["building-comfort-level-calc"][0]["ComfortLevel"], 47)
        self.assertEqual(
            sum(row["ComfortLevel"] for row in result["room-comfort"]) / 10, 47.2,
        )
        self.assertEqual([row["RoomId"] for row in result["room-alert"]], ["extra"])
        self.assertEqual(result["floor-alert"], [])
        self.assertEqual(result["building-alert"], [])

    def run_post_create(self, *, lockfile):
        repository = self.directory / "learning-drasi-server"
        script = repository / ".devcontainer/building-comfort/post-create.sh"
        script.parent.mkdir(parents=True)
        script.write_text(POST_CREATE.read_text())
        (repository / "tutorials/building-comfort").mkdir(parents=True)
        for name in ("drasi-server/Cargo.toml", "drasi-core/lib/Cargo.toml"):
            manifest = self.directory / name
            manifest.parent.mkdir(parents=True)
            manifest.touch()
        lock = self.directory / "drasi-core/Cargo.lock"
        if lockfile:
            lock.write_text("existing lockfile\n")
        commands = self.directory / "commands"
        commands.mkdir()
        for name, body in (
            ("sudo", "#!/bin/sh\nexit 0\n"),
            ("python3", '#!/bin/sh\nprintf "BUILD: %s %s\\n" "$1" "$2"\n'),
        ):
            executable = commands / name
            executable.write_text(body)
            executable.chmod(0o755)
        result = subprocess.run(
            ["/bin/bash", str(script)], cwd=self.directory,
            env=dict(os.environ, PATH=f"{commands}:/usr/bin:/bin"),
            capture_output=True, text=True, check=False,
        )
        return result, lock

    def test_devcontainer_missing_lockfile_has_actionable_error(self):
        result, lock = self.run_post_create(lockfile=False)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Core's workspace Cargo.lock is required", result.stdout)
        self.assertIn(
            "RUSTUP_TOOLCHAIN=1.95.0 cargo generate-lockfile --manifest-path ../../../drasi-core/Cargo.toml",
            result.stdout,
        )
        self.assertNotIn("BUILD:", result.stdout)
        self.assertFalse(lock.exists())

    def test_devcontainer_keeps_lockfile_and_uses_tutorial_build(self):
        result, lock = self.run_post_create(lockfile=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BUILD: scripts/demo.py build", result.stdout)
        self.assertEqual(lock.read_text(), "existing lockfile\n")


if __name__ == "__main__":
    unittest.main()
