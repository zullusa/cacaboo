import logging
import time

import pika

from app.domain.models import SmsMessage
from app.errors import InvalidMessageError
from app.interfaces.protocols import MessageConsumer

logger = logging.getLogger(__name__)


class RabbitMqConsumer(MessageConsumer):
    """Pulls SMS messages off a RabbitMQ queue in batch (drain) mode.

    Every ``drain()`` call fetches all currently available messages with
    ``basic_get`` and acknowledges each one immediately, so messages are
    extracted from the queue as they are handed to the caller. Processing
    afterwards happens in worker threads owned by the dispatch service.
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
        reconnect_delay: int = 5,
    ) -> None:
        self._host = host
        self._port = port
        self._credentials = pika.PlainCredentials(user, password)
        self._vhost = vhost
        self._queue_name = queue_name
        self._exchange = exchange
        self._routing_key = routing_key or queue_name
        self._heartbeat = heartbeat
        self._reconnect_delay = reconnect_delay
        self._connection = None
        self._channel = None

    def drain(self, max_messages: int | None = None) -> list[SmsMessage]:
        """Extract (ack) all available messages and parse them to SmsMessage.

        The channel must already be connected (``ensure_channel``). Returns
        the list of successfully parsed messages; malformed messages are
        nack'ed (removed without requeue) so they cannot poison the queue.
        """
        if self._channel is None or not self._channel.is_open:
            self.ensure_channel()

        messages: list[SmsMessage] = []
        while True:
            try:
                method, _properties, body = self._channel.basic_get(
                    queue=self._queue_name, auto_ack=False
                )
            except pika.exceptions.AMQPError as exc:
                logger.warning("basic_get failed (%s); reconnecting", exc)
                self.close()
                self.ensure_channel()
                continue

            if method is None:
                break

            try:
                message = SmsMessage.from_json(body)
            except InvalidMessageError as exc:
                logger.error("Dropping malformed message: %s", exc)
                self._channel.basic_nack(method.delivery_tag, requeue=False)
                continue

            self._channel.basic_ack(method.delivery_tag)
            messages.append(message)

            if max_messages is not None and len(messages) >= max_messages:
                break

        return messages

    def ensure_channel(self) -> None:
        """(Re)connect and declare/bind the queue. Safe to call repeatedly."""
        if self._connection is not None and self._connection.is_open:
            if self._channel is not None and self._channel.is_open:
                return
            self._connection.close()

        self._connection = pika.BlockingConnection(self._parameters())
        self._channel = self._connection.channel()
        self._channel.queue_declare(queue=self._queue_name, durable=True)

        if self._exchange:
            self._channel.exchange_declare(
                exchange=self._exchange, exchange_type="direct", durable=True
            )
            self._channel.queue_bind(
                queue=self._queue_name,
                exchange=self._exchange,
                routing_key=self._routing_key,
            )

        logger.info(
            "Connected to queue %r (host=%s)", self._queue_name, self._host
        )

    def _parameters(self) -> pika.ConnectionParameters:
        return pika.ConnectionParameters(
            host=self._host,
            port=self._port,
            virtual_host=self._vhost,
            credentials=self._credentials,
            heartbeat=self._heartbeat,
        )

    def close(self) -> None:
        if self._channel is not None and self._channel.is_open:
            self._channel.close()
        if self._connection is not None and self._connection.is_open:
            self._connection.close()
        self._channel = None
        self._connection = None