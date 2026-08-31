"""Periodic SMS poller for the Keenetic modem.

Polls the modem's SMS inbox on a cron schedule, forwards each SMS to a
Telegram channel, and deletes the SMS from the modem after successful
delivery.  If Telegram delivery fails the SMS is left on the modem for
the next cycle.
"""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request

import requests
from croniter import croniter

from app.services.authenticator import KeeneticAuthenticator

logger = logging.getLogger(__name__)


class SmsPoller:
    """Periodically fetches SMS from the Keenetic modem and forwards to Telegram."""

    def __init__(
        self,
        authenticator: KeeneticAuthenticator,
        base_url: str,
        interface_name: str,
        telegram_bot_token: str,
        telegram_channel_id: str,
        cron_expression: str,
        telegram_proxy: str | None = None,
        ignore_sender: str = "MegaFon",
        ignore_keywords: tuple[str, ...] = (
            "код подтверждения",
            "код для входа",
            "ваш код",
        ),
    ) -> None:
        self._authenticator = authenticator
        self._base_url = base_url.rstrip("/")
        self._interface_name = interface_name
        self._telegram_bot_token = telegram_bot_token
        self._telegram_channel_id = telegram_channel_id
        self._telegram_proxy = telegram_proxy
        self._cron_expression = cron_expression
        self._ignore_sender = (ignore_sender or "").strip()
        self._ignore_keywords = [k.lower() for k in (ignore_keywords or ())]
        self._session: requests.Session | None = None
        self._headers: dict | None = None
        self._should_stop = threading.Event()

    @property
    def rci_url(self) -> str:
        return f"{self._base_url}/rci/"

    def start(self) -> None:
        """Start the poller in a background daemon thread."""
        t = threading.Thread(target=self._loop, name="sms-poller", daemon=True)
        t.start()
        logger.info(
            "SMS poller started (cron=%r)", self._cron_expression,
        )

    def stop(self) -> None:
        self._should_stop.set()

    # ── scheduling ─────────────────────────────────────────────────────

    def _loop(self) -> None:
        cron = croniter(self._cron_expression, time.time())
        while not self._should_stop.is_set():
            next_run = cron.get_next(float)
            sleep_seconds = max(0, next_run - time.time())
            logger.debug("Next SMS poll in %.0f s", sleep_seconds)
            self._should_stop.wait(timeout=sleep_seconds)
            if self._should_stop.is_set():
                break
            try:
                self._poll()
            except Exception:
                logger.exception("SMS poll cycle failed")

    # ── modem interaction ──────────────────────────────────────────────

    def _ensure_session(self) -> None:
        if self._session is None or self._headers is None:
            self._session, self._headers = self._authenticator.authenticate()

    def _rci_post(self, payload: list) -> requests.Response:
        """Post an RCI command array, re-authenticating once on 401."""
        self._ensure_session()
        resp = self._session.post(
            self.rci_url,
            data=json.dumps(payload),
            headers=self._headers,
        )
        if resp.status_code == 401:
            self._session, self._headers = self._authenticator.authenticate()
            resp = self._session.post(
                self.rci_url,
                data=json.dumps(payload),
                headers=self._headers,
            )
        return resp

    def _fetch_sms_list(self) -> list[dict]:
        """Return the raw list of SMS message dicts from the modem."""
        payload = [
            {
                "sms": {
                    "list": {
                        "interface": self._interface_name,
                    }
                }
            }
        ]
        resp = self._rci_post(payload)
        if resp.status_code != 200:
            logger.error("RCI SMS list failed: HTTP %s %s", resp.status_code, resp.text[:200])
            return []

        body = resp.json()
        if not isinstance(body, list):
            return []

        # The first element contains the SMS list
        sms_entry = body[0] if body else {}
        messages = (
            sms_entry
            .get("sms", {})
            .get("list", {})
            .get("messages", {})
        )
        if not isinstance(messages, dict):
            return []

        result = []
        for msg_id, msg_data in messages.items():
            if not isinstance(msg_data, dict):
                continue
            result.append({"id": msg_id, **msg_data})
        return result

    def _delete_sms(self, msg_id: str) -> bool:
        """Delete a single SMS by its modem-local id (e.g. 'nv-6')."""
        payload = [
            {
                "sms": {
                    "delete": [
                        {
                            "interface": self._interface_name,
                            "id": msg_id,
                        }
                    ]
                }
            }
        ]
        resp = self._rci_post(payload)
        if resp.status_code == 200:
            logger.info("Deleted SMS %s from modem", msg_id)
            return True
        logger.warning(
            "Failed to delete SMS %s: HTTP %s %s",
            msg_id, resp.status_code, resp.text[:200],
        )
        return False

    # ── Telegram forwarding ────────────────────────────────────────────

    def _send_telegram(self, text: str) -> bool:
        """Send *text* to the configured Telegram channel. Returns True on success."""
        url = (
            f"https://api.telegram.org/bot{self._telegram_bot_token}/sendMessage"
            f"?chat_id={urllib.parse.quote(str(self._telegram_channel_id))}"
            f"&text={urllib.parse.quote(text)}"
        )
        try:
            if self._telegram_proxy:
                proxy_handler = urllib.request.ProxyHandler({
                    "https": self._telegram_proxy,
                    "http": self._telegram_proxy,
                })
                opener = urllib.request.build_opener(proxy_handler)
            else:
                opener = urllib.request.build_opener()

            with opener.open(url, timeout=15) as response:
                if response.status == 200:
                    logger.info("Telegram message sent successfully")
                    return True
                logger.warning(
                    "Telegram responded with HTTP %s: %s",
                    response.status,
                    response.read().decode("utf-8", errors="replace")[:200],
                )
                return False
        except Exception:
            logger.exception("Could not send Telegram message")
            return False

    def _format_message(self, msg: dict) -> str:
        """Format a modem SMS dict into a readable Telegram message."""
        sender = msg.get("from", "—")
        timestamp = msg.get("timestamp", "—")
        text = msg.get("text", "").strip()
        return (
            f"📩 SMS\n"
            f"📱 От: {sender}\n"
            f"🕐 Дата: {timestamp}\n"
            f"💬 {text}"
        )

    def _should_ignore(self, msg: dict) -> bool:
        """Return True if the SMS should not be forwarded to Telegram.

        Ignores service/OTP messages (e.g. operator confirmation codes)
        matching the configured sender and one of the ignore keywords.
        """
        sender = (msg.get("from") or "").strip()
        text = (msg.get("text") or "").lower()

        if not self._ignore_sender:
            return False

        if sender.lower() != self._ignore_sender.lower():
            return False

        return any(keyword in text for keyword in self._ignore_keywords)

    # ── main poll cycle ────────────────────────────────────────────────

    def _poll(self) -> None:
        logger.info("Polling modem for SMS...")
        messages = self._fetch_sms_list()

        if not messages:
            logger.debug("No SMS found on modem")
            return

        logger.info("Found %d SMS on modem", len(messages))

        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id:
                continue

            if self._should_ignore(msg):
                logger.info(
                    "Ignoring SMS %s from '%s' (OTP/service message)",
                    msg_id, msg.get("from", "?"),
                )
                continue

            telegram_text = self._format_message(msg)
            logger.info(
                "Forwarding SMS %s from '%s' to Telegram",
                msg_id, msg.get("from", "?"),
            )

            if self._send_telegram(telegram_text):
                self._delete_sms(msg_id)
            else:
                logger.warning(
                    "Telegram delivery failed for SMS %s; skipping delete", msg_id
                )
