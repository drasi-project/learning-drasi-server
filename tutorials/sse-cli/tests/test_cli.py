"""Black-box transport/lifecycle regression tests, not live Drasi proof.

Set DRASI_SSE_CLI to the tutorial-built binary before running unittest discovery.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import unittest
import uuid


BINARY = os.environ.get("DRASI_SSE_CLI")
QUERY_ID = "08f93596-5c0d-4c5d-890a-cf015bb3d809"


@unittest.skipUnless(BINARY, "set DRASI_SSE_CLI to a locally built tutorial binary")
class CliTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.payload = ('data: ' + json.dumps({"queryId": QUERY_ID, "results": [], "timestamp": 1}) + '\n\n').encode()
        self.content_type = "text/event-stream; charset=utf-8"
        self.create_status = 200
        self.create_body = None
        self.delete_status = 200
        self.revision = 0
        self.reaction_id = None
        self.keep_open = False
        self.connected = threading.Event()
        self.release = threading.Event()
        case = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = self.rfile.read(int(self.headers["Content-Length"]))
                body = json.loads(payload)
                case.requests.append(("POST", self.path, body))
                case.reaction_id = str(uuid.uuid4())
                case.revision += 1
                self.send_response(case.create_status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(case.create_body if case.create_body is not None else json.dumps({
                    "success": True, "data": {
                        "requestId": body["requestId"], "revision": case.revision, "durable": False,
                        "components": [{"id": case.reaction_id, "name": body["component"]["definition"]["name"]}],
                    },
                }).encode())

            def do_DELETE(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                case.requests.append(("DELETE", self.path, body))
                case.revision += 1
                self.send_response(case.delete_status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "data": {
                    "requestId": body["requestId"], "revision": case.revision,
                    "durable": False, "components": [],
                }}).encode())

            def do_GET(self):
                case.requests.append(("GET", self.path, None))
                if self.path != "/events":
                    responses = {
                        "/api/v1/instances/selected/components/by-name/q": {"id": QUERY_ID, "name": "q"},
                        f"/api/v1/instances/selected/queries/{QUERY_ID}": {"id": QUERY_ID, "name": "q", "status": "Running"},
                        "/api/v1/instances/selected/computation/desired": {"revision": case.revision},
                        f"/api/v1/instances/selected/reactions/{case.reaction_id}": {"id": case.reaction_id, "status": "Running"},
                    }
                    self.send_response(200 if self.path in responses else 404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": self.path in responses, "data": responses.get(self.path)}).encode())
                    return
                self.send_response(200)
                self.send_header("Content-Type", case.content_type)
                self.end_headers()
                self.wfile.write(case.payload)
                self.wfile.flush()
                case.connected.set()
                if case.keep_open:
                    case.release.wait(10)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.base = f"http://127.0.0.1:{self.port}"
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def command(self, *extra, direct=False):
        mode = ["--sse-url", f"{self.base}/events"] if direct else [
            "--server", self.base, "--instance", "selected", "--query", "q",
            "--sse-port", str(self.port),
        ]
        return [BINARY, *mode, *extra]

    def execute(self, *extra, direct=False):
        return subprocess.run(
            self.command(*extra, direct=direct), text=True, capture_output=True, timeout=10
        )

    def assert_cleanup(self):
        post = next(item for item in self.requests if item[0] == "POST")
        self.assertEqual(post[1], "/api/v1/instances/selected/computation/ordinary-definitions")
        expected = f"{post[1]}/{self.reaction_id}"
        delete = next(item for item in self.requests if item[:2] == ("DELETE", expected))
        self.assertEqual(delete[2]["expectedRevision"], post[2]["expectedRevision"] + 1)
        uuid.UUID(delete[2]["requestId"])
        definition = post[2]["component"]["definition"]
        self.assertEqual(definition["queries"], [{"id": QUERY_ID}])
        self.assertNotIn("id", definition)
        self.assertTrue(definition["name"].startswith("sse-cli-"))
        return definition

    def test_adapter_payload_log_and_disconnect_cleanup(self):
        self.payload = (
            'data: {"type":"heartbeat","ts":1}\r\n\r\n'
            'data: {"queryId":"q",\r\n'
            'data: "results":[{"type":"DELETE","data":{"name":"café"},'
            '"row_signature":18446744073709551615}],"timestamp":1}\r\n\r\n'
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "events.json"
            result = self.execute("--log-file", str(log))
            self.assertEqual(log.read_text(), result.stdout)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("SSE stream closed", result.stderr)
        self.assertEqual(json.loads(result.stdout)["results"][0]["row_signature"], 2**64 - 1)
        self.assertEqual(self.assert_cleanup()["host"], "127.0.0.1")

    def test_existing_native_endpoint_is_never_created_or_deleted(self):
        payload = {
            "output": {"alias": "items", "component": "source", "port": "out"},
            "sequence": 42, "publishedAt": 123, "changes": [
                {"operation": "PATCH", "identity": {"namespace": "s", "id": "1"},
                 "after": {"name": None}, "removedProperties": ["old"]},
                {"operation": "DELETE", "identity": {"namespace": "s", "id": "1"}},
            ],
        }
        self.payload = ("data: " + json.dumps(payload) + "\n\n").encode()
        result = self.execute(direct=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout), payload)
        self.assertEqual(self.requests, [("GET", "/events", None)])

    def test_malformed_json_and_wrong_content_type_fail_after_cleanup(self):
        for payload, content_type, diagnostic in [
            (b"data: not-json\n\n", "text/event-stream", "Invalid JSON"),
            (b"data: \xff\n\n", "text/event-stream", "Invalid UTF-8"),
            (b"data: {}\n", "text/event-stream", "incomplete event"),
            (b"<html>wrong endpoint</html>", "text/html", "Expected text/event-stream"),
        ]:
            with self.subTest(diagnostic=diagnostic):
                self.requests.clear()
                self.payload = payload
                self.content_type = content_type
                result = self.execute()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(diagnostic, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assert_cleanup()

    def test_bad_log_path_does_not_create_a_reaction(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute("--log-file", str(Path(directory) / "missing/events.json"))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Could not open event log", result.stderr)
        self.assertEqual(self.requests, [])

    def test_ambiguous_create_failure_is_reported_without_retry(self):
        self.create_status = 500
        self.create_body = b'{"success":false,"error":{"code":"PERSISTENCE_FAILED","message":"applied but persistence failed"}}'
        result = self.execute()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("PERSISTENCE_FAILED", result.stderr)
        self.assertIn("Creation was not confirmed", result.stderr)
        posts = [item for item in self.requests if item[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertFalse(any(item[0] == "DELETE" for item in self.requests))
        self.assertIn(posts[0][2]["requestId"], result.stderr)
        self.assertIn(posts[0][2]["component"]["definition"]["name"], result.stderr)
        self.assertEqual(result.stdout, "")

    def test_ctrl_c_cleanup_and_cleanup_failure_exit_status(self):
        self.keep_open = True
        for delete_status, exit_status in [(200, 0), (500, 1)]:
            with self.subTest(delete_status=delete_status):
                self.requests.clear()
                self.connected.clear()
                self.delete_status = delete_status
                process = subprocess.Popen(
                    self.command("--sse-host", "0.0.0.0"),
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                try:
                    self.assertTrue(self.connected.wait(5), "CLI did not connect")
                    lines = []
                    while True:
                        line = process.stdout.readline()
                        lines.append(line)
                        if line in ("}\n", ""):
                            break
                    process.send_signal(signal.SIGINT)
                    stdout, stderr = process.communicate(timeout=10)
                    stdout = "".join(lines) + stdout
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
                self.assertEqual(process.returncode, exit_status, stderr)
                self.assertEqual(json.loads(stdout)["queryId"], QUERY_ID)
                self.assertEqual(self.assert_cleanup()["host"], "0.0.0.0")
                if delete_status == 500:
                    self.assertIn("Could not delete reaction", stderr)


if __name__ == "__main__":
    unittest.main()
