#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
"""Build and run Curbside Pickup against the matching local Server/Core graph."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

TUTORIAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TUTORIAL.parents[1] / "scripts"))
import local_build

INSTANCE = "curbside-pickup-server"
PLUGINS = (
    "drasi-source-postgres", "drasi-bootstrap-postgres",
    "drasi-source-mysql", "drasi-bootstrap-mysql", "drasi-reaction-dashboard",
)
PANELS = (
    "orders-preparing", "orders-ready", "vehicles-parking",
    "vehicles-curbside", "delivery", "delay",
)
QUERIES = (*PANELS, "pickup-state")
IMAGES = ("docker.io/library/postgres:15-alpine", "docker.io/library/mysql:8.0")


def state_dir():
    return Path(os.environ.get("DRASI_DEMO_DIR", TUTORIAL / ".runtime")).resolve()


def load_environment():
    path = TUTORIAL / ".env"
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                raise ValueError(f"{path}:{number}: expected NAME=value")
            os.environ.setdefault(key, value.strip().strip("'\""))
    os.environ["DRASI_TUTORIAL_DIR"] = str(TUTORIAL)
    os.environ["DRASI_DEMO_DIR"] = str(state_dir())
    os.environ.setdefault("COMPOSE_PROJECT_NAME", "curbside-pickup-cg")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,50}", os.environ["COMPOSE_PROJECT_NAME"]):
        raise ValueError("COMPOSE_PROJECT_NAME must be a lowercase project name")
    for name, default in (("POSTGRES", "5742"), ("MYSQL", "3309")):
        os.environ.setdefault(name + "_PORT", os.environ.get(name + "_HOST_PORT", default))
        os.environ.setdefault(name + "_HOST_PORT", os.environ[name + "_PORT"])
        if os.environ[name + "_PORT"] != os.environ[name + "_HOST_PORT"]:
            raise ValueError(f"{name}_PORT and {name}_HOST_PORT must match")
        os.environ.setdefault(name + "_HOST", "127.0.0.1")
        if os.environ[name + "_HOST"] not in ("localhost", "127.0.0.1"):
            raise ValueError(f"{name}_HOST must refer to this demo's local database")
    for name, port in (("SERVER", "8480"), ("DASHBOARD", "3000"), ("WEBUI", "3001")):
        os.environ.setdefault(name + "_HOST", "127.0.0.1")
        os.environ.setdefault(name + "_PORT", port)
    for name, expected in (
        ("POSTGRES_DATABASE", "RetailOperations"), ("MYSQL_DATABASE", "PhysicalOperations"),
        ("POSTGRES_USER", "drasi_user"), ("MYSQL_USER", "drasi_user"),
        ("POSTGRES_PASSWORD", "drasi_password"), ("MYSQL_PASSWORD", "drasi_password"),
    ):
        if os.environ.get(name, expected) != expected:
            raise ValueError(f"{name} must match the supplied local demo seed configuration")
    ports = [int(os.environ[name + "_PORT"]) for name in
             ("POSTGRES", "MYSQL", "SERVER", "DASHBOARD", "WEBUI")]
    if len(set(ports)) != len(ports) or any(not 1 <= port <= 65535 for port in ports):
        raise ValueError("All five demo ports must be distinct and between 1 and 65535")


def run(argv, *, capture=False, stdin=None, cwd=TUTORIAL):
    print("+", " ".join(map(str, argv)), flush=True)
    return subprocess.run(
        list(map(str, argv)), cwd=cwd, check=True, text=True, input=stdin,
        stdout=subprocess.PIPE if capture else None,
    ).stdout


def engine():
    if not shutil.which("podman"):
        raise RuntimeError("Podman is required; start its machine/service before running the demo")
    return "podman"


def compose(*arguments):
    run([engine(), "compose", "-p", os.environ["COMPOSE_PROJECT_NAME"],
         "-f", TUTORIAL / "database/docker-compose.yml", *arguments])


def container(database):
    return os.environ["COMPOSE_PROJECT_NAME"] + "-" + database


def check_ownership():
    project = os.environ["COMPOSE_PROJECT_NAME"]
    resources = {
        "container": [container("postgres"), container("mysql")],
        "volume": [project + "_curbside_postgres_data", project + "_curbside_mysql_data"],
        "network": [project + "_default"],
    }
    for kind, expected in resources.items():
        listing = (["ps", "-a"] if kind == "container" else [kind, "ls"])
        names = run([engine(), *listing, "--format", "{{.Names}}" if kind == "container"
                     else "{{.Name}}"], capture=True).splitlines()
        for name in expected:
            if name not in names:
                continue
            info = json.loads(run([engine(), kind, "inspect", name], capture=True))[0]
            labels = (info["Config"].get("Labels") if kind == "container"
                      else info.get("Labels", info.get("labels"))) or {}
            if (labels.get("io.drasi.curbside-pickup.path") != str(TUTORIAL)
                    or labels.get("io.drasi.curbside-pickup.run") != str(state_dir())):
                raise RuntimeError(f"Refusing to reuse or remove unowned {kind}: {name}")


def postgres(statement):
    return run([engine(), "exec", "-i", "-e", "PGPASSWORD=postgres_admin",
                container("postgres"), "psql", "-h", "127.0.0.1",
                "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "RetailOperations",
                "-At"], capture=True, stdin=statement).strip()


def mysql(statement):
    # Pass the credential through the subprocess environment, not logged argv.
    environment = dict(os.environ, MYSQL_PWD=os.environ.get("MYSQL_ROOT_PASSWORD", "root_admin"))
    result = subprocess.run(
        [engine(), "exec", "-i", "-e", "MYSQL_PWD", container("mysql"),
         "mysql", "-h", "127.0.0.1", "-uroot", "-N", "-B", "PhysicalOperations"],
        check=True, text=True, input=statement, stdout=subprocess.PIPE, env=environment,
    )
    return result.stdout.strip()


def wait_for(probe, description, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return probe()
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                subprocess.CalledProcessError, RuntimeError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{description} timed out: {error}") from error
            time.sleep(0.5)


def database():
    check_ownership()
    for image in IMAGES:
        result = subprocess.run([engine(), "image", "inspect", image],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            run([engine(), "pull", image])
    compose("up", "-d")
    wait_for(lambda: postgres("SELECT 1;"), "PostgreSQL startup")
    wait_for(lambda: mysql("SELECT 1;"), "MySQL startup")
    for name, query, sql in (
        ("postgres", "SELECT count(*) FROM pg_tables WHERE schemaname='public';", postgres),
        ("mysql", "SELECT count(*) FROM information_schema.tables "
                  "WHERE table_schema='PhysicalOperations';", mysql),
    ):
        count = sql(query)
        if count == "0":
            print(sql((TUTORIAL / "database" / (name + "-init.sql")).read_text()))
        elif count != "1":
            raise RuntimeError(f"Unexpected existing {name} schema; no data was reset")
    postgres("SELECT id, customer_name, driver_name, plate, status FROM orders LIMIT 1;")
    mysql("SELECT plate, driver_name, customer_name, make, model, color, location FROM vehicles LIMIT 1;")
    if postgres("SELECT count(*) FROM pg_publication WHERE pubname='drasi_curbside_pub';") != "1":
        raise RuntimeError("Required PostgreSQL CDC publication is missing")
    print("Both databases ready. Existing orders and vehicle locations were preserved.")


def reset():
    check_ownership()
    print(postgres("UPDATE orders SET status='preparing';"))
    print(mysql("UPDATE vehicles SET location='Parking';"))
    print("Reset complete: Preparing/Parking list the rows; Ready/Curbside/Matched/Delayed clear.")


def cleanup(volumes=False):
    if (state_dir() / "server.lock").exists():
        raise RuntimeError("Stop this demo with Ctrl+C before cleanup; server.lock is present")
    check_ownership()
    compose("down", *(["--volumes"] if volumes else []))
    print("Owned databases removed." if volumes else "Owned containers removed; database volumes preserved.")


def get_json(url):
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


def api_url():
    return f"http://127.0.0.1:{os.environ['SERVER_PORT']}/api/v1/instances/{INSTANCE}"


def check():
    proof = get_json(api_url() + "/runtime")
    if proof.get("success") is not True or proof.get("data") != {
        "instanceId": INSTANCE, "runtime": "computationGraph", "running": True,
    }:
        raise RuntimeError(f"Expected this instance's running ComputationGraph, got {proof}")
    for kind, expected in (
        ("sources", {"retail-ops", "physical-ops"}),
        ("queries", set(QUERIES)), ("reactions", {"curbside-dashboard"}),
    ):
        response = get_json(api_url() + "/" + kind)
        if response.get("success") is not True:
            raise RuntimeError(f"Cannot inspect {kind}: {response}")
        components = response["data"]
        identities = {component["id"] for component in components}
        allowed = expected | ({"__component_graph__"} if kind == "sources" else set())
        if not expected <= identities or not identities <= allowed or any(
                component["status"].lower() != "running" for component in components):
            raise RuntimeError(f"Unexpected or stopped {kind}: {components}")
    dashboards = get_json(f"http://127.0.0.1:{os.environ['DASHBOARD_PORT']}/api/dashboards")
    if not any(item["id"] == "curbside-pickup" for item in dashboards):
        raise RuntimeError("The Curbside Pickup dashboard is not available")
    console = get_json(f"http://127.0.0.1:{os.environ['WEBUI_PORT']}/api/state")
    if console.get("connecting") or console.get("error") or not {
            "orders", "vehicles", "log"} <= console.keys():
        raise RuntimeError(f"Operations console is not connected to both databases: {console}")
    return proof


def start():
    binary, plugins = local_build.verified_build(state_dir(), PLUGINS)
    if not shutil.which("node"):
        raise RuntimeError("Node.js 18+ is required for the operations console")
    # A real import check distinguishes missing dependencies from other startup failures.
    run(["node", "--input-type=module", "-e",
         "await Promise.all(['express','dotenv','pg','mysql2/promise'].map(x => import(x)))"],
        cwd=TUTORIAL / "webui")
    state = state_dir()
    state.mkdir(parents=True, exist_ok=True)
    lock = state / "server.lock"
    processes = []
    with lock.open("x") as stream:
        stream.write(str(os.getpid()) + "\n")
    previous = signal.getsignal(signal.SIGTERM)
    try:
        for name in ("SERVER", "DASHBOARD", "WEBUI"):
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind((os.environ[name + "_HOST"], int(os.environ[name + "_PORT"])))
                probe.listen(1)
        config = TUTORIAL / "server-config.yaml"
        environment = dict(os.environ, DRASI_PLUGINS_DIR=str(plugins))
        processes.append(subprocess.Popen(
            [str(binary), "--config", str(config), "--plugins-dir", str(plugins),
             "--skip-verification"], cwd=state, env=environment))
        processes.append(subprocess.Popen(
            ["node", "src/server.js"], cwd=TUTORIAL / "webui", env=environment))

        def interrupted(*_):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, interrupted)

        def ready():
            if any(process.poll() is not None for process in processes):
                raise ChildProcessError("Server or operations console exited during startup")
            return check()

        proof = wait_for(ready, "Curbside Pickup readiness")
        (state / "runtime.json").write_text(json.dumps(proof, indent=2) + "\n")
        print(f"\nCurbside Pickup READY: ComputationGraph; two sources, seven queries, six panels."
              f"\nDashboard: http://localhost:{os.environ['DASHBOARD_PORT']}"
              f"\nOperations console: http://localhost:{os.environ['WEBUI_PORT']}"
              "\nCtrl+C stops both processes and preserves database data.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("Server or operations console exited; stopping the other process")
    finally:
        signal.signal(signal.SIGTERM, previous)
        forced = False
        try:
            for process in reversed(processes):
                if process.poll() is None:
                    process.send_signal(signal.SIGINT if os.name != "nt" else signal.SIGTERM)
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                        forced = True
        finally:
            lock.unlink()
        if forced:
            raise RuntimeError("A demo process required forced shutdown after 30 seconds")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("build", "verify-build", "database", "start", "start-demo", "check", "reset"):
        commands.add_parser(action)
    commands.add_parser("cleanup").add_argument("--volumes", action="store_true")
    args = parser.parse_args()
    try:
        load_environment()
        if args.action == "build":
            if (state_dir() / "server.lock").exists():
                raise RuntimeError("Stop this demo before rebuilding")
            local_build.build(state_dir(), PLUGINS)
        elif args.action == "verify-build":
            local_build.verified_build(state_dir(), PLUGINS)
        elif args.action == "database":
            database()
        elif args.action == "start-demo":
            local_build.verified_build(state_dir(), PLUGINS)
            database()
            start()
        elif args.action == "start":
            start()
        elif args.action == "check":
            print(json.dumps(check(), indent=2))
        elif args.action == "reset":
            reset()
        elif args.action == "cleanup":
            cleanup(args.volumes)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
