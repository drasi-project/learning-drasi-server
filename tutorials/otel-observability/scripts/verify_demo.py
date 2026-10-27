#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Exercise the actual running OTel store/Collector/policy/dashboard scenario.

Requires Node 22+ for the dashboard WebSocket check. Changes only the helper's
owned run. Start Server separately, then run this script from any directory.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import demo


def main():
    demo.environment()
    demo.ownership()
    demo.check()
    output = demo.state() / "verification"
    output.mkdir(exist_ok=True)
    snapshots = {}
    dashboard = f"http://127.0.0.1:{os.environ['DASHBOARD_PORT']}"

    def observe(name, query, predicate, timeout=90):
        def ready():
            rows = demo.results(query)
            if predicate(rows):
                snapshots[name] = rows
                (output / "results.json").write_text(json.dumps({
                    "complete": False, "observations": snapshots,
                }, indent=2) + "\n")
                return True
            return False
        demo.wait_until(name, ready, timeout)
        print(f"PASS {name}: {snapshots[name]}", flush=True)
        return snapshots[name]

    def checkout(rows, version, high=False):
        return len(rows) == 1 and rows[0]["service"] == "checkout" \
            and rows[0]["deployVersion"] == version \
            and (rows[0]["latencyMs"] > 750 if high else 100 < rows[0]["latencyMs"] < 750)

    def empty(rows):
        return rows == []

    def alert(rows):
        return len(rows) == 1 and rows[0]["service"] == "checkout"

    def dependencies(rows):
        return len(rows) == 2 and {(row["fromService"], row["toService"]) for row in rows} == {
            ("frontend", "checkout"), ("checkout", "payments"),
        }

    events = output / "dashboard-events.jsonl"
    ready = output / "dashboard-ready"
    events.write_text("")
    ready.unlink(missing_ok=True)
    watcher = subprocess.Popen([
        "node", str(Path(__file__).with_name("watch-dashboard.mjs")),
        f"ws://127.0.0.1:{os.environ['DASHBOARD_PORT']}/ws", str(events), str(ready),
    ])
    try:
        def connected():
            if watcher.poll() is not None:
                raise ChildProcessError("Dashboard WebSocket watcher exited")
            return ready.exists()
        demo.wait_until("dashboard WebSocket connection", connected, 15)
        with urllib.request.urlopen(dashboard + "/dashboard/otel-observability", timeout=5) as page:
            if page.status != 200 or b"<html" not in page.read().lower():
                raise RuntimeError("Dashboard HTML is unavailable")
        demo.kubectl("scale", "deployment/checkout", "--replicas=1")
        demo.roll("v41")
        demo.control("delay/400")
        demo.control("heartbeat/on")
        demo.set_slo(750)
        observe("three live service rows", "current-health",
                lambda rows: len(rows) == 3
                and {row["service"]: row["deployVersion"] for row in rows}
                == {"frontend": "v1", "checkout": "v41", "payments": "v1"}
                and all(row["deployVersion"] == row["rolloutVersion"] for row in rows))
        observe("healthy checkout v41", "checkout-health", lambda rows: checkout(rows, "v41"))
        observe("healthy SLO", "slo-alert", empty)
        observe("live CLIENT-span dependencies", "service-dependencies", dependencies)
        observe("positive checkout pulse", "checkout-heartbeat",
                lambda rows: len(rows) == 1 and rows[0]["pulse"] > 0)
        observe("healthy heartbeat", "missing-heartbeat", empty)

        demo.roll("v42")
        observe("rolled checkout v42", "checkout-health", lambda rows: checkout(rows, "v42", True))
        observe("rollout SLO Added", "slo-alert", lambda rows: alert(rows) and rows[0]["deployVersion"] == "v42")
        demo.roll("v41")
        observe("recovered checkout v41", "checkout-health", lambda rows: checkout(rows, "v41"))
        observe("rollout SLO Removed", "slo-alert", empty)

        for iteration in range(2):
            demo.set_slo(100)
            started = time.monotonic()
            while time.monotonic() - started < 3:
                if demo.results("slo-alert"):
                    raise RuntimeError("SLO alert fired before its five-second sustained window")
                time.sleep(0.2)
            observe(f"policy cycle {iteration + 1} Added", "slo-alert",
                    lambda rows: alert(rows) and rows[0]["thresholdMs"] == 100)
            if time.monotonic() - started < 4.5:
                raise RuntimeError("Policy alert did not sustain its condition for five seconds")
            demo.set_slo(750)
            observe(f"policy cycle {iteration + 1} Removed", "slo-alert", empty)

        demo.control("heartbeat/off")
        observe("explicit missing heartbeat Added", "missing-heartbeat", alert)
        demo.control("heartbeat/on")
        observe("explicit missing heartbeat Removed", "missing-heartbeat", empty)
        demo.kubectl("scale", "deployment/checkout", "--replicas=0")
        observe("absent exporter timer Added", "missing-heartbeat", alert, 45)
        observe("CLIENT-span edges expired", "service-dependencies", empty, 95)
        demo.kubectl("scale", "deployment/checkout", "--replicas=1")
        demo.roll("v41")
        observe("restored exporter timer Removed", "missing-heartbeat", empty)
        observe("restored dependency edges", "service-dependencies", dependencies)

        for query in demo.QUERIES:
            result = demo.get_json(dashboard + f"/api/queries/{query}/snapshot")
            rows = [row["v"] for row in result["rows"]]
            snapshots["dashboard " + query] = rows
            if query in ("slo-alert", "missing-heartbeat") and rows:
                raise RuntimeError(f"Dashboard retained resolved alert rows: {query}: {rows}")
            if query == "checkout-health" and not checkout(rows, "v41"):
                raise RuntimeError(f"Dashboard checkout KPI is not the recovered v41 row: {rows}")

        if watcher.poll() is not None:
            raise RuntimeError("Dashboard WebSocket watcher stopped before verification completed")
        messages = [json.loads(line) for line in events.read_text().splitlines()]
        for query in ("slo-alert", "missing-heartbeat"):
            operations = {
                diff["op"] for message in messages if message.get("query_id") == query
                for diff in message.get("results", [])
            }
            if not {"add", "delete"} <= operations:
                raise RuntimeError(f"Dashboard did not stream both add/delete for {query}: {operations}")
            signatures = {
                diff["k"] for message in messages if message.get("query_id") == query
                for diff in message.get("results", []) if diff["op"] in ("add", "delete")
            }
            if len(signatures) != 1 or "0" in signatures:
                raise RuntimeError(f"Alert identity changed across add/remove cycles: {query}: {signatures}")
        (output / "results.json").write_text(json.dumps({
            "complete": True, "observations": snapshots,
        }, indent=2) + "\n")
        print(f"PASS complete store scenario and live dashboard transitions. Evidence: {output}")
    finally:
        watcher.terminate()
        try:
            watcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher.wait()
        ready.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
