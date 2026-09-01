"""sms.ru SMS provider.

Sends SMS through https://sms.ru/sms/send and polls delivery status via
https://sms.ru/sms/status, so the caller only acknowledges a message that
was actually delivered.
"""

import logging
import time

import requests

from app.domain.models import SmsMessage
from app.errors import SmsSendError, SmsStatusError
from app.interfaces.protocols import SmsSender, SmsStatusChecker

logger = logging.getLogger(__name__)

SMSRU_BASE = "https://sms.ru"

# sms.ru status_code values (see /api/status).
_STATUS_DELIVERED = 103
# Terminal statuses that are considered a failure (no further retries).
_STATUS_FAILED = {
    104, 105, 106, 107, 108, 150,  # various "not delivered"
}


class SmsRuSmsSender(SmsSender, SmsStatusChecker):
    """Sends SMS via sms.ru and checks their delivery status."""

    def __init__(
        self,
        api_id: str,
        from_name: str | None = None,
        base_url: str = SMSRU_BASE,
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_id = api_id
        self._from_name = from_name
        self._timeout = timeout
        self._session = requests.Session()

    # ── SmsSender ──────────────────────────────────────────────────────

    def send(self, message: SmsMessage) -> str | None:
        params = {
            "api_id": self._api_id,
            "to": message.phone_number,
            "msg": message.text,
            "json": 1,
        }
        if self._from_name:
            params["from"] = self._from_name

        try:
            response = self._session.post(
                f"{self._base_url}/sms/send",
                data=params,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise SmsSendError(f"sms.ru request failed: {exc}") from exc

        if response.status_code != 200:
            raise SmsSendError(
                f"sms.ru HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SmsSendError(
                f"sms.ru returned non-JSON response: {response.text[:300]}"
            ) from exc

        if payload.get("status") != "OK":
            raise SmsSendError(
                f"sms.ru API error: code={payload.get('status_code')} "
                f"text={payload.get('status_text')!r}"
            )

        sms = payload.get("sms") or {}
        entry = sms.get(message.phone_number) or {}
        if entry.get("status") != "OK":
            raise SmsSendError(
                f"sms.ru rejected message to {message.phone_number}: "
                f"code={entry.get('status_code')} text={entry.get('status_text')!r}"
            )

        tracking_id = entry.get("sms_id")
        if not tracking_id:
            raise SmsSendError(
                f"sms.ru did not return an sms_id for {message.phone_number}: {payload!r}"
            )
        logger.info("sms.ru accepted SMS id=%s", tracking_id)
        return str(tracking_id)

    # ── SmsStatusChecker ───────────────────────────────────────────────

    def wait_for_delivery(
        self,
        tracking_id: str,
        timeout: float,
        poll_interval: float,
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status_code = self._fetch_status(tracking_id)

            if status_code == _STATUS_DELIVERED:
                logger.info("SMS %s delivered", tracking_id)
                return True

            if status_code in _STATUS_FAILED:
                logger.warning(
                    "SMS %s failed (status_code=%s)", tracking_id, status_code
                )
                return False

            time.sleep(poll_interval)

        logger.warning("SMS %s status check timed out", tracking_id)
        return False

    def _fetch_status(self, tracking_id: str) -> int:
        try:
            response = self._session.post(
                f"{self._base_url}/sms/status",
                data={
                    "api_id": self._api_id,
                    "sms_id": tracking_id,
                    "json": 1,
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise SmsStatusError(f"sms.ru status request failed: {exc}") from exc

        if response.status_code != 200:
            raise SmsStatusError(
                f"sms.ru status HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SmsStatusError(
                f"sms.ru status non-JSON response: {response.text[:300]}"
            ) from exc

        if payload.get("status") != "OK":
            raise SmsStatusError(
                f"sms.ru status API error: code={payload.get('status_code')} "
                f"text={payload.get('status_text')!r}"
            )

        sms = payload.get("sms") or {}
        entry = sms.get(tracking_id) or {}
        status_code = entry.get("status_code")
        if status_code is None:
            raise SmsStatusError(
                f"sms.ru status missing status_code for {tracking_id}: {entry!r}"
            )
        return int(status_code)
