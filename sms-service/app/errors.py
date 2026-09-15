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


class SmsForwardedError(SmsServiceError):
    """Raised after a message was handed off to another provider's queue.

    Used when the routing sender decides that a number belongs to another
    provider (e.g. Beeline) and re-publishes the message to that provider's
    own queue. The caller must NOT acknowledge (or fail) the message, because
    the downstream provider worker will report the delivery status.
    """


class InvalidMessageError(SmsServiceError):
    """Raised when a consumed message has no phone number or text."""