#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
"""Run the real High Risk Containers tutorial with locally built Server/Core."""

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
import uuid

TUTORIAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TUTORIAL.parents[1] / "scripts"))
import local_build

INSTANCE = "high-risk-containers-server"
PLUGINS = (
    "drasi-source-postgres", "drasi-bootstrap-postgres",
    "drasi-source-kubernetes", "drasi-bootstrap-kubernetes",
    "drasi-reaction-dashboard", "drasi-reaction-http",
)
LABEL = "io.drasi.high-risk-containers.owner"
QUERIES = {"pod-containers", "high-risk-containers"}


def environment():
    path = TUTORIAL / ".env"
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                raise ValueError(f"{path}:{number}: expected NAME=value")
            os.environ.setdefault(name, value.strip().strip("'\""))
    os.environ.setdefault("SERVER_HOST", "127.0.0.1")
    os.environ.setdefault("DASHBOARD_HOST", "127.0.0.1")
    os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
    if os.environ["POSTGRES_HOST"] not in ("127.0.0.1", "localhost"):
        raise ValueError("This owned demo requires a loopback POSTGRES_HOST")
    os.environ.setdefault("POSTGRES_PORT", os.environ.get("POSTGRES_HOST_PORT", "5732"))
    os.environ.setdefault("POSTGRES_HOST_PORT", os.environ["POSTGRES_PORT"])
    if os.environ["POSTGRES_PORT"] != os.environ["POSTGRES_HOST_PORT"]:
        raise ValueError("POSTGRES_PORT must match POSTGRES_HOST_PORT")
    for name, expected in (("POSTGRES_DATABASE", "high_risk_containers"),
                           ("POSTGRES_USER", "drasi_user"), ("POSTGRES_PASSWORD", "drasi_password")):
        if os.environ.get(name, expected) != expected:
            raise ValueError(f"This isolated seed database requires {name}={expected}")


def state():
    return Path(os.environ.get("DRASI_DEMO_DIR", TUTORIAL / ".runtime")).resolve()


def run(argv, *, capture=False, stdin=None, env=None):
    print("+", " ".join(map(str, argv)), flush=True)
    return subprocess.run(
        list(map(str, argv)), cwd=TUTORIAL, check=True, text=True, input=stdin,
        stdout=subprocess.PIPE if capture else None, env=env,
    ).stdout


def engine():
    name = os.environ.get("CONTAINER_ENGINE", "podman")
    if name not in ("podman", "docker") or not shutil.which(name):
        raise RuntimeError(f"Container engine {name!r} unavailable; install Podman and start its machine")
    return name


def ownership(create=False):
    path = state() / "ownership.json"
    if not path.exists():
        if not create:
            raise RuntimeError("No owned run exists. Run start-demo (or database/cluster) first.")
        identifier = os.environ.get("DRASI_RUN_ID", "hrc-" + uuid.uuid4().hex[:12])
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}[a-z0-9]", identifier):
            raise ValueError("DRASI_RUN_ID must be a 3-41 character DNS label, starting with a letter")
        ports = {
            key: int(os.environ.get(key, default))
            for key, default in (("POSTGRES_PORT", "5732"), ("K3D_API_PORT", "6550"),
                                 ("SERVER_PORT", "8380"), ("DASHBOARD_PORT", "3000"))
        }
        if len(set(ports.values())) != 4 or any(not 1024 <= p <= 65535 for p in ports.values()):
            raise ValueError("The four tutorial ports must be distinct and between 1024 and 65535")
        state().mkdir(parents=True, exist_ok=True)
        record = {"run": identifier, "path": str(state()), "tutorial": str(TUTORIAL),
                  "engine": engine(), "ports": ports}
        with path.open("x") as stream:
            json.dump(record, stream, indent=2)
    record = json.loads(path.read_text())
    if record["path"] != str(state()) or record["tutorial"] != str(TUTORIAL):
        raise RuntimeError("Ownership file belongs to a different tutorial/state directory")
    if record["engine"] != engine():
        raise RuntimeError("Container engine differs from the owned run")
    if os.environ.get("DRASI_RUN_ID", record["run"]) != record["run"]:
        raise RuntimeError("DRASI_RUN_ID differs from the owned run; use a new DRASI_DEMO_DIR")
    for key, value in record["ports"].items():
        if int(os.environ.get(key, value)) != value:
            raise RuntimeError(f"{key} differs from the owned run; use its original ports")
        os.environ[key] = str(value)
    os.environ["POSTGRES_HOST_PORT"] = os.environ["POSTGRES_PORT"]
    return record


