"""Lokalny serwer nakładek agenta (tylko 127.0.0.1): strona nakładek, kiosk, stan sesji i mapa toru.

Okno nad grą, kiosk na monitorze stanowiska i ewentualny OBS czytają stan prosto od agenta,
kilkadziesiąt razy na sekundę, bez pośrednictwa centrali.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("racecoach.overlay")
STATIC = Path(__file__).resolve().parent / "static"
FILES = {"/": "overlay.html", "/index.html": "overlay.html", "/overlay.html": "overlay.html", "/overlay.js": "overlay.js",
         "/overlay.css": "overlay.css", "/kiosk": "kiosk.html", "/kiosk.html": "kiosk.html"}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


class OverlayServer:
    def __init__(self, state, reference, map_file, port=31399):
        """state(), reference() → dict; map_file() → ścieżka map.png bieżącego toru albo None."""
        self.state, self.reference, self.map_file, self.port = state, reference, map_file, port
        self.httpd = None

    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, code, body, kind):
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                try:
                    if path in FILES:
                        file = STATIC / FILES[path]
                        return self.send(200, file.read_bytes(), TYPES[file.suffix])
                    if path == "/state":
                        return self.send(200, json.dumps(outer.state(), ensure_ascii=False).encode(), "application/json")
                    if path == "/reference":
                        return self.send(200, json.dumps(outer.reference()).encode(), "application/json")
                    if path == "/map.png":
                        file = outer.map_file()
                        if file:
                            return self.send(200, Path(file).read_bytes(), "image/png")
                    self.send(404, b"Nie znaleziono", "text/plain; charset=utf-8")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception:
                    log.exception("Błąd serwera nakładek")
                    self.send(500, b"Blad", "text/plain")

        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError as exc:
            log.warning("Nakładki: port %s zajęty (%s) – strona nakładek niedostępna", self.port, exc)
            return False
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="overlay-http").start()
        log.info("Nakładki: http://127.0.0.1:%s/  · ekran stanowiska: http://127.0.0.1:%s/kiosk", self.port, self.port)
        return True

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
