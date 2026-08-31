import logging
import sys

from app.config import Settings
from app.services.authenticator import KeeneticAuthenticator
from app.services.dispatcher import SmsDispatchService
from app.services.notified_publisher import RabbitMqNotifiedPublisher
from app.services.rabbitmq_consumer import RabbitMqConsumer
from app.services.sms_sender import KeeneticSmsSender
from app.services.sms_poller import SmsPoller


def build_settings() -> Settings:
    return Settings.from_env()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = build_settings()

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

    if settings.telegram_bot_token and settings.telegram_channel_id:
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
        logging.getLogger(__name__).warning(
            "SMS poller disabled (TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID not set)"
        )

    SmsDispatchService(
        consumer=consumer,
        sender=sender,
        notified_publisher=notified_publisher,
    ).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())