def inspect_owned(kind, name):
    listing = [engine(), "ps", "-a", "--format", "{{.Names}}"] if kind == "container" else [
        engine(), "volume", "ls", "--format", "{{.Name}}"]
    if name not in run(listing, capture=True).splitlines():
        return None
    item = json.loads(run([engine(), kind, "inspect", name], capture=True))[0]
    labels = item["Config"].get("Labels") if kind == "container" else item.get("Labels")
    if not labels or labels.get(LABEL) != str(state()):
        raise RuntimeError(f"Refusing unowned {kind}: {name}")
    return item


def free_ports(*ports):
    for port in ports:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", int(port)))
            probe.listen(1)


def sql(statement, *, admin=False, variables=()):
    record = ownership()
    name = record["run"] + "-postgres"
    if not inspect_owned("container", name):
        raise RuntimeError("Owned PostgreSQL container is missing; run database first")
    arguments = [item for key, value in variables for item in ("-v", f"{key}={value}")]
    return run(
        [engine(), "exec", "-i", name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-U", "postgres" if admin else "drasi_user", "-d", "high_risk_containers",
         "-At", *arguments], stdin=statement, capture=True,
    ).strip()


def database():
    record = ownership(create=True)
    name = record["run"] + "-postgres"
    volume = record["run"] + "-postgres-data"
    container = inspect_owned("container", name)
    existing_volume = inspect_owned("volume", volume)
    if not container:
        free_ports(record["ports"]["POSTGRES_PORT"])
        if not existing_volume:
            run([engine(), "volume", "create", "--label", f"{LABEL}={state()}", volume])
        run([engine(), "run", "-d", "--name", name, "--label", f"{LABEL}={state()}",
             "-p", f"127.0.0.1:{record['ports']['POSTGRES_PORT']}:5432",
             "-e", "POSTGRES_DB=high_risk_containers", "-e", "POSTGRES_USER=postgres",
             "-e", "POSTGRES_PASSWORD=postgres_admin", "-v", f"{volume}:/var/lib/postgresql/data",
             "docker.io/library/postgres:14-alpine", "postgres", "-c", "wal_level=logical",
             "-c", "max_replication_slots=10", "-c", "max_wal_senders=10"])
    elif not container["State"]["Running"]:
        run([engine(), "start", name])
    deadline = time.monotonic() + 90
    while subprocess.run([engine(), "exec", name, "pg_isready", "-h", "127.0.0.1",
                          "-U", "postgres", "-d", "high_risk_containers"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        if time.monotonic() >= deadline:
            raise RuntimeError(f"PostgreSQL readiness timed out; inspect {name}")
        time.sleep(1)
    tables = sql("SELECT count(*) FROM pg_tables WHERE schemaname='public';", admin=True)
    if tables == "0":
        print(sql((TUTORIAL / "database/init.sql").read_text(), admin=True))
    elif sql("""SELECT count(*) FROM pg_tables
                WHERE schemaname='public' AND tablename='RiskyImage';""", admin=True) != "1":
        raise RuntimeError("Unexpected existing schema; nothing was reset")
    else:
        print("Keeping existing risky-image rows; no reseed.")
    if sql("SELECT count(*) FROM pg_publication WHERE pubname='drasi_high_risk_containers_pub';") != "1":
        raise RuntimeError("Required CDC publication is missing")


def kube_environment():
    result = dict(os.environ, KUBECONFIG=str(state() / "kubeconfig.yaml"))
    if engine() == "podman" and not result.get("DOCKER_HOST"):
        raise RuntimeError(
            "k3d needs the running rootful Podman API socket. Set DOCKER_HOST to its unix:// "
            "endpoint (on macOS: podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}'). "
            "Do not point it at Docker Desktop."
        )
    return result


def verify_engine_endpoint():
    environment = kube_environment()
    if engine() == "podman":
        template = "{{.Host.Hostname}}|{{.Store.GraphRoot}}"
        expected = run(["podman", "info", "--format", template], capture=True).strip()
        actual = run(["podman", "--url", environment["DOCKER_HOST"], "info", "--format", template],
                     capture=True).strip()
        if not actual or actual != expected:
            raise RuntimeError("DOCKER_HOST is not the Podman engine that owns this run")


def clusters():
    return json.loads(run([os.environ.get("K3D", "k3d"), "cluster", "list", "-o", "json"],
                          capture=True, env=kube_environment()))


def verify_cluster(record, items=None):
    items = clusters() if items is None else items
    found = [item for item in items if item["name"] == record["run"]]
    if not found:
        return False
    nodes = found[0].get("nodes", [])
    if not nodes:
        raise RuntimeError("Owned cluster has no inspectable nodes")
    for node in nodes:
        if not inspect_owned("container", node["name"]):
            raise RuntimeError(f"Cluster node is missing: {node['name']}")
    return True


def kubectl(*arguments, capture=False, stdin=None):
    forbidden = {"--kubeconfig", "--context", "--namespace", "-n", "--server", "-s",
                 "--cluster", "--user", "--token", "--all-namespaces", "-A"}
    if any(str(argument).split("=", 1)[0] in forbidden for argument in arguments):
        raise ValueError("Do not override the owned Kubernetes connection or namespace")
    record = ownership()
    return run(["kubectl", "--kubeconfig", state() / "kubeconfig.yaml",
                "--context", "k3d-" + record["run"], "--namespace", record["run"], *arguments],
               capture=capture, stdin=stdin)


def verify_namespace():
    record = ownership()
    if not verify_cluster(record):
        raise RuntimeError("Owned cluster is missing; run cluster first")
    namespace = json.loads(kubectl("get", "namespace", record["run"], "-o", "json", capture=True))
    if namespace["metadata"].get("labels", {}).get("io.drasi.tutorial-run") != record["run"]:
        raise RuntimeError("Namespace ownership mismatch")


def cluster():
    record = ownership(create=True)
    k3d = os.environ.get("K3D", "k3d")
    if not shutil.which(k3d) or not shutil.which("kubectl"):
        raise RuntimeError("Install k3d and kubectl before running the real Kubernetes scenario")
    verify_engine_endpoint()
    items = clusters()
    if not verify_cluster(record, items):
        free_ports(record["ports"]["K3D_API_PORT"])
        (state() / "cluster.intent").write_text(record["run"])
        run([k3d, "cluster", "create", record["run"],
             "--api-port", f"127.0.0.1:{record['ports']['K3D_API_PORT']}",
             "--kubeconfig-update-default=false", "--kubeconfig-switch-context=false",
             "--runtime-label", f"{LABEL}={state()}@all",
             "--k3s-arg", "--disable=traefik@server:0", "--wait", "--timeout", "180s"],
            env=kube_environment())
        if not verify_cluster(record):
            raise RuntimeError("Cluster creation returned without an owned cluster")
    kubeconfig = state() / "kubeconfig.yaml"
    content = run([k3d, "kubeconfig", "get", record["run"]], capture=True, env=kube_environment())
    with open(kubeconfig, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        stream.write(content)
    kubeconfig.chmod(0o600)
    namespaces = json.loads(kubectl("get", "namespaces", "-o", "json", capture=True))
    if not any(item["metadata"]["name"] == record["run"] for item in namespaces["items"]):
        kubectl("create", "-f", "-", stdin=json.dumps({
            "apiVersion": "v1", "kind": "Namespace",
            "metadata": {"name": record["run"], "labels": {"io.drasi.tutorial-run": record["run"]}},
        }))
    verify_namespace()
    pods = json.loads(kubectl("get", "pods", "-o", "json", capture=True))["items"]
    names = {pod["metadata"]["name"] for pod in pods}
    if not names:
        kubectl("create", "-f", TUTORIAL / "k8s/my-app.yaml")
    elif names != {"my-app-1", "my-app-2"}:
        raise RuntimeError("Unexpected or partial Pod set; not replacing it automatically")
    else:
        print("Keeping existing Pod images; no reset.")
    kubectl("wait", "--for=condition=Ready", "pod/my-app-1", "pod/my-app-2", "--timeout=180s")
    kubectl("get", "pods", "-o", "wide")


def add_risk(image, reason, mitigation, identifier):
    print(sql('''INSERT INTO "RiskyImage" ("Id", "Image", "Reason", "Mitigation")
        VALUES (:'id'::int, :'image', :'reason', :'mitigation')
        ON CONFLICT ("Id") DO UPDATE SET "Image"=EXCLUDED."Image",
        "Reason"=EXCLUDED."Reason", "Mitigation"=EXCLUDED."Mitigation";''',
        variables=(("id", identifier), ("image", image), ("reason", reason), ("mitigation", mitigation))))


def upgrade(pod, image, container="app"):
    verify_namespace()
    if pod not in ("my-app-1", "my-app-2") or container != "app":
        raise ValueError("Only this tutorial's two app containers may be changed")
    kubectl("set", "image", "pod/" + pod, container + "=" + image)
    deadline = time.monotonic() + 180
    while True:
        data = json.loads(kubectl("get", "pod", pod, "-o", "json", capture=True))
        statuses = data.get("status", {}).get("containerStatuses", [])
        if any(item["name"] == container and item.get("image") == image and item.get("ready")
               and "running" in item.get("state", {}) for item in statuses):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"{pod} has not become ready on {image}; inspect kubectl describe pod")
        time.sleep(1)


def reset(identifier):
    verify_namespace()
    print(sql('DELETE FROM "RiskyImage" WHERE "Id" = :\'id\'::int;', variables=(("id", identifier),)))
    upgrade("my-app-1", "ghcr.io/drasi-project/my-app:0.1")
    upgrade("my-app-2", "ghcr.io/drasi-project/my-app:0.2")
    print("Reset only the added risk row and the two tutorial Pod images.")


def get_json(url):
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


def api(path):
    port = ownership()["ports"]["SERVER_PORT"]
    result = get_json(f"http://127.0.0.1:{port}/api/v1/instances/{INSTANCE}/{path}")
    if result.get("success") is not True:
        raise RuntimeError(f"{path} failed: {result}")
    return result["data"]


def check():
    proof = api("runtime")
    if proof != {"instanceId": INSTANCE, "runtime": "computationGraph", "running": True}:
        raise RuntimeError(f"Wrong runtime identity/state: {proof}")
    for kind, expected in (("sources", {"k8s", "devops"}), ("queries", QUERIES),
                           ("reactions", {"high-risk-containers-dashboard"})):
        items = api(kind)
        actual = {item["id"] for item in items}
        allowed = expected | ({"__component_graph__"} if kind == "sources" else
                              {"discord-alerts"} if kind == "reactions" else set())
        if not expected <= actual <= allowed or any(item["status"].lower() != "running" for item in items):
            raise RuntimeError(f"{kind} not ready: {items}")
    inspection = api("computation")
    if inspection["graph"]["driverFailed"]:
        raise RuntimeError(f"Computation driver failed: {inspection['graph']}")
    for component in inspection["components"]:
        if component.get("failurePhase") or component.get("waitingFor"):
            raise RuntimeError(f"Graph component is failed or waiting: {component}")
    dashboards = get_json(
        f"http://127.0.0.1:{ownership()['ports']['DASHBOARD_PORT']}/api/dashboards")
    if not any(item["id"] == "high-risk-containers" for item in dashboards):
        raise RuntimeError("Predefined dashboard is not available")
    return {"runtime": proof, "computation": inspection}


def config():
    text = Path(os.environ.get("CONFIG_FILE", TUTORIAL / "server-config.yaml")).read_text()
    for old, new in (("kubeconfigPath: bin/kubeconfig.yaml",
                      "kubeconfigPath: " + json.dumps(str(state() / "kubeconfig.yaml"))),
                     ("          - default\n", "          - " + ownership()["run"] + "\n")):
        if text.count(old) != 1:
            raise RuntimeError(f"Expected exactly one configuration placeholder: {old!r}")
        text = text.replace(old, new)
    target = state() / "server-config.yaml"
    target.write_text(text)
    target.chmod(0o600)
    return target


def start():
    binary, plugins = local_build.verified_build(state(), PLUGINS)
    record = ownership()
    verify_namespace()
    if not inspect_owned("container", record["run"] + "-postgres"):
        raise RuntimeError("Owned database is missing")
    configuration = config()
    lock = state() / "server.lock"
    process = None
    old_term = signal.getsignal(signal.SIGTERM)
    with lock.open("x") as stream:
        stream.write(str(os.getpid()))
    try:
        free_ports(record["ports"]["SERVER_PORT"], record["ports"]["DASHBOARD_PORT"])
        process = subprocess.Popen(
            [str(binary), "--config", str(configuration), "--plugins-dir", str(plugins),
             "--skip-verification"], cwd=state(), env=dict(os.environ, DRASI_PLUGINS_DIR=str(plugins)))
        signal.signal(signal.SIGTERM, lambda *_: process.send_signal(signal.SIGINT))
        deadline = time.monotonic() + 180
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"Server exited during startup: {process.returncode}")
            try:
                proof = check()
                break
            except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Readiness timed out: {error}") from error
                time.sleep(0.5)
        (state() / "runtime.json").write_text(json.dumps(proof, indent=2) + "\n")
        print(f"\nHigh Risk Containers READY: ComputationGraph; both sources, both queries and reactions running."
              f"\nDashboard: http://localhost:{record['ports']['DASHBOARD_PORT']}"
              "\nCtrl+C stops Server only; PostgreSQL and Kubernetes are preserved.", flush=True)
        if process.wait():
            raise RuntimeError(f"Server exited with status {process.returncode}")
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
                    raise RuntimeError("Server required forced shutdown after 30 seconds") from error
        finally:
            lock.unlink()


def cleanup(volumes=False):
    if (state() / "server.lock").exists():
        raise RuntimeError("Stop the foreground Server with Ctrl+C before cleanup")
    record = ownership()
    if (state() / "cluster.intent").exists() or (state() / "kubeconfig.yaml").exists():
        verify_engine_endpoint()
        if verify_cluster(record):
            run([os.environ.get("K3D", "k3d"), "cluster", "delete", record["run"]], env=kube_environment())
        (state() / "cluster.intent").unlink(missing_ok=True)
    (state() / "kubeconfig.yaml").unlink(missing_ok=True)
    name = record["run"] + "-postgres"
    if inspect_owned("container", name):
        run([engine(), "rm", "-f", name])
    volume = record["run"] + "-postgres-data"
    if volumes and inspect_owned("volume", volume):
        run([engine(), "volume", "rm", volume])
    print("Owned infrastructure removed. " + ("Database volume deleted." if volumes else "Database volume retained."))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("build", "verify-build", "database", "cluster", "start", "start-demo", "check", "inspect", "kubectl"):
        command = actions.add_parser(name)
        if name == "kubectl":
            command.add_argument("arguments", nargs=argparse.REMAINDER)
    command = actions.add_parser("add-risk")
    command.add_argument("image", nargs="?", default="ghcr.io/drasi-project/my-app:0.2")
    command.add_argument("reason", nargs="?", default="Critical Bug")
    command.add_argument("mitigation", nargs="?", default="Update to latest version")
    command.add_argument("--id", type=int, default=int(os.environ.get("RISKY_IMAGE_ID", "101")))
    command = actions.add_parser("upgrade")
    command.add_argument("pod", nargs="?", default="my-app-2")
    command.add_argument("image", nargs="?", default="ghcr.io/drasi-project/my-app:0.3")
    command.add_argument("--container", default="app")
    command = actions.add_parser("reset")
    command.add_argument("--id", type=int, default=int(os.environ.get("RISKY_IMAGE_ID", "101")))
    command = actions.add_parser("cleanup")
    command.add_argument("--volumes", action="store_true")
    args = parser.parse_args()
    try:
        environment()
        if args.action == "build":
            local_build.build(state(), PLUGINS)
        elif args.action == "verify-build":
            local_build.verified_build(state(), PLUGINS)
        elif args.action == "database":
            database()
        elif args.action == "cluster":
            cluster()
        elif args.action == "start-demo":
            local_build.verified_build(state(), PLUGINS)
            cluster()
            database()
            start()
        elif args.action == "start":
            start()
        elif args.action == "add-risk":
            add_risk(args.image, args.reason, args.mitigation, args.id)
        elif args.action == "upgrade":
            upgrade(args.pod, args.image, args.container)
        elif args.action == "reset":
            reset(args.id)
        elif args.action == "cleanup":
            cleanup(args.volumes)
        elif args.action == "kubectl":
            verify_namespace()
            kubectl(*args.arguments)
        elif args.action in ("check", "inspect"):
            print(json.dumps(check() if args.action == "check" else api("computation"), indent=2))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError,
            urllib.error.URLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
