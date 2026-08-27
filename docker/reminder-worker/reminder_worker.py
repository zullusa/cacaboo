"""Easy!Appointments reminder worker.

Every minute this worker scans the `appointments` table for appointments whose
start date/time is exactly one of the configured reminder offsets ahead (by
default 7 days, 3 days and 1 day). For every matching appointment a reminder
notification is published to the RabbitMQ queue using the same payload format
as the "appointment_saved" notifications that are produced when an appointment
is booked.

All configuration values are read from environment variables so that the
worker can be deployed together with the rest of the Easy!Appointments stack
in Docker.
"""

import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pika
import pymysql

logger = logging.getLogger("reminder-worker")



def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


ADDRESS = env("ADDRESS", "Пушкина,19")
CONTACT_PHONE = env("CONTACT_PHONE", "+74955554433")

def get_db_config() -> dict:
    return {
        "host": env("DB_HOST", "mysql"),
        "port": int(env("DB_PORT", "3306")),
        "user": env("DB_USERNAME", "cacaboo"),
        "password": env("DB_PASSWORD", "cacaboo_pass"),
        "database": env("DB_NAME", "cacaboo"),
        "charset": "utf8mb4",
        "autocommit": True,
    }


def get_broker_config() -> dict:
    return {
        "host": env("RABBITMQ_HOST", "mq.bossonoga.ru"),
        "port": int(env("RABBITMQ_PORT", "5672")),
        "user": env("RABBITMQ_USERNAME", "cacaboo"),
        "password": env("RABBITMQ_PASSWORD", ""),
        "vhost": env("RABBITMQ_VHOST", "/"),
    }


def get_amqp_config() -> dict:
    return {
        **get_broker_config(),
        "queue": env("RABBITMQ_QUEUE", "notifications"),
        "exchange": env("RABBITMQ_EXCHANGE", "notifications_exchange"),
        "routing_key": env("RABBITMQ_ROUTING_KEY", "notifications"),
    }


def get_notified_amqp_config() -> dict:
    return {
        **get_broker_config(),
        "queue": env("RABBITMQ_NOTIFIED_QUEUE", "notified"),
        "exchange": env("RABBITMQ_NOTIFIED_EXCHANGE", "notified_exchange"),
        "routing_key": env("RABBITMQ_NOTIFIED_ROUTING_KEY", "notified"),
    }


def get_offsets() -> list[int]:
    raw = env("REMINDER_OFFSETS", "7,3,1")
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def get_timezone() -> ZoneInfo:
    return ZoneInfo(env("TIMEZONE", "Europe/Moscow"))


def parse_start_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_message(start_datetime: datetime) -> str:
    return (
        f"Добрый день! Напоминаем, что вы записаны на СТО по адресу "
        f"{ADDRESS} в {start_datetime:%H:%M} {start_datetime:%d.%m.%Y}. "
        f"Телефон для связи с нами {CONTACT_PHONE}."
    )


def build_payload(
    appointment: dict,
    start_datetime: datetime,
    subject: str,
    phone: str | None = None,
    offset_days: int | None = None,
) -> dict:
    return {
        "type": env("REMINDER_TYPE", "appointment_reminder"),
        "appointment_id": int(appointment["id"]),
        "phone": phone if phone is not None else (appointment["phone"] or ""),
        "email": appointment["email"] or "",
        "subject": subject,
        "message": build_message(start_datetime),
        "offset_days": offset_days,
    }


