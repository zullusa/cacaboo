class SmsServiceError(Exception):
    """Base error for the whole SMS service."""


class AuthenticationError(SmsServiceError):
    """Raised when Keenetic authentication fails."""


class SmsSendError(SmsServiceError):
    """Raised when an SMS could not be delivered to the modem."""


class InvalidMessageError(SmsServiceError):
    """Raised when a consumed message has no phone number or text."""