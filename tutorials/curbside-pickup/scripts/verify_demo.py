#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors. Licensed under Apache-2.0.
"""Exercise real curbside actions on an isolated disposable running demo."""

import argparse
import json
import os
import sys
import time
import urllib.request

import demo

EVIDENCE = []


def rows(query):
    response = demo.get_json(demo.api_url() + f"/queries/{query}/results")
    if response.get("success") is not True:
        raise RuntimeError(f"{query} results failed: {response}")
    return response["data"]


def canonical(values):
    return sorted(json.dumps(value, sort_keys=True) for value in values)


def snapshots():
    values = {query: rows(query) for query in demo.QUERIES}
    for query in demo.PANELS:
        snapshot = demo.get_json(
            f"http://127.0.0.1:{os.environ['DASHBOARD_PORT']}/api/queries/{query}/snapshot")
        if canonical([row["v"] for row in snapshot["rows"]]) != canonical(values[query]):
            raise RuntimeError(f"Dashboard {query} snapshot differs from query results")
        keys = [row["k"] for row in snapshot["rows"]]
        if len(keys) != len(set(keys)) or any(not isinstance(key, str) for key in keys):
            raise RuntimeError(f"Invalid or duplicate dashboard row identities: {keys}")
    return values


def expect(name, counts, timeout=8):
    def check():
        values = snapshots()
        actual = {query: len(values[query]) for query in demo.QUERIES}
        if actual != dict(zip(demo.QUERIES, counts)):
            raise RuntimeError(f"{name}: unexpected counts {actual}")
        return values
    result = demo.wait_for(check, name, timeout)
    EVIDENCE.append({"step": name, "queries": result})
    print("PASS:", name, flush=True)
    return result


def toggle(kind, identity):
    request = urllib.request.Request(
        f"http://127.0.0.1:{os.environ['WEBUI_PORT']}/api/{kind}/{identity}/toggle",
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        state = json.load(response)
    if state.get("error"):
        raise RuntimeError(state["error"])
    EVIDENCE.append({"action": f"{kind}/{identity}/toggle", "console": state})
    return state


def no_delay_for(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if rows("delay"):
            raise RuntimeError("Unexpected early or canceled delay")
        time.sleep(0.1)


def verify():
    demo.check_ownership()
    demo.check()
    demo.reset()
    expect("reset and six initial panels", (3, 0, 3, 0, 0, 0, 3))
    toggle("orders", "1")
    expect("order ready moves panels", (2, 1, 3, 0, 0, 0, 3))
    toggle("vehicles", "A1234")
    result = expect("vehicle completes cross-database delivery", (2, 1, 2, 1, 1, 0, 3))
    delivery = result["delivery"][0]
    if not (delivery["orderId"] == 1 and delivery["vehicleId"] == "A1234"
            and delivery["driverName"] == "Elijah Brooks"
            and delivery["vehicleMake"] == "Toyota" and delivery["vehicleColor"] == "Blue"):
        raise RuntimeError(f"Wrong delivery projection: {delivery}")
    toggle("vehicles", "A1234")
    expect("departing vehicle removes delivery", (2, 1, 3, 0, 0, 0, 3))
    toggle("orders", "1")
    toggle("vehicles", "A1234")
    expect("vehicle first waits for preparing order", (3, 0, 2, 1, 0, 0, 3))
    toggle("orders", "1")
    expect("order completes reverse-order delivery", (2, 1, 2, 1, 1, 0, 3))
    toggle("vehicles", "A1234")
    demo.reset()
    expect("reset before timed wait", (3, 0, 3, 0, 0, 0, 3))
    started = time.monotonic()
    toggle("vehicles", "B5678")
    expect("curbside not immediately delayed", (3, 0, 2, 1, 0, 0, 3))
    # MySQL binlog event timestamps have one-second resolution.
    no_delay_for(max(0, 9 - (time.monotonic() - started)))
    result = expect("ten-second timer without another write", (3, 0, 2, 1, 0, 1, 3))
    elapsed = time.monotonic() - started
    if not 9 <= elapsed <= 16:
        raise RuntimeError(f"Delay fired outside the expected threshold window: {elapsed:.2f}s")
    if result["delay"][0]["orderId"] != 2 or result["delay"][0]["customerName"] != "Mason Rivera":
        raise RuntimeError(f"Wrong delayed order: {result['delay']}")
    EVIDENCE.append({"timerSeconds": elapsed})
    toggle("orders", "2")
    expect("ready cancels alert and creates match", (2, 1, 2, 1, 1, 0, 3))
    demo.reset()
    expect("reset after delayed delivery", (3, 0, 3, 0, 0, 0, 3))
    toggle("vehicles", "C9876")
    expect("pending vehicle wait", (3, 0, 2, 1, 0, 0, 3))
    time.sleep(2)
    toggle("vehicles", "C9876")
    expect("departure cancels wait", (3, 0, 3, 0, 0, 0, 3))
    no_delay_for(11)
    toggle("vehicles", "C9876")
    expect("new pending wait", (3, 0, 2, 1, 0, 0, 3))
    time.sleep(2)
    toggle("orders", "3")
    expect("ready cancels pending wait", (2, 1, 2, 1, 1, 0, 3))
    no_delay_for(11)
    demo.postgres("DELETE FROM orders WHERE id=3;")
    expect("delete removes shared join and delivery", (2, 0, 2, 1, 0, 0, 2))
    demo.postgres(
        "INSERT INTO orders (id,customer_name,driver_name,plate,status) "
        "VALUES (3,'Ava Mitchell','Liam Bennett','C9876','ready');")
    expect("reinsert restores one delivery without duplicates", (2, 1, 2, 1, 1, 0, 3))
    demo.reset()
    expect("final reset", (3, 0, 3, 0, 0, 0, 3))
    demo.check()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-reset", required=True, action="store_true",
                        help="Consent to modify/reset the disposable run's three seeded rows")
    parser.parse_args()
    demo.load_environment()
    output = demo.state_dir() / "scenario-evidence.json"
    try:
        verify()
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        EVIDENCE.append({"failure": str(error)})
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(EVIDENCE, indent=2) + "\n")
    print(f"Scenario evidence: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
