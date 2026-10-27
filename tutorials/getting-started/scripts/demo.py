#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Owned local infrastructure for the Getting Started walkthrough."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


TUTORIAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TUTORIAL.parents[1] / "scripts"))
INSTANCE = "getting-started-server"
PLUGINS = (
    "drasi-source-postgres", "drasi-bootstrap-postgres",
    "drasi-reaction-log", "drasi-reaction-sse",
    "drasi-source-http", "drasi-bootstrap-scriptfile",
)
LABEL = "io.drasi.getting-started.owner"
IMAGE = "docker.io/library/postgres:14-alpine"


def environment():
    path = TUTORIAL / ".env"
    if path.is_file():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                raise ValueError(f"{path}:{number}: expected NAME=value")
            os.environ.setdefault(key, value.strip().strip("'\""))
    defaults = {
        "DRASI_RUN_ID": "getting-started-cg", "POSTGRES_PORT": "5532",
        "SERVER_PORT": "8180", "SSE_PORT": "8181", "HTTP_PORT": "8182",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,50}", os.environ["DRASI_RUN_ID"]):
        raise ValueError("DRASI_RUN_ID must be 3-51 lowercase letters, digits or hyphens")
    for key in ("POSTGRES_PORT", "SERVER_PORT", "SSE_PORT", "HTTP_PORT"):
        if not 1024 <= int(os.environ[key]) <= 65535:
            raise ValueError(f"{key} must be an unprivileged TCP port")
    if len({int(os.environ[key]) for key in defaults if key.endswith("_PORT")}) != 4:
        raise ValueError("Database, API, SSE and HTTP ports must be distinct")
    os.environ["DRASI_TUTORIAL_DIR"] = str(TUTORIAL)
    os.environ.setdefault("RUSTUP_TOOLCHAIN", "1.95.0")
    os.environ.setdefault("CARGO_BUILD_JOBS", "1")
    os.environ.setdefault("CARGO_INCREMENTAL", "0")
    os.environ.setdefault("CARGO_PROFILE_DEV_DEBUG", "0")


def state():
    return TUTORIAL / ".runtime" / os.environ["DRASI_RUN_ID"]


def build_state():
    return TUTORIAL / ".runtime" / "build"


def local_build():
    # Shared build policy has no released-binary or registry fallback.
    import local_build as helper
    return helper


def cli_build(verify=False):
    directory = build_state() / "cli"
    binary = directory / "drasi-sse-cli"
    args = [
        sys.executable, TUTORIAL.parent / "sse-cli/scripts/build.py",
        "--destination", binary, "--state", directory / "provenance.json",
        "--target-dir", os.environ.get("CARGO_TARGET_DIR", TUTORIAL.parents[2] / "drasi-server/target"),
        "--profile", "debug", "--toolchain", "1.95.0",
    ]
    if verify:
        args.append("--verify-only")
    run(args)
    return binary


def run(argv, *, stdin=None, capture=False):
    return subprocess.run(
        list(map(str, argv)), cwd=TUTORIAL, input=stdin, check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
    ).stdout


def container():
    return os.environ["DRASI_RUN_ID"] + "-postgres"


def volume():
    return os.environ["DRASI_RUN_ID"] + "-postgres-data"


def owner():
    return str(state().resolve())


def owned(kind, name):
    listing = ["podman", "ps", "-a", "--format", "{{.Names}}"] if kind == "container" else [
        "podman", "volume", "ls", "--format", "{{.Name}}"]
    if name not in run(listing, capture=True).splitlines():
        return False
    record = json.loads(run(["podman", kind, "inspect", name], capture=True))[0]
    labels = record["Config"].get("Labels") if kind == "container" else record.get("Labels")
    if not labels or labels.get(LABEL) != owner():
        raise RuntimeError(f"Refusing unowned {kind}: {name}")
    return True


