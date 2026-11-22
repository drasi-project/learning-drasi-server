#!/usr/bin/env python3
# Copyright 2025 The Drasi Authors.
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

"""Print the webhook messages that a tutorial's HTTP reaction sends.

A local stand-in for a Discord channel: it accepts each POST, prints the
message text and answers 204 No Content, as a Discord webhook does.
"""

import argparse
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def message_text(body):
    try:
        payload = json.loads(body)
    except ValueError:
        return body
    if isinstance(payload, dict) and isinstance(payload.get("content"), str):
        return payload["content"]
    return json.dumps(payload, indent=2, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace")
        print(f"[{datetime.now():%H:%M:%S}] POST {self.path}\n{message_text(body)}\n", flush=True)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8390)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Listening on http://127.0.0.1:{args.port}/ (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
