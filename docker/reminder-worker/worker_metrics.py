"""Prometheus metrics helper for the workers.

Provides a minimal /metrics HTTP endpoint (default port 8002) plus process
basics. Kept dependency-light: workers don't need the full prometheus_client
feature set, only counters.
"""

from __future__ import annotations

import functools
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)


class Counter:
    """A tiny thread-safe Prometheus counter."""

    def __init__(self, name: str, help: str, labels: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help = help
        self.labels = labels
        self._lock = threading.Lock()
        self._series: dict[tuple, float] = {}

    def inc(self, value: float = 1, label_values: tuple = ()) -> None:
        if len(label_values) != len(self.labels):
            raise ValueError("label count mismatch")
        key = tuple(label_values)
        with self._lock:
            self._series[key] = self._series.get(key, 0.0) + value

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        with self._lock:
            for key, value in self._series.items():
                label_text = ""
                if self.labels:
                    pairs = ", ".join(
                        f'{l}="{k}"' for l, k in zip(self.labels, key)
                    )
                    label_text = f"{{{pairs}}}"
                lines.append(f"{self.name}{label_text} {value}")
        return "\n".join(lines) + "\n"


def metrics_server(counters: dict[str, Counter], port: int) -> ThreadingHTTPServer:
    """Build an HTTP server that renders *counters* at /metrics."""

    class Handler(BaseHTTPRequestHandler):
        @functools.wraps(metrics_server)
        def do_GET(self):  # noqa: N802
            if self.path == "/metrics":
                body = _render(counters)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path in ("/healthz", "/health"):
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):
            logger.debug(fmt, *args)

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.name = "metrics-server"
    thread.start()
    logger.info("Metrics server listening on :%d/metrics", port)
    return server


def _render(counters: dict[str, Counter]) -> bytes:
    parts = [c.render() for c in counters.values()]
    return "".join(parts).encode()