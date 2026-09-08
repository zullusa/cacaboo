from abc import ABC, abstractmethod

from app.domain.models import SmsMessage


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
    ) -> bool:
        """Block until a terminal status is reached.

        Returns True if the SMS was successfully delivered, False otherwise
        (failed/expired/timeout).
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