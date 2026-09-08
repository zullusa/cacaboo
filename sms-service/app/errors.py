class SmsServiceError(Exception):
    """Base error for the whole SMS service."""


class AuthenticationError(SmsServiceError):
    """Raised when Keenetic authentication fails."""


class SmsSendError(SmsServiceError):
    """Raised when an SMS could not be delivered to the gateway."""


class SmsDelayedError(SmsServiceError):
    """Raised when an SMS should be retried later instead of failing.

    Used for transient gateway limits (e.g. "daily limit of identical
    messages" from sms.ru) so the message can be moved to a delayed queue
    rather than retried immediately or dropped.
    """


class SmsStatusError(SmsServiceError):
    """Raised when a gateway delivery status could not be retrieved."""


class InvalidMessageError(SmsServiceError):
    """Raised when a consumed message has no phone number or text."""