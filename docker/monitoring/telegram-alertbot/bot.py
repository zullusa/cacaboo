"""Minimal webhook receiver that forwards Grafana alert notifications to Telegram.

Listens on port 8080, receives POST /alert from Grafana Contact Points
(webhook type), formats the alert, and sends it to a Telegram chat/channel.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("telegram-alertbot")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
PROXY_URL = os.environ.get("TELEGRAM_PROXY", "")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

SEVERITY_EMOJI = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
    "ok": "🟢",
}


def _format_alert(payload: dict) -> str:
    """Convert a Grafana webhook payload into a readable Telegram message."""
    alerts = payload.get("alerts", [])
    if not alerts:
        return ""

    lines: list[str] = []
    for alert in alerts:
        status = alert.get("status", "unknown")
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        severity = labels.get("severity", "info")

        emoji = SEVERITY_EMOJI.get(severity, "⚪")
        title = annotations.get("summary", labels.get("alertname", "Unknown alert"))
        desc = annotations.get("description", "")

        line = f"{emoji} *{status.upper()}*: {title}"
        if desc:
            line += f"\n    {desc}"
        lines.append(line)

    return "\n\n".join(lines)


def _send_telegram(text: str) -> None:
    """Send a text message to Telegram using the Bot API."""
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID not set, skipping")
        return

    body = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()

    req = Request(TELEGRAM_API, data=body, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                logger.error("Telegram API returned %d", resp.status)
    except URLError as exc:
        logger.error("Failed to send Telegram message: %s", exc)


class AlertHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/alert":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        text = _format_alert(payload)
        if text:
            logger.info("Forwarding %d alert(s) to Telegram", len(payload.get("alerts", [])))
            _send_telegram(text)

        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug(fmt, *args)


def main() -> int:
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning(
            "Starting without TELEGRAM_BOT_TOKEN/TELEGRAM_CHANNEL_ID - "
            "alerts will be logged but not sent"
        )

    server = HTTPServer(("0.0.0.0", 8080), AlertHandler)
    logger.info("Telegram alertbot listening on :8080/alert")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
