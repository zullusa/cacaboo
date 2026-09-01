import logging

from app.domain.models import SmsMessage
from app.interfaces.protocols import (
    MessageConsumer,
    NotifiedPublisher,
    SmsSender,
    SmsStatusChecker,
)

logger = logging.getLogger(__name__)

# How long to wait for a gateway delivery report before giving up and not
# acknowledging the message.
STATUS_TIMEOUT = float(120)
STATUS_POLL_INTERVAL = float(10)


class SmsDispatchService:
    """Orchestrates the flow: consume -> send -> (await status) -> notify.

    Depends on abstractions (MessageConsumer, SmsSender, SmsStatusChecker,
    NotifiedPublisher) that are injected, so it never knows about RabbitMQ
    or a concrete gateway (DIP).

    When the sender returns a tracking id, the message is acknowledged to
    the notified queue only after the delivery status is confirmed as
    successful. Senders without status reporting (e.g. a modem) are
    acknowledged right after the accept.
    """

    def __init__(
        self,
        consumer: MessageConsumer,
        sender: SmsSender,
        notified_publisher: NotifiedPublisher | None = None,
        status_checker: SmsStatusChecker | None = None,
        status_timeout: float = STATUS_TIMEOUT,
        status_poll_interval: float = STATUS_POLL_INTERVAL,
    ) -> None:
        self._consumer = consumer
        self._sender = sender
        self._notified_publisher = notified_publisher
        self._status_checker = status_checker
        self._status_timeout = status_timeout
        self._status_poll_interval = status_poll_interval

    def run(self) -> None:
        logger.info("SMS dispatch service started")
        self._consumer.consume(self._handle)

    def _handle(self, message: SmsMessage) -> None:
        logger.info("Sending SMS to %s", message.phone_number)
        tracking_id = self._sender.send(message)

        if not self._delivered(tracking_id):
            logger.warning(
                "SMS to %s not confirmed as delivered; not acknowledging "
                "appointment %s",
                message.phone_number,
                message.appointment_id,
            )
            return

        self._acknowledge(message)

    def _delivered(self, tracking_id: str | None) -> bool:
        if tracking_id is None or self._status_checker is None:
            return True
        try:
            return self._status_checker.wait_for_delivery(
                tracking_id,
                timeout=self._status_timeout,
                poll_interval=self._status_poll_interval,
            )
        except Exception:
            logger.exception("Delivery status check failed for %s", tracking_id)
            return False

    def _acknowledge(self, message: SmsMessage) -> None:
        if message.appointment_id is None or self._notified_publisher is None:
            return
        self._notified_publisher.publish(message.appointment_id, message.offset_days)