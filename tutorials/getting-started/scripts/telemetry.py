#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Owned Jaeger, Prometheus and Grafana for the optional Getting Started telemetry page."""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import demo


ASSETS = demo.TUTORIAL / "telemetry"
STEP_3 = demo.TUTORIAL / "configs/getting-started-step-3.yaml"
IMAGES = {
    "jaeger": "cr.jaegertracing.io/jaegertracing/jaeger:2.22.0",
    "prometheus": "docker.io/prom/prometheus:v3.16.0",
    "grafana": "docker.io/grafana/grafana:13.3.1",
}
PORT_DEFAULTS = {"OTLP_PORT": "4318", "JAEGER_PORT": "16686",
                 "PROMETHEUS_PORT": "9090", "GRAFANA_PORT": "3000"}
# Container port -> setting that selects its 127.0.0.1 host port.
SERVICE_PORTS = {
    "jaeger": {"4318": "OTLP_PORT", "16686": "JAEGER_PORT"},
    "prometheus": {"9090": "PROMETHEUS_PORT"},
    "grafana": {"3000": "GRAFANA_PORT"},
}
SERVICES = tuple(SERVICE_PORTS)
TUTORIAL_PORTS = ("POSTGRES_PORT", "SERVER_PORT", "SSE_PORT", "HTTP_PORT")
SERVICE_NAME = "drasi-getting-started"
DASHBOARD_UID = "drasi-getting-started"
DASHBOARD_FILE = "getting-started-telemetry.json"
TELEMETRY_BLOCK = """\
# Added by scripts/telemetry.py. Server reads this block only at startup.
telemetry:
  profile: debug
  inspection:
    enabled: true
  tracing:
    endpoint: http://127.0.0.1:{otlp_port}/v1/traces
    protocol: http/protobuf
    serviceName: {service_name}
    sampleRatio: 1.0
  metrics:
    backend: prometheus
    processMetrics: true
    prometheus:
      path: /metrics
"""


def environment():
    demo.environment()
    for key, value in PORT_DEFAULTS.items():
        os.environ.setdefault(key, value)
    for key in PORT_DEFAULTS:
        if not 1024 <= int(os.environ[key]) <= 65535:
            raise ValueError(f"{key} must be an unprivileged TCP port")
    keys = (*TUTORIAL_PORTS, *PORT_DEFAULTS)
    if len({int(os.environ[key]) for key in keys}) != len(keys):
        raise ValueError("Tutorial and telemetry ports must be distinct: " +
                         ", ".join(f"{key}={os.environ[key]}" for key in keys))


def container(service):
    return f"{os.environ['DRASI_RUN_ID']}-{service}"


def network():
    return f"{os.environ['DRASI_RUN_ID']}-telemetry"


def targets():
    return demo.state() / "telemetry" / "targets"


def telemetry_block():
    return TELEMETRY_BLOCK.format(otlp_port=os.environ["OTLP_PORT"], service_name=SERVICE_NAME)


def prepare_config():
    path = demo.state() / "getting-started.yaml"
    if path.exists():
        if re.search(r"^telemetry:", path.read_text(), re.MULTILINE):
            return path
        raise RuntimeError(
            f"{path} already exists without telemetry, and Server reads telemetry only at "
            "startup. Configure telemetry before Server's first start: choose a new "
            "DRASI_RUN_ID and free ports in .env, then run this command again.")
    demo.state().mkdir(parents=True, exist_ok=True)
    content = demo.working_config(STEP_3.read_text()).rstrip("\n")
    path.write_text(f"{content}\n\n{telemetry_block()}")
    return path


def owned_network(name):
    listing = demo.run(["podman", "network", "ls", "--format", "{{.Name}}"], capture=True)
    if name not in listing.splitlines():
        return False
    record = json.loads(demo.run(["podman", "network", "inspect", name], capture=True))[0]
    labels = record.get("labels") or record.get("Labels") or {}
    if labels.get(demo.LABEL) != demo.owner():
        raise RuntimeError(f"Refusing unowned network: {name}")
    return True


def image_present(image):
    code = subprocess.run(["podman", "image", "exists", image]).returncode
    if code not in (0, 1):
        raise RuntimeError(f"Podman image inspection failed: {code}")
    return code == 0


def expected_bindings(service):
    return {f"{port}/tcp": [{"HostIp": "127.0.0.1", "HostPort": os.environ[key]}]
            for port, key in SERVICE_PORTS[service].items()}


