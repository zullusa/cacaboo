from abc import ABC, abstractmethod
from typing import Callable

from app.domain.models import SmsMessage


class SmsSender(ABC):
    """Delivers a single SMS through any gateway."""

    @abstractmethod
    def send(self, message: SmsMessage) -> None:
        """Send the message or raise SmsServiceError on failure."""


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