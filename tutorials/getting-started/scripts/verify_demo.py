#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
"""Execute the eight-step walkthrough on fresh owned data, including durable restart."""

import argparse
import json
import os
from pathlib import Path
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import demo


def wait_for(description, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = predicate()
            if last:
                return last
        except (urllib.error.URLError, TimeoutError) as error:
            last = str(error)
        time.sleep(0.2)
    raise AssertionError(f"{description} not satisfied within {timeout}s; last result: {last!r}")


def rows(query):
    return demo.api(demo.component_path("queries", query, "/results"))


def selected(query, **values):
    return [row for row in rows(query)
            if all(str(row.get(key)) == str(value) for key, value in values.items())]


def add_query(name):
    body = json.loads((demo.TUTORIAL / f"configs/{name}.json").read_text())
    demo.api("queries", method="POST", body=body)
    wait_for(f"{name} running",
             lambda: demo.api(demo.component_path("queries", name))["status"].lower() == "running")


def location(identifier, name, place, status="online", operation="insert"):
    request = urllib.request.Request(
        f"http://127.0.0.1:{os.environ['HTTP_PORT']}/sources/"
        f"{demo.component_id('location-tracker')}/events",
        method="POST", headers={"Content-Type": "application/json"},
        data=json.dumps({"operation": operation, "element": {
            "type": "node", "id": identifier, "labels": ["UserLocation"],
            "properties": {"name": name, "location": place, "status": status},
        }}).encode(),
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status not in (200, 201, 202):
            raise AssertionError(f"HTTP event rejected: {response.read()!r}")


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=35)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            raise RuntimeError("Owned process did not stop normally") from error
    if process.returncode not in (0, 130, -signal.SIGINT):
        raise RuntimeError(f"Owned process exited with {process.returncode}")


class Stream:
    """Observe the CLI-created reaction on its actual HTTP endpoint."""

    def __init__(self, query, directory):
        self.query = query
        self.query_id = demo.component_id(query)
        self.directory = directory
        self.frames = queue.Queue()
        self.received = []
        self.response = None
        self.stopping = threading.Event()

    def __enter__(self):
        self.log = (self.directory / f"{self.query}-cli.log").open("w")
        self.process = subprocess.Popen(
            [sys.executable, str(demo.TUTORIAL / "scripts/demo.py"), "stream", self.query],
            stdout=self.log, stderr=subprocess.STDOUT, env=os.environ.copy(), cwd=demo.TUTORIAL,
        )
        try:
            def connect():
                if self.process.poll() is not None:
                    raise RuntimeError(f"CLI exited; see {self.log.name}")
                self.response = urllib.request.urlopen(
                    f"http://127.0.0.1:{os.environ['SSE_PORT']}/events", timeout=90)
                return self.response
            wait_for("SSE connection", connect)
            self.thread = threading.Thread(target=self.read, daemon=True)
            self.thread.start()
            return self
        except BaseException:
            if self.process.poll() is None:
                stop(self.process)
            self.log.close()
            raise

    def read(self):
        try:
            for raw in self.response:
                if self.stopping.is_set():
                    break
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                body = json.loads(line[5:].strip())
                if body.get("type") == "heartbeat":
                    continue
                if body.get("queryId") != self.query_id or not isinstance(body.get("results"), list):
                    raise AssertionError(f"Unexpected SSE adapter payload: {body}")
                self.received.append(body)
                self.frames.put(body)
        except (OSError, ValueError, AssertionError) as error:
            if not self.stopping.is_set():
                self.frames.put(error)

    def change(self, description, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                body = self.frames.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if isinstance(body, Exception):
                raise body
            for result in body["results"]:
                if predicate(result):
                    if not isinstance(result.get("row_signature"), int):
                        raise AssertionError(f"Missing row identity: {result}")
                    return result
        raise AssertionError(f"No SSE difference for {description}; frames: {self.received}")

    def __exit__(self, *_):
        self.stopping.set()
        try:
            stop(self.process)
            self.thread.join(timeout=5)
            self.response.close()
            wait_for("CLI removes temporary reaction",
                     lambda: not any(r["id"].startswith("sse-cli-") for r in demo.api("reactions")))
        finally:
            self.log.close()
            (self.directory / f"{self.query}-events.json").write_text(
                json.dumps(self.received, indent=2) + "\n")


def attached(query, change, predicate, timeout=30):
    """Read the query's attach stream: its snapshot, then the first matching change."""
    url = (f"http://127.0.0.1:{os.environ['SERVER_PORT']}/api/v1/instances/{demo.INSTANCE}"
           f"/queries/{query}/attach")
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if not response.headers.get("Content-Type", "").startswith("text/event-stream"):
            raise AssertionError(f"attach is not an event stream: {response.headers}")
        snapshot, event, data = None, None, []
        for raw in response:
            line = raw.decode().rstrip("\r\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
            elif not line and data:
                body = json.loads("\n".join(data))
                if event == "snapshot":
                    snapshot = body
                    change()
                elif snapshot is None:
                    raise AssertionError(f"attach sent a change before its snapshot: {body}")
                elif any(predicate(result) for result in body["results"]):
                    return snapshot, body
                event, data = None, []
    raise AssertionError("attach stream ended before the expected change")


def edit_working_config(old, new):
    """Make the same text edit as the reader in Step 8."""
    path = demo.state() / "getting-started.yaml"
    text = path.read_text()
    if text.count(old) != 1:
        raise AssertionError(f"Expected exactly one {old!r} in {path}")
    path.write_text(text.replace(old, new))


def free_ports():
    probes = []
    try:
        for _ in range(4):
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            probes.append(probe)
        return [str(probe.getsockname()[1]) for probe in probes]
    finally:
        for probe in probes:
            probe.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=f"getting-started-check-{uuid.uuid4().hex[:10]}")
    args = parser.parse_args()
    os.environ["DRASI_RUN_ID"] = args.run_id
    for key, port in zip(("POSTGRES_PORT", "SERVER_PORT", "SSE_PORT", "HTTP_PORT"), free_ports()):
        os.environ[key] = port
    demo.environment()
    directory = demo.state()
    if directory.exists():
        raise RuntimeError(f"Acceptance requires a new run directory: {directory}")
    demo.local_build().verified_build(demo.build_state(), demo.PLUGINS)
    demo.cli_build(verify=True)
    directory.mkdir(parents=True)
    checks = []
    server = None
    logs = []

    def passed(name):
        checks.append(name)
        print(f"PASS: {name}", flush=True)

    def launch(name):
        log = (directory / name).open("w")
        logs.append(log)
        process = subprocess.Popen(
            [sys.executable, str(demo.TUTORIAL / "scripts/demo.py"), "start"],
            stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy(), cwd=demo.TUTORIAL)
        def ready():
            if process.poll() is not None:
                raise RuntimeError(f"Server exited; see {log.name}")
            try:
                return demo.check()
            except RuntimeError:
                return False
        try:
            wait_for("Server readiness", ready, 120)
        except BaseException:
            stop(process)
            raise
        return process

    error = None
    try:
        demo.database()
        server = launch("server.log")
        wait_for("four bootstrap rows", lambda: len(rows("all-messages")) == 4)
        passed("step 3: four Message rows and exact ComputationGraph readiness")

        with Stream("all-messages", directory) as stream:
            demo.sql("""INSERT INTO "Message" ("From","Message") VALUES ('You','My first message!');""")
            added = stream.change("insert", lambda r: r["type"] == "ADD" and r["data"]["From"] == "You")
            wait_for("insert in current results", lambda: selected("all-messages", From="You"))
            demo.sql("""UPDATE "Message" SET "Message"='My first UPDATED message!' WHERE "From"='You';""")
            updated = stream.change("update", lambda r: r["type"] == "UPDATE" and r["after"]["From"] == "You")
            assert updated["before"]["Message"] == "My first message!"
            assert updated["after"]["Message"] == "My first UPDATED message!"
            assert updated["row_signature"] == added["row_signature"]
            demo.sql("""DELETE FROM "Message" WHERE "From"='You';""")
            deleted = stream.change("delete", lambda r: r["type"] == "DELETE" and r["data"]["From"] == "You")
            assert deleted["row_signature"] == added["row_signature"]
            wait_for("delete in results", lambda: not selected("all-messages", From="You"))
        passed("step 3: insert/update/delete and stable result identity over ordinary SSE")

        add_query("hello-world-senders")
        demo.api(demo.component_path("reactions", "log-reaction"), method="PUT", body={
            "kind": "log", "id": demo.component_id("log-reaction"),
            "name": "log-reaction", "autoStart": True,
            "queries": [
                {"id": demo.component_id("all-messages")},
                {"id": demo.component_id("hello-world-senders")},
            ]})
        wait_for("chained initial snapshot", lambda: selected("hello-world-senders", Sender="Brian Kernighan"))
        demo.sql("""INSERT INTO "Message" ("From","Message") VALUES
                    ('Alice','Hello World'), ('Bob','Goodbye World');""")
        wait_for("Alice filtered", lambda: selected("hello-world-senders", Sender="Alice"))
        wait_for("Bob in upstream", lambda: selected("all-messages", From="Bob"))
        assert not selected("hello-world-senders", Sender="Bob")
        view = demo.graph()
        for line in ("  my-postgres -> all-messages\n",
                     "  all-messages -> hello-world-senders  (data + bootstrap)\n",
                     "  all-messages -> log-reaction\n", "  hello-world-senders -> log-reaction"):
            assert line in view + "\n", f"Missing {line!r} in graph view:\n{view}"
        (directory / "graph-step-4.txt").write_text(view + "\n")
        passed("step 4: query-output bootstrap, Alice included and Bob excluded; graph connections")

        add_query("message-counts")
        wait_for("Hello World count 2", lambda: selected("message-counts", MessageText="Hello World", Count=2))
        with Stream("message-counts", directory) as stream:
            demo.sql("""INSERT INTO "Message" ("From","Message") VALUES ('Eve','Hello World');""")
            increase = stream.change("count 2 to 3", lambda r: r["type"] == "aggregation"
                                     and r["after"] == {"MessageText": "Hello World", "Count": 3})
            assert increase["before"] == {"MessageText": "Hello World", "Count": 2}
            demo.sql("""DELETE FROM "Message" WHERE "From"='Eve';""")
            decrease = stream.change("count 3 to 2", lambda r: r["type"] == "aggregation"
                                     and r["after"] == {"MessageText": "Hello World", "Count": 2})
            assert decrease["before"] == {"MessageText": "Hello World", "Count": 3}
            assert decrease["row_signature"] == increase["row_signature"]
        passed("step 5: exact count transitions 2 -> 3 -> 2 over SSE")

        snapshot, change = attached(
            "message-counts",
            lambda: demo.sql("""INSERT INTO "Message" ("From","Message") VALUES ('Eve','Hello World');"""),
            lambda r: r["type"] == "aggregation" and r["after"] == {"MessageText": "Hello World", "Count": 3})
        assert {"MessageText": "Hello World", "Count": 2} in snapshot, snapshot
        assert change["query_id"] == demo.component_id("message-counts") and change["sequence"] > 0
        demo.sql("""DELETE FROM "Message" WHERE "From"='Eve';""")
        wait_for("Eve removed", lambda: selected("message-counts", MessageText="Hello World", Count=2))
        log = (directory / "watch-cli.log").open("w")
        logs.append(log)
        watcher = subprocess.Popen(
            [sys.executable, str(demo.TUTORIAL / "scripts/demo.py"), "watch", "message-counts"],
            stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy(), cwd=demo.TUTORIAL)
        try:
            wait_for("watch snapshot", lambda: "Live changes follow" in
                     (directory / "watch-cli.log").read_text(), 15)
        finally:
            stop(watcher)
        assert "Snapshot of the query's 4 current row(s):" in (directory / "watch-cli.log").read_text()
        passed("step 5: attach snapshot then change, and watch prints the snapshot without a reaction")

        add_query("inactive-senders")
        with Stream("inactive-senders", directory) as stream:
            wait_for("Alice initial inactivity", lambda: selected("inactive-senders", MessageFrom="Alice"), 35)
            for message in ("About to go inactive", "Active again"):
                began = time.monotonic()
                demo.sql('INSERT INTO "Message" ("From","Message") VALUES (\'Alice\', :\'message\');',
                         variables={"message": message})
                stream.change("Alice active", lambda r: r["type"] == "DELETE" and r["data"]["MessageFrom"] == "Alice")
                wait_for("Alice absent", lambda: not selected("inactive-senders", MessageFrom="Alice"))
                stream.change("Alice inactive without another write", lambda r: r["type"] == "ADD"
                              and r["data"]["MessageFrom"] == "Alice", 30)
                assert time.monotonic() - began >= 19.9, "Inactivity appeared before the 20-second window"
                wait_for("Alice returned", lambda: selected("inactive-senders", MessageFrom="Alice"))
        passed("step 6: two source-timestamp active/idle cycles with 20-second timer")

        demo.api("sources", method="POST", body={
            "kind": "http", "id": demo.component_id("location-tracker"),
            "name": "location-tracker", "autoStart": True,
            "host": "127.0.0.1", "port": int(os.environ["HTTP_PORT"]),
            "bootstrapProvider": {"kind": "scriptfile", "filePaths": [str(demo.TUTORIAL / "locations.jsonl")]}})
        add_query("messages-with-location")
        wait_for("initial Brian join", lambda: selected("messages-with-location", Sender="Brian Kernighan",
                                                       Location="Building A, Floor 3", Status="online"))
        with Stream("messages-with-location", directory) as stream:
            location("brian", "Brian Kernighan", "Conference Room B", "away", "update")
            moved = stream.change("Brian moves", lambda r: r["type"] == "UPDATE"
                                  and r["after"]["Sender"] == "Brian Kernighan")
            assert moved["before"]["Location"] == "Building A, Floor 3"
            assert moved["after"]["Location"] == "Conference Room B"
            assert moved["after"]["Status"] == "away"
            demo.sql("""INSERT INTO "Message" ("From","Message") VALUES ('Carol','Good morning!');""")
            wait_for("Carol upstream", lambda: selected("all-messages", From="Carol"))
            assert not selected("messages-with-location", Sender="Carol")
            location("carol", "Carol", "Home Office")
            stream.change("Carol joins", lambda r: r["type"] == "ADD"
                          and r["data"]["Sender"] == "Carol" and r["data"]["Location"] == "Home Office")
            demo.sql("""UPDATE "Message" SET "Message"='Good afternoon!' WHERE "From"='Carol';""")
            stream.change("Carol message update", lambda r: r["type"] == "UPDATE"
                          and r["after"]["Sender"] == "Carol" and r["after"]["Message"] == "Good afternoon!")
        view = demo.graph()
        assert "  location-tracker -> messages-with-location\n" in view + "\n", view
        assert "  all-messages -> messages-with-location  (data + bootstrap)" in view, view
        passed("step 7: HTTP and PostgreSQL changes both propagate through the chained join")

        stop(server)
        server = None
        edit_working_config("  persistIndex: false\n", "  persistIndex: true\n")
        rejected_log = directory / "durable-rejected.log"
        with rejected_log.open("w") as log:
            rejected = subprocess.Popen(
                [sys.executable, str(demo.TUTORIAL / "scripts/demo.py"), "start"],
                stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy(), cwd=demo.TUTORIAL)
            try:
                rejected.wait(timeout=120)
            except subprocess.TimeoutExpired:
                stop(rejected)
                raise AssertionError("A durable HTTP-fed query was not rejected")
        output = rejected_log.read_text()
        assert rejected.returncode != 0, output
        assert ("IncompatibleSource: sources that do not support replay cannot feed persistent query "
                f"'{demo.component_id('messages-with-location')}' "
                f"(source '{demo.component_id('location-tracker')}', supports_replay=false)") in output, output
        edit_working_config("    result:\n      label: LocatedMessage\n",
                            "    result:\n      label: LocatedMessage\n"
                            "    storageBackend:\n      kind: memory\n")
        server = launch("durable.log")
        wait_for("durable queries running", lambda: selected("hello-world-senders", Sender="Alice"))
        assert list((directory / "data").glob("*/index")), "No durable index directory under data/"
        passed("step 8: HTTP-fed durable query rejected; durable indexes with an in-memory join start")

        stop(server)
        server = None
        demo.sql("""INSERT INTO "Message" ("From","Message") VALUES ('Dana','Hello World');""")
        server = launch("restart.log")
        wait_for("offline message applied", lambda: selected("hello-world-senders", Sender="Dana"))
        wait_for("count includes Dana", lambda: selected("message-counts", MessageText="Hello World", Count=3))
        restart = (directory / "restart.log").read_text()
        assert "Bootstrapped" not in restart, "Durable PostgreSQL queries bootstrapped again"
        assert "Replication started from read LSN" in restart, restart
        assert (f"Bootstrap completed successfully for query "
                f"'{demo.component_id('messages-with-location')}', sent 4 events") in restart, restart
        wait_for("static location restored", lambda: selected("messages-with-location", Sender="Brian Kernighan",
                                                            Location="Building A, Floor 3"))
        assert not selected("messages-with-location", Sender="Carol")
        location("carol", "Carol", "Home Office")
        wait_for("HTTP location resent", lambda: selected("messages-with-location", Sender="Carol",
                                                       Message="Good afternoon!", Location="Home Office"))
        wait_for("Dana inactive after the restart", lambda: selected("inactive-senders", MessageFrom="Dana"), 35)
        passed("step 8: restart resumed durable queries without bootstrap; join rebuilt from file; timer ran")
    except BaseException as caught:
        error = caught
        raise
    finally:
        try:
            if server is not None:
                stop(server)
            demo.cleanup(remove_volumes=True)
        except BaseException as cleanup_error:
            if error is None:
                error = cleanup_error
            raise
        finally:
            for log in logs:
                log.close()
            (directory / "acceptance.json").write_text(json.dumps({
                "passed": error is None, "checks": checks, "error": str(error) if error else None,
                "runtime": "computationGraph", "instance": demo.INSTANCE,
            }, indent=2) + "\n")
    print(f"Live acceptance passed. Evidence: {directory}")


if __name__ == "__main__":
    main()
