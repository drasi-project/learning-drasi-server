#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Run the existing sibling Server Trading application on an isolated local database."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


TUTORIAL = Path(__file__).resolve().parents[1]
LEARNING = TUTORIAL.parents[1]
SERVER = LEARNING.parent / "drasi-server"
EXAMPLE = SERVER / "examples/trading"
APP = EXAMPLE / "app"
STATE = TUTORIAL / ".runtime"
INSTANCE = "trading-server"
PLUGINS = (
    "drasi-computation-source-postgres", "drasi-computation-bootstrap-postgres",
    "drasi-computation-source-http", "drasi-computation-bootstrap-http", "drasi-reaction-sse",
)


def command(args, *, cwd=EXAMPLE, env=None, data=None):
    return subprocess.run(
        list(map(str, args)), cwd=cwd, env=env, input=data,
        text=True, capture_output=True, check=True, timeout=600,
    ).stdout.strip()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def local_build():
    sys.path.insert(0, str(LEARNING / "scripts"))
    import local_build as shared
    return shared


def build():
    if (STATE / "server.lock").exists():
        raise RuntimeError("Stop this tutorial before rebuilding; server.lock is present")
    local_build().build(STATE, PLUGINS, server_repo=SERVER)
    binary, plugins = local_build().verified_build(STATE, PLUGINS)
    target = Path(os.environ.get("CARGO_TARGET_DIR", SERVER / "target")).resolve()
    print("Building Trading's native metadata generator and existing React package...", flush=True)
    command(["cargo", "build", "--locked", "--manifest-path", SERVER / "Cargo.toml",
             "--target-dir", target, "--example", "native-postgres"], cwd=SERVER)
    command(["npm", "run", "build"], cwd=SERVER / "dev-tools/react")
    command(["node", "--import", "tsx", "scripts/export-native-recipe.ts",
             target / "debug/examples/native-postgres", plugins], cwd=APP)
    command([APP / "node_modules/.bin/tsc", "--noEmit"], cwd=APP)
    generator = STATE / "native-postgres"
    shutil.copy2(target / "debug/examples/native-postgres", generator)
    bundle = APP / "public/native-computation.json"
    record = {"server": str(binary), "generator": str(generator), "plugins": str(plugins),
              "generator_sha256": digest(generator), "bundle_sha256": digest(bundle)}
    (STATE / "trading-build.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Matching local Trading build ready: {STATE / 'trading-build.json'}")


def verified_build():
    binary, plugins = local_build().verified_build(STATE, PLUGINS)
    record = json.loads((STATE / "trading-build.json").read_text())
    generator = Path(record["generator"])
    if (record["server"] != str(binary) or record["plugins"] != str(plugins)
            or digest(generator) != record["generator_sha256"]
            or digest(APP / "public/native-computation.json") != record["bundle_sha256"]):
        raise RuntimeError("Trading build or generated bundle changed; run demo.py build again")
    return binary, plugins, generator


def request(url, body=None, method=None):
    req = Request(url, data=None if body is None else json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method=method)
    with urlopen(req, timeout=10) as response:
        return json.load(response)


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for(description, check, children=(), timeout=60):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        for name, process, _log in children:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited with {process.returncode}; inspect its run log")
        try:
            if check():
                print(f"Ready: {description}", flush=True)
                return
        except (URLError, ConnectionError, TimeoutError) as error:
            last_error = error
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {description}; last connection error: {last_error}")


def runtime_ready(body):
    return (body.get("success") is True
            and body.get("data", {}).get("instanceId") == INSTANCE
            and body["data"].get("runtime") == "computationGraph"
            and body["data"].get("running") is True)


