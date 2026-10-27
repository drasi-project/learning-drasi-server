#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Compare the inventory, findings and dashboard with real PostgreSQL/Pod data.

Read-only by default. --exercise drives the published flow and restores its
inputs; use an isolated run and stop other writers before exercising it.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import demo


def sources():
    demo.verify_namespace()
    pods = json.loads(demo.kubectl("get", "pods", "-o", "json", capture=True))["items"]
    risks = json.loads(demo.sql('''SELECT coalesce(json_agg(row_to_json(r)), '[]'::json)
                                 FROM (SELECT * FROM "RiskyImage" ORDER BY "Id") r;'''))
    return pods, risks


def expected_results(pods, risks):
    inventory = [
        {"pod": pod["metadata"]["name"], "namespace": pod["metadata"]["namespace"],
         "container": container["name"], "image": container["image"]}
        for pod in pods for container in pod["spec"]["containers"]
    ]
    findings = [
        dict(container, reason=risk["Reason"], mitigation=risk["Mitigation"])
        for container in inventory for risk in risks if container["image"] == risk["Image"]
    ]
    return {"pod-containers": inventory, "high-risk-containers": findings}


def assert_rows(actual, expected, label):
    canonical = lambda rows: sorted(json.dumps(row, sort_keys=True) for row in rows)
    if canonical(actual) != canonical(expected):
        raise AssertionError(f"{label}: actual {actual!r} != expected {expected!r}")


def capture(name):
    demo.check()
    pods, risks = sources()
    expected = expected_results(pods, risks)
    deadline = time.monotonic() + 30
    while True:
        try:
            actual = {}
            for query in ("pod-containers", "high-risk-containers"):
                actual[query] = demo.api(f"queries/{query}/results")
                assert_rows(actual[query], expected[query], query)
            dashboard = demo.get_json(
                f"http://127.0.0.1:{demo.ownership()['ports']['DASHBOARD_PORT']}"
                "/api/queries/high-risk-containers/snapshot")
            keys = [row["k"] for row in dashboard["rows"]]
            if len(set(keys)) != len(keys):
                raise AssertionError(f"Duplicate dashboard row identities: {keys}")
            assert_rows([row["v"] for row in dashboard["rows"]],
                        expected["high-risk-containers"], "dashboard")
            print(f"PASS {name}: {len(actual['pod-containers'])} containers, "
                  f"{len(actual['high-risk-containers'])} findings; dashboard matches")
            return {"scenario": name, "expected": expected, "actual": actual, "dashboard": dashboard,
                    "pods": pods, "risks": risks}
        except AssertionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def count(snapshot, expected):
    actual = len(snapshot["actual"]["high-risk-containers"])
    if actual != expected:
        raise AssertionError(f"Expected {expected} findings, got {actual}")


def exercise():
    pods, risks = sources()
    if {pod["metadata"]["name"] for pod in pods} != {"my-app-1", "my-app-2"}:
        raise RuntimeError("--exercise requires exactly the two tutorial Pods")
    if {risk["Id"] for risk in risks} != {1, 2}:
        raise RuntimeError("--exercise requires only the two seeded risk rows; reset first")
    for pod in pods:
        if [item["name"] for item in pod["spec"]["containers"]] != ["app"]:
            raise RuntimeError("--exercise requires the original single-container Pods")
    evidence = []
    try:
        demo.reset(101)
        baseline = capture("initial single risk")
        count(baseline, 1)
        evidence.append(baseline)
        demo.add_risk("ghcr.io/drasi-project/my-app:0.2", "Critical Bug", "Update to latest version", 101)
        added = capture("new risk: my-app-2 appears")
        count(added, 2)
        evidence.append(added)
        demo.add_risk("ghcr.io/drasi-project/my-app:0.2", "Critical Bug (confirmed)", "Upgrade to :0.3", 101)
        updated = capture("risk update propagates without duplicate findings")
        count(updated, 2)
        before = {row["v"]["pod"]: row["k"] for row in added["dashboard"]["rows"]}
        after = {row["v"]["pod"]: row["k"] for row in updated["dashboard"]["rows"]}
        if before != after:
            raise AssertionError("Risk property update changed the dashboard finding identity")
        evidence.append(updated)
        demo.upgrade("my-app-2", "ghcr.io/drasi-project/my-app:0.3")
        upgraded = capture("safe Pod image removes my-app-2")
        count(upgraded, 1)
        evidence.append(upgraded)
        demo.reset(101)
        reset = capture("reset restores the original flow")
        count(reset, 1)
        evidence.append(reset)
        demo.sql('DELETE FROM "RiskyImage" WHERE "Id" = 1;')
        clear = capture("all-clear dashboard after removing the matching risk")
        count(clear, 0)
        evidence.append(clear)
    finally:
        for risk in risks:
            demo.add_risk(risk["Image"], risk["Reason"], risk["Mitigation"], risk["Id"])
        demo.sql('DELETE FROM "RiskyImage" WHERE "Id" = 101;')
        for pod in pods:
            demo.upgrade(pod["metadata"]["name"], pod["spec"]["containers"][0]["image"])
    evidence.append(capture("original inputs restored"))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise", action="store_true")
    parser.add_argument("--output", type=Path, help="Write observed source/results evidence as JSON")
    args = parser.parse_args()
    try:
        demo.environment()
        observations = exercise() if args.exercise else [capture("current state")]
        if args.output:
            args.output.write_text(json.dumps(observations, indent=2) + "\n")
    except (OSError, ValueError, KeyError, RuntimeError, AssertionError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
