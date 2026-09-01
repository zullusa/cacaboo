from abc import ABC, abstractmethod
from typing import Callable

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
    """Continuously fetches incoming messages from a queue/broker."""

    @abstractmethod
    def consume(self, handler: Callable[[SmsMessage], None]) -> None:
        """Block forever, calling handler for every incoming message."""


class NotifiedPublisher(ABC):
    """Acknowledges a successfully sent SMS back to the caller."""

    @abstractmethod
    def publish(self, appointment_id: int, offset_days: int | None = None) -> None:
        """Publish the appointment id to the notified feedback queue."""