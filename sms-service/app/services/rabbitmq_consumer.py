import logging
import time
from typing import Callable

import pika

from app.domain.models import SmsMessage
from app.errors import InvalidMessageError, SmsServiceError
from app.interfaces.protocols import MessageConsumer

logger = logging.getLogger(__name__)


class RabbitMqConsumer(MessageConsumer):
    """Blocking RabbitMQ consumer that runs forever and reconnects on failure.

    Single responsibility: take raw messages off the queue, hand parsed
    ``SmsMessage`` objects to the handler and acknowledge/reject them
    accordingly. It does not know anything about SMS sending.
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

    def consume(self, handler: Callable[[SmsMessage], None]) -> None:
        while True:
            try:
                self._connect()
                self._channel.basic_qos(prefetch_count=1)
                self._channel.basic_consume(
                    queue=self._queue_name,
                    on_message_callback=self._make_callback(handler),
                    auto_ack=False,
                )
                logger.info(
                    "Listening on queue %r (host=%s)", self._queue_name, self._host
                )
                self._channel.start_consuming()
            except KeyboardInterrupt:
                logger.info("Stopping consumer")
                self.close()
                return
            except Exception as exc:  # noqa: BLE001 - reconnect on any broker error
                logger.exception("RabbitMQ error (%s); reconnecting", exc)
                self.close()
                time.sleep(self._reconnect_delay)

    def _connect(self) -> None:
        parameters = pika.ConnectionParameters(
            host=self._host,
            port=self._port,
            virtual_host=self._vhost,
            credentials=self._credentials,
            heartbeat=self._heartbeat,
        )
        self._connection = pika.BlockingConnection(parameters)
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

    def _make_callback(self, handler: Callable[[SmsMessage], None]):
        def callback(ch, method, properties, body: bytes) -> None:
            try:
                message = SmsMessage.from_json(body)
            except InvalidMessageError as exc:
                logger.error("Rejecting malformed message: %s", exc)
                ch.basic_nack(method.delivery_tag, requeue=False)
                return
            try:
                handler(message)
            except SmsServiceError as exc:
                logger.error("Failed to process message, requeueing: %s", exc)
                ch.basic_nack(method.delivery_tag, requeue=True)
                return
            ch.basic_ack(method.delivery_tag)
            logger.info("SMS %s delivered to %s", message.text, message.phone_number)

        return callback

    def close(self) -> None:
        if self._channel is not None and self._channel.is_open:
            self._channel.close()
        if self._connection is not None and self._connection.is_open:
            self._connection.close()
        self._channel = None
        self._connection = None