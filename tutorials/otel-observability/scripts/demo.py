#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Run the OTel store scenario with local Drasi artifacts and owned infrastructure."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

TUTORIAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TUTORIAL.parents[1] / "scripts"))
import local_build

INSTANCE = "otel-observability-server"
PLUGINS = (
    "drasi-source-postgres", "drasi-bootstrap-postgres",
    "drasi-source-kubernetes", "drasi-bootstrap-kubernetes", "drasi-source-otel",
    "drasi-reaction-dashboard", "drasi-reaction-log", "drasi-reaction-http",
)
QUERIES = (
    "current-health", "checkout-health", "slo-alert", "service-dependencies",
    "checkout-heartbeat", "missing-heartbeat",
)
LABEL = "io.drasi.otel-observability.owner"
PORTS = {
    "POSTGRES_PORT": "5732", "SERVER_PORT": "8380", "DASHBOARD_PORT": "3000",
    "OTEL_GRPC_PORT": "14317", "OTEL_HTTP_PORT": "14318",
    "CHECKOUT_CONTROL_PORT": "18080", "K3D_API_PORT": "6551",
}


def environment():
    path = TUTORIAL / ".env"
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                raise ValueError(f"{path}:{number}: expected NAME=value (not shell code)")
            os.environ.setdefault(key, value.strip().strip("'\""))
    for key, default in PORTS.items():
        os.environ.setdefault(key, default)
        if not 0 < int(os.environ[key]) < 65536:
            raise ValueError(f"{key} must be a port from 1 to 65535")
    if len({os.environ[key] for key in PORTS}) != len(PORTS):
        raise ValueError("Each OTel tutorial listener needs a distinct port")
    os.environ.setdefault("SERVER_HOST", "127.0.0.1")
    os.environ.setdefault("DASHBOARD_HOST", "127.0.0.1")
    os.environ.setdefault("K8S_NAMESPACE", "otel-observability")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,61}[a-z0-9]", os.environ["K8S_NAMESPACE"]):
        raise ValueError("K8S_NAMESPACE must be a DNS label")
    os.environ["KUBECONFIG_PATH"] = str(state() / "kubeconfig.yaml")
    os.environ.setdefault("OTEL_GRPC_BIND", "0.0.0.0:" + os.environ["OTEL_GRPC_PORT"])
    os.environ.setdefault("OTEL_HTTP_BIND", "127.0.0.1:" + os.environ["OTEL_HTTP_PORT"])
    for protocol in ("GRPC", "HTTP"):
        bind = os.environ[f"OTEL_{protocol}_BIND"]
        if bind.rsplit(":", 1)[-1] != os.environ[f"OTEL_{protocol}_PORT"]:
            raise ValueError(f"OTEL_{protocol}_BIND must use OTEL_{protocol}_PORT")


def state():
    return Path(os.environ.get("DRASI_DEMO_DIR", TUTORIAL / ".runtime")).resolve()


def run(argv, *, capture=False, stdin=None, env=None):
    print("+", " ".join(map(str, argv)), flush=True)
    return subprocess.run(
        list(map(str, argv)), check=True, text=True, input=stdin, cwd=TUTORIAL,
        stdout=subprocess.PIPE if capture else None, env=env,
    ).stdout


def engine():
    name = os.environ.get("CONTAINER_ENGINE", "podman")
    if name not in ("podman", "docker") or not shutil.which(name):
        raise RuntimeError("Install Podman and start its engine (or explicitly set CONTAINER_ENGINE=docker)")
    return name


def k3d(*args, capture=False):
    executable = os.environ.get("K3D", "k3d")
    if not shutil.which(executable):
        raise RuntimeError("k3d is missing; install k3d 5.8+ or set K3D to its executable")
    # k3d uses the Docker-compatible API, not the Podman CLI connection.
    if engine() == "podman" and not os.environ.get("DOCKER_HOST"):
        raise RuntimeError("Set DOCKER_HOST to your running Podman API socket for k3d")
    return run([executable, *args], capture=capture)


