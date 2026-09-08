import logging
import sys
from dataclasses import dataclass

from app.config import Settings
from app.services import dispatcher as dispatcher_module
from app.services.authenticator import KeeneticAuthenticator
from app.services.delayed_publisher import RabbitMqDelayedPublisher
from app.services.dispatcher import SmsDispatchService
from app.services.notified_publisher import RabbitMqNotifiedPublisher
from app.services.operator_lookup import OperatorLookup
from app.services.rabbitmq_consumer import RabbitMqConsumer
from app.services.routing_sender import RoutingSmsSender
from app.services.sms_aero import SmsAeroSmsSender
from app.services.sms_ru import SmsRuSmsSender
from app.services.sms_sender import KeeneticSmsSender
from app.services.sms_poller import SmsPoller

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SenderConfig:
    """Resolved SMS sender plus optional delivery-status watching settings."""

    sender: object
    status_checker: object | None
    status_timeout: int
    status_poll_interval: int


def build_settings() -> Settings:
    return Settings.from_env()


def _build_keenetic(settings: Settings) -> SenderConfig:
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
    return SenderConfig(sender=sender, status_checker=None, status_timeout=0, status_poll_interval=0)


def _build_smsaero(settings: Settings) -> SenderConfig:
    if not settings.smsaero_email or not settings.sms_gate_api_key:
        raise RuntimeError(
            "SMS_PROVIDER=smsaero requires SMSAERO_EMAIL and SMS_GATE_API_KEY"
        )
    sender = SmsAeroSmsSender(
        email=settings.smsaero_email,
        api_key=settings.sms_gate_api_key,
        sign=settings.sms_gate_from or None,
        channel=settings.smsaero_channel or None,
    )
    return SenderConfig(
        sender=sender,
        status_checker=sender,
        status_timeout=settings.sms_gate_status_timeout,
        status_poll_interval=settings.sms_gate_status_poll_interval,
    )


def _build_smsru(settings: Settings) -> SenderConfig:
    if not settings.sms_gate_api_key:
        raise RuntimeError(
            "SMS_PROVIDER=smsru requires SMS_GATE_API_KEY (see https://sms.ru)"
        )
    sender = SmsRuSmsSender(
        api_id=settings.sms_gate_api_key,
        from_name=settings.sms_gate_from or None,
    )
    return SenderConfig(
        sender=sender,
        status_checker=sender,
        status_timeout=settings.sms_gate_status_timeout,
        status_poll_interval=settings.sms_gate_status_poll_interval,
    )


def _build_routing(settings: Settings) -> SenderConfig:
    """SMS_PROVIDER=routing: Megafon via Keenetic modem, everyone else via sms.ru.

    The operator is resolved per number through the BDPN lookup (nic-t.ru)
    and the matching sender is used. sms.ru is the default (and provides the
    delivery-tracking id, since modem reports are unavailable).
    """
    if not settings.sms_gate_api_key:
        raise RuntimeError(
            "SMS_PROVIDER=routing requires SMS_GATE_API_KEY (sms.ru for "
            "non-Megafon numbers)"
        )
    keenetic_cfg = _build_keenetic(settings)
    smsru_cfg = _build_smsru(settings)
    lookup = OperatorLookup(
        url=settings.sms_mno_lookup_url,
        timeout=settings.sms_mno_lookup_timeout,
    )
    sender = RoutingSmsSender(
        operator_lookup=lookup,
        operator_sender_map={"мегафон": keenetic_cfg.sender},
        default_sender=smsru_cfg.sender,
    )
    return SenderConfig(
        sender=sender,
        status_checker=sender,
        status_timeout=smsru_cfg.status_timeout,
        status_poll_interval=smsru_cfg.status_poll_interval,
    )


def _build_sender(settings: Settings) -> SenderConfig:
    if settings.sms_provider == "smsru":
        return _build_smsru(settings)
    if settings.sms_provider == "smsaero":
        return _build_smsaero(settings)
    if settings.sms_provider == "keenetic":
        return _build_keenetic(settings)
    if settings.sms_provider == "routing":
        return _build_routing(settings)
    raise RuntimeError(
        f"Unknown SMS_PROVIDER={settings.sms_provider!r} "
        "(expected 'keenetic', 'smsaero', 'smsru' or 'routing')"
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = build_settings()

    sender_config = _build_sender(settings)
    sender = sender_config.sender
    status_checker = sender_config.status_checker
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
    delayed_publisher = RabbitMqDelayedPublisher(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        user=settings.rabbitmq_user,
        password=settings.rabbitmq_password,
        vhost=settings.rabbitmq_vhost,
        queue_name=settings.sms_delayed_queue,
        heartbeat=settings.rabbitmq_heartbeat,
    )

    if (
        settings.sms_provider in ("keenetic", "routing")
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
        delayed_publisher=delayed_publisher,
        status_timeout=(
            sender_config.status_timeout
            if status_checker
            else dispatcher_module.STATUS_TIMEOUT
        ),
        status_poll_interval=(
            sender_config.status_poll_interval
            if status_checker
            else dispatcher_module.STATUS_POLL_INTERVAL
        ),
        drain_interval=settings.sms_drain_interval,
        send_workers=settings.sms_send_workers,
        status_workers=settings.sms_status_workers,
    ).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())