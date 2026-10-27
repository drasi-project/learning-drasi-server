#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Compare all six queries and dashboard snapshots with the actual source rows.

The default is read-only. --exercise changes the seeded demo's sensor readings
and adds/removes one temporary room, then restores the original readings.
Stop other writers/the simulator before running it.
"""

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import demo


def source_rooms():
    return json.loads(demo.sql("""
        SELECT coalesce(json_agg(row_to_json(room)), '[]'::json) FROM (
          SELECT r.*, f.name AS floor_name, b.id AS building_id, b.name AS building_name
          FROM "Room" r JOIN "Floor" f ON r.floor_id=f.id
          JOIN "Building" b ON f.building_id=b.id ORDER BY r.id
        ) room;
    """))


def expected_results(rooms):
    result = {query: [] for query in demo.QUERIES}
    floors = {}
    buildings = {}
    for room in rooms:
        comfort = math.floor(50 + room["temperature"] - 72 + room["humidity"] - 42
                             + max(room["co2"] - 500, 0) / 25)
        row = {
            "RoomId": room["id"], "RoomName": room["name"],
            "FloorId": room["floor_id"], "FloorName": room["floor_name"],
            "BuildingId": room["building_id"], "BuildingName": room["building_name"],
            "Temperature": room["temperature"], "Humidity": room["humidity"],
            "CO2": room["co2"], "ComfortLevel": comfort,
        }
        result["room-comfort"].append(row)
        if comfort < 40 or comfort > 50:
            result["room-alert"].append({key: row[key] for key in ("RoomId", "RoomName", "ComfortLevel")})
        floors.setdefault(room["floor_id"], []).append((room, comfort))
    for identifier, entries in floors.items():
        room = entries[0][0]
        comfort = sum(value for _, value in entries) / len(entries)
        row = {
            "FloorId": identifier, "FloorName": room["floor_name"],
            "BuildingId": room["building_id"], "BuildingName": room["building_name"],
            "ComfortLevel": comfort,
        }
        result["floor-comfort-level-calc"].append(row)
        if comfort < 40 or comfort > 50:
            result["floor-alert"].append(
                {key: row[key] for key in ("FloorId", "FloorName", "ComfortLevel")}
            )
        buildings.setdefault(room["building_id"], []).append((room, comfort))
    for identifier, entries in buildings.items():
        comfort = sum(value for _, value in entries) / len(entries)
        row = {
            "BuildingId": identifier, "BuildingName": entries[0][0]["building_name"],
            "ComfortLevel": comfort,
        }
        result["building-comfort-level-calc"].append(row)
        if comfort < 40 or comfort > 50:
            result["building-alert"].append(dict(row))
    return result


def assert_rows(actual, expected, label):
    def identity(row):
        return tuple(str(row[key]) for key in ("RoomId", "FloorId", "BuildingId") if key in row)
    actual = sorted(actual, key=identity)
    expected = sorted(expected, key=identity)
    if len(actual) != len(expected):
        raise AssertionError(f"{label}: expected {len(expected)} rows, got {actual}")
    for left, right in zip(actual, expected):
        if left.keys() != right.keys():
            raise AssertionError(f"{label}: fields differ: {left} != {right}")
        for key, value in right.items():
            received = left[key]
            equal = (isinstance(received, (int, float))
                     and math.isclose(received, value, rel_tol=0, abs_tol=1e-7)) \
                if isinstance(value, (int, float)) else received == value
            if not equal:
                raise AssertionError(f"{label}: {key}: expected {value!r}, got {received!r}")


def capture(name):
    demo.check()
    expected = expected_results(source_rooms())
    deadline = time.monotonic() + 30
    while True:
        snapshots = {}
        try:
            for query in demo.QUERIES:
                response = demo.get_json(demo.api_url() + f"/queries/{query}/results")
                if response.get("success") is not True:
                    raise RuntimeError(f"Query read failed: {response}")
                assert_rows(response["data"], expected[query], f"Server {query}")
                snapshot = demo.get_json(
                    f"http://127.0.0.1:{os.environ.get('DASHBOARD_PORT', '3000')}"
                    f"/api/queries/{query}/snapshot")
                keys = [row["k"] for row in snapshot["rows"]]
                if len(set(keys)) != len(keys):
                    raise AssertionError(f"Duplicate dashboard row identities for {query}: {keys}")
                assert_rows([row["v"] for row in snapshot["rows"]], expected[query],
                            f"Dashboard {query}")
                snapshots[query] = snapshot
            print(f"PASS {name}: all six query results and dashboard snapshots match source data")
            return {"scenario": name, "expected": expected, "dashboard": snapshots}
        except AssertionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)


def exercise():
    original = source_rooms()
    ids = {f"room_01_{floor:02}_{room:02}" for floor in range(1, 4) for room in range(1, 4)}
    if {room["id"] for room in original} != ids:
        raise RuntimeError("--exercise requires exactly the nine seeded rooms; use an isolated demo")
    probe_created = False
    evidence = []
    try:
        demo.reset_room()
        baseline = capture("comfortable baseline")
        evidence.append(baseline)
        demo.set_room("room_01_01_01", 40, 20, 700)
        changed = capture("one cold room: room and floor alerts, no building alert")
        before = {row["v"]["RoomId"]: row["k"] for row in baseline["dashboard"]["room-comfort"]["rows"]}
        after = {row["v"]["RoomId"]: row["k"] for row in changed["dashboard"]["room-comfort"]["rows"]}
        if before != after:
            raise AssertionError("Updating a room changed its dashboard row identity")
        evidence.append(changed)
        demo.reset_room("room_01_01_01")
        evidence.append(capture("single-room reset"))
        demo.set_room("room_01_02_03", 82, 40, 10)
        evidence.append(capture("hot room: floor average exactly 50 does not alert"))
        demo.reset_room()
        demo.set_room("room_01_01_01", 40, 20, 700)
        demo.set_room("room_01_01_02", 40, 20, 700)
        evidence.append(capture("two cold rooms: building alert"))
        demo.reset_room()
        evidence.append(capture("multi-row transaction clears every alert"))
        demo.sql("""INSERT INTO "Room" (id,name,temperature,humidity,co2,floor_id)
                    VALUES ('room_migration_probe','Migration probe',82,40,10,'floor_01_01');""")
        probe_created = True
        unequal = capture("insert: unequal floor sizes still average floors correctly")
        evidence.append(unequal)
        floor = next(row["ComfortLevel"] for row in unequal["expected"]["floor-comfort-level-calc"]
                     if row["FloorId"] == "floor_01_01")
        building = unequal["expected"]["building-comfort-level-calc"][0]["ComfortLevel"]
        rooms = unequal["expected"]["room-comfort"]
        room_average = sum(row["ComfortLevel"] for row in rooms) / len(rooms)
        print(f"Unequal floors: Floor 01 = {floor:g}; building = {building:g}; "
              f"averaging all rooms directly would give {room_average:g}.")
        demo.sql("""DELETE FROM "Room" WHERE id='room_migration_probe';""")
        probe_created = False
        evidence.append(capture("delete restores nine rooms and all aggregates"))
        demo.simulate(0.2, count=3)
        evidence.append(capture("three real simulator updates"))
    finally:
        if probe_created:
            demo.sql("""DELETE FROM "Room" WHERE id='room_migration_probe';""")
        for room in original:
            demo.set_room(room["id"], room["temperature"], room["humidity"], room["co2"])
    evidence.append(capture("original readings restored"))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise", action="store_true")
    parser.add_argument("--output", type=Path, help="Write the successful result captures as JSON")
    args = parser.parse_args()
    try:
        demo.load_environment()
        evidence = exercise() if args.exercise else [capture("current source state")]
        if args.output:
            args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    except (OSError, ValueError, RuntimeError, AssertionError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
