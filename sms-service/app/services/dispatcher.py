import logging
import queue
import threading
import time
from dataclasses import dataclass

from app.domain.models import SmsMessage
from app.errors import SmsDelayedError, SmsServiceError
from app.interfaces.protocols import (
    DelayedPublisher,
    DeliveryStatus,
    MessageConsumer,
    NotifiedPublisher,
    SmsSender,
    SmsStatusChecker,
)
from app.metrics import (
    sms_acknowledged_total,
    sms_delayed_total,
    sms_drain_errors_total,
    sms_drained_total,
    sms_delivery_wait_seconds,
    sms_send_duration_seconds,
    sms_send_queue_size,
    sms_sent_total,
    sms_status_checks_total,
    sms_status_exhausted_total,
    sms_status_retries_total,
)

logger = logging.getLogger(__name__)

STATUS_TIMEOUT = float(120)
STATUS_POLL_INTERVAL = float(10)
STATUS_MAX_RETRIES = 3
DRAIN_INTERVAL = float(1.0)

_SENTINEL = object()


@dataclass
class _PendingStatus:
    message: SmsMessage
    tracking_id: str


class SmsDispatchService:
    """Orchestrates: drain queue -> send via gateway -> (await status) -> notify.

    The queue is drained in batch: every message is extracted from the broker
    in the main loop, then handled concurrently by two pools of worker
    threads:

      * send workers call ``SmsSender.send()`` and, on a transient failure,
        move the message to the delayed queue;
      * status workers poll the gateway delivery status and only publish the
        confirmed-delivery notification to the notified queue.

    Depends on abstractions (MessageConsumer, SmsSender, SmsStatusChecker,
    NotifiedPublisher, DelayedPublisher) injected in, so it never knows about
    RabbitMQ or a concrete gateway (DIP).
    """

    def __init__(
        self,
        consumer: MessageConsumer,
        sender: SmsSender,
        notified_publisher: NotifiedPublisher | None = None,
        status_checker: SmsStatusChecker | None = None,
        delayed_publisher: DelayedPublisher | None = None,
        status_timeout: float = STATUS_TIMEOUT,
        status_poll_interval: float = STATUS_POLL_INTERVAL,
        status_max_retries: int = STATUS_MAX_RETRIES,
        drain_interval: float = DRAIN_INTERVAL,
        send_workers: int = 4,
        status_workers: int = 4,
        provider: str = "unknown",
    ) -> None:
        self._consumer = consumer
        self._sender = sender
        self._notified_publisher = notified_publisher
        self._status_checker = status_checker
        self._delayed_publisher = delayed_publisher
        self._status_timeout = status_timeout
        self._status_poll_interval = status_poll_interval
        self._status_max_retries = max(0, status_max_retries)
        self._drain_interval = drain_interval
        self._send_workers = max(1, send_workers)
        self._status_workers = max(1, status_workers)
        self._provider = provider

        self._to_send: queue.Queue = queue.Queue()
        self._to_check: queue.Queue = queue.Queue()
        self._stop = threading.Event()

    def run(self) -> None:
        logger.info("SMS dispatch service started")
        threads = [
            threading.Thread(target=self._send_loop, name=f"sms-send-{i}", daemon=True)
            for i in range(self._send_workers)
        ] + [
            threading.Thread(
                target=self._status_loop, name=f"sms-status-{i}", daemon=True
            )
            for i in range(self._status_workers)
        ]
        for t in threads:
            t.start()

        try:
            self._drain_loop()
        except KeyboardInterrupt:
            logger.info("Stopping SMS dispatch service")
            self._stop.set()
            for _ in range(self._send_workers):
                self._to_send.put(_SENTINEL)
            for _ in range(self._status_workers):
                self._to_check.put(_SENTINEL)

    # ── main loop: extract everything from the queue ───────────────────

    def _drain_loop(self) -> None:
        while not self._stop.is_set():
            try:
                messages = self._consumer.drain()
            except SmsDelayedError:
                logger.exception("Unexpected SmsDelayedError during drain")
                sms_drain_errors_total.inc()
                self._sleep_or_stop()
                continue
            except Exception:  # noqa: BLE001 - keep the drain loop alive
                logger.exception("Drain failed; retrying in %.0fs", self._drain_interval)
                sms_drain_errors_total.inc()
                self._sleep_or_stop()
                continue

            if not messages:
                self._sleep_or_stop()
                continue

            logger.info("Extracted %d message(s) from the queue", len(messages))
            sms_drained_total.inc(len(messages))
            sms_send_queue_size.inc(len(messages))
            for message in messages:
                self._to_send.put(message)

    def _sleep_or_stop(self) -> None:
        self._stop.wait(timeout=self._drain_interval)

    # ── send workers ───────────────────────────────────────────────────

    def _send_loop(self) -> None:
        while True:
            item = self._to_send.get()
            if item is _SENTINEL:
                return
            self._handle_send(item)

    def _handle_send(self, message: SmsMessage) -> None:
        logger.info("Sending SMS to %s", message.phone_number)
        sms_send_queue_size.dec()
        start = time.monotonic()
        try:
            tracking_id = self._sender.send(message)
        except SmsDelayedError as exc:
            logger.error(
                "Message deferred (%s); moving to delayed queue", exc
            )
            sms_sent_total.labels(provider=self._provider, status="delayed").inc()
            self._move_to_delayed(message)
            return
        except SmsServiceError:
            logger.exception("Failed to send SMS to %s", message.phone_number)
            sms_sent_total.labels(provider=self._provider, status="failed").inc()
            return
        except Exception:  # noqa: BLE001 - never kill a send worker
            logger.exception("Unexpected error while sending SMS to %s", message.phone_number)
            sms_sent_total.labels(provider=self._provider, status="error").inc()
            return

        elapsed = time.monotonic() - start
        sms_send_duration_seconds.labels(provider=self._provider).observe(elapsed)
        sms_sent_total.labels(provider=self._provider, status="sent").inc()

        if tracking_id and self._status_checker is not None:
            self._to_check.put(_PendingStatus(message=message, tracking_id=tracking_id))
        else:
            logger.info(
                "No status tracking for SMS to %s; acknowledging immediately",
                message.phone_number,
            )
            self._acknowledge(message)

    def _move_to_delayed(self, message: SmsMessage) -> None:
        if self._delayed_publisher is None:
            logger.error(
                "No delayed publisher configured; deferred SMS to %s is dropped",
                message.phone_number,
            )
            return
        try:
            self._delayed_publisher.publish(message)
            sms_delayed_total.labels(provider=self._provider).inc()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to move deferred SMS to delayed queue; dropping it"
            )

    # ── status workers ─────────────────────────────────────────────────

    def _status_loop(self) -> None:
        while True:
            item = self._to_check.get()
            if item is _SENTINEL:
                return
            self._handle_status(item)

    def _handle_status(self, pending: _PendingStatus) -> None:
        message = pending.message
        status = self._await_delivery(pending.tracking_id)
        if status.delivered:
            sms_status_checks_total.labels(provider=self._provider, result="delivered").inc()
            self._acknowledge(message)
        else:
            sms_status_checks_total.labels(provider=self._provider, result="not_delivered").inc()
            logger.warning(
                "SMS to %s not confirmed as delivered (timed_out=%s); "
                "not acknowledging appointment %s",
                message.phone_number,
                status.timed_out,
                message.appointment_id,
            )

    def _await_delivery(self, tracking_id: str) -> DeliveryStatus:
        """Wait for delivery, retrying when the wait window simply times out.

        A timeout means the status is still unknown (the SMS may still be in
        transit), so the check is retried up to ``status_max_retries`` times.
        A terminal failure is never retried.
        """
        attempts = self._status_max_retries + 1
        start = time.monotonic()
        for attempt in range(1, attempts + 1):
            status = self._delivered(tracking_id)
            if status.delivered or not status.timed_out:
                sms_delivery_wait_seconds.labels(provider=self._provider).observe(
                    time.monotonic() - start
                )
                return status
            if attempt < attempts:
                sms_status_retries_total.labels(provider=self._provider, status="timed_out").inc()
                logger.warning(
                    "Status wait for %s timed out (attempt %d/%d); retrying",
                    tracking_id,
                    attempt,
                    attempts,
                )
        sms_delivery_wait_seconds.labels(provider=self._provider).observe(
            time.monotonic() - start
        )
        sms_status_exhausted_total.labels(provider=self._provider).inc()
        logger.warning(
            "Status wait for %s timed out after %d attempt(s)", tracking_id, attempts
        )
        return status

    def _delivered(self, tracking_id: str) -> DeliveryStatus:
        try:
            return self._status_checker.wait_for_delivery(
                tracking_id,
                timeout=self._status_timeout,
                poll_interval=self._status_poll_interval,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Delivery status check failed for %s", tracking_id)
            return DeliveryStatus(delivered=False)

    def _acknowledge(self, message: SmsMessage) -> None:
        if message.appointment_id is None or self._notified_publisher is None:
            return
        try:
            self._notified_publisher.publish(
                message.appointment_id, message.offset_days
            )
            sms_acknowledged_total.labels(provider=self._provider).inc()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to publish notified for appointment %s",
                message.appointment_id,
            )