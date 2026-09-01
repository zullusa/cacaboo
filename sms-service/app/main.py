import logging
import sys

from app.config import Settings
from app.services.authenticator import KeeneticAuthenticator
from app.services.dispatcher import SmsDispatchService
from app.services.notified_publisher import RabbitMqNotifiedPublisher
from app.services.rabbitmq_consumer import RabbitMqConsumer
from app.services.sms_aero import SmsAeroSmsSender
from app.services.sms_sender import KeeneticSmsSender
from app.services.sms_poller import SmsPoller

logger = logging.getLogger(__name__)


def build_settings() -> Settings:
    return Settings.from_env()


def _build_keenetic(settings: Settings):
    authenticator = KeeneticAuthenticator(
        base_url=settings.modem_url_base,
        login=settings.modem_user,
        password=settings.modem_password,
    )
    sender = KeeneticSmsSender(
        authenticator=authenticator,
        interface_name=settings.modem_name,
        base_url=settings.modem_url_base,
    )
    return sender, None


def _build_smsaero(settings: Settings) -> tuple:
    if not settings.smsaero_email or not settings.smsaero_api_key:
        raise RuntimeError(
            "SMS_PROVIDER=smsaero requires SMSAERO_EMAIL and SMSAERO_API_KEY"
        )
    sender = SmsAeroSmsSender(
        email=settings.smsaero_email,
        api_key=settings.smsaero_api_key,
        sign=settings.smsaero_sign or None,
        channel=settings.smsaero_channel or None,
    )
    return sender, sender


def _build_sender(settings: Settings) -> tuple:
    if settings.sms_provider == "smsaero":
        return _build_smsaero(settings)
    if settings.sms_provider == "keenetic":
        return _build_keenetic(settings)
    raise RuntimeError(
        f"Unknown SMS_PROVIDER={settings.sms_provider!r} "
        "(expected 'keenetic' or 'smsaero')"
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = build_settings()

    sender, status_checker = _build_sender(settings)
    consumer = RabbitMqConsumer(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        user=settings.rabbitmq_user,
        password=settings.rabbitmq_password,
        vhost=settings.rabbitmq_vhost,
        queue_name=settings.rabbitmq_queue,
        exchange=settings.rabbitmq_exchange,
        routing_key=settings.rabbitmq_routing_key,
        heartbeat=settings.rabbitmq_heartbeat,
        reconnect_delay=settings.rabbitmq_reconnect_delay,
    )
    notified_publisher = RabbitMqNotifiedPublisher(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        user=settings.rabbitmq_user,
        password=settings.rabbitmq_password,
        vhost=settings.rabbitmq_vhost,
        queue_name=settings.notified_queue,
        exchange=settings.notified_exchange,
        routing_key=settings.notified_routing_key,
        heartbeat=settings.rabbitmq_heartbeat,
    )

    if (
        settings.sms_provider == "keenetic"
        and settings.telegram_bot_token
        and settings.telegram_channel_id
    ):
        authenticator = KeeneticAuthenticator(
            base_url=settings.modem_url_base,
            login=settings.modem_user,
            password=settings.modem_password,
        )
        poller = SmsPoller(
            authenticator=authenticator,
            base_url=settings.modem_url_base,
            interface_name=settings.modem_name,
            telegram_bot_token=settings.telegram_bot_token,
            telegram_channel_id=settings.telegram_channel_id,
            cron_expression=settings.sms_poll_cron,
            telegram_proxy=settings.telegram_proxy or None,
            ignore_sender=settings.sms_ignore_sender,
            ignore_keywords=tuple(
                k.strip() for k in settings.sms_ignore_keywords.split(",") if k.strip()
            ),
        )
        poller.start()
    else:
        logger.warning(
            "SMS poller disabled (requires SMS_PROVIDER=keenetic and Telegram env vars)"
        )

    SmsDispatchService(
        consumer=consumer,
        sender=sender,
        notified_publisher=notified_publisher,
        status_checker=status_checker,
    ).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())