def write_owner(owner):
    state().mkdir(parents=True, exist_ok=True)
    temporary = state() / "ownership.json.tmp"
    temporary.write_text(json.dumps(owner, indent=2) + "\n")
    temporary.replace(state() / "ownership.json")


def ownership(create=False):
    path = state() / "ownership.json"
    settings = {key: os.environ[key] for key in (*PORTS, "K8S_NAMESPACE")}
    if path.exists():
        owner = json.loads(path.read_text())
        if owner["tutorial"] != str(TUTORIAL) or owner["settings"] != settings:
            raise RuntimeError("This run belongs to another path or port/namespace configuration; use its original .env")
        if owner["engine"] != engine():
            raise RuntimeError("Use the original run's container engine")
        return owner
    if not create:
        raise RuntimeError("No owned run; start with python3 scripts/demo.py start-demo")
    identity = uuid.uuid4().hex
    owner = {
        "tutorial": str(TUTORIAL), "id": identity, "settings": settings, "engine": engine(),
        "cluster": "otel-cg-" + identity[:10],
        "container": "otel-cg-" + identity[:10] + "-postgres",
        "volume": "otel-cg-" + identity[:10] + "-data",
    }
    write_owner(owner)
    return owner


def resource(kind, name):
    listing = [engine(), "ps", "-a", "--format", "{{.Names}}"] if kind == "container" else [
        engine(), "volume", "ls", "--format", "{{.Name}}"]
    if name not in run(listing, capture=True).splitlines():
        return None
    return json.loads(run([engine(), kind, "inspect", name], capture=True))[0]


def check_resource(owner, kind, name):
    item = resource(kind, name)
    if item is not None:
        labels = item["Config"].get("Labels") if kind == "container" else item.get("Labels")
        if not labels or labels.get(LABEL) != owner["id"]:
            raise RuntimeError(f"Refusing to reuse or delete unowned {kind} {name}")
    return item


def sql(statement, *, admin=False):
    owner = ownership()
    if not check_resource(owner, "container", owner["container"]):
        raise RuntimeError("Owned PostgreSQL container is missing")
    return run([engine(), "exec", "-i", owner["container"], "psql", "-X",
                "-v", "ON_ERROR_STOP=1", "-U", "postgres" if admin else "drasi_user",
                "-d", "otel_observability", "-At"], capture=True, stdin=statement).strip()


def wait_until(description, operation, timeout=90):
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            value = operation()
            if value:
                return value
        except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError) as exc:
            error = exc
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {description}; last error: {error}")