def run(no_prices):
    binary, plugins, generator = verified_build()
    STATE.mkdir(parents=True, exist_ok=True)
    lock = STATE / "server.lock"
    # One foreground owner; never infer permission to take over another run.
    with lock.open("x") as stream:
        stream.write(str(os.getpid()))
    children = []
    container = None
    work = Path(tempfile.mkdtemp(prefix="run-", dir=STATE))

    def interrupt(_signum, _frame):
        raise KeyboardInterrupt

    previous_termination = signal.signal(signal.SIGTERM, interrupt)
    try:
        ports = {}
        while len(ports) < 5:
            candidate = available_port()
            if candidate not in ports.values():
                ports[("server", "source", "sse", "api", "app")[len(ports)]] = candidate
        urls = {name: f"http://127.0.0.1:{number}" for name, number in ports.items()}
        container = command([
            "podman", "run", "--detach", "--name", f"trading-tutorial-{work.name}",
            "--label", f"drasi.tutorial.trading={work.name}",
            "--publish", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql/data:rw",
            "--env", "POSTGRES_DB=trading_demo", "--env", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
            "docker.io/library/postgres:16-alpine", "-c", "wal_level=logical",
            "-c", "max_replication_slots=32", "-c", "max_wal_senders=32",
        ])
        if len(container) != 64 or any(char not in "0123456789abcdef" for char in container):
            raise RuntimeError("Podman did not return a concrete owned container ID")

        def postgres_ready():
            result = subprocess.run(["podman", "exec", container, "pg_isready",
                                     "-h", "127.0.0.1", "-U", "postgres"],
                                    capture_output=True, timeout=10)
            return result.returncode == 0

        wait_for("fresh PostgreSQL", postgres_ready)
        command(["podman", "exec", "-i", container, "psql", "-X", "-q",
                 "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "trading_demo"],
                data=(EXAMPLE / "database/init.sql").read_text())
        address = command(["podman", "port", container, "5432/tcp"])
        if not address.startswith("127.0.0.1:"):
            raise RuntimeError(f"PostgreSQL must be loopback-only, got {address}")
        password = secrets.token_hex(24)
        command(["podman", "exec", "-i", container, "psql", "-X", "-q",
                 "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "trading_demo"],
                data=f"ALTER USER drasi_user PASSWORD '{password}';")
        env = {**os.environ,
               "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": address.rsplit(":", 1)[1],
               "POSTGRES_DB": "trading_demo", "POSTGRES_USER": "drasi_user", "POSTGRES_PASSWORD": password,
               "TRADING_STOCKS_SLOT": "drasi_trading_slot", "TRADING_STOCKS_PUBLICATION": "drasi_trading_pub",
               "TRADING_BROKER_SLOT": "drasi_broker_slot", "TRADING_BROKER_PUBLICATION": "drasi_broker_pub",
               "TRADING_API_HOST": "127.0.0.1", "TRADING_API_PORT": str(ports["api"]),
               "TRADING_SNAPSHOT_URL": urls["api"] + "/api/initial-prices",
               "DRASI_HTTP_PRICE_FEED_HOST": "127.0.0.1", "DRASI_HTTP_PRICE_FEED_PORT": str(ports["source"]),
               "DRASI_SERVER_URL": urls["server"], "DRASI_INSTANCE_ID": INSTANCE,
               "TRADING_PRICE_SOURCE_URL": urls["source"],
               "VITE_DRASI_SERVER_URL": urls["server"], "VITE_TRADING_API_URL": urls["api"],
               "VITE_TRADING_SSE_HOST": "127.0.0.1", "VITE_TRADING_SSE_PORT": str(ports["sse"]),
               "VITE_TRADING_SSE_URL": urls["sse"] + "/events"}
        recipe = EXAMPLE / "server/trading-native-recipe.json"
        for source, key in [("postgres-stocks", "DRASI_PG_POSTGRES_STOCKS_SETTINGS"),
                            ("postgres-broker", "DRASI_PG_POSTGRES_BROKER_SETTINGS"),
                            ("price-feed", "DRASI_HTTP_PRICE_FEED_SETTINGS")]:
            env[key] = command([generator, "settings", recipe, source], env=env)

        def start(name, args, cwd=work):
            log = (work / f"{name}.log").open("w")
            process = subprocess.Popen(list(map(str, args)), cwd=cwd, env=env,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            children.append((name, process, log))

        start("trading-api", [sys.executable, EXAMPLE / "mock-generator/trading_api.py"])
        wait_for("real Trading API", lambda: request(urls["api"] + "/health")["status"] == "healthy", children)
        config = json.loads(command([generator, "inspect", EXAMPLE / "server/trading-sources-only.yaml"]))
        config.update({"host": "127.0.0.1", "port": ports["server"], "enableUi": False,
                       "persistConfig": False, "autoInstallPlugins": False})
        config_path = work / "server.json"
        config_path.write_text(json.dumps(config, indent=2) + "\n")
        start("server", [binary, "--config", config_path, "--plugins-dir", plugins, "--skip-verification"])
        wait_for("trading-server ComputationGraph",
                 lambda: runtime_ready(request(urls["server"] + f"/api/v1/instances/{INSTANCE}/runtime")),
                 children)
        setup = command(["node", "--import", "tsx", "scripts/qualify-native-setup.ts"], cwd=APP, env=env)
        (work / "app-setup.log").write_text(setup + "\n")
        start("app", ["node", APP / "node_modules/vite/bin/vite.js",
                      "--host", "127.0.0.1", "--port", ports["app"], "--strictPort"], cwd=APP)

        def app_ready():
            with urlopen(urls["app"], timeout=5) as response:
                return response.status == 200

        wait_for("existing Trading dashboard", app_ready, children)
        if not no_prices:
            start("prices", [sys.executable, EXAMPLE / "mock-generator/simple_price_generator.py"])
        (work / "endpoints.json").write_text(json.dumps(
            {"instance": INSTANCE, "urls": urls, "container": container, "owner_pid": os.getpid(),
             "random_prices": not no_prices}, indent=2) + "\n")
        print(f"\nDashboard: {urls['app']}\nRun directory: {work}\n"
              "Ctrl+C stops only this run and removes its disposable database. Logs are retained.", flush=True)
        while True:
            for name, process, _log in children:
                if process.poll() is not None:
                    raise RuntimeError(f"{name} exited with {process.returncode}; see {work / (name + '.log')}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping owned Trading run...", flush=True)
    finally:
        failures = []
        for name, process, log in reversed(children):
            try:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
                failures.append(f"{name} required forced termination")
            finally:
                log.close()
        if container and len(container) == 64 and all(char in "0123456789abcdef" for char in container):
            try:
                command(["podman", "rm", "--force", container])
            except subprocess.CalledProcessError as error:
                failures.append(f"Owned database cleanup failed: {error.stderr}")
        lock.unlink()
        signal.signal(signal.SIGTERM, previous_termination)
        if failures:
            raise RuntimeError("; ".join(failures))


def verify(work):
    record = json.loads((work / "endpoints.json").read_text())
    api = record["urls"]["server"] + f"/api/v1/instances/{INSTANCE}"
    if not runtime_ready(request(api + "/runtime")):
        raise RuntimeError("Expected running trading-server ComputationGraph")
    queries = request(api + "/queries")
    if queries.get("success") is not True or len(queries["data"]) != 11:
        raise RuntimeError("Expected all eleven Trading queries")
    if any(query["status"] != "Running" for query in queries["data"]):
        raise RuntimeError("Some Trading queries are not Running")
    observations = {}
    for query in queries["data"]:
        response = request(api + f"/queries/{query['id']}/results")
        if response.get("success") is not True or not isinstance(response.get("data"), list):
            raise RuntimeError(f"Invalid result snapshot for {query['id']}")
        observations[query["id"]] = response["data"]
    if len(observations["price-ticker-query"]) != 50 or len(observations["portfolio-query"]) != 8:
        raise RuntimeError("Expected full 50-price seed and eight demo positions before editing")
    if len(observations["portfolio-summary-query"]) != 1:
        raise RuntimeError("Portfolio summary must contain one authoritative current row")
    (work / "snapshots.json").write_text(json.dumps(observations, indent=2) + "\n")
    print(f"All eleven queries running; full initial snapshots saved to {work / 'snapshots.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("build", help="Build matching local binaries, plugins and native Trading bundle")
    runner = actions.add_parser("run", help="Run the real app against fresh isolated Podman data")
    runner.add_argument("--no-prices", action="store_true", help="Keep bootstrap prices for deterministic exercises")
    checker = actions.add_parser("verify", help="Read and save the initial real query snapshots")
    checker.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    if args.action == "build":
        build()
    elif args.action == "run":
        run(args.no_prices)
    else:
        verify(args.run_directory.resolve())


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"{Path(error.cmd[0]).name} failed (exit {error.returncode}):\n{error.stderr}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Trading tutorial failed: {error}", file=sys.stderr)
        sys.exit(1)
