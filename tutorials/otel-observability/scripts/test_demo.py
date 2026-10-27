#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Fast safety and graph-contract checks; live verification is separate."""

import os
import socket
import tempfile
import unittest
from unittest.mock import patch

import demo


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(os.environ, {
            "DRASI_DEMO_DIR": self.directory.name,
            **demo.PORTS, "K8S_NAMESPACE": "otel-test",
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.engine = patch.object(demo, "engine", return_value="podman")
        self.engine.start()
        self.addCleanup(self.engine.stop)

    def test_unique_owned_names_and_settings(self):
        owner = demo.ownership(create=True)
        self.assertEqual(demo.ownership(), owner)
        self.assertTrue(owner["cluster"].startswith("otel-cg-"))
        os.environ["SERVER_PORT"] = "49999"
        with self.assertRaisesRegex(RuntimeError, "port/namespace"):
            demo.ownership()

    def test_otlp_listener_and_collector_port_must_match(self):
        os.environ["OTEL_GRPC_BIND"] = "0.0.0.0:55555"
        with self.assertRaisesRegex(ValueError, "OTEL_GRPC_PORT"):
            demo.environment()

    def test_reject_cached_wrong_checkout_variant(self):
        image = {"Config": {"Env": ["SERVICE_NAME=checkout", "SERVICE_VERSION=v41", "WORK_MS=400"]}}
        demo.verify_image(image, "checkout", "v41", 400)
        with self.assertRaisesRegex(RuntimeError, "incorrect"):
            demo.verify_image(image, "checkout", "v42", 920)

    def test_render_plain_kubernetes_fields_only(self):
        demo.environment()
        rendered = demo.render_config((demo.TUTORIAL / "server-config.yaml").read_text())
        self.assertNotIn("${KUBECONFIG_PATH}", rendered)
        self.assertNotIn("${K8S_NAMESPACE", rendered)
        self.assertIn('"otel-test"', rendered)
        self.assertIn("${OTEL_GRPC_BIND", rendered)
        self.assertIn("${SERVER_PORT", rendered)

    def test_port_probe_rejects_listener_but_allows_restart(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("0.0.0.0", 0))
            port = listener.getsockname()[1]
            listener.listen(1)
            os.environ["SERVER_PORT"] = str(port)
            with self.assertRaisesRegex(RuntimeError, "SERVER_PORT"):
                demo.check_ports("SERVER_PORT")
            with socket.create_connection(("127.0.0.1", port)) as client:
                connection, _ = listener.accept()
                connection.close()
                self.assertEqual(client.recv(1), b"")
        demo.check_ports("SERVER_PORT")

    def test_refuse_foreign_container(self):
        owner = demo.ownership(create=True)
        with patch.object(demo, "resource", return_value={"Config": {"Labels": {}}}):
            with self.assertRaisesRegex(RuntimeError, "unowned"):
                demo.check_resource(owner, "container", owner["container"])

    def test_accept_owned_volume(self):
        owner = demo.ownership(create=True)
        item = {"Labels": {demo.LABEL: owner["id"]}}
        with patch.object(demo, "resource", return_value=item):
            self.assertEqual(demo.check_resource(owner, "volume", owner["volume"]), item)

    def test_refuse_replaced_cluster(self):
        owner = demo.ownership(create=True)
        owner["nodeIds"] = ["original-id"]
        with patch.object(demo, "cluster_nodes", return_value=[{"name": "node"}]), \
                patch.object(demo, "node_ids", return_value=["replacement-id"]):
            with self.assertRaisesRegex(RuntimeError, "container identities"):
                demo.check_cluster(owner)

    def test_cleanup_refuses_running_server(self):
        (demo.state() / "server.lock").write_text("123\n")
        with self.assertRaisesRegex(RuntimeError, "foreground"):
            demo.cleanup()

    def test_cleanup_preserves_volume_by_default(self):
        owner = demo.ownership(create=True)
        with patch.object(demo, "check_cluster", return_value=[]), \
                patch.object(demo, "check_resource", return_value={"owned": True}), \
                patch.object(demo, "run") as run:
            demo.cleanup()
        run.assert_called_once_with(["podman", "rm", "-f", owner["container"]])

    def test_policy_update_requires_exactly_one_row(self):
        with patch.object(demo, "sql", return_value="UPDATE 0"):
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                demo.set_slo(100)

    def test_finite_control_values(self):
        for value in ("nan", "inf", "-1", "1; DROP TABLE policy"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                demo.number(value)
        self.assertEqual(demo.number("750"), 750)

    def test_shell_and_powershell_compatibility(self):
        self.assertEqual(demo.compatibility(["roll-checkout.ps1", "-Version", "v41"]), ["roll", "v41"])
        self.assertEqual(demo.compatibility(["cleanup.sh", "--volumes"]), ["cleanup", "--volumes"])
        self.assertEqual(demo.compatibility(["cleanup.ps1", "-RemoveVolumes"]), ["cleanup", "--volumes"])
        self.assertEqual(demo.compatibility(["download.sh"]), ["build"])
        self.assertEqual(demo.compatibility(["stop-heartbeat.ps1"]), ["heartbeat", "off"])

    def test_instance_runtime_identity_is_required(self):
        with patch.object(demo, "get_json", return_value={
            "success": True, "data": {"instanceId": "foreign", "runtime": "computationGraph", "running": True},
        }):
            with self.assertRaisesRegex(RuntimeError, "runtime identity"):
                demo.check()

    def test_query_results_are_current_api_array(self):
        with patch.object(demo, "get_json", return_value={"success": True, "data": [{"service": "checkout"}]}):
            self.assertEqual(demo.results("checkout-health"), [{"service": "checkout"}])

    def test_kubectl_always_scopes_namespace_and_kubeconfig(self):
        demo.environment()
        demo.ownership(create=True)
        with patch.object(demo, "check_cluster", return_value=[{"name": "owned"}]), \
                patch.object(demo, "run") as run:
            demo.kubectl("get", "pods")
        command = run.call_args.args[0]
        self.assertEqual(command[1:5], [
            "--kubeconfig", str(demo.state() / "kubeconfig.yaml"), "--namespace", "otel-test",
        ])

    def test_explicit_shared_query_edges(self):
        config = (demo.TUTORIAL / "server-config.yaml").read_text()
        self.assertEqual(config.count("label: ServiceHealth"), 2)  # result and policy join key
        self.assertEqual(config.count("- current-health"), 3)  # two consumers and dashboard
        self.assertEqual(config.count("- checkout-heartbeat"), 2)  # timer and dashboard
        self.assertIn("autoInstallPlugins: false", config)
        self.assertNotIn("ref: source/", config)
        requests = (demo.TUTORIAL / "requests.http").read_text()
        self.assertNotIn("{{baseUrl}}/api/v1/queries", requests)


if __name__ == "__main__":
    unittest.main()