def database():
    owner = ownership(create=True)
    existing = check_resource(owner, "container", owner["container"])
    if existing is None:
        check_ports("POSTGRES_PORT")
    if not check_resource(owner, "volume", owner["volume"]):
        run([engine(), "volume", "create", "--label", f"{LABEL}={owner['id']}", owner["volume"]])
    if existing is None:
        run([engine(), "run", "-d", "--name", owner["container"],
             "--label", f"{LABEL}={owner['id']}",
             "-p", f"127.0.0.1:{os.environ['POSTGRES_PORT']}:5432",
             "-e", "POSTGRES_DB=otel_observability", "-e", "POSTGRES_USER=postgres",
             "-e", "POSTGRES_PASSWORD=postgres_admin",
             "-v", f"{owner['volume']}:/var/lib/postgresql/data",
             "docker.io/library/postgres:14-alpine", "postgres",
             "-c", "wal_level=logical", "-c", "max_replication_slots=10", "-c", "max_wal_senders=10"])
    else:
        run([engine(), "start", owner["container"]])
    def ready():
        return subprocess.run(
            [engine(), "exec", owner["container"], "pg_isready", "-U", "postgres",
             "-d", "otel_observability"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
    wait_until("PostgreSQL", ready)
    tables = sql("SELECT count(*) FROM pg_tables WHERE schemaname='public';", admin=True)
    if tables == "0":
        print(sql((TUTORIAL / "database/init.sql").read_text(), admin=True))
    elif sql("SELECT to_regclass('public.service_slo_policy');", admin=True) != "service_slo_policy":
        raise RuntimeError("Unexpected existing database schema; nothing was reset")
    if sql("SELECT count(*) FROM pg_publication WHERE pubname='drasi_otel_observability_pub';") != "1":
        raise RuntimeError("Required SLO publication is missing")
    print(sql("SELECT * FROM service_slo_policy;"))


def cluster_nodes(owner):
    clusters = json.loads(k3d("cluster", "list", "-o", "json", capture=True))
    matching = [item for item in clusters if item["name"] == owner["cluster"]]
    return matching[0]["nodes"] if matching else []


def check_cluster(owner):
    nodes = cluster_nodes(owner)
    if nodes:
        expected = owner.get("nodeIds")
        identities = node_ids(nodes)
        if expected != identities:
            raise RuntimeError(f"Cluster {owner['cluster']} does not match its recorded container identities")
    return nodes


def node_ids(nodes):
    if not nodes:
        raise RuntimeError("k3d returned no nodes for the newly created cluster")
    inspected = json.loads(run([engine(), "inspect", *(node["name"] for node in nodes)], capture=True))
    return sorted(item["Id"] for item in inspected)


def kubectl(*args, capture=False, stdin=None):
    owner = ownership()
    if not check_cluster(owner):
        raise RuntimeError("Owned cluster is missing")
    return run(["kubectl", "--kubeconfig", os.environ["KUBECONFIG_PATH"],
                "--namespace", os.environ["K8S_NAMESPACE"], *args], capture=capture, stdin=stdin)


def collector_endpoint(owner):
    explicit = os.environ.get("COLLECTOR_DRASI_ENDPOINT")
    if explicit:
        if not re.fullmatch(r"[A-Za-z0-9.-]+:[0-9]+", explicit):
            raise ValueError("COLLECTOR_DRASI_ENDPOINT must be hostname:port or IPv4:port")
        return explicit
    hosts = run([engine(), "exec", f"k3d-{owner['cluster']}-server-0", "cat", "/etc/hosts"], capture=True)
    aliases = ("host.containers.internal", "host.k3d.internal", "host.docker.internal")
    for alias in aliases:
        for line in hosts.splitlines():
            fields = line.split()
            if len(fields) > 1 and alias in fields[1:] and ":" not in fields[0]:
                return fields[0] + ":" + os.environ["OTEL_GRPC_PORT"]
    raise RuntimeError("No host gateway alias in k3d node; set COLLECTOR_DRASI_ENDPOINT to a reachable host:port")


def verify_image(information, service, version, delay):
    baked = dict(item.split("=", 1) for item in information["Config"]["Env"])
    expected = {"SERVICE_NAME": service, "SERVICE_VERSION": version}
    if delay is not None:
        expected["WORK_MS"] = str(delay)
    if any(baked.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"Built image for {service}:{version} has incorrect service/version/delay: {baked}")


def import_images(owner, images):
    with tempfile.TemporaryDirectory(prefix="image-import-", dir=state()) as directory:
        archive = Path(directory) / "images.tar"
        run([engine(), "save", "-o", archive, *images])
        k3d("image", "import", str(archive), "-c", owner["cluster"])


def cluster():
    owner = ownership(create=True)
    if not shutil.which("kubectl"):
        raise RuntimeError("kubectl is missing")
    nodes = check_cluster(owner)
    if not nodes:
        check_ports("K3D_API_PORT", "CHECKOUT_CONTROL_PORT")
        k3d("cluster", "create", owner["cluster"], "--api-port", f"127.0.0.1:{os.environ['K3D_API_PORT']}",
            "--port", f"127.0.0.1:{os.environ['CHECKOUT_CONTROL_PORT']}:30080@server:0",
            "--kubeconfig-update-default=false", "--kubeconfig-switch-context=false",
            "--k3s-arg", "--tls-san=127.0.0.1@server:0", "--wait")
        owner["nodeIds"] = node_ids(cluster_nodes(owner))
        write_owner(owner)
    kubeconfig = k3d("kubeconfig", "get", owner["cluster"], capture=True)
    path = Path(os.environ["KUBECONFIG_PATH"])
    path.write_text(kubeconfig)
    path.chmod(0o600)
    namespace = os.environ["K8S_NAMESPACE"]
    kubectl("apply", "-f", "-", stdin=json.dumps({
        "apiVersion": "v1", "kind": "Namespace",
        "metadata": {"name": namespace, "labels": {LABEL: owner["id"]}},
    }))
    images = []
    for service, version, delay in (("frontend", "v1", None), ("checkout", "v41", 400),
                                    ("checkout", "v42", 920), ("payments", "v1", None)):
        image = f"localhost/{owner['cluster']}-{service}:{version}"
        args = [engine(), "build", "--label", f"{LABEL}={owner['id']}", "-t", image,
                "-f", TUTORIAL / f"services/{service}/Dockerfile"]
        if delay is not None:
            # Some Podman/Buildah caches reuse the prior tag's ARG/ENV layers.
            args += ["--no-cache", "--build-arg", f"SERVICE_VERSION={version}", "--build-arg", f"WORK_MS={delay}"]
        run([*args, TUTORIAL / "services"])
        information = json.loads(run([engine(), "image", "inspect", image], capture=True))[0]
        verify_image(information, service, version, delay)
        images.append(image)
    import_images(owner, images)
    endpoint = collector_endpoint(owner)
    collector = (TUTORIAL / "k8s/collector.yaml").read_text().replace(
        "host.k3d.internal:14317", endpoint).replace("namespace: default", f"namespace: {namespace}")
    store = (TUTORIAL / "k8s/store.yaml").read_text().replace(
        "namespace: default", f"namespace: {namespace}").replace(
        "otel-observability-", f"localhost/{owner['cluster']}-")
    kubectl("apply", "-f", "-", stdin=collector)
    kubectl("apply", "-f", "-", stdin=store)
    kubectl("rollout", "restart", "deployment/frontend", "deployment/checkout",
            "deployment/payments", "deployment/otel-collector")
    for name in ("otel-collector", "frontend", "checkout", "payments"):
        kubectl("rollout", "status", f"deployment/{name}", "--timeout=180s")
    wait_until("checkout v41 control endpoint", lambda: get_json(
        f"http://127.0.0.1:{os.environ['CHECKOUT_CONTROL_PORT']}/state")["version"] == "v41")
    print(f"Collector forwards app telemetry to {endpoint}. Private kubeconfig: {path}")


def get_json(url, method="GET"):
    with urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=5) as response:
        return json.load(response)


def api():
    return f"http://127.0.0.1:{os.environ['SERVER_PORT']}/api/v1/instances/{INSTANCE}"


def results(query):
    response = get_json(api() + f"/queries/{query}/results")
    if response.get("success") is not True:
        raise RuntimeError(f"Query inspection failed: {response}")
    if not isinstance(response.get("data"), list):
        raise RuntimeError(f"Expected a result array: {response}")
    return response["data"]


def check():
    proof = get_json(api() + "/runtime")
    if proof.get("success") is not True or proof.get("data") != {
        "instanceId": INSTANCE, "runtime": "computationGraph", "running": True,
    }:
        raise RuntimeError(f"Wrong runtime identity/readiness: {proof}")
    for kind, expected in (("sources", {"slo", "k8s", "otel"}),
                           ("queries", set(QUERIES)),
                           ("reactions", {"console-log", "otel-observability-dashboard"})):
        response = get_json(api() + "/" + kind)
        if response.get("success") is not True:
            raise RuntimeError(f"Cannot inspect {kind}: {response}")
        components = response["data"]
        if not expected <= {item["id"] for item in components}:
            raise RuntimeError(f"Missing {kind}: {components}")
        if any(item["status"].lower() != "running" for item in components):
            raise RuntimeError(f"Not all {kind} are running: {components}")
    dashboards = get_json(f"http://127.0.0.1:{os.environ['DASHBOARD_PORT']}/api/dashboards")
    if not any(item["id"] == "otel-observability" for item in dashboards):
        raise RuntimeError("OTel dashboard is not seeded")
    return proof


def render_config(source):
    # These Kubernetes descriptor fields are plain strings, not ConfigValue.
    return source.replace(
        '"${KUBECONFIG_PATH}"', json.dumps(os.environ["KUBECONFIG_PATH"]),
    ).replace(
        '"${K8S_NAMESPACE:-otel-observability}"', json.dumps(os.environ["K8S_NAMESPACE"]),
    )


def start():
    binary, plugins = local_build.verified_build(state(), PLUGINS)
    owner = ownership()
    if not check_cluster(owner) or not check_resource(owner, "container", owner["container"]):
        raise RuntimeError("Start the owned cluster and database first")
    config = Path(os.environ.get("CONFIG_FILE", TUTORIAL / "server-config.yaml")).resolve()
    env = dict(os.environ, DRASI_PLUGINS_DIR=str(plugins))
    lock = state() / "server.lock"
    with lock.open("x") as stream:
        stream.write(str(os.getpid()) + "\n")
    process = None
    old_term = signal.getsignal(signal.SIGTERM)
    try:
        check_ports("SERVER_PORT", "DASHBOARD_PORT", "OTEL_GRPC_PORT", "OTEL_HTTP_PORT")
        generated = state() / "server-config.generated.yaml"
        generated.write_text(render_config(config.read_text()))
        process = subprocess.Popen(
            [str(binary), "--config", str(generated), "--plugins-dir", str(plugins), "--skip-verification"],
            cwd=state(), env=env,
        )
        signal.signal(signal.SIGTERM, lambda *_: process.send_signal(signal.SIGINT))
        def ready():
            if process.poll() is not None:
                raise ChildProcessError(f"Drasi exited: {process.returncode}")
            return check()
        proof = wait_until("the instance's graph and dashboard", ready, timeout=120)
        (state() / "runtime.json").write_text(json.dumps(proof, indent=2) + "\n")
        print(f"OTel READY. Dashboard: http://localhost:{os.environ['DASHBOARD_PORT']}\n"
              "Wait for the next Collector export; readiness is not scenario verification.", flush=True)
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
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise RuntimeError("Server required forced shutdown after 30 seconds")
        finally:
            lock.unlink()


def control(path):
    if not check_cluster(ownership()):
        raise RuntimeError("Owned cluster is missing")
    return get_json(f"http://127.0.0.1:{os.environ['CHECKOUT_CONTROL_PORT']}/{path}", "POST")


def roll(version):
    if version not in ("v41", "v42"):
        raise ValueError("Only v41 and v42 are built")
    owner = ownership()
    if not check_cluster(owner):
        raise RuntimeError("Owned cluster is missing")
    image = f"localhost/{owner['cluster']}-checkout:{version}"
    information = json.loads(run([engine(), "image", "inspect", image], capture=True))[0]
    if information["Config"].get("Labels", {}).get(LABEL) != owner["id"]:
        raise RuntimeError(f"Checkout image is no longer owned by this run: {image}")
    verify_image(information, "checkout", version, 400 if version == "v41" else 920)
    # Kubelet may garbage-collect the inactive version during a long tutorial.
    import_images(owner, [image])
    kubectl("set", "image", "deployment/checkout", f"app={image}")
    kubectl("rollout", "status", "deployment/checkout", "--timeout=180s")
    kubectl("label", "deployment/checkout", f"version={version}", "--overwrite")
    wait_until(f"checkout {version} control endpoint", lambda: get_json(
        f"http://127.0.0.1:{os.environ['CHECKOUT_CONTROL_PORT']}/state")["version"] == version)


def number(value):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("Expected a finite, nonnegative number")
    return result


def check_ports(*keys):
    for key in keys:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("0.0.0.0", int(os.environ[key])))
                probe.listen(1)
            except OSError as error:
                raise RuntimeError(f"{key}={os.environ[key]} is unavailable: {error}") from error