def sql(statement, *, admin=False, variables=None):
    if not owned("container", container()):
        raise RuntimeError("Run the database command first")
    args = ["podman", "exec", "-i", container(), "psql", "-X", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres" if admin else "drasi_user", "-d", "getting_started", "-At"]
    for name, value in (variables or {}).items():
        args.extend(["-v", f"{name}={value}"])
    return run(args, stdin=statement, capture=True).strip()


def free_port(port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", int(port)))
        probe.listen(1)


def database():
    exists = owned("container", container())
    has_volume = owned("volume", volume())
    state().mkdir(parents=True, exist_ok=True)
    if not exists:
        free_port(os.environ["POSTGRES_PORT"])
        image = subprocess.run(["podman", "image", "exists", IMAGE])
        if image.returncode == 1:
            run(["podman", "pull", IMAGE])
        elif image.returncode:
            raise RuntimeError(f"Podman image inspection failed: {image.returncode}")
        if not has_volume:
            run(["podman", "volume", "create", "--label", f"{LABEL}={owner()}", volume()])
        run(["podman", "run", "-d", "--name", container(), "--label", f"{LABEL}={owner()}",
             "-p", f"127.0.0.1:{os.environ['POSTGRES_PORT']}:5432",
             "-e", "POSTGRES_DB=getting_started", "-e", "POSTGRES_PASSWORD=postgres_admin",
             "-v", f"{volume()}:/var/lib/postgresql/data", IMAGE,
             "postgres", "-c", "wal_level=logical",
             "-c", "max_replication_slots=10", "-c", "max_wal_senders=10"])
    else:
        record = json.loads(run(["podman", "container", "inspect", container()], capture=True))[0]
        binding = record["HostConfig"]["PortBindings"].get("5432/tcp", [])
        if binding != [{"HostIp": "127.0.0.1", "HostPort": os.environ["POSTGRES_PORT"]}]:
            raise RuntimeError("Existing owned database uses a different port; it was not changed")
        run(["podman", "start", container()])
    deadline = time.monotonic() + 90
    while subprocess.run(["podman", "exec", container(), "pg_isready", "-U", "postgres",
                         "-d", "getting_started"], stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL).returncode:
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Database not ready; inspect podman logs {container()}")
        time.sleep(1)
    tables = sql("SELECT count(*) FROM pg_tables WHERE schemaname='public';", admin=True)
    if tables == "0":
        print(sql((TUTORIAL / "database/init.sql").read_text(), admin=True))
    elif sql("SELECT to_regclass('public.\"Message\"') IS NOT NULL;", admin=True) != "t":
        raise RuntimeError("Existing data has an unexpected schema; nothing was reset")
    if sql("SELECT count(*) FROM pg_publication WHERE pubname='drasi_pub';") != "1":
        raise RuntimeError("Required drasi_pub publication is missing")
    # A separate statement/session avoids coupling slot creation to schema DDL.
    if sql("SELECT count(*) FROM pg_replication_slots WHERE slot_name='drasi_slot';") == "0":
        print(sql("SELECT pg_create_logical_replication_slot('drasi_slot', 'pgoutput');", admin=True))
    (state() / "database.json").write_text(json.dumps({
        "container": container(), "volume": volume(), "owner": owner(),
        "port": int(os.environ["POSTGRES_PORT"]),
    }, indent=2) + "\n")
    print(sql('SELECT "MessageId", "From", "Message" FROM "Message" ORDER BY "MessageId";'))


def api(path, *, method="GET", body=None):
    url = f"http://127.0.0.1:{os.environ['SERVER_PORT']}/api/v1/instances/{INSTANCE}/{path}"
    request = urllib.request.Request(url, method=method,
                                    data=json.dumps(body).encode() if body is not None else None,
                                    headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url}: HTTP {error.code}: {detail}") from error
    if payload.get("success") is not True:
        raise RuntimeError(f"{method} {url}: {payload}")
    return payload["data"]


def check():
    proof = api("runtime")
    if proof != {"instanceId": INSTANCE, "runtime": "computationGraph", "running": True}:
        raise RuntimeError(f"Unexpected runtime identity/readiness: {proof}")
    for kind in ("sources", "queries", "reactions"):
        components = api(kind)
        if any(component["status"].lower() != "running" for component in components):
            raise RuntimeError(f"Not all {kind} are running: {components}")
    if not any(query["id"] == "all-messages" for query in api("queries")):
        raise RuntimeError("Missing all-messages query")
    return proof


def working_config(content):
    return content.replace('"../../locations.jsonl"', json.dumps(str(TUTORIAL / "locations.jsonl")))


def start(config=None):
    binary, plugins = local_build().verified_build(build_state(), PLUGINS)
    state().mkdir(parents=True, exist_ok=True)
    config_path = state() / "getting-started.yaml"
    if config is not None:
        if config_path.exists():
            raise RuntimeError(f"{config_path} exists; do not overwrite API changes. Use start without --config")
        config_path.write_text(working_config(Path(config).read_text()))
    elif not config_path.exists():
        config_path.write_text(working_config((TUTORIAL / "configs/getting-started-step-3.yaml").read_text()))
    lock = state() / "server.lock"
    process = None
    old_term = signal.getsignal(signal.SIGTERM)
    with lock.open("x") as stream:
        stream.write(f"{os.getpid()}\n")
    try:
        free_port(os.environ["SERVER_PORT"])
        process = subprocess.Popen(
            [str(binary), "--config", str(config_path), "--plugins-dir", str(plugins),
             "--skip-verification"], cwd=state(),
            env=dict(os.environ, DRASI_PLUGINS_DIR=str(plugins)),
        )
        signal.signal(signal.SIGTERM, lambda *_: process.send_signal(signal.SIGINT))
        deadline = time.monotonic() + 120
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"Server exited during startup: {process.returncode}")
            try:
                proof = check()
                break
            except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Server readiness timed out: {error}") from error
                time.sleep(0.5)
        (state() / "runtime.json").write_text(json.dumps(proof, indent=2) + "\n")
        print(f"READY: {INSTANCE}, computationGraph. API port {os.environ['SERVER_PORT']}.", flush=True)
        print(f"Working configuration: {config_path}\nCtrl+C stops Server, not PostgreSQL.", flush=True)
        code = process.wait()
        if code:
            raise RuntimeError(f"Server exited with status {code}")
    finally:
        signal.signal(signal.SIGTERM, old_term)
        try:
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired as error:
                    process.kill()
                    process.wait()
                    raise RuntimeError("Server required forced shutdown") from error
        finally:
            lock.unlink()


def cleanup(remove_volumes=False):
    if (state() / "server.lock").exists():
        raise RuntimeError("Stop this run's foreground Server before cleanup")
    has_container = owned("container", container())
    has_volume = owned("volume", volume())
    if has_container:
        run(["podman", "stop", container()])
        run(["podman", "rm", container()])
    if remove_volumes and has_volume:
        run(["podman", "volume", "rm", volume()])
    print("Owned database removed." if remove_volumes else "Owned database stopped; volume preserved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for name in ("build", "build-cli", "verify-build", "database", "check"):
        commands.add_parser(name)
    serve = commands.add_parser("start")
    serve.add_argument("--config", type=Path)
    clean = commands.add_parser("cleanup")
    clean.add_argument("--volumes", "-v", action="store_true")
    statement = commands.add_parser("sql")
    statement.add_argument("statement", nargs="?", help="SQL text; omit to read stdin")
    add = commands.add_parser("add-message")
    add.add_argument("sender")
    add.add_argument("message")
    delete = commands.add_parser("delete-message")
    delete.add_argument("id", type=int)
    results = commands.add_parser("results")
    results.add_argument("query", nargs="?", default="all-messages")
    stream = commands.add_parser("stream")
    stream.add_argument("query")
    args = parser.parse_args()
    try:
        environment()
        if args.action == "build":
            if any((TUTORIAL / ".runtime").glob("*/server.lock")):
                raise RuntimeError("Stop all Getting Started Server runs before rebuilding")
            local_build().build(build_state(), PLUGINS)
        elif args.action == "build-cli":
            cli_build()
        elif args.action == "verify-build":
            print(local_build().verified_build(build_state(), PLUGINS))
        elif args.action == "database":
            database()
        elif args.action == "start":
            start(args.config)
        elif args.action == "check":
            print(json.dumps(check(), indent=2))
        elif args.action == "cleanup":
            cleanup(args.volumes)
        elif args.action == "sql":
            print(sql(args.statement if args.statement is not None else sys.stdin.read()))
        elif args.action == "add-message":
            print(sql('INSERT INTO "Message" ("From", "Message") VALUES '
                      "(:'sender', :'message') RETURNING \"MessageId\";",
                      variables={"sender": args.sender, "message": args.message}))
        elif args.action == "delete-message":
            result = sql(f'DELETE FROM "Message" WHERE "MessageId"={args.id} RETURNING "MessageId";')
            if result != f"{args.id}\nDELETE 1":
                raise RuntimeError(f"Expected one deleted message, got {result!r}")
            print(result)
        elif args.action == "results":
            if not re.fullmatch(r"[a-z][a-z0-9-]*", args.query):
                raise ValueError("Invalid query ID")
            print(json.dumps(api(f"queries/{args.query}/results"), indent=2))
        elif args.action == "stream":
            binary = cli_build(verify=True)
            free_port(os.environ["SSE_PORT"])
            os.execv(str(binary), [
                str(binary), "--server", f"http://127.0.0.1:{os.environ['SERVER_PORT']}",
                "--instance", INSTANCE, "--query", args.query,
                "--sse-port", os.environ["SSE_PORT"], "--sse-host", "127.0.0.1",
            ])
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, KeyError, ImportError,
            subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
