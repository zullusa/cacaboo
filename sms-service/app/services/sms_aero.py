"""SMSAero SMS provider.

Sends SMS through https://gate.smsaero.ru/v2 and can poll delivery status
so the caller only acknowledges a message that was actually delivered.
"""

import logging
import time

import requests

from app.domain.models import SmsMessage
from app.errors import SmsSendError, SmsStatusError
from app.interfaces.protocols import DeliveryStatus, SmsSender, SmsStatusChecker

logger = logging.getLogger(__name__)

SMSAERO_BASE = "https://gate.smsaero.ru/v2"

# SMSAero status_id values for sent messages.
_STATUS_DELIVERED = 1
# Terminal statuses that are considered a failure (no further retries).
_STATUS_FAILED = {2, 5, 13, 14, 15}
# Any other status_id we receive is treated as still pending.


class SmsAeroSmsSender(SmsSender, SmsStatusChecker):
    """Sends SMS via SMSAero and checks their delivery status."""

    def __init__(
        self,
        email: str,
        api_key: str,
        sign: str | None = None,
        channel: str | None = None,
        base_url: str = SMSAERO_BASE,
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._sign = sign
        self._channel = channel
        self._timeout = timeout
        self._session = requests.Session()
        self._session.auth = (email, api_key)

    # ── SmsSender ──────────────────────────────────────────────────────

    def send(self, message: SmsMessage) -> str | None:
        params = {
            "number": message.phone_number,
            "text": message.text,
        }
        if self._sign:
            params["sign"] = self._sign
        if self._channel:
            params["channel"] = self._channel

        try:
            response = self._session.post(
                f"{self._base_url}/sms/send",
                data=params,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise SmsSendError(f"SMSAero request failed: {exc}") from exc

        payload = self._decode(response, expected_http=200)
        data = payload.get("data") or {}
        tracking_id = data.get("id")
        if tracking_id is None:
            raise SmsSendError(f"SMSAero did not return a message id: {payload!r}")
        logger.info("SMSAero accepted SMS id=%s", tracking_id)
        return str(tracking_id)

    # ── SmsStatusChecker ───────────────────────────────────────────────

    def wait_for_delivery(
        self,
        tracking_id: str,
        timeout: float,
        poll_interval: float,
    ) -> DeliveryStatus:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status_id = self._fetch_status(tracking_id)

            if status_id == _STATUS_DELIVERED:
                logger.info("SMS %s delivered", tracking_id)
                return DeliveryStatus(delivered=True)

            if status_id in _STATUS_FAILED:
                logger.warning("SMS %s failed (status_id=%s)", tracking_id, status_id)
                return DeliveryStatus(delivered=False)

            time.sleep(poll_interval)

        logger.warning("SMS %s status check timed out", tracking_id)
        return DeliveryStatus(delivered=False, timed_out=True)

    def _fetch_status(self, tracking_id: str) -> int:
        try:
            response = self._session.post(
                f"{self._base_url}/sms/status",
                data={"id": tracking_id},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise SmsStatusError(f"SMSAero status request failed: {exc}") from exc

        payload = self._decode(response, expected_http=200)
        data = payload.get("data") or []
        if not isinstance(data, list) or not data:
            raise SmsStatusError(f"SMSAero returned no status for {tracking_id}: {payload!r}")
        row = data[0]
        status_id = row.get("status_id")
        if status_id is None:
            raise SmsStatusError(f"SMSAero status missing status_id: {row!r}")
        return int(status_id)

    # ── helpers ────────────────────────────────────────────────────────

    def _decode(self, response: requests.Response, expected_http: int) -> dict:
        if response.status_code != expected_http:
            raise SmsSendError(
                f"SMSAero HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SmsSendError(
                f"SMSAero returned non-JSON response: {response.text[:300]}"
            ) from exc
        if not isinstance(payload, dict) or not payload.get("success"):
            raise SmsSendError(f"SMSAero API error: {payload!r}")
        return payload
