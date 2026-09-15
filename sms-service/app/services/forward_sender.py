"""SmsSender that hands a message off to the shared provider queue."""

import logging

from app.domain.models import SmsMessage
from app.errors import SmsForwardedError
from app.interfaces.protocols import SmsSender
from app.services.forward_publisher import RabbitMqForwardPublisher

logger = logging.getLogger(__name__)


class ForwardingSmsSender(SmsSender):
    """A ``SmsSender`` that re-publishes the message to the provider queue.

    Instead of delivering directly, it moves the SMS into the shared
    ``notifications_others`` queue stamped with its ``provider`` routing key
    and raises ``SmsForwardedError`` so the dispatch service neither
    acknowledges nor fails the message. The modem-service instance configured
    for that provider delivers it and reports the outcome to the ``notified``
    queue.
    """

    def __init__(self, provider: str, publisher: RabbitMqForwardPublisher) -> None:
        self._provider = provider
        self._publisher = publisher

    def __repr__(self) -> str:
        return f"ForwardingSmsSender(provider={self._provider!r})"

    def send(self, message: SmsMessage) -> str | None:
        self._publisher.publish(self._provider, message)
        raise SmsForwardedError(
            f"Message for {message.phone_number} was forwarded to the "
            f"provider queue (routing key provider={self._provider!r})"
        )