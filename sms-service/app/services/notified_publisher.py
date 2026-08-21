import json
import logging

import pika

from app.interfaces.protocols import NotifiedPublisher

logger = logging.getLogger(__name__)


class RabbitMqNotifiedPublisher(NotifiedPublisher):
    """Publishes appointment ids to the "notified" queue.

    Called right after an SMS is delivered so that a downstream worker can
    mark the appointment as notified.
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

    def publish(self, appointment_id: int, offset_days: int | None = None) -> None:
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

            body: dict = {"appointment_id": appointment_id}

            if offset_days is not None:
                body["offset_days"] = offset_days

            channel.basic_publish(
                exchange=self._exchange,
                routing_key=self._routing_key,
                body=json.dumps(body, ensure_ascii=False),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                ),
            )
            logger.info(
                "Published appointment %s to %s queue",
                appointment_id,
                self._queue_name,
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