class ReminderWorker:
    def __init__(self) -> None:
        self.db_config = get_db_config()
        self.amqp_config = get_amqp_config()
        self.offsets = get_offsets()
        self.timezone = get_timezone()
        self.poll_interval = int(env("POLL_INTERVAL", "60"))
        self.tolerance = timedelta(seconds=int(env("TOLERANCE_SECONDS", "120")))
        self.subject = env("REMINDER_SUBJECT", "Напоминание о записи на СТО")
        self.table_prefix = env("DB_PREFIX", "ea_")
        self.notified_status = env("REMINDER_STATUS_NOTIFIED", "Оповещен")
        self.booked_status = env("REMINDER_STATUS_BOOKED", "Записано")
        self.error_status = env("REMINDER_STATUS_ERROR", "Ошибка")
        self.phone_prefix = env("REMINDER_PHONE_PREFIX", "+7")
        self.telegram_bot_token = env("TELEGRAM_BOT_TOKEN")
        self.telegram_channel_id = env("TELEGRAM_CHANNEL_ID")
        self.should_stop = False
        self.schema_missing_logged = False
        self.heartbeat = int(env("RABBITMQ_HEARTBEAT", "60"))
        self.notified_updater = NotifiedStatusUpdater(
            amqp_config=get_notified_amqp_config(),
            db_config=self.db_config,
            status=self.notified_status,
            table_prefix=self.table_prefix,
            heartbeat=self.heartbeat,
            status_offset=int(env("REMINDER_STATUS_OFFSET", "1")),
        )

    def stop(self) -> None:
        self.should_stop = True
        self.notified_updater.stop()

    def normalize_phone(self, phone: str) -> str:
        """Prepend the configured phone prefix (e.g. "+7") when missing."""
        phone = (phone or "").strip()
        if not phone or phone.startswith("+"):
            return phone
        return f"{self.phone_prefix}{phone}"

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())

        notified_thread = threading.Thread(
            target=self.notified_updater.run,
            name="notified-status-updater",
            daemon=True,
        )
        notified_thread.start()

        logger.info(
            "Reminder worker started (offsets=%s days, poll interval=%s s, tolerance=%s s)",
            self.offsets,
            self.poll_interval,
            self.tolerance.seconds,
        )

        while not self.should_stop:
            started_at = time.monotonic()

            try:
                self.process_cycle()
            except Exception:
                logger.exception("Reminder cycle failed")

            elapsed = time.monotonic() - started_at
            time.sleep(max(1, self.poll_interval - elapsed))

        logger.info("Reminder worker stopped")

    def process_cycle(self) -> None:
        now = datetime.now(self.timezone)

        connection = pymysql.connect(**self.db_config)
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                if not self.app_schema_present(cursor):
                    if not self.schema_missing_logged:
                        logger.warning(
                            "Easy!Appointments schema not found "
                            "(table %sappointments is missing). "
                            "Waiting for the application to be installed.",
                            self.table_prefix,
                        )
                        self.schema_missing_logged = True
                    return

                self.schema_missing_logged = False

                self.ensure_log_table(cursor)

                for days in self.offsets:
                    self.process_offset(cursor, now, days)

                self.process_last_day(cursor, now)
        finally:
            connection.close()

    def app_schema_present(self, cursor) -> bool:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            (self.table_prefix + "appointments",),
        )
        return cursor.fetchone()["cnt"] > 0

    def process_offset(self, cursor, now: datetime, days: int) -> None:
        offset = timedelta(days=days)
        window_start = now + offset - self.tolerance
        window_end = now + offset

        appointments = self.fetch_candidates(cursor, window_start, window_end)

        if not appointments:
            return

        logger.info("Found %s appointment(s) %s day(s) ahead", len(appointments), days)

        self.notify_appointments(cursor, appointments, days)

    def process_last_day(self, cursor, now: datetime) -> None:
        """Remind booked appointments that start within the next 24 hours.

        Appointments that were created (or moved) into the last day window
        never match the exact one day ahead reminder window, so they are
        picked up here. The messages are identical to the one day ahead
        reminders (including the status change to "Оповещен" after a
        successful delivery) and share the same deduplication marker.
        """
        window_start = now
        window_end = now + timedelta(days=1)

        appointments = self.fetch_candidates(cursor, window_start, window_end)

        if not appointments:
            return

        logger.info("Found %s appointment(s) starting within the next day", len(appointments))

        self.notify_appointments(cursor, appointments, 1)

    def notify_appointments(self, cursor, appointments: list[dict], days: int) -> None:
        for appointment in appointments:
            appointment_id = int(appointment["id"])
            start_datetime = parse_start_datetime(appointment["start_datetime"])

            if not appointment["phone"]:
                logger.info(
                    "Skipping appointment %s: no recipient phone number",
                    appointment_id,
                )
                continue

            if self.already_sent(cursor, appointment_id, days):
                logger.info(
                    "Skipping appointment %s: reminder %s day(s) ahead already sent",
                    appointment_id,
                    days,
                )
                continue

            raw_phone = (appointment["phone"] or "").strip()

            if raw_phone.startswith("8"):
                logger.warning(
                    "Skipping SMS for appointment %s: phone number starts with '8' ('%s')",
                    appointment_id,
                    raw_phone,
                )
                self.notify_telegram(appointment, raw_phone)
                self.mark_error(cursor, appointment_id)
                self.mark_sent(cursor, appointment_id, days)
                continue

            payload = build_payload(
                appointment,
                start_datetime,
                self.subject,
                self.normalize_phone(appointment["phone"]),
                offset_days=days,
            )

            try:
                self.publish(payload)
            except Exception:
                logger.exception("Could not publish reminder for appointment %s", appointment_id)
                continue

            self.mark_sent(cursor, appointment_id, days)

            logger.info(
                "Published reminder for appointment %s (%s day(s) ahead)",
                appointment_id,
                days,
            )

    def ensure_log_table(self, cursor) -> None:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_prefix}reminder_log (
                appointment_id BIGINT UNSIGNED NOT NULL,
                offset_days TINYINT UNSIGNED NOT NULL,
                sent_at DATETIME NOT NULL,
                PRIMARY KEY (appointment_id, offset_days)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    def fetch_candidates(self, cursor, window_start: datetime, window_end: datetime) -> list[dict]:
        cursor.execute(
            f"""
            SELECT
                a.id,
                a.start_datetime,
                a.car_make,
                a.car_plate,
                a.notes,
                COALESCE(s.name, '') AS appointment_type,
                COALESCE(NULLIF(u.phone_number, ''), u.mobile_number, '') AS phone,
                COALESCE(u.email, '') AS email,
                COALESCE(u.first_name, '') AS first_name,
                COALESCE(u.last_name, '') AS last_name
            FROM {self.table_prefix}appointments a
            LEFT JOIN {self.table_prefix}services s ON s.id = a.id_services
            LEFT JOIN {self.table_prefix}users u ON u.id = a.id_users_customer
            WHERE a.is_unavailability = 0
              AND a.status = %s
              AND a.start_datetime BETWEEN %s AND %s
            """,
            (
                self.booked_status,
                window_start.strftime("%Y-%m-%d %H:%M:%S"),
                window_end.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        return cursor.fetchall()

    def already_sent(self, cursor, appointment_id: int, offset_days: int) -> bool:
        cursor.execute(
            f"SELECT 1 FROM {self.table_prefix}reminder_log WHERE appointment_id = %s AND offset_days = %s",
            (appointment_id, offset_days),
        )
        return cursor.fetchone() is not None

    def mark_sent(self, cursor, appointment_id: int, offset_days: int) -> None:
        cursor.execute(
            f"INSERT INTO {self.table_prefix}reminder_log (appointment_id, offset_days, sent_at) VALUES (%s, %s, %s)",
            (appointment_id, offset_days, datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")),
        )

    def mark_error(self, cursor, appointment_id: int) -> None:
        cursor.execute(
            f"UPDATE {self.table_prefix}appointments SET status = %s WHERE id = %s",
            (self.error_status, appointment_id),
        )

    def notify_telegram(self, appointment: dict, phone: str) -> None:
        """Send a message to the configured Telegram channel about an invalid phone number."""
        if not self.telegram_bot_token or not self.telegram_channel_id:
            logger.warning(
                "Telegram is not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID); "
                "skipping invalid phone notification for appointment %s",
                appointment["id"],
            )
            return

        first_name = (appointment.get("first_name") or "").strip()
        last_name = (appointment.get("last_name") or "").strip()
        customer_name = " ".join(part for part in (first_name, last_name) if part) or "—"

        car_make = (appointment.get("car_make") or "").strip() or "—"
        car_plate = (appointment.get("car_plate") or "").strip() or "—"
        start_datetime = parse_start_datetime(appointment["start_datetime"])
        start_time = start_datetime.strftime("%H:%M")
        start_date = start_datetime.strftime("%d.%m.%Y")

        text = (
            "⚠️ Некорректный номер телефона\n"
            f"👤 Клиент: {customer_name}\n"
            f"🚗 Авто: {car_make}\n"
            f"🔢 Регномер: {car_plate}\n"
            f"📞 Телефон: {phone}\n"
            f"🗓 Дата/время: {start_date} {start_time}"
        )

        url = (
            f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            f"?chat_id={urllib.parse.quote(str(self.telegram_channel_id))}"
            f"&text={urllib.parse.quote(text)}"
        )

        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                body = response.read()
                logger.info(
                    "Telegram notification sent for appointment %s (invalid phone '%s')",
                    appointment["id"],
                    phone,
                )
                if response.status != 200:
                    logger.warning(
                        "Telegram responded with status %s: %s",
                        response.status,
                        body.decode("utf-8", errors="replace")[:200],
                    )
        except Exception:
            logger.exception(
                "Could not send Telegram notification for appointment %s (invalid phone '%s')",
                appointment["id"],
                phone,
            )

    def publish(self, payload: dict) -> None:
        credentials = pika.PlainCredentials(self.amqp_config["user"], self.amqp_config["password"])
        parameters = pika.ConnectionParameters(
            host=self.amqp_config["host"],
            port=self.amqp_config["port"],
            virtual_host=self.amqp_config["vhost"],
            credentials=credentials,
            heartbeat=self.heartbeat,
        )

        queue = self.amqp_config["queue"]
        exchange = self.amqp_config["exchange"]
        routing_key = self.amqp_config["routing_key"]

        connection = pika.BlockingConnection(parameters)
        try:
            channel = connection.channel()
            channel.queue_declare(queue=queue, durable=True)

            if exchange:
                channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)
                channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)

            channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(payload, ensure_ascii=False),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                ),
            )
        finally:
            connection.close()


