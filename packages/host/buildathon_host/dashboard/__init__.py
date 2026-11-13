"""A dependency-free web dashboard: camera, state, stop button. Same page for sim and real."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("buildathon.dashboard")
PAGE = Path(__file__).with_name("index.html")


def start_dashboard(host, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep the host log quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/status":
                header, _, _ = host.snapshot()
                self._send(200, json.dumps(header).encode(), "application/json")
            elif path in ("/stream/camera.mjpg", "/stream/overview.mjpg"):
                self._stream(overview=path.endswith("overview.mjpg"))
            elif path in ("/frame/camera.jpg", "/frame/overview.jpg"):
                if path.endswith("overview.jpg"):
                    host.want_overview()
                _, images, overview = host.snapshot()
                frame = overview if path.endswith("overview.jpg") else next(iter(images.values()), None)
                if frame:
                    self._send(200, frame, "image/jpeg")
                else:
                    self._send(404, b"no frame yet", "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

        def _stream(self, overview: bool) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = None
            try:
                while True:
                    if overview:
                        host.want_overview()
                    host.wait_tick(1.0)
                    _, images, over = host.snapshot()
                    frame = over if overview else next(iter(images.values()), None)
                    if frame is None or frame is last:
                        continue
                    last = frame
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(frame)).encode()
                        + b"\r\n\r\n"
                        + frame
                        + b"\r\n"
                    )
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def do_POST(self):
            if self.path != "/api/rpc":
                self._send(404, b"not found", "text/plain")
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                request = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self._send(400, b'{"ok":false,"error":"bad JSON"}', "application/json")
                return
            if request.get("op") in ("step", "hello", "observe"):
                reply = {"ok": False, "error": "not available over HTTP"}
            else:
                reply = host.call_from_thread(request)
            self._send(200, json.dumps(reply).encode(), "application/json")

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="dashboard").start()
    return server
