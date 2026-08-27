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

"""Mock store service: exports allowlisted OTLP/HTTP protobuf and a control API.

Stdlib only — no pip packages — so the tutorial images build without PyPI.

Environment:
  SERVICE_NAME                 Resource service.name
  SERVICE_VERSION              Optional service.version
  PEER_SERVICE                 If set, emit a CLIENT span to this destination
  OTEL_EXPORTER_OTLP_ENDPOINT  Collector base URL (default http://otel-collector:4318)
  LATENCY_P99_MS               Initial latency gauge (default 400)
  HEARTBEAT_ENABLED            true/false (default true)
  CONTROL_PORT                 HTTP control port (default 8080)
  EXPORT_INTERVAL_SECS         How often to export (default 2)
"""

from __future__ import annotations

import json
import os
import struct
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import deque
from typing import Any
from urllib.parse import urlparse

SERVICE_NAME = os.environ.get("SERVICE_NAME", "checkout")
SERVICE_VERSION = os.environ.get("SERVICE_VERSION", "v1")
PEER_SERVICE = os.environ.get("PEER_SERVICE", "").strip()
PEER_URL = os.environ.get(
    "PEER_URL",
    f"http://{PEER_SERVICE}:8080/work" if PEER_SERVICE else "",
)
OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
).rstrip("/")
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", "8080"))
EXPORT_INTERVAL_SECS = float(os.environ.get("EXPORT_INTERVAL_SECS", "2"))
GENERATE_TRAFFIC = os.environ.get("GENERATE_TRAFFIC", "false").lower() not in {
    "0",
    "false",
    "no",
    "off",
}

_state_lock = threading.Lock()
_work_ms = float(os.environ.get("WORK_MS", os.environ.get("LATENCY_P99_MS", "400")))
_samples: deque[float] = deque(maxlen=32)
# First export should be the configured delay, not a missing gauge (KPI 0).
_samples.append(_work_ms)
_heartbeat_enabled = os.environ.get("HEARTBEAT_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
}

_VARINT = 0
_FIXED64 = 1
_LEN = 2