def run_arguments(service):
    owner = f"{demo.LABEL}={demo.owner()}"
    argv = ["podman", "run", "-d", "--name", container(service), "--label", owner,
            "--network", network(), "--network-alias", service]
    for port, key in SERVICE_PORTS[service].items():
        argv += ["-p", f"127.0.0.1:{os.environ[key]}:{port}"]
    if service == "prometheus":
        argv += ["-v", f"{ASSETS / 'prometheus.yml'}:/etc/prometheus/prometheus.yml:ro",
                 "-v", f"{targets()}:/etc/prometheus/targets:ro", IMAGES[service],
                 "--config.file=/etc/prometheus/prometheus.yml",
                 "--storage.tsdb.path=/prometheus", "--storage.tsdb.retention.time=1d"]
    elif service == "grafana":
        # Anonymous read-only Viewer; no admin user, login form or basic auth.
        settings = {
            "GF_SERVER_ROOT_URL": f"http://127.0.0.1:{os.environ['GRAFANA_PORT']}/",
            "GF_SECURITY_DISABLE_INITIAL_ADMIN_CREATION": "true",
            "GF_AUTH_ANONYMOUS_ENABLED": "true", "GF_AUTH_ANONYMOUS_ORG_ROLE": "Viewer",
            "GF_AUTH_DISABLE_LOGIN_FORM": "true", "GF_AUTH_BASIC_ENABLED": "false",
            "GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH": f"/etc/grafana/dashboards/{DASHBOARD_FILE}",
            "GF_ANALYTICS_REPORTING_ENABLED": "false", "GF_ANALYTICS_CHECK_FOR_UPDATES": "false",
            "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES": "false",
            "GF_NEWS_NEWS_FEED_ENABLED": "false", "GF_PLUGINS_PREINSTALL_DISABLED": "true",
        }
        for name, value in settings.items():
            argv += ["-e", f"{name}={value}"]
        grafana = ASSETS / "grafana"
        argv += ["-v", f"{grafana / 'provisioning/datasources'}:/etc/grafana/provisioning/datasources:ro",
                 "-v", f"{grafana / 'provisioning/dashboards'}:/etc/grafana/provisioning/dashboards:ro",
                 "-v", f"{grafana / 'dashboards'}:/etc/grafana/dashboards:ro", IMAGES[service]]
    else:
        argv.append(IMAGES[service])
    return argv


def links():
    return [
        f"Grafana dashboard: http://127.0.0.1:{os.environ['GRAFANA_PORT']}/d/{DASHBOARD_UID}",
        f"Jaeger traces:     http://127.0.0.1:{os.environ['JAEGER_PORT']}/search?service={SERVICE_NAME}",
        f"Prometheus:        http://127.0.0.1:{os.environ['PROMETHEUS_PORT']}/targets",
    ]


def responds(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_ready(timeout=90):
    checks = {
        "jaeger": f"http://127.0.0.1:{os.environ['JAEGER_PORT']}/api/v3/services",
        "prometheus": f"http://127.0.0.1:{os.environ['PROMETHEUS_PORT']}/-/ready",
        "grafana": f"http://127.0.0.1:{os.environ['GRAFANA_PORT']}/api/health",
    }
    deadline = time.monotonic() + timeout
    for service, url in checks.items():
        while not responds(url):
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{service} is not ready; inspect podman logs {container(service)}")
            time.sleep(1)


def listening(port):
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", int(port))) == 0


def wait_closed(keys, timeout=15):
    deadline = time.monotonic() + timeout
    while busy := [f"{key}={os.environ[key]}" for key in keys if listening(os.environ[key])]:
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Ports still open after removing the containers: {', '.join(busy)}")
        time.sleep(1)


def up():
    try:
        demo.run(["podman", "info"], capture=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Podman is not working (on macOS: podman machine start)") from error
    existing = {service: demo.owned("container", container(service)) for service in SERVICES}
    has_network = owned_network(network())
    config = prepare_config()
    for service in SERVICES:
        if existing[service]:
            record = json.loads(demo.run(["podman", "container", "inspect", container(service)],
                                         capture=True))[0]
            if record["HostConfig"]["PortBindings"] != expected_bindings(service):
                raise RuntimeError(f"Existing owned {container(service)} uses different ports; "
                                   "it was not changed. Run telemetry.py down first.")
    missing = [service for service in SERVICES if not existing[service]]
    for service in missing:
        for key in SERVICE_PORTS[service].values():
            try:
                demo.free_port(os.environ[key])
            except OSError as error:
                raise RuntimeError(f"{key}={os.environ[key]} is already in use on 127.0.0.1; "
                                   "set a free port in .env") from error
    for service in missing:
        if not image_present(IMAGES[service]):
            demo.run(["podman", "pull", IMAGES[service]])
    if not has_network:
        demo.run(["podman", "network", "create", "--label",
                  f"{demo.LABEL}={demo.owner()}", network()], capture=True)
    targets().mkdir(parents=True, exist_ok=True)
    (targets() / "drasi-server.json").write_text(json.dumps(
        [{"targets": [f"host.containers.internal:{os.environ['SERVER_PORT']}"]}]) + "\n")
    for service in SERVICES:
        if existing[service]:
            demo.run(["podman", "start", container(service)], capture=True)
        else:
            demo.run(run_arguments(service), capture=True)
    wait_ready()
    print(f"Telemetry backends are ready. Server configuration: {config}", *links(),
          "Next: return to Step 3 and run python3 scripts/demo.py start", sep="\n")


def down():
    existing = {service: demo.owned("container", container(service)) for service in SERVICES}
    has_network = owned_network(network())
    closed = []
    for service in reversed(SERVICES):
        if existing[service]:
            demo.run(["podman", "rm", "--force", "--volumes", "--time", "5", container(service)],
                     capture=True)
            closed += SERVICE_PORTS[service].values()
    if has_network:
        demo.run(["podman", "network", "rm", network()], capture=True)
    if closed:
        wait_closed(closed)
    print("Owned telemetry backends removed." if closed or has_network
          else "No owned telemetry backends to remove.")
    print("Server, the database and the working configuration were not changed.")


def status():
    found = False
    for service in SERVICES:
        name = container(service)
        if demo.owned("container", name):
            record = json.loads(demo.run(["podman", "container", "inspect", name], capture=True))[0]
            print(f"{name}: {record['State']['Status']}")
            found = True
        else:
            print(f"{name}: not created")
    if found:
        print(*links(), sep="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for name in ("up", "down", "status"):
        commands.add_parser(name)
    args = parser.parse_args()
    try:
        environment()
        {"up": up, "down": down, "status": status}[args.action]()
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, KeyError,
            subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
