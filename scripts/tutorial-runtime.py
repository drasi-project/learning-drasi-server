#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
"""Isolated infrastructure for evaluating the published server tutorials.

This prepares real tutorial databases, not substitute fixtures. The optional
serve action requires an explicitly hashed ComputationGraph-only server build
and checks the live instance's identity and running status. There is no engine
selector.
Infrastructure readiness is never reported as a tutorial acceptance result.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TUTORIALS = (
    "getting-started",
    "building-comfort",
    "high-risk-containers",
    "curbside-pickup",
)
DATABASES = ("getting_started", "building_comfort", "high_risk_containers", "RetailOperations")


def command(args, evidence, name, *, stdin=None, env=None):
    result = subprocess.run(
        [str(arg) for arg in args],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        timeout=300,
    )
    (evidence / f"{name}.log").write_text(
        f"$ {shlex.join([str(arg) for arg in args])}\n"
        f"{result.stdout}{result.stderr}\nexit_code={result.returncode}\n"
    )
    if result.returncode:
        raise RuntimeError(f"{name} failed; see {evidence / (name + '.log')}")
    return result.stdout


def free_ports(ports):
    for port in ports:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))


def prepare(args):
    index = TUTORIALS.index(args.tutorial)
    project = f"{args.run_id}-{args.tutorial}"
    evidence = args.output.resolve() / args.tutorial
    if evidence.exists():
        raise RuntimeError(f"Refusing to overwrite existing evaluation: {evidence}")
    evidence.mkdir(parents=True)
    tutorial = ROOT / "tutorials" / args.tutorial
    port = args.base_port + index * 10
    free_ports(range(port, port + 6))
    existing = command(
        ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
        evidence, "01-existing-resources",
    )
    if existing.strip():
        raise RuntimeError(f"Compose project {project} already owns containers")
    existing_volumes = command(
        ["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"],
        evidence, "02-existing-volumes",
    )
    if existing_volumes.strip():
        raise RuntimeError(f"Compose project {project} already owns data volumes")
    compose = json.loads(command(
        ["docker", "compose", "-f", tutorial / "database/docker-compose.yml", "config", "--format", "json"],
        evidence, "03-published-compose",
    ))
    compose["name"] = project
    for name, service in compose["services"].items():
        service["container_name"] = f"{project}-{name}"
        service["labels"] = {"io.drasi.tutorial-evaluation": args.run_id}
        service["ports"] = [{
            "target": 5432 if name == "postgres" else 3306,
            "published": str(port + (0 if name == "postgres" else 1)),
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        }]
    for name, network in compose.get("networks", {}).items():
        network.pop("external", None)
        network["name"] = f"{project}-{name}"
    for name, volume in compose.get("volumes", {}).items():
        volume["name"] = f"{project}-{name}"
    for kind, resources in (("volume", compose.get("volumes", {})), ("network", compose.get("networks", {}))):
        existing_names = set(command(
            ["docker", kind, "ls", "--format", "{{.Name}}"],
            evidence, f"03-existing-{kind}-names",
        ).splitlines())
        collisions = existing_names.intersection(resource["name"] for resource in resources.values())
        if collisions:
            raise RuntimeError(f"Refusing to reuse existing {kind}s: {', '.join(collisions)}")
    compose_file = evidence / "compose.json"
    compose_file.write_text(json.dumps(compose, indent=2) + "\n")
    environment = {
        "COMPOSE_PROJECT_NAME": project,
        "POSTGRES_CONTAINER": f"{project}-postgres",
        "POSTGRES_HOST": "127.0.0.1",
        "DB_HOST": "127.0.0.1",
        "POSTGRES_PORT": str(port),
        "POSTGRES_HOST_PORT": str(port),
        "POSTGRES_DATABASE": DATABASES[index],
        "POSTGRES_USER": "drasi_user",
        "POSTGRES_PASSWORD": "drasi_password",
        "MYSQL_CONTAINER": f"{project}-mysql",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": str(port + 1),
        "MYSQL_DATABASE": "PhysicalOperations",
        "MYSQL_USER": "drasi_user",
        "MYSQL_PASSWORD": "drasi_password",
        "SERVER_HOST": "127.0.0.1",
        "SERVER_PORT": str(port + 2),
        "DASHBOARD_HOST": "127.0.0.1",
        "DASHBOARD_PORT": str(port + 3),
        "WEBUI_HOST": "127.0.0.1",
        "WEBUI_PORT": str(port + 4),
        "HTTP_SOURCE_PORT": str(port + 5),
    }
    config = tutorial / (
        "configs/getting-started-step-3.yaml"
        if args.tutorial == "getting-started" else "server-config.yaml"
    )
    text = config.read_text()
    if args.tutorial == "getting-started":
        text = text.replace("host: 0.0.0.0\n", 'host: "${SERVER_HOST:-127.0.0.1}"\n', 1)
        text = text.replace("port: 8080\n", "port: ${SERVER_PORT:-8080}\n", 1)
        text = text.replace("  port: 5432\n", "  port: ${POSTGRES_PORT:-5432}\n", 1)
    config_file = evidence / "server-config.yaml"
    config_file.write_text(text)
    environment["CONFIG_FILE"] = str(config_file)
    (evidence / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    (evidence / "environment.sh").write_text(
        "\n".join(f"export {key}={shlex.quote(value)}" for key, value in environment.items()) + "\n"
    )
    (evidence / "ownership.json").write_text(json.dumps({
        "run_id": args.run_id,
        "project": project,
        "tutorial": args.tutorial,
        "compose_file": str(compose_file),
        "tutorial_revision": command(["git", "-C", ROOT, "rev-parse", "HEAD"], evidence, "04-revision").strip(),
    }, indent=2) + "\n")
    command(
        ["docker", "compose", "-p", project, "-f", compose_file, "up", "-d", "--wait", "--wait-timeout", "180"],
        evidence, "05-databases-up",
    )
    sql_name = "postgres-init.sql" if args.tutorial == "curbside-pickup" else "init.sql"
    command(
        ["docker", "exec", "-i", environment["POSTGRES_CONTAINER"], "psql",
         "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASES[index]],
        evidence, "06-postgres-seed", stdin=(tutorial / "database" / sql_name).read_text(),
    )
    if args.tutorial == "curbside-pickup":
        command(
            ["docker", "exec", "-i", "-e", "MYSQL_PWD=root_admin",
             environment["MYSQL_CONTAINER"], "mysql", "-uroot"],
            evidence, "07-mysql-seed", stdin=(tutorial / "database/mysql-init.sql").read_text(),
        )
    command(
        ["docker", "compose", "-p", project, "-f", compose_file, "ps", "--format", "json"],
        evidence, "08-resources",
    )
    for service in compose["services"]:
        command(
            ["docker", "inspect", f"{project}-{service}"],
            evidence, f"09-{service}-inspect",
        )
    print(f"Prepared real {args.tutorial} databases. No server/tutorial result asserted.")
    print(f"Environment: source {shlex.quote(str(evidence / 'environment.sh'))}")
    print(f"Configuration: {config_file}")


def cleanup(args):
    evidence = args.output.resolve() / args.tutorial
    ownership = json.loads((evidence / "ownership.json").read_text())
    project = f"{args.run_id}-{args.tutorial}"
    if ownership["project"] != project or ownership["run_id"] != args.run_id:
        raise RuntimeError("Ownership manifest does not match requested cleanup")
    compose_file = evidence / "compose.json"
    if ownership["compose_file"] != str(compose_file):
        raise RuntimeError("Ownership manifest does not match evidence directory")
    command(
        ["docker", "compose", "-p", project, "-f", compose_file, "logs", "--no-color"],
        evidence, "98-database-final",
    )
    command(
        ["docker", "compose", "-p", project, "-f", compose_file, "down", "--volumes"],
        evidence, "99-databases-down",
    )
    if ownership.get("cluster"):
        verify_cluster(args.k3d, ownership["cluster"], args.run_id, evidence)
        command(
            [args.k3d, "cluster", "delete", ownership["cluster"]],
            evidence, "99-cluster-delete",
            env={**os.environ, "KUBECONFIG": str(evidence / "kubeconfig.yaml")},
        )
    print(f"Removed only the recorded Compose project {project}.")


def verify_cluster(k3d, cluster, run_id, evidence):
    nodes = json.loads(command(
        ["docker", "inspect", f"k3d-{cluster}-server-0"],
        evidence, "10-cluster-ownership",
    ))
    if nodes[0]["Config"]["Labels"].get("io.drasi.tutorial-evaluation") != run_id:
        raise RuntimeError(f"Refusing to touch cluster {cluster}: ownership label mismatch")


def cluster(args):
    if args.tutorial != "high-risk-containers":
        raise RuntimeError("Only High Risk Containers uses Kubernetes")
    evidence = args.output.resolve() / args.tutorial
    ownership = json.loads((evidence / "ownership.json").read_text())
    if ownership["run_id"] != args.run_id:
        raise RuntimeError("Ownership manifest does not match requested cluster")
    kubeconfig = evidence / "kubeconfig.yaml"
    environment = {**os.environ, "KUBECONFIG": str(kubeconfig)}
    clusters = json.loads(command(
        [args.k3d, "cluster", "list", "-o", "json"],
        evidence, "10-cluster-list", env=environment,
    ))
    if not any(item["name"] == args.run_id for item in clusters):
        free_ports([args.kube_port])
        command(
            [args.k3d, "cluster", "create", args.run_id,
             "--api-port", f"127.0.0.1:{args.kube_port}",
             "--kubeconfig-update-default=false", "--kubeconfig-switch-context=false",
             "--runtime-label", f"io.drasi.tutorial-evaluation={args.run_id}@all",
             "--k3s-arg", "--disable=traefik@server:0", "--wait", "--timeout", "180s"],
            evidence, "10-cluster-create", env=environment,
        )
    verify_cluster(args.k3d, args.run_id, args.run_id, evidence)
    ownership["cluster"] = args.run_id
    (evidence / "ownership.json").write_text(json.dumps(ownership, indent=2) + "\n")
    kubeconfig.write_text(command(
        [args.k3d, "kubeconfig", "get", args.run_id],
        evidence, "11-kubeconfig", env=environment,
    ))
    kubeconfig.chmod(0o600)
    kubectl = ["kubectl", "--kubeconfig", kubeconfig]
    namespace = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": args.run_id,
            "labels": {"io.drasi.tutorial-evaluation": args.run_id},
        },
    }
    command(
        [*kubectl, "apply", "-f", "-"], evidence, "12-namespace",
        stdin=json.dumps(namespace),
    )
    command(
        [*kubectl, "config", "set-context", "--current", "--namespace", args.run_id],
        evidence, "13-private-context",
    )
    pods = (ROOT / "tutorials/high-risk-containers/k8s/my-app.yaml").read_text()
    pods = pods.replace("namespace: default", f"namespace: {args.run_id}")
    (evidence / "pods.yaml").write_text(pods)
    command([*kubectl, "apply", "-f", evidence / "pods.yaml"], evidence, "14-pods")
    command(
        [*kubectl, "label", "pods", "my-app-1", "my-app-2",
         f"io.drasi.tutorial-evaluation={args.run_id}", "--overwrite"],
        evidence, "15-pod-ownership",
    )
    command(
        [*kubectl, "wait", "--for=condition=Ready", "pod/my-app-1", "pod/my-app-2", "--timeout=180s"],
        evidence, "16-pods-ready",
    )
    command([*kubectl, "get", "pods", "-o", "json"], evidence, "17-pod-state")
    config_file = evidence / "server-config.yaml"
    text = config_file.read_text()
    text = text.replace("      - default\n", f"      - {args.run_id}\n", 1)
    text = text.replace("kubeconfigPath: bin/kubeconfig.yaml", f"kubeconfigPath: {json.dumps(str(kubeconfig))}")
    config_file.write_text(text)
    print(f"Ready: owned cluster/namespace {args.run_id}, private kubeconfig {kubeconfig}")


def serve(args):
    if not args.server or not args.server_sha256 or not args.plugins:
        raise RuntimeError("serve requires --server, --server-sha256, and --plugins")
    server = args.server.resolve()
    plugins = args.plugins.resolve()
    if not plugins.is_dir():
        raise RuntimeError(f"Local plugin artifact directory does not exist: {plugins}")
    actual_hash = hashlib.sha256(server.read_bytes()).hexdigest()
    if actual_hash != args.server_sha256:
        raise RuntimeError(f"Server SHA256 mismatch: expected {args.server_sha256}, got {actual_hash}")
    evidence = args.output.resolve() / args.tutorial
    ownership = json.loads((evidence / "ownership.json").read_text())
    if ownership["run_id"] != args.run_id:
        raise RuntimeError("Ownership manifest does not match requested server")
    environment = json.loads((evidence / "environment.json").read_text())
    free_ports([int(environment["SERVER_PORT"]), int(environment["DASHBOARD_PORT"])])
    config = evidence / "server-config.yaml"
    text = config.read_text()
    text = re.sub(r"^pluginRegistry:.*\n", "", text, flags=re.MULTILINE)
    text = f"pluginRegistry: {json.dumps(str(plugins))}\n{text}"
    config.write_text(text)
    match = re.search(r"^id:\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        raise RuntimeError("Expected a top-level instance id in tutorial config")
    instance_id = match.group(1).strip("\"'")
    run = evidence / f"server-{time.time_ns()}"
    run.mkdir()
    argv = [
        str(server), "--config", str(config),
        "--plugins-dir", str(plugins), "--skip-verification",
    ]
    (run / "provenance.json").write_text(json.dumps({
        "server": str(server), "server_sha256": actual_hash, "argv": argv,
        "runtime": "computationGraph",
        "tutorial_revision": ownership["tutorial_revision"],
        "plugins": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in plugins.iterdir() if p.suffix in (".dylib", ".so", ".dll")},
        "note": "Signature verification skipped only for explicitly supplied local development artifacts.",
    }, indent=2) + "\n")
    with (run / "server.log").open("w") as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                   env={**os.environ, **environment}, cwd=evidence)
        (run / "pid").write_text(f"{process.pid}\n")
        old_term = signal.signal(signal.SIGTERM, lambda *_: process.send_signal(signal.SIGINT))
        try:
            deadline = time.monotonic() + 180
            url = f'http://127.0.0.1:{environment["SERVER_PORT"]}/api/v1/instances/{instance_id}/runtime'
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Server exited {process.returncode}; see {run / 'server.log'}")
                try:
                    with urllib.request.urlopen(url, timeout=3) as response:
                        proof = json.load(response)
                except (urllib.error.URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"Native runtime proof unavailable; see {run / 'server.log'}")
                    time.sleep(0.5)
                    continue
                (run / "native-runtime.json").write_text(json.dumps(proof, indent=2) + "\n")
                expected = {"instanceId": instance_id, "runtime": "computationGraph", "running": True}
                if not proof.get("success") or proof.get("data") != expected:
                    raise RuntimeError(f"Native runtime proof did not match: {proof}")
                print(f"Native ComputationGraph running: {url}\nEvidence: {run}", flush=True)
                break
            code = process.wait()
            if code:
                raise RuntimeError(f"Server exited {code}; see {run / 'server.log'}")
        finally:
            signal.signal(signal.SIGTERM, old_term)
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise RuntimeError(f"Server required forced shutdown; see {run / 'server.log'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "cluster", "serve", "cleanup"))
    parser.add_argument("tutorial", choices=TUTORIALS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-port", type=int, default=49100)
    parser.add_argument("--k3d", default="k3d", help="Path to an already installed k3d executable")
    parser.add_argument("--kube-port", type=int, default=49650)
    parser.add_argument("--server", type=Path)
    parser.add_argument("--server-sha256")
    parser.add_argument("--plugins", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,30}", args.run_id):
        parser.error("--run-id must be a unique 3-31 character lowercase project prefix")
    if not 1024 <= args.base_port <= 65499:
        parser.error("--base-port must leave room for all four tutorials above port 1023")
    try:
        {"prepare": prepare, "cluster": cluster, "serve": serve, "cleanup": cleanup}[args.action](args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
