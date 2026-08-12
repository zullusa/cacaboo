from dataclasses import dataclass
from os import environ

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    modem_name: str
    modem_user: str
    modem_password: str
    modem_url_base: str
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str
    rabbitmq_vhost: str
    rabbitmq_queue: str
    rabbitmq_exchange: str
    rabbitmq_routing_key: str
    rabbitmq_heartbeat: int
    rabbitmq_reconnect_delay: int
    notified_queue: str
    notified_exchange: str
    notified_routing_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            modem_name=environ.get("MODEM_NAME", "UsbQmi0"),
            modem_user=environ.get("MODEM_USER", "samsa"),
            modem_password=environ.get("MODEM_PASSWORD", "samsa"),
            modem_url_base=environ.get("MODEM_URL_BASE", "http://192.168.0.1"),
            rabbitmq_host=environ.get("RABBITMQ_HOST", "rabbitmq"),
            rabbitmq_port=int(environ.get("RABBITMQ_PORT", "5672")),
            rabbitmq_user=environ.get("RABBITMQ_USER", "sms"),
            rabbitmq_password=environ.get("RABBITMQ_PASSWORD", "sms"),
            rabbitmq_vhost=environ.get("RABBITMQ_VHOST", "/"),
            rabbitmq_queue=environ.get("RABBITMQ_QUEUE", "sms"),
            rabbitmq_exchange=environ.get("RABBITMQ_EXCHANGE", "notifications_exchange"),
            rabbitmq_routing_key=environ.get("RABBITMQ_ROUTING_KEY", "notifications"),
            rabbitmq_heartbeat=int(environ.get("RABBITMQ_HEARTBEAT", "30")),
            rabbitmq_reconnect_delay=int(environ.get("RABBITMQ_RECONNECT_DELAY", "5")),
            notified_queue=environ.get("RABBITMQ_NOTIFIED_QUEUE", "notified"),
            notified_exchange=environ.get("RABBITMQ_NOTIFIED_EXCHANGE", "notified_exchange"),
            notified_routing_key=environ.get("RABBITMQ_NOTIFIED_ROUTING_KEY", "notified"),
        )