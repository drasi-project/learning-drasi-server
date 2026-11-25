#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
"""Checks for the optional telemetry page's helper and backend settings.

They mock Podman and never start Server or any container.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import yaml

import demo
import telemetry


ASSETS = demo.TUTORIAL / "telemetry"
STEP_3 = demo.TUTORIAL / "configs/getting-started-step-3.yaml"
DEFAULT_PORTS = {"OTLP_PORT": "4318", "JAEGER_PORT": "16686",
                 "PROMETHEUS_PORT": "9090", "GRAFANA_PORT": "3000"}
REAL_FREE_PORT = demo.free_port
REAL_LISTENING = telemetry.listening


class TelemetryAssetTests(unittest.TestCase):
    def test_dashboard_uses_only_provisioned_datasources(self):
        sources = yaml.safe_load(
            (ASSETS / "grafana/provisioning/datasources/getting-started.yaml").read_text())
        defined = {source["uid"]: source["url"] for source in sources["datasources"]}
        self.assertEqual(defined, {"drasi-prometheus": "http://prometheus:9090",
                                   "drasi-jaeger": "http://jaeger:16686"})
        dashboard = json.loads(
            (ASSETS / "grafana/dashboards/getting-started-telemetry.json").read_text())
        self.assertEqual(dashboard["uid"], "drasi-getting-started")
        used = {panel["datasource"]["uid"] for panel in dashboard["panels"]
                if panel.get("datasource")}
        self.assertTrue(used)
        self.assertLessEqual(used, set(defined))

    def test_telemetry_folder_is_safe_for_the_docs_site(self):
        names = [path.name for path in ASSETS.rglob("*")]
        self.assertTrue(names)
        self.assertNotIn("README.md", names)
        self.assertEqual([name for name in names if name.endswith(".html")], [])

    def test_main_tutorial_configs_have_no_telemetry(self):
        paths = [*sorted((demo.TUTORIAL / "configs").glob("*.yaml")),
                 demo.TUTORIAL / "server-config.yaml"]
        for path in paths:
            self.assertNotIn("telemetry", yaml.safe_load(path.read_text()), path)


def free_ports(count):
    sockets = [socket.socket() for _ in range(count)]
    try:
        for probe in sockets:
            probe.bind(("127.0.0.1", 0))
        return [str(probe.getsockname()[1]) for probe in sockets]
    finally:
        for probe in sockets:
            probe.close()


class TelemetryHelperTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state = Path(self.directory.name)
        self.config = self.state / "getting-started.yaml"
        self.calls = []
        self.bindings = {}
        for patcher in (
            patch.dict(os.environ, {
                "DRASI_RUN_ID": "getting-started-unit", "POSTGRES_PORT": "5532",
                "SERVER_PORT": "8180", "SSE_PORT": "8181", "HTTP_PORT": "8182",
                **DEFAULT_PORTS,
            }),
            patch.object(demo, "state", return_value=self.state),
            patch.object(demo, "run", side_effect=self.podman),
            patch.object(demo, "free_port"),
            patch.object(telemetry, "image_present", return_value=True),
            patch.object(telemetry, "wait_ready"),
            patch.object(telemetry, "wait_closed"),
            patch.object(telemetry, "listening", return_value=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.directory.cleanup)
        telemetry.environment()

    def podman(self, argv, *, stdin=None, capture=False):
        argv = list(map(str, argv))
        self.calls.append(argv)
        if argv[1:3] == ["container", "inspect"]:
            return json.dumps([{"HostConfig": {"PortBindings": self.bindings[argv[3]]}}])
        return ""

    def created(self):
        return [call for call in self.calls
                if call[:2] == ["podman", "run"] or call[:3] == ["podman", "network", "create"]]

    def removed(self):
        return [call for call in self.calls
                if call[:2] == ["podman", "rm"] or call[:3] == ["podman", "network", "rm"]]

    def published(self):
        return [call[index + 1] for call in self.calls if call[:2] == ["podman", "run"]
                for index, value in enumerate(call) if value == "-p"]

    def up(self, owned=False):
        output = io.StringIO()
        with patch.object(demo, "owned", return_value=owned), patch.object(
            telemetry, "owned_network", return_value=owned
        ), contextlib.redirect_stdout(output):
            telemetry.up()
        return output.getvalue()

    def test_ports_must_be_unprivileged_and_distinct_across_all_eight(self):
        with patch.dict(os.environ, {"GRAFANA_PORT": "8180"}):
            with self.assertRaisesRegex(ValueError, "distinct"):
                telemetry.environment()
        with patch.dict(os.environ, {"PROMETHEUS_PORT": "5532"}):
            with self.assertRaisesRegex(ValueError, "distinct"):
                telemetry.environment()
        with patch.dict(os.environ, {"OTLP_PORT": "80"}):
            with self.assertRaisesRegex(ValueError, "OTLP_PORT.*unprivileged TCP port"):
                telemetry.environment()

    def test_new_run_gets_step_3_config_with_telemetry_block(self):
        path = telemetry.prepare_config()
        self.assertEqual(path, self.config)
        config = yaml.safe_load(path.read_text())
        step3 = yaml.safe_load(demo.working_config(STEP_3.read_text()))
        self.assertEqual({key: value for key, value in config.items() if key != "telemetry"}, step3)
        self.assertEqual(config["telemetry"], {
            "profile": "debug", "inspection": {"enabled": True},
            "tracing": {"endpoint": "http://127.0.0.1:4318/v1/traces",
                        "protocol": "http/protobuf",
                        "serviceName": "drasi-getting-started", "sampleRatio": 1.0},
            "metrics": {"backend": "prometheus", "processMetrics": True,
                        "prometheus": {"path": "/metrics"}},
        })

    def test_existing_config_with_telemetry_is_kept(self):
        content = "instances: []\ntelemetry:\n  profile: basic\n"
        self.config.write_text(content)
        telemetry.prepare_config()
        self.assertEqual(self.config.read_text(), content)

    def test_existing_config_without_telemetry_is_refused(self):
        content = "instances: []\n# telemetry: not here\n"
        self.config.write_text(content)
        with self.assertRaisesRegex(RuntimeError, "DRASI_RUN_ID"):
            telemetry.prepare_config()
        self.assertEqual(self.config.read_text(), content)

    def test_up_refuses_unowned_resources_before_creating_anything(self):
        def owned(kind, name):
            if name.endswith("-grafana"):
                raise RuntimeError(f"Refusing unowned {kind}: {name}")
            return False

        with patch.object(demo, "owned", side_effect=owned), patch.object(
            telemetry, "owned_network", return_value=False
        ):
            with self.assertRaisesRegex(RuntimeError, "unowned"):
                telemetry.up()
        self.assertEqual(self.created(), [])
        self.assertFalse(self.config.exists())

    def test_up_refuses_occupied_port_before_creating_anything(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            busy = str(listener.getsockname()[1])
            otlp, jaeger, prometheus = free_ports(3)
            with patch.dict(os.environ, {
                "OTLP_PORT": otlp, "JAEGER_PORT": jaeger,
                "PROMETHEUS_PORT": prometheus, "GRAFANA_PORT": busy,
            }), patch.object(demo, "free_port", new=REAL_FREE_PORT), patch.object(
                telemetry, "listening", new=REAL_LISTENING):
                with self.assertRaisesRegex(RuntimeError, f"GRAFANA_PORT={busy}"):
                    self.up()
        self.assertEqual(self.created(), [])
        self.assertFalse(self.config.exists())

    def test_up_refuses_port_used_on_all_interfaces(self):
        with socket.socket() as listener:
            listener.bind(("0.0.0.0", 0))
            listener.listen(1)
            busy = str(listener.getsockname()[1])
            otlp, jaeger, prometheus = free_ports(3)
            with patch.dict(os.environ, {
                "OTLP_PORT": otlp, "JAEGER_PORT": jaeger,
                "PROMETHEUS_PORT": prometheus, "GRAFANA_PORT": busy,
            }), patch.object(demo, "free_port", new=REAL_FREE_PORT), patch.object(
                telemetry, "listening", new=REAL_LISTENING):
                with self.assertRaisesRegex(RuntimeError, f"GRAFANA_PORT={busy}"):
                    self.up()
        self.assertEqual(self.created(), [])
        self.assertFalse(self.config.exists())

    def test_existing_telemetry_config_with_another_otlp_port_is_refused(self):
        content = "telemetry:\n  tracing:\n    endpoint: http://127.0.0.1:4318/v1/traces\n"
        self.config.write_text(content)
        with patch.dict(os.environ, {"OTLP_PORT": "14318"}):
            with self.assertRaisesRegex(RuntimeError, "OTLP_PORT=14318"):
                telemetry.prepare_config()
        self.assertEqual(self.config.read_text(), content)

    def test_published_ports_are_loopback_only(self):
        self.up()
        published = self.published()
        self.assertEqual(len(published), 4)
        for value in published:
            self.assertTrue(value.startswith("127.0.0.1:"), value)

    def test_up_twice_reuses_owned_containers(self):
        content = "instances: []\ntelemetry:\n  profile: debug\n"
        self.config.write_text(content)
        self.bindings = {
            telemetry.container("jaeger"): {
                "4318/tcp": [{"HostIp": "127.0.0.1", "HostPort": "4318"}],
                "16686/tcp": [{"HostIp": "127.0.0.1", "HostPort": "16686"}]},
            telemetry.container("prometheus"): {
                "9090/tcp": [{"HostIp": "127.0.0.1", "HostPort": "9090"}]},
            telemetry.container("grafana"): {
                "3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3000"}]},
        }
        self.up(owned=True)
        self.assertEqual(self.created(), [])
        self.assertEqual(
            sorted(call[2] for call in self.calls if call[:2] == ["podman", "start"]),
            sorted(telemetry.container(service) for service in ("jaeger", "prometheus", "grafana")),
        )
        self.assertEqual(self.config.read_text(), content)

    def test_up_refuses_owned_container_with_different_ports(self):
        self.config.write_text("telemetry:\n  profile: debug\n")
        self.bindings = {telemetry.container("jaeger"): {
            "4318/tcp": [{"HostIp": "127.0.0.1", "HostPort": "14318"}],
            "16686/tcp": [{"HostIp": "127.0.0.1", "HostPort": "16686"}]}}
        with self.assertRaisesRegex(RuntimeError, "different ports"):
            self.up(owned=True)
        self.assertFalse([call for call in self.calls if call[:2] == ["podman", "start"]])

    def test_overridden_ports_flow_into_block_target_and_links(self):
        with patch.dict(os.environ, {"OTLP_PORT": "14318", "JAEGER_PORT": "16687",
                                     "PROMETHEUS_PORT": "19090", "GRAFANA_PORT": "13000"}):
            output = self.up()
        config = yaml.safe_load(self.config.read_text())
        self.assertEqual(config["telemetry"]["tracing"]["endpoint"],
                         "http://127.0.0.1:14318/v1/traces")
        targets = json.loads((self.state / "telemetry/targets/drasi-server.json").read_text())
        self.assertEqual(targets, [{"targets": ["host.containers.internal:8180"]}])
        self.assertEqual(sorted(self.published()), sorted([
            "127.0.0.1:14318:4318", "127.0.0.1:16687:16686",
            "127.0.0.1:19090:9090", "127.0.0.1:13000:3000",
        ]))
        self.assertIn("http://127.0.0.1:13000/d/drasi-getting-started", output)
        self.assertIn("http://127.0.0.1:16687/search?service=drasi-getting-started", output)
        self.assertIn("http://127.0.0.1:19090/targets", output)

    def test_down_checks_every_owner_before_removing(self):
        with patch.object(demo, "owned", side_effect=[
            True, RuntimeError("Refusing unowned container: x"), True,
        ]), patch.object(telemetry, "owned_network", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "unowned"):
                telemetry.down()
        self.assertEqual(self.removed(), [])

    def test_down_removes_only_owned_resources_and_keeps_config(self):
        self.config.write_text("telemetry:\n  profile: debug\n")
        with patch.object(demo, "owned", side_effect=lambda kind, name: name.endswith("-jaeger")), \
                patch.object(telemetry, "owned_network", return_value=True), \
                contextlib.redirect_stdout(io.StringIO()):
            telemetry.down()
        self.assertEqual(self.removed(), [
            ["podman", "rm", "--force", "--volumes", "--time", "5", telemetry.container("jaeger")],
            ["podman", "network", "rm", telemetry.network()],
        ])
        telemetry.wait_closed.assert_called_once_with(["OTLP_PORT", "JAEGER_PORT"])
        self.assertEqual(self.config.read_text(), "telemetry:\n  profile: debug\n")

    def test_down_with_nothing_created_is_a_no_op(self):
        self.config.write_text("telemetry:\n  profile: debug\n")
        with patch.object(demo, "owned", return_value=False), patch.object(
            telemetry, "owned_network", return_value=False
        ), contextlib.redirect_stdout(io.StringIO()):
            telemetry.down()
        self.assertEqual(self.removed(), [])
        telemetry.wait_closed.assert_not_called()
        self.assertEqual(self.config.read_text(), "telemetry:\n  profile: debug\n")


if __name__ == "__main__":
    unittest.main()
