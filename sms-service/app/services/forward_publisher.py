import json
import logging

import pika

from app.domain.models import SmsMessage

logger = logging.getLogger(__name__)


class RabbitMqForwardPublisher:
    """Publishes SMS messages to the shared provider queue.

    Used by the routing sender for numbers of providers served by dedicated
    downstream workers (modem-service, e.g. Beeline). The message is forwarded
    unchanged (phone, text, appointment id and offset days) into a single
    ``notifications_others`` queue with an extra ``provider`` routing key in
    the payload, so every modem-service instance can pick its own messages.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        queue_name: str,
        vhost: str = "/",
        exchange: str = "",
        routing_key: str = "",
        heartbeat: int = 30,
    ) -> None:
        self._credentials = pika.PlainCredentials(user, password)
        self._host = host
        self._port = port
        self._vhost = vhost
        self._queue_name = queue_name
        self._exchange = exchange
        self._routing_key = routing_key or queue_name
        self._heartbeat = heartbeat

    def publish(self, provider: str, message: SmsMessage) -> None:
        payload = message.to_dict()
        payload["provider"] = provider

        body = json.dumps(payload, ensure_ascii=False)

        connection = pika.BlockingConnection(self._parameters())
        try:
            channel = connection.channel()
            channel.queue_declare(queue=self._queue_name, durable=True)

            if self._exchange:
                channel.exchange_declare(
                    exchange=self._exchange, exchange_type="direct", durable=True
                )
                channel.queue_bind(
                    queue=self._queue_name,
                    exchange=self._exchange,
                    routing_key=self._routing_key,
                )

            channel.basic_publish(
                exchange=self._exchange,
                routing_key=self._routing_key,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                ),
            )
            logger.info(
                "Forwarded SMS to %s queue (provider=%s, phone=%s)",
                self._queue_name,
                provider,
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