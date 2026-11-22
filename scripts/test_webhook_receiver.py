# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.

import contextlib
import io
import json
import threading
import unittest
import urllib.request

import webhook_receiver


class WebhookReceiverTests(unittest.TestCase):
    def post(self, body):
        server = webhook_receiver.ThreadingHTTPServer(("127.0.0.1", 0), webhook_receiver.Handler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        output = io.StringIO()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/", data=body.encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with contextlib.redirect_stdout(output):
            with urllib.request.urlopen(request, timeout=5) as response:
                status = response.status
        return status, output.getvalue()

    def test_prints_discord_message_text_and_answers_204(self):
        status, output = self.post(json.dumps({"content": "🚨 **High risk container detected**"}))
        self.assertEqual(status, 204)
        self.assertIn("POST /\n🚨 **High risk container detected**", output)

    def test_prints_other_bodies_unchanged_or_as_json(self):
        self.assertIn('"operation": "UPDATE"', self.post(json.dumps({"operation": "UPDATE"}))[1])
        self.assertIn("plain text", self.post("plain text")[1])


if __name__ == "__main__":
    unittest.main()
