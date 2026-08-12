import json
from dataclasses import dataclass

from app.errors import InvalidMessageError

_PHONE_KEYS = ("phone_number", "phone", "to", "number", "mobile")
_TEXT_KEYS = ("message", "text", "body", "content")
_ID_KEYS = ("appointment_id", "appointmentId", "id")


@dataclass(frozen=True)
class SmsMessage:
    """Domain model: a single SMS to be delivered."""

    phone_number: str
    text: str
    appointment_id: int | None = None

    @classmethod
    def from_dict(cls, payload: dict) -> "SmsMessage":
        phone_number = next(
            (str(payload[key]) for key in _PHONE_KEYS if payload.get(key)), None
        )
        text = next(
            (str(payload[key]) for key in _TEXT_KEYS if payload.get(key)), None
        )
        if not phone_number or not text:
            raise InvalidMessageError(
                "Message must contain a phone number and a text "
                f"(expected keys {_PHONE_KEYS} and {_TEXT_KEYS})"
            )
        return cls(
            phone_number=phone_number,
            text=text,
            appointment_id=cls._parse_appointment_id(payload),
        )

    @staticmethod
    def _parse_appointment_id(payload: dict) -> int | None:
        for key in _ID_KEYS:
            raw = payload.get(key)
            if raw is None or raw == "":
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        return None

    @classmethod
    def from_json(cls, raw: bytes | str) -> "SmsMessage":
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise InvalidMessageError(f"Message is not valid JSON: {raw!r}") from exc
        if not isinstance(payload, dict):
            raise InvalidMessageError(
                f"Message must be a JSON object, got {type(payload).__name__}"
            )
        return cls.from_dict(payload)