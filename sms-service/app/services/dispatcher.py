import logging

from app.domain.models import SmsMessage
from app.interfaces.protocols import MessageConsumer, NotifiedPublisher, SmsSender

logger = logging.getLogger(__name__)


class SmsDispatchService:
    """Orchestrates the flow: consume from queue -> send via gateway -> notify.

    Depends on abstractions (MessageConsumer, SmsSender, NotifiedPublisher)
    that are injected, so it never knows about RabbitMQ or Keenetic
    specifics (DIP).
    """

    def __init__(
        self,
        consumer: MessageConsumer,
        sender: SmsSender,
        notified_publisher: NotifiedPublisher | None = None,
    ) -> None:
        self._consumer = consumer
        self._sender = sender
        self._notified_publisher = notified_publisher

    def run(self) -> None:
        logger.info("SMS dispatch service started")
        self._consumer.consume(self._handle)

    def _handle(self, message: SmsMessage) -> None:
        logger.info("Sending SMS to %s", message.phone_number)
        self._sender.send(message)
        self._acknowledge(message)

    def _acknowledge(self, message: SmsMessage) -> None:
        if message.appointment_id is None or self._notified_publisher is None:
            return
        self._notified_publisher.publish(message.appointment_id, message.offset_days)