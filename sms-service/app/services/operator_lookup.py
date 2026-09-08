"""Mobile network operator (MNO) detection via the BDPN service at nic-t.ru."""

import logging
import re
import time
from html import unescape
from urllib.parse import urlencode

import requests

from app.errors import SmsServiceError

logger = logging.getLogger(__name__)

DEFAULT_LOOKUP_URL = "https://www.nic-t.ru/bdpn/bdpn-proverka-nomera/"

_ELEMENTOR_BLOCK = re.compile(
    r'<div\s+class="elementor-widget-container"[^>]*>', re.IGNORECASE
)
_INNER_DIV = re.compile(r"<div\b|</div>", re.IGNORECASE)
_OPERATOR_LINE = re.compile(r"Оператор:\s*(.+?)(?:<br|$)", re.IGNORECASE | re.DOTALL)


class OperatorLookupError(SmsServiceError):
    """Raised when the operator of a number cannot be determined."""


def normalize_number(phone_number: str) -> str:
    """Return a 10-digit national number (drop +7/8 prefix and formatting).

    ``+79266728202`` -> ``9266728202``, ``89266728202`` -> ``9266728202``.
    """
    digits = re.sub(r"\D", "", phone_number)
    return digits[-10:] if len(digits) >= 10 else digits


def _elementor_blocks(html: str):
    """Yield the inner content of every ``elementor-widget-container`` div.

    Divs may nest arbitrarily, so a balanced scan is done from each opening
    tag to its matching ``</div>``.
    """
    for opening in _ELEMENTOR_BLOCK.finditer(html):
        depth = 1
        for nm in _INNER_DIV.finditer(html, opening.end()):
            if nm.group().lower().startswith("<div"):
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    yield html[opening.end() : nm.start()]
                    break


class OperatorLookup:
    """Resolves the operator of a phone number (BPDN, nic-t.ru).

    POSTs ``num=<10-digit number>`` with ``application/x-www-form-urlencoded``
    and parses the returned page. The operator name lives inside an
    ``elementor-widget-container`` block, in the form
    ``Оператор: "МегаФон" ПАО``.

    The BDPN service is rate-limited and occasionally answers 200 with no
    result block, so a short retry is done before giving up. A small
    in-memory TTL cache avoids hammering the service for numbers that repeat
    (e.g. a deferred message being retried later).
    """

    def __init__(
        self,
        url: str = DEFAULT_LOOKUP_URL,
        timeout: float = 15.0,
        cache_ttl: float = 24 * 3600,
        max_attempts: int = 2,
        retry_delay: float = 1.5,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._cache_ttl = cache_ttl
        self._max_attempts = max(1, max_attempts)
        self._retry_delay = retry_delay
        self._cache: dict[str, tuple[float, str | None]] = {}
        self._session = requests.Session()

    def get_operator(self, phone_number: str) -> str | None:
        """Return the operator name (e.g. ``МегаФон ПАО``) or None."""
        number = normalize_number(phone_number)
        if not number:
            raise OperatorLookupError(
                f"cannot extract a 10-digit number from {phone_number!r}"
            )

        cached = self._cache.get(number)
        now = time.monotonic()
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        operator = self._fetch(number)
        self._cache[number] = (now, operator)
        return operator

    def _fetch(self, number: str) -> str | None:
        for attempt in range(1, self._max_attempts + 1):
            operator = self._request(number)
            if operator:
                return operator
            if attempt < self._max_attempts:
                logger.warning(
                    "BDPN returned no operator for %s (attempt %d/%d); retrying",
                    number,
                    attempt,
                    self._max_attempts,
                )
                time.sleep(self._retry_delay)
        return None

    def _request(self, number: str) -> str | None:
        try:
            response = self._session.post(
                self._url,
                data=urlencode({"num": number}),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise OperatorLookupError(
                f"BDPN request failed for {number}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise OperatorLookupError(
                f"BDPN HTTP {response.status_code} for {number}: "
                f"{response.text[:300]}"
            )

        operator = self._parse(response.text)
        logger.info("Operator of %s -> %s", number, operator)
        return operator

    @staticmethod
    def _parse(html: str) -> str | None:
        for block in _elementor_blocks(html):
            text = unescape(block)
            match = _OPERATOR_LINE.search(text)
            if not match:
                continue
            operator = (
                re.sub(r"\s+", " ", match.group(1))
                .strip()
                .replace('"', "")
                .strip()
            )
            if operator:
                return operator
        return None