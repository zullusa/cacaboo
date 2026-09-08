import logging

import pika

from app.domain.models import SmsMessage
from app.interfaces.protocols import DelayedPublisher

logger = logging.getLogger(__name__)


class RabbitMqDelayedPublisher(DelayedPublisher):
    """Publishes SMS messages to the delayed queue for a later retry.

    Called when a gateway reports a transient failure (e.g. sms.ru code 232
    "daily limit of identical messages"), so the message is not lost and not
    retried immediately.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        queue_name: str,
        vhost: str = "/",
        heartbeat: int = 30,
    ) -> None:
        self._credentials = pika.PlainCredentials(user, password)
        self._host = host
        self._port = port
        self._vhost = vhost
        self._queue_name = queue_name
        self._heartbeat = heartbeat

    def publish(self, message: SmsMessage) -> None:
        body = message.to_json()
        connection = pika.BlockingConnection(self._parameters())
        try:
            channel = connection.channel()
            channel.queue_declare(queue=self._queue_name, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=self._queue_name,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                ),
            )
            logger.info(
                "Published deferred SMS to %s (phone=%s)",
                self._queue_name,
                message.phone_number,
            )
        finally:
            connection.close()

    def _parameters(self) -> pika.ConnectionParameters:
        return pika.ConnectionParameters(
            host=self._host,
            port=self._port,
            virtual_host=self._vhost,
            credentials=self._credentials,
            heartbeat=self._heartbeat,
        )