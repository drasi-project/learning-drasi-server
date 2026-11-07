#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
"""Small checks that do not build Rust or start any services."""

import json
import io
import os
from pathlib import Path
import re
import socket
import tempfile
import unittest
import urllib.error
from uuid import UUID
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
            queries = {item["name"]: item for item in instance["queries"]}
            self.assertTrue(all("id" not in item for item in instance["queries"]))
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
        self.assertEqual([q["name"] for q in complete["queries"]], expected + ["messages-with-location"])
        for query in complete["queries"]:
            if query["name"] in previous:
                self.assertEqual(query, previous[query["name"]])
        self.assertEqual(complete["queries"][-1]["inputs"], ["all-messages", "location-tracker"])
        location_source = next(s for s in complete["sources"] if s["name"] == "location-tracker")
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

    def test_revisioned_http_queries_match_authoring_definitions(self):
        definitions = {}
        for request in (demo.TUTORIAL / "requests.http").read_text().split("###"):
            marker = "Content-Type: application/json\n\n"
            if marker not in request:
                continue
            body = re.sub(r"\{\{[^{}]+\}\}", "0", request.split(marker, 1)[1]).strip()
            payload = json.loads(body)
            component = payload.get("component", {})
            if component.get("type") != "query":
                continue
            self.assertEqual(payload["expectedRevision"], 0)
            self.assertTrue(payload["requestId"])
            definition = component["definition"]
            definitions[definition["name"]] = definition
        self.assertEqual(set(definitions), {
            "hello-world-senders", "message-counts", "inactive-senders", "messages-with-location",
        })
        for name, definition in definitions.items():
            fixture = json.loads((demo.TUTORIAL / f"configs/{name}.json").read_text())
            self.assertEqual(definition, fixture)

    def test_generated_reference_uses_absolute_scriptfile_path(self):
        content = (demo.TUTORIAL / "server-config.yaml").read_text()
        config = yaml.safe_load(demo.working_config(content))
        source = next(s for s in config["instances"][0]["sources"] if s["name"] == "location-tracker")
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
            with patch.object(demo, "api", return_value={**runtime, "allowExternalComponentIds": False}):
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

    def test_creation_uses_revision_and_receipt_assigned_uuid(self):
        identifier = "08f93596-5c0d-4c5d-890a-cf015bb3d809"
        request_id = "32408b47-4678-45b1-b77d-917519d6fdb4"
        definition = {"name": "new-query", "query": "RETURN 1"}
        with patch.object(demo.uuid, "uuid4", return_value=UUID(request_id)), \
                patch.object(demo, "api", side_effect=[
                    {"revision": 7},
                    {"requestId": request_id, "components": [{"id": identifier, "name": "new-query"}]},
                ]) as api:
            self.assertEqual(demo.create_query(definition), identifier)
        api.assert_called_with("computation/ordinary-definitions", method="POST", body={
            "expectedRevision": 7, "requestId": request_id,
            "component": {"type": "query", "definition": definition},
        })
        self.assertNotIn("id", definition)

    def test_update_retains_uuid_and_does_not_create_new_members(self):
        identifier = "08f93596-5c0d-4c5d-890a-cf015bb3d809"
        request_id = "32408b47-4678-45b1-b77d-917519d6fdb4"
        with patch.object(demo.uuid, "uuid4", return_value=UUID(request_id)), \
                patch.object(demo, "api", side_effect=[
                    {"revision": 8}, {"requestId": request_id, "components": []},
                ]) as api:
            self.assertEqual(demo.configure_component("reaction", {"name": "log"}, identifier), identifier)
        self.assertEqual(api.call_args.args[0], f"computation/ordinary-definitions/{identifier}")
        self.assertEqual(api.call_args.kwargs["method"], "PUT")

    def test_creation_failure_reports_nonce_without_retry(self):
        request_id = "32408b47-4678-45b1-b77d-917519d6fdb4"
        with patch.object(demo.uuid, "uuid4", return_value=UUID(request_id)), \
                patch.object(demo, "api", side_effect=[{"revision": 8}, TimeoutError("lost reply")]) as api:
            with self.assertRaisesRegex(RuntimeError, request_id):
                demo.create_query({"name": "new-query"})
        self.assertEqual(api.call_count, 2)

    def test_explicit_deletion_uses_the_bound_uuid_and_revision(self):
        identifier = "08f93596-5c0d-4c5d-890a-cf015bb3d809"
        request_id = "32408b47-4678-45b1-b77d-917519d6fdb4"
        with patch.object(demo, "component_id", return_value=identifier), \
                patch.object(demo.uuid, "uuid4", return_value=UUID(request_id)), \
                patch.object(demo, "api", side_effect=[
                    {"id": identifier, "name": "log-reaction"}, {"revision": 8},
                    {"requestId": request_id, "components": []}, [],
                ]) as api:
            self.assertEqual(demo.delete_component("reaction", "log-reaction"), identifier)
        self.assertEqual(api.call_args_list[2].args, (f"computation/ordinary-definitions/{identifier}",))
        self.assertEqual(api.call_args_list[2].kwargs, {
            "method": "DELETE", "body": {"expectedRevision": 8, "requestId": request_id},
        })

    def test_uncertain_deletion_does_not_retry_or_recreate(self):
        identifier = "08f93596-5c0d-4c5d-890a-cf015bb3d809"
        request_id = "32408b47-4678-45b1-b77d-917519d6fdb4"
        with patch.object(demo, "component_id", return_value=identifier), \
                patch.object(demo.uuid, "uuid4", return_value=UUID(request_id)), \
                patch.object(demo, "api", side_effect=[
                    {"id": identifier, "name": "log-reaction"}, {"revision": 8}, TimeoutError("lost reply"),
                ]) as api:
            with self.assertRaisesRegex(RuntimeError, request_id):
                demo.delete_component("reaction", "log-reaction")
        self.assertEqual(api.call_count, 3)

    def test_unsupported_update_never_falls_back_to_replacement(self):
        identifier = "08f93596-5c0d-4c5d-890a-cf015bb3d809"
        with patch.object(demo, "api", side_effect=[
            {"revision": 8}, RuntimeError("factory does not support updates"),
        ]) as api:
            with self.assertRaisesRegex(RuntimeError, "factory does not support updates"):
                demo.configure_component("reaction", {"name": "log-reaction"}, identifier)
        self.assertEqual(api.call_count, 2)
        self.assertEqual(api.call_args.kwargs["method"], "PUT")

    def test_name_lookup_and_results_keep_names_separate_from_uuid(self):
        identifier = "08f93596-5c0d-4c5d-890a-cf015bb3d809"
        with patch.object(demo, "api", side_effect=[
            {"id": identifier, "name": "orders/v1"}, [{"count": 2}],
        ]) as api:
            self.assertEqual(demo.query_results("orders/v1"), [{"count": 2}])
        self.assertEqual(api.call_args_list[0].args, ("components/by-name/orders%2Fv1",))
        self.assertEqual(api.call_args_list[1].args, (f"queries/{identifier}/results",))

    def test_waiting_uses_query_collection_and_reports_failures(self):
        with patch.object(demo, "api", return_value={"status": "Running"}) as api:
            demo.wait_running("query", "08f93596-5c0d-4c5d-890a-cf015bb3d809")
        self.assertEqual(api.call_args.args, ("queries/08f93596-5c0d-4c5d-890a-cf015bb3d809",))
        with patch.object(demo, "api", return_value={"status": "Error", "errorMessage": "factory failed"}):
            with self.assertRaisesRegex(RuntimeError, "factory failed"):
                demo.wait_running("reaction", "32408b47-4678-45b1-b77d-917519d6fdb4")


if __name__ == "__main__":
    unittest.main()
