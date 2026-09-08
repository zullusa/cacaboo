from dataclasses import dataclass
from os import environ

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    sms_provider: str
    modem_name: str
    modem_user: str
    modem_password: str
    modem_url_base: str
    sms_gate_api_key: str
    smsaero_email: str
    smsaero_channel: str
    sms_gate_status_timeout: int
    sms_gate_status_poll_interval: int
    sms_gate_from: str
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
    sms_delayed_queue: str
    sms_poll_cron: str
    telegram_bot_token: str
    telegram_channel_id: str
    telegram_proxy: str
    sms_ignore_sender: str
    sms_ignore_keywords: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            sms_provider=environ.get("SMS_PROVIDER", "keenetic").strip().lower(),
            modem_name=environ.get("MODEM_NAME", "UsbQmi0"),
            modem_user=environ.get("MODEM_USER", "samsa"),
            modem_password=environ.get("MODEM_PASSWORD", "samsa"),
            modem_url_base=environ.get("MODEM_URL_BASE", "http://192.168.0.1"),
            sms_gate_api_key=environ.get("SMS_GATE_API_KEY", ""),
            smsaero_email=environ.get("SMSAERO_EMAIL", ""),
            smsaero_channel=environ.get("SMSAERO_CHANNEL", ""),
            sms_gate_status_timeout=int(environ.get("SMS_GATE_STATUS_TIMEOUT", "120")),
            sms_gate_status_poll_interval=int(
                environ.get("SMS_GATE_STATUS_POLL_INTERVAL", "10")
            ),
            sms_gate_from=environ.get("SMS_GATE_FROM", ""),
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
            sms_delayed_queue=environ.get("SMS_DELAYED_QUEUE", "sms_delayed"),
            sms_poll_cron=environ.get("SMS_POLL_CRON", "* * * * *"),
            telegram_bot_token=environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_channel_id=environ.get("TELEGRAM_CHANNEL_ID", ""),
            telegram_proxy=environ.get(
                "TELEGRAM_PROXY",
                environ.get("HTTPS_PROXY", environ.get("https_proxy", "")),
            ),
            sms_ignore_sender=environ.get("SMS_IGNORE_SENDER", "MegaFon"),
            sms_ignore_keywords=environ.get(
                "SMS_IGNORE_KEYWORDS",
                "код подтверждения,код для входа,ваш код",
            ),
        )