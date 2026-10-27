#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Scoped, dependency-free regression checks for the tutorial runner."""

import json
import os
from pathlib import Path
import re
import socket
import tempfile
import unittest
from unittest.mock import patch

import demo


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.environment = patch.dict(os.environ, {
            "DRASI_DEMO_DIR": str(self.directory),
            "DRASI_RUN_ID": "hrc-unit-check",
            "CONTAINER_ENGINE": "podman",
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.engine = patch.object(demo, "engine", return_value="podman")
        self.engine.start()
        self.addCleanup(self.engine.stop)

    def record(self):
        return demo.ownership(create=True)

    def test_run_identity_and_ports_are_persistent(self):
        record = self.record()
        self.assertEqual(demo.ownership(), record)
        os.environ["DRASI_RUN_ID"] = "different-run"
        with self.assertRaisesRegex(RuntimeError, "differs"):
            demo.ownership()

    def test_changed_port_cannot_target_another_run(self):
        self.record()
        os.environ["SERVER_PORT"] = "55555"
        with self.assertRaisesRegex(RuntimeError, "SERVER_PORT differs"):
            demo.ownership()

    def test_bad_or_duplicate_ports_rejected(self):
        os.environ["SERVER_PORT"] = "5732"
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.record()

    def test_port_probe_allows_clean_immediate_restart(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port)) as client:
                connection, _ = listener.accept()
                connection.close()
                self.assertEqual(client.recv(1), b"")
        demo.free_ports(port)

    def test_port_probe_still_rejects_live_listener(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            with self.assertRaises(OSError):
                demo.free_ports(listener.getsockname()[1])

    def test_run_id_must_be_a_kubernetes_dns_label(self):
        os.environ["DRASI_RUN_ID"] = "hrc-invalid-"
        with self.assertRaisesRegex(ValueError, "DNS label"):
            self.record()

    def test_ownership_cannot_move_between_directories(self):
        record = self.record()
        record["path"] = "/not-this-directory"
        (self.directory / "ownership.json").write_text(json.dumps(record))
        with self.assertRaisesRegex(RuntimeError, "different"):
            demo.ownership()

    def test_unowned_container_and_volume_rejected(self):
        for kind, item in (("container", {"Config": {"Labels": {}}}), ("volume", {"Labels": {}})):
            with self.subTest(kind=kind), patch.object(demo, "run", side_effect=["existing\n", json.dumps([item])]):
                with self.assertRaisesRegex(RuntimeError, "unowned"):
                    demo.inspect_owned(kind, "existing")

    def test_matching_ownership_label_required(self):
        item = {"Config": {"Labels": {demo.LABEL: str(self.directory)}}}
        with patch.object(demo, "run", side_effect=["ours\n", json.dumps([item])]):
            self.assertEqual(demo.inspect_owned("container", "ours"), item)

    def test_k3d_requires_explicit_podman_endpoint(self):
        with self.assertRaisesRegex(RuntimeError, "Podman API socket"):
            demo.kube_environment()
        os.environ["DOCKER_HOST"] = "unix:///owned-podman.sock"
        self.assertEqual(demo.kube_environment()["KUBECONFIG"], str(self.directory / "kubeconfig.yaml"))

    def test_kubectl_never_uses_global_context(self):
        self.record()
        with patch.object(demo, "run", return_value="") as run:
            demo.kubectl("get", "pods")
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:7], [
            "--kubeconfig", self.directory / "kubeconfig.yaml",
            "--context", "k3d-hrc-unit-check", "--namespace", "hrc-unit-check",
        ])

    def test_kubectl_rejects_context_override(self):
        with self.assertRaisesRegex(ValueError, "override"):
            demo.kubectl("get", "pods", "--context=unowned")

    def test_wrong_podman_endpoint_rejected_before_cluster_changes(self):
        os.environ["DOCKER_HOST"] = "unix:///wrong.sock"
        with patch.object(demo, "run", side_effect=["host|/root-a", "host|/root-b"]):
            with self.assertRaisesRegex(RuntimeError, "not the Podman engine"):
                demo.verify_engine_endpoint()

    def test_cluster_creation_preserves_global_config_and_pod_images(self):
        record = self.record()
        responses = iter([
            "apiVersion: v1\n", json.dumps({"items": [{"metadata": {"name": record["run"]}}]}),
            json.dumps({"items": [{"metadata": {"name": "my-app-1"}}, {"metadata": {"name": "my-app-2"}}]}),
            "", "",
        ])
        with patch.object(demo.shutil, "which", return_value="/tool"), \
             patch.object(demo, "clusters", return_value=[]), \
             patch.object(demo, "verify_cluster", side_effect=[False, True]), \
             patch.object(demo, "verify_engine_endpoint"), \
             patch.object(demo, "verify_namespace"), patch.object(demo, "free_ports"), \
             patch.object(demo, "kube_environment", return_value={}), \
             patch.object(demo, "run", side_effect=lambda argv, **kwargs:
                          "" if "create" in argv else next(responses)) as run:
            demo.cluster()
        creation = run.call_args_list[0].args[0]
        self.assertIn("--kubeconfig-update-default=false", creation)
        self.assertIn("--kubeconfig-switch-context=false", creation)
        self.assertEqual((self.directory / "kubeconfig.yaml").stat().st_mode & 0o777, 0o600)
        self.assertFalse(any("apply" in call.args[0] for call in run.call_args_list))

    def test_existing_database_is_not_reseeded(self):
        self.record()
        with patch.object(demo, "inspect_owned", return_value={"State": {"Running": True}}), \
             patch.object(demo.subprocess, "run") as probe, \
             patch.object(demo, "sql", side_effect=["1", "1", "1"]) as sql:
            probe.return_value.returncode = 0
            demo.database()
        self.assertFalse(any("DROP" in call.args[0] or "INSERT" in call.args[0] for call in sql.call_args_list))

    def test_risk_values_use_psql_variables(self):
        with patch.object(demo, "sql", return_value="INSERT 0 1") as sql:
            demo.add_risk("image", "reason with 'quote'", "fix it", 101)
        self.assertNotIn("reason with", sql.call_args.args[0])
        self.assertIn(("reason", "reason with 'quote'"), sql.call_args.kwargs["variables"])

    def test_failed_upgrade_is_not_silent_success(self):
        with patch.object(demo, "verify_namespace"), \
             patch.object(demo, "kubectl", side_effect=RuntimeError("Pod rejected")):
            with self.assertRaisesRegex(RuntimeError, "Pod rejected"):
                demo.upgrade("my-app-2", "safe-image")

    def test_cleanup_refuses_running_server(self):
        (self.directory / "server.lock").touch()
        with patch.object(demo, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "Stop"):
                demo.cleanup(True)
        run.assert_not_called()

    def test_database_only_cleanup_does_not_require_k3d(self):
        self.record()
        with patch.object(demo, "inspect_owned", return_value=None), \
             patch.object(demo, "clusters") as clusters:
            demo.cleanup()
        clusters.assert_not_called()

    def test_generated_config_keeps_authoring_file_unchanged(self):
        self.record()
        original = (demo.TUTORIAL / "server-config.yaml").read_text()
        configured = demo.config().read_text()
        self.assertIn("          - hrc-unit-check\n", configured)
        self.assertIn("kubeconfigPath: " + json.dumps(str(self.directory / "kubeconfig.yaml")), configured)
        self.assertEqual((demo.TUTORIAL / "server-config.yaml").read_text(), original)
        self.assertIn("autoInstallPlugins: false", configured)
        self.assertNotIn("\n  - ref:", configured)

    def test_derived_input_has_no_source_only_selectors(self):
        text = (demo.TUTORIAL / "server-config.yaml").read_text()
        derived = re.search(r"          - component: pod-containers\n(.*?)          - component: devops",
                            text, re.DOTALL)
        self.assertIsNotNone(derived)
        self.assertFalse(derived.group(1).strip())
        self.assertIn("MATCH (c:ContainerImage)-[:HAS_IMAGE]->(i:RiskyImage)", text)

    def test_runtime_identity_must_match(self):
        self.record()
        with patch.object(demo, "api", return_value={
            "instanceId": "different-server", "runtime": "computationGraph", "running": True,
        }):
            with self.assertRaisesRegex(RuntimeError, "Wrong runtime"):
                demo.check()

    def test_graph_waiting_dependency_blocks_readiness(self):
        self.record()
        responses = [
            {"instanceId": demo.INSTANCE, "runtime": "computationGraph", "running": True},
            [{"id": name, "status": "Running"} for name in ("k8s", "devops")],
            [{"id": name, "status": "Running"} for name in demo.QUERIES],
            [{"id": "high-risk-containers-dashboard", "status": "Running"}],
            {"graph": {"driverFailed": False}, "components": [
                {"id": "pod-containers", "waitingFor": ["k8s"]}]},
        ]
        with patch.object(demo, "api", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "failed or waiting"):
                demo.check()


if __name__ == "__main__":
    unittest.main()
