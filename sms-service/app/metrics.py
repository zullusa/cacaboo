"""Prometheus metrics for the SMS service.

Exposes a /metrics HTTP endpoint on port 8001 for VictoriaMetrics/Prometheus
scraping. All metric names are prefixed with ``sms_``.
"""

from __future__ import annotations

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── SMS sending metrics ──────────────────────────────────────────────

sms_sent_total = Counter(
    "sms_sent_total",
    "Total SMS messages sent",
    ["provider", "status"],
)

sms_send_duration_seconds = Histogram(
    "sms_send_duration_seconds",
    "Time to send a single SMS (seconds)",
    ["provider"],
    buckets=(0.5, 1, 2, 5, 10, 15, 30, 60),
)

sms_send_queue_size = Gauge(
    "sms_send_queue_size",
    "Number of messages waiting in the send queue",
)

# ── SMS delivery status metrics ──────────────────────────────────────

sms_status_checks_total = Counter(
    "sms_status_checks_total",
    "Total delivery-status check attempts",
    ["provider", "result"],
)

sms_status_retries_total = Counter(
    "sms_status_retries_total",
    "Total delivery-status retries (timed out, re-checking)",
    ["provider", "status"],
)

sms_status_exhausted_total = Counter(
    "sms_status_exhausted_total",
    "Messages whose delivery status was still unknown after all retries",
    ["provider"],
)

sms_delivery_wait_seconds = Histogram(
    "sms_delivery_wait_seconds",
    "Time waiting for delivery confirmation (seconds)",
    ["provider"],
    buckets=(5, 10, 30, 60, 120, 180, 300, 600),
)

# ── SMS acknowledgement metrics ─────────────────────────────────────

sms_acknowledged_total = Counter(
    "sms_acknowledged_total",
    "Total SMS acknowledged (published to notified queue)",
    ["provider"],
)

sms_delayed_total = Counter(
    "sms_delayed_total",
    "Total SMS moved to the delayed/retry queue",
    ["provider"],
)

# ── Consumer / drain metrics ────────────────────────────────────────

sms_drained_total = Counter(
    "sms_drained_total",
    "Total messages extracted from the queue",
)

sms_drain_errors_total = Counter(
    "sms_drain_errors_total",
    "Total queue drain failures",
)

# ── Operator lookup metrics ─────────────────────────────────────────

sms_operator_lookup_seconds = Histogram(
    "sms_operator_lookup_seconds",
    "Time for an operator MNO lookup (seconds)",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 15),
)

sms_operator_lookup_errors_total = Counter(
    "sms_operator_lookup_errors_total",
    "Total operator lookup failures",
)

# ── Poller metrics ──────────────────────────────────────────────────

sms_poller_forwarded_total = Counter(
    "sms_poller_forwarded_total",
    "Total incoming SMS forwarded to Telegram by the poller",
)

# ── Service info ────────────────────────────────────────────────────

sms_service_info = Info(
    "sms_service",
    "SMS service build/runtime information",
)


class _MetricsHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that serves Prometheus metrics."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/metrics":
            data = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug("metrics request: %s", fmt % args)


def start_metrics_server(port: int = 8001) -> None:
    """Start the Prometheus metrics HTTP server in a background daemon thread.

    The server binds to ``0.0.0.0:<port>`` and serves ``/metrics`` and
    ``/healthz``.  It is non-blocking and the calling code can continue
    normally.
    """
    server = HTTPServer(("0.0.0.0", port), _MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.name = "metrics-server"
    thread.start()
    logger.info("Prometheus metrics server started on :%d/metrics", port)