def compatibility(arguments):
    aliases = {
        "download": ["build"], "install-otel-plugin": ["build"],
        "setup-database": ["database"], "setup-cluster": ["cluster"],
        "start-server": ["start"], "start-demo": ["start-demo"],
        "cleanup": ["cleanup"], "reset": ["reset"], "roll-checkout": ["roll"],
        "set-latency": ["set-latency"], "set-slo": ["set-slo"],
        "start-heartbeat": ["heartbeat", "on"], "stop-heartbeat": ["heartbeat", "off"],
    }
    stem = Path(arguments[0]).stem
    trailing = [
        "--volumes" if item.lower() in ("-removevolumes", "-v") else item
        for item in arguments[1:] if item.lower() not in ("-version", "-value", "-threshold")
    ]
    return aliases[stem] + trailing


def set_slo(value):
    result = sql(f"UPDATE service_slo_policy SET threshold_ms={number(value)} "
                 "WHERE service_name='checkout' AND metric_name='latency_p99_ms' RETURNING service_name;")
    if result.splitlines() != ["checkout", "UPDATE 1"]:
        raise RuntimeError(f"Expected exactly one policy update; got {result!r}")
    print(result)


def cleanup(volumes=False):
    if (state() / "server.lock").exists():
        raise RuntimeError("Stop the foreground Server with Ctrl+C before cleanup")
    owner = ownership()
    nodes = check_cluster(owner)
    container = check_resource(owner, "container", owner["container"])
    volume = check_resource(owner, "volume", owner["volume"])
    if nodes:
        k3d("cluster", "delete", owner["cluster"])
    if container:
        run([engine(), "rm", "-f", owner["container"]])
    if volumes and volume:
        run([engine(), "volume", "rm", owner["volume"]])
    (state() / "kubeconfig.yaml").unlink(missing_ok=True)
    print("Owned cluster and container removed; database volume " + ("removed." if volumes else "preserved."))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("build", "verify-build", "database", "cluster", "start", "start-demo", "check", "reset"):
        commands.add_parser(action)
    clean = commands.add_parser("cleanup")
    clean.add_argument("--volumes", action="store_true")
    commands.add_parser("roll").add_argument("version", choices=("v41", "v42"), default="v42", nargs="?")
    commands.add_parser("heartbeat").add_argument("value", choices=("on", "off"))
    commands.add_parser("set-latency").add_argument("value", type=number)
    commands.add_parser("set-slo").add_argument("value", type=number)
    commands.add_parser("sql").add_argument("statement")
    commands.add_parser("kubectl").add_argument("arguments", nargs=argparse.REMAINDER)
    arguments = sys.argv[1:]
    if arguments and arguments[0] == "compat":
        arguments = compatibility(arguments[1:])
    args = parser.parse_args(arguments)
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
        elif args.action == "check":
            print(json.dumps(check(), indent=2))
        elif args.action == "cleanup":
            cleanup(args.volumes)
        elif args.action == "roll":
            roll(args.version)
        elif args.action == "heartbeat":
            print(control("heartbeat/" + args.value))
        elif args.action == "set-latency":
            print(control(f"delay/{args.value}"))
        elif args.action == "set-slo":
            set_slo(args.value)
        elif args.action == "sql":
            print(sql(args.statement))
        elif args.action == "kubectl":
            kubectl(*args.arguments)
        elif args.action == "reset":
            roll("v41")
            control("delay/400")
            control("heartbeat/on")
            set_slo(750)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
