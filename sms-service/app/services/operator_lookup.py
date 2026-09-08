"""Mobile network operator (MNO) detection via the kody.su check-tel service."""

import logging
import re
import time
from html import unescape
from urllib.parse import urlencode

import requests

from app.errors import SmsServiceError

logger = logging.getLogger(__name__)

DEFAULT_LOOKUP_URL = "https://www.kody.su/check-tel"

# Default lifespan of a cached operator entry: one week.
WEEK_SECONDS = 7 * 24 * 3600

# The answer lives in the paragraph following "Результат распознавания номера":
#   <p><span style="color:#0d6c32;font-weight:bold">8 (926) 672-82-02</span>
#      &mdash; [<s>old-operator</s>] <img /> <span style="color:#...">current</span></p>
# A strikethrough <s> shows the previous operator when the number was ported
# (MNP), so it must be dropped: the remaining text is the current operator.
_RESULT_ANCHOR = re.compile(r"Результат распознавания номера", re.IGNORECASE)
_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_NUMBER_SPAN = re.compile(
    r'<span style="color:#0d6c32;font-weight:bold">.*?</span>',
    re.IGNORECASE | re.DOTALL,
)
_STRIKETHROUGH = re.compile(r"<s[^>]*>.*?</s>", re.IGNORECASE | re.DOTALL)
_IMAGE_TAG = re.compile(r"<img\b[^>]*/?>", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")


class OperatorLookupError(SmsServiceError):
    """Raised when the operator of a number cannot be determined."""


def normalize_number(phone_number: str) -> str:
    """Return a 10-digit national number (drop +7/8 prefix and formatting).

    ``+79266728202`` -> ``9266728202``, ``89266728202`` -> ``9266728202``.
    """
    digits = re.sub(r"\D", "", phone_number)
    return digits[-10:] if len(digits) >= 10 else digits


class OperatorLookup:
    """Resolves the operator of a phone number (kody.su check-tel).

    POSTs ``number=<10-digit number>`` with ``application/x-www-form-urlencoded``
    and parses the returned page. The current operator is read from the
    "Результат распознавания номера" paragraph; a strikethrough <s> element
    (the ported-away operator) is skipped so ported (MNP) numbers resolve to
    their actual current operator.

    Fresh lookups are persisted in a SqliteOperatorStore keyed by the 10-digit
    number; results are served from it until they are older than ``cache_ttl``
    (default: one week), after which the operator is checked again. This
    survives restarts and avoids hammering the remote service.

    The check-tel service occasionally answers 200 with no result block, so
    a short retry is done before giving up. When a re-check comes back empty,
    the last-known operator is kept and its timestamp refreshed, so the
    (possibly stale) value is served from cache for the rest of the TTL
    instead of hammering the service on every message.
    """

    def __init__(
        self,
        url: str = DEFAULT_LOOKUP_URL,
        timeout: float = 15.0,
        store=None,
        cache_ttl: float = WEEK_SECONDS,
        max_attempts: int = 2,
        retry_delay: float = 1.5,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._store = store
        self._cache_ttl = cache_ttl
        self._max_attempts = max(1, max_attempts)
        self._retry_delay = retry_delay
        self._session = requests.Session()

    def get_operator(self, phone_number: str) -> str | None:
        """Return the operator name (e.g. ``МегаФон ПАО``) or None."""
        number = normalize_number(phone_number)
        if not number:
            raise OperatorLookupError(
                f"cannot extract a 10-digit number from {phone_number!r}"
            )

        now = time.time()
        cached = self._store.get(number) if self._store is not None else None
        if cached is not None:
            operator, checked_at = cached
            age = now - checked_at
            if age < self._cache_ttl:
                logger.info(
                    "Operator cache hit for %s (%r, age=%.1fh)",
                    number,
                    operator,
                    age / 3600,
                )
                return operator
            logger.info(
                "Operator cache for %s expired (age=%.1fh); re-checking",
                number,
                age / 3600,
            )

        operator = self._fetch(number)
        if self._store is not None:
            try:
                if operator:
                    self._store.set(number, operator, checked_at=now)
                elif cached is not None:
                    logger.warning(
                        "Re-check of %s returned nothing; keeping last-known "
                        "operator %r for another TTL",
                        number,
                        cached[0],
                    )
                    self._store.set(number, cached[0], checked_at=now)
                    operator = cached[0]
            except Exception:  # noqa: BLE001 - keep the send path alive
                logger.exception("Failed to persist operator for %s", number)
        return operator

    def _fetch(self, number: str) -> str | None:
        for attempt in range(1, self._max_attempts + 1):
            operator = self._request(number)
            if operator:
                return operator
            if attempt < self._max_attempts:
                logger.warning(
                    "MNO returned no operator for %s (attempt %d/%d); retrying",
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
                data=urlencode({"number": number}),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise OperatorLookupError(
                f"MNO request failed for {number}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise OperatorLookupError(
                f"MNO HTTP {response.status_code} for {number}: "
                f"{response.text[:300]}"
            )

        operator = self._parse(response.text)
        logger.info("Operator of %s -> %s", number, operator)
        return operator

    @staticmethod
    def _parse(html: str) -> str | None:
        match = _RESULT_ANCHOR.search(html)
        if not match:
            return None
        block = _PARAGRAPH.search(html[match.end() :])
        if not block:
            return None

        fragment = block.group(1)
        # Drop the formatted number, the ported-away operator (<s>…</s>) and
        # the operator logo; the remaining text is the current operator.
        fragment = _NUMBER_SPAN.sub(" ", fragment)
        fragment = _STRIKETHROUGH.sub(" ", fragment)
        fragment = _IMAGE_TAG.sub(" ", fragment)
        text = unescape(_HTML_TAG.sub(" ", fragment))
        operator = re.sub(r"\s+", " ", text).strip(" \u2014-\u2013\t").strip()
        return operator or None