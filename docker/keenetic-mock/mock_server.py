#!/usr/bin/env python3
"""Keenetic NDM API mock.

Emulates the parts of a Keenetic router used by the SMS service:

- ``GET /auth``     -> returns ``X-NDM-Challenge`` / ``X-NDM-Realm`` /
                       ``Set-Cookie`` headers (challenge-response handshake).
- ``POST /auth``    -> verifies ``login`` + challenge-encrypted ``password``.
- ``POST /rci/``    -> accepts ``[{"sms":{"send":{...}}}]`` payloads, requires an
                       authenticated session, returns 401 otherwise (so the real
                       client re-authenticates just like against a real router).

Helpers for tests:
- ``GET /mock/sms``    -> JSON dump of all SMS sent to the mock.
- ``DELETE /mock/sms`` -> clears the stored SMS.

Only the Python standard library is used, so the mock has zero dependencies.
"""

import hashlib
import json
import logging
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("keenetic-mock")

LOGIN = os.getenv("MODEM_USER", "samsa")
PASSWORD = os.getenv("MODEM_PASSWORD", "samsa")
REALM = os.getenv("MOCK_REALM", "MockRealm")
HOST = os.getenv("MOCK_HOST", "0.0.0.0")
PORT = int(os.getenv("MOCK_PORT", "8080"))

_sessions = {}
_sent_sms = []
_lock = threading.Lock()


def encrypt_password(login: str, password: str, challenge: str, realm: str) -> str:
    """Same scheme as the Keenetic client: sha256(challenge + md5(login:realm:password))."""
    first = hashlib.md5(f"{login}:{realm}:{password}".encode()).hexdigest()
    return hashlib.sha256((challenge + first).encode()).hexdigest()


class KeeneticMockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, status: int, payload: dict, headers: dict | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _session_token(self) -> str | None:
        for part in self.headers.get("Cookie", "").split(";"):
            part = part.strip()
            if part.startswith("session="):
                return part.split("=", 1)[1]
        return None

    def _get_session(self, token: str) -> dict:
        with _lock:
            if token not in _sessions:
                _sessions[token] = {
                    "challenge": uuid.uuid4().hex,
                    "realm": REALM,
                    "authenticated": False,
                }
            return _sessions[token]

    def _rotate_challenge(self, session: dict) -> str:
        with _lock:
            session["challenge"] = uuid.uuid4().hex
            return session["challenge"]

    # ------------------------------------------------------------------ routes

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/auth":
            return self._handle_auth_challenge()

        if path == "/mock/sms":
            with _lock:
                return self._send_json(
                    200,
                    {"count": len(_sent_sms), "messages": list(_sent_sms)},
                )

        return self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/auth":
            return self._handle_auth_login(body)

        if path in ("/rci/", "/rci"):
            return self._handle_rci(body)

        return self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        if urlparse(self.path).path == "/mock/sms":
            with _lock:
                _sent_sms.clear()
            return self._send_json(200, {"result": "cleared"})
        return self._send_json(404, {"error": "not found"})

    # ---------------------------------------------------------------- handlers

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _handle_auth_challenge(self):
        token = self._session_token()

        if token is None:
            token = uuid.uuid4().hex

        session = self._get_session(token)
        challenge = self._rotate_challenge(session)

        logger.info(
            "Auth challenge issued for session %s... (challenge %s)",
            token[:8],
            challenge[:8],
        )

        self._send_json(
            401,
            {"error": "Unauthorized"},
            headers={
                "X-NDM-Challenge": challenge,
                "X-NDM-Realm": session["realm"],
                "Set-Cookie": f"session={token}; Path=/",
            },
        )

    def _handle_auth_login(self, body: bytes):
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "bad request"})

        login = payload.get("login", "")
        encrypted = payload.get("password", "")
        token = self._session_token()

        if token is None or token not in _sessions:
            return self._send_json(401, {"error": "no session"})

        session = _sessions[token]
        expected = encrypt_password(login, PASSWORD, session["challenge"], session["realm"])

        if login == LOGIN and encrypted == expected:
            with _lock:
                session["authenticated"] = True
            logger.info("Session %s... authenticated", token[:8])
            return self._send_json(200, {"result": "ok"})

        logger.warning("Failed login attempt for session %s...", token[:8])
        return self._send_json(401, {"error": "login or password is incorrect"})

    def _handle_rci(self, body: bytes):
        token = self._session_token()

        if token is None or token not in _sessions or not _sessions[token]["authenticated"]:
            return self._send_json(401, {"error": "not authorized"})

        try:
            payload = json.loads(body or b"[]")
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "bad request"})

        commands = payload if isinstance(payload, list) else [payload]
        sms_id = uuid.uuid4().hex

        for command in commands:
            sms = (command or {}).get("sms", {}).get("send")
            if not sms:
                continue
            with _lock:
                _sent_sms.append(
                    {
                        "id": sms_id,
                        "interface": sms.get("interface"),
                        "to": sms.get("to"),
                        "message": sms.get("message"),
                    }
                )
            logger.info("Mock SMS sent -> %s: %s", sms.get("to"), sms.get("message"))

        return self._send_json(200, {"result": "Ok", "id": sms_id})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), KeeneticMockHandler)
    logger.info("Keenetic mock listening on http://%s:%s (user=%s)", HOST, PORT, LOGIN)
    server.serve_forever()


if __name__ == "__main__":
    main()