from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.models import SmsMessage


@dataclass(frozen=True)
class DeliveryStatus:
    """Outcome of a single delivery-status wait window."""

    delivered: bool
    timed_out: bool = False
    queued: bool = False


class SmsSender(ABC):
    """Delivers a single SMS through any gateway."""

    @abstractmethod
    def send(self, message: SmsMessage) -> str | None:
        """Send the message or raise SmsServiceError on failure.

        Returns an external tracking id when the gateway can report message
        status later, or None when no status tracking is available
        (e.g. a modem that has no delivery reports).
        """


class SmsStatusChecker(ABC):
    """Checks delivery status of a previously sent SMS."""

    @abstractmethod
    def wait_for_delivery(
        self,
        tracking_id: str,
        timeout: float,
        poll_interval: float,
    ) -> DeliveryStatus:
        """Block until a terminal status is reached (or timeout).

        Returns ``DeliveryStatus(delivered=True)`` on confirmed delivery,
        ``DeliveryStatus(delivered=False)`` on a terminal failure, or
        ``DeliveryStatus(delivered=False, timed_out=True)`` when the timeout
        elapsed before a terminal status arrived (status still unknown — the
        caller may retry). Providers that hold messages in their own queue
        (e.g. sms.ru outside its working hours) may return
        ``DeliveryStatus(delivered=False, queued=True)`` to signal that the
        caller should remember the tracking id and re-check it later.
        """


class MessageConsumer(ABC):
    """Pulls messages from a queue/broker."""

    @abstractmethod
    def drain(self, max_messages: int | None = None) -> list[SmsMessage]:
        """Extract (ack) all currently available messages and return them.

        The queue is drained in one pass: every returned message has already
        been acknowledged and removed from the broker queue.
        """


class NotifiedPublisher(ABC):
    """Acknowledges a successfully sent SMS back to the caller."""

    @abstractmethod
    def publish(self, appointment_id: int, offset_days: int | None = None) -> None:
        """Publish the appointment id to the notified feedback queue."""


class DelayedPublisher(ABC):
    """Moves a message to a delayed/retry queue."""

    @abstractmethod
    def publish(self, message: SmsMessage) -> None:
        """Publish the message to the delayed queue for later retry."""


class QueuedSmsStore(ABC):
    """Persists SMS queued by a gateway until its working hours."""

    @abstractmethod
    def add(self, sms_id: str, message: SmsMessage) -> None:
        """Remember a gateway-queued SMS by its tracking id."""

    @abstractmethod
    def list(self) -> list[tuple[str, SmsMessage, int]]:
        """Return (sms_id, message, attempts) for every pending SMS."""

    @abstractmethod
    def touch(self, sms_id: str) -> int:
        """Record one more status re-check; return the new attempt count."""

    @abstractmethod
    def remove(self, sms_id: str) -> None:
        """Forget a pending SMS (delivered, failed or exhausted)."""