def _varint(n: int) -> bytes:
    out = bytearray()
    n &= (1 << 64) - 1
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def _key(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _bytes_field(field: int, data: bytes) -> bytes:
    return _key(field, _LEN) + _varint(len(data)) + data


def _string(field: int, value: str) -> bytes:
    return _bytes_field(field, value.encode("utf-8"))


def _double(field: int, value: float) -> bytes:
    return _key(field, _FIXED64) + struct.pack("<d", value)


def _fixed64(field: int, value: int) -> bytes:
    return _key(field, _FIXED64) + struct.pack("<Q", value)


def _enum(field: int, value: int) -> bytes:
    return _key(field, _VARINT) + _varint(value)


def _embedded(field: int, payload: bytes) -> bytes:
    return _bytes_field(field, payload)


def _key_value(key: str, value: str) -> bytes:
    return _string(1, key) + _embedded(2, _string(1, value))


def _resource() -> bytes:
    attrs = _embedded(1, _key_value("service.name", SERVICE_NAME))
    attrs += _embedded(1, _key_value("service.version", SERVICE_VERSION))
    return attrs


def _now_nano() -> int:
    return time.time_ns()


def _number_point(value: float) -> bytes:
    now = _now_nano()
    point = _fixed64(2, now) + _fixed64(3, now) + _double(4, value)
    point += _embedded(7, _key_value("version", SERVICE_VERSION))
    return point


def _gauge_metric(name: str, unit: str, value: float) -> bytes:
    return (
        _string(1, name)
        + _string(3, unit)
        + _embedded(5, _embedded(1, _number_point(value)))
    )


def _export_metrics_request(metrics: list[bytes]) -> bytes:
    scope_metrics = b"".join(_embedded(2, m) for m in metrics)
    resource_metrics = _embedded(1, _resource()) + _embedded(2, scope_metrics)
    return _embedded(1, resource_metrics)


def _span(name: str, peer: str, start_nano: int, end_nano: int) -> bytes:
    return (
        _bytes_field(1, os.urandom(16))
        + _bytes_field(2, os.urandom(8))
        + _string(5, name)
        + _enum(6, 3)
        + _fixed64(7, start_nano)
        + _fixed64(8, end_nano)
        + _embedded(9, _key_value("peer.service", peer))
    )


def _export_traces_request(peer: str, start_nano: int, end_nano: int) -> bytes:
    scope_spans = _embedded(
        2, _span(f"{SERVICE_NAME}->{peer}", peer, start_nano, end_nano)
    )
    resource_spans = _embedded(1, _resource()) + _embedded(2, scope_spans)
    return _embedded(1, resource_spans)


def _post_otlp(path: str, payload: bytes) -> None:
    req = urllib.request.Request(
        f"{OTLP_ENDPOINT}{path}",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-protobuf"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except urllib.error.URLError as exc:
        print(f"[otlp] {path} failed: {exc}")


def _current_work_ms() -> float:
    with _state_lock:
        return _work_ms


def _record_sample(duration_ms: float) -> None:
    with _state_lock:
        _samples.append(duration_ms)


def _p99_ms() -> float | None:
    with _state_lock:
        if not _samples:
            return None
        ordered = sorted(_samples)
    idx = min(len(ordered) - 1, max(0, round(0.99 * (len(ordered) - 1))))
    return ordered[idx]


def _heartbeat_on() -> bool:
    with _state_lock:
        return _heartbeat_enabled


_PEER_ERRORS = (urllib.error.URLError, TimeoutError, OSError)


def _http_peer(timeout: float) -> None:
    req = urllib.request.Request(PEER_URL, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


def _handle_work() -> float:
    started = time.perf_counter()
    time.sleep(max(_current_work_ms(), 0) / 1000.0)
    if PEER_SERVICE and PEER_URL and not GENERATE_TRAFFIC:
        start_nano = _now_nano()
        try:
            _http_peer(timeout=2.0)
            _post_otlp(
                "/v1/traces",
                _export_traces_request(PEER_SERVICE, start_nano, _now_nano()),
            )
        except _PEER_ERRORS as exc:
            print(f"[work] downstream {PEER_URL} failed: {exc}")
            # Local work only — do not keep a 5s timeout in the p99 window.
            duration_ms = (time.perf_counter() - started) * 1000.0
            _record_sample(min(duration_ms, _current_work_ms() + 50.0))
            return duration_ms
    duration_ms = (time.perf_counter() - started) * 1000.0
    _record_sample(duration_ms)
    return duration_ms


def _generate_traffic() -> tuple[int, int] | None:
    if not (GENERATE_TRAFFIC and PEER_SERVICE and PEER_URL):
        return None
    start_nano = _now_nano()
    started = time.perf_counter()
    try:
        _http_peer(timeout=4.0)
    except _PEER_ERRORS as exc:
        print(f"[traffic] {PEER_URL} failed: {exc}")
        return None
    duration_ms = (time.perf_counter() - started) * 1000.0
    _record_sample(duration_ms)
    return start_nano, _now_nano()


def _snapshot() -> dict[str, Any]:
    with _state_lock:
        samples = list(_samples)
        work = _work_ms
        hb = _heartbeat_enabled
    p99 = None
    if samples:
        ordered = sorted(samples)
        idx = min(len(ordered) - 1, max(0, round(0.99 * (len(ordered) - 1))))
        p99 = ordered[idx]
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "peerService": PEER_SERVICE or None,
        "workMs": work,
        "latencyP99Ms": p99,
        "sampleCount": len(samples),
        "heartbeatEnabled": hb,
        "otlpEndpoint": OTLP_ENDPOINT,
    }


def _exporter_loop() -> None:
    while True:
        try:
            span = _generate_traffic()
            metrics: list[bytes] = []
            p99 = _p99_ms()
            if p99 is not None:
                metrics.append(_gauge_metric("latency_p99_ms", "ms", p99))
            # Always export the pulse. 0 means explicitly disabled so Drasi
            # sees an Update immediately instead of waiting for lastSeen to age.
            pulse = float(time.time()) if _heartbeat_on() else 0.0
            metrics.append(_gauge_metric("health.heartbeat", "1", pulse))
            if metrics:
                _post_otlp("/v1/metrics", _export_metrics_request(metrics))
            if span and PEER_SERVICE:
                _post_otlp(
                    "/v1/traces",
                    _export_traces_request(PEER_SERVICE, span[0], span[1]),
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[export] loop failed: {exc}")
        time.sleep(EXPORT_INTERVAL_SECS)


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        print(f"[control] {self.address_string()} {format % args}")

    def _send(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/health", "/"):
            self._send(200, {"status": "ok", "service": SERVICE_NAME})
            return
        if path == "/state":
            self._send(200, _snapshot())
            return
        if path == "/work":
            duration_ms = _handle_work()
            self._send(200, {"status": "ok", "durationMs": duration_ms})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        global _work_ms, _heartbeat_enabled
        path = urlparse(self.path).path.rstrip("/")
        parts = [p for p in path.split("/") if p]

        if len(parts) == 2 and parts[0] in ("delay", "latency"):
            try:
                value = float(parts[1])
            except ValueError:
                self._send(400, {"error": "delay must be a number"})
                return
            with _state_lock:
                _work_ms = value
                _samples.clear()
            print(f"[control] work_ms={value}")
            self._send(200, _snapshot())
            return

        if parts == ["heartbeat", "on"]:
            with _state_lock:
                _heartbeat_enabled = True
            print("[control] heartbeat enabled")
            self._send(200, _snapshot())
            return

        if parts == ["heartbeat", "off"]:
            with _state_lock:
                _heartbeat_enabled = False
            print("[control] heartbeat disabled")
            self._send(200, _snapshot())
            return

        self._send(404, {"error": "not found"})


def main() -> None:
    print(
        f"Starting {SERVICE_NAME} {SERVICE_VERSION} "
        f"(otlp={OTLP_ENDPOINT}, peer={PEER_SERVICE or '-'}, port={CONTROL_PORT})"
    )
    threading.Thread(target=_exporter_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", CONTROL_PORT), ControlHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