class NotifiedStatusUpdater:
    """Consumes the "notified" queue and marks appointments as notified.

    The SMS service publishes every appointment id right after it has
    successfully sent the reminder SMS. This consumer turns that signal
    into a database status update (e.g. "Оповещен") — but only for the
    reminders that were sent for the configured offset (by default one
    day ahead). Reminders for other offsets (e.g. 7 or 3 days ahead)
    do not change the appointment status.
    """

    def __init__(
        self,
        amqp_config: dict,
        db_config: dict,
        status: str,
        table_prefix: str,
        reconnect_delay: int = 5,
        heartbeat: int = 60,
        status_offset: int = 1,
    ) -> None:
        self.amqp_config = amqp_config
        self.db_config = db_config
        self.status = status
        self.table_prefix = table_prefix
        self.reconnect_delay = reconnect_delay
        self.heartbeat = heartbeat
        self.status_offset = status_offset
        self.should_stop = False

    def stop(self) -> None:
        self.should_stop = True

    def run(self) -> None:
        while not self.should_stop:
            try:
                self._consume_blocking()
            except pika.exceptions.AMQPConnectionError as exc:
                if self.should_stop:
                    break
                logger.warning(
                    "RabbitMQ connection lost (%s); reconnecting in %ss",
                    exc,
                    self.reconnect_delay,
                )
                time.sleep(self.reconnect_delay)
            except Exception:
                logger.exception("Notified consumer error; reconnecting")
                time.sleep(self.reconnect_delay)

    def _consume_blocking(self) -> None:
        queue = self.amqp_config["queue"]
        exchange = self.amqp_config["exchange"]
        routing_key = self.amqp_config["routing_key"]

        credentials = pika.PlainCredentials(
            self.amqp_config["user"], self.amqp_config["password"]
        )
        parameters = pika.ConnectionParameters(
            host=self.amqp_config["host"],
            port=self.amqp_config["port"],
            virtual_host=self.amqp_config["vhost"],
            credentials=credentials,
            heartbeat=self.heartbeat,
        )

        connection = pika.BlockingConnection(parameters)
        try:
            channel = connection.channel()
            channel.queue_declare(queue=queue, durable=True)

            if exchange:
                channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)
                channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=queue,
                on_message_callback=self._make_callback(),
                auto_ack=False,
            )

            logger.info("Listening for notified appointments on queue %r", queue)
            channel.start_consuming()
        finally:
            try:
                connection.close()
            except pika.exceptions.AMQPConnectionError:
                pass

    def _make_callback(self):
        def callback(ch, method, properties, body: bytes) -> None:
            try:
                appointment_id, offset_days = self._parse_message(body)

                if appointment_id is None:
                    logger.warning(
                        "Discarding notified message without appointment id: %r",
                        body,
                    )
                    ch.basic_ack(method.delivery_tag)
                    return

                if offset_days is not None and offset_days != self.status_offset:
                    logger.info(
                        "Appointment %s not marked as '%s': reminder was sent %s day(s) ahead "
                        "(only %s day(s) ahead reminders update the status)",
                        appointment_id,
                        self.status,
                        offset_days,
                        self.status_offset,
                    )
                    ch.basic_ack(method.delivery_tag)
                    return

                self._mark_notified(appointment_id)

                logger.info(
                    "Appointment %s marked as '%s'",
                    appointment_id,
                    self.status,
                )
                ch.basic_ack(method.delivery_tag)
            except Exception:
                logger.exception(
                    "Could not mark appointment as notified; requeueing"
                )
                ch.basic_nack(method.delivery_tag, requeue=True)

        return callback

    @staticmethod
    def _parse_message(body: bytes) -> tuple[int | None, int | None]:
        """Extract the appointment id and the reminder offset from a message."""
        payload = json.loads(body)

        if not isinstance(payload, dict):
            return None, None

        return _to_int(payload.get("appointment_id")), _to_int(payload.get("offset_days"))

    def _mark_notified(self, appointment_id: int) -> None:
        connection = pymysql.connect(**self.db_config)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {self.table_prefix}appointments SET status = %s WHERE id = %s",
                    (self.status, appointment_id),
                )
        finally:
            connection.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    try:
        ReminderWorker().run()
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
