"""Routes each SMS to a provider selected by the recipient's operator."""

import logging

from app.domain.models import SmsMessage
from app.interfaces.protocols import SmsSender, SmsStatusChecker
from app.services.operator_lookup import OperatorLookup, OperatorLookupError

logger = logging.getLogger(__name__)


class RoutingSmsSender(SmsSender, SmsStatusChecker):
    """Sends each SMS through the provider that matches the operator.

    The ``operator_sender_map`` maps a lowercase operator-name substring to
    the SmsSender used for numbers of that operator, e.g.
    ``{"мегафон": keenetic_sender}``. Numbers whose operator is unknown (or
    when the lookup fails) are sent through ``default_sender``.

    Only the default sender is expected to provide delivery tracking
    (return a non-None tracking id and implement ``wait_for_delivery``) —
    e.g. Megafon goes through a modem (no status reports) and everyone else
    through sms.ru (tracking available).
    """

    def __init__(
        self,
        operator_lookup: OperatorLookup,
        operator_sender_map: dict[str, SmsSender],
        default_sender: SmsSender,
    ) -> None:
        self._lookup = operator_lookup
        self._operator_sender_map = operator_sender_map
        self._default_sender = default_sender

    def send(self, message: SmsMessage) -> str | None:
        sender = self._select_sender(message.phone_number)
        return sender.send(message)

    # ── SmsStatusChecker ───────────────────────────────────────────────

    def wait_for_delivery(
        self,
        tracking_id: str,
        timeout: float,
        poll_interval: float,
    ) -> bool:
        checker = getattr(self._default_sender, "wait_for_delivery", None)
        if checker is None:
            return False
        return checker(tracking_id, timeout, poll_interval)

    # ── internals ──────────────────────────────────────────────────────

    def _select_sender(self, phone_number: str) -> SmsSender:
        try:
            operator = self._lookup.get_operator(phone_number)
        except OperatorLookupError:
            logger.warning(
                "Operator lookup failed for %s; falling back to %s",
                phone_number,
                type(self._default_sender).__name__,
            )
            return self._default_sender

        if operator:
            normalized = operator.lower()
            for keyword, sender in self._operator_sender_map.items():
                if keyword in normalized:
                    logger.info(
                        "Operator %r for %s -> %s",
                        operator,
                        phone_number,
                        type(sender).__name__,
                    )
                    return sender

        return self._default_sender