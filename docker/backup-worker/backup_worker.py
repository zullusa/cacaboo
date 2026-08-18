"""Easy!Appointments database backup worker.

Once per day (at a configurable local time) this worker dumps the
Easy!Appointments MySQL database with ``mysqldump``, compresses the dump with
gzip and uploads it to a remote Windows share (SMB) using ``smbclient``.

Backup files are named ``<BACKUP_NAME_PREFIX>_YYYY-MM-DD_HHMMSS.sql.gz`` and the
oldest files are pruned from the share once they are older than
``BACKUP_RETENTION_DAYS``.

All configuration values are read from environment variables so that the
worker can be deployed together with the rest of the Easy!Appointments stack
in Docker.
"""

import gzip
import logging
import os
import re
import shutil
import signal
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger("backup-worker")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def get_db_config() -> dict:
    return {
        "host": env("DB_HOST", "mysql"),
        "port": env("DB_PORT", "3306"),
        "user": env("DB_USERNAME", "cacaboo"),
        "password": env("DB_PASSWORD", "cacaboo_pass"),
        "database": env("DB_NAME", "cacaboo"),
    }


def get_timezone() -> ZoneInfo:
    return ZoneInfo(env("TIMEZONE", "Europe/Moscow"))


def get_backup_time() -> tuple[int, int]:
    raw = env("BACKUP_TIME", "02:00")
    hour, minute = raw.split(":")
    return int(hour), int(minute)


class BackupWorker:
    def __init__(self) -> None:
        self.db_config = get_db_config()
        self.timezone = get_timezone()
        self.backup_time = get_backup_time()
        self.retention_days = int(env("BACKUP_RETENTION_DAYS", "30"))
        self.run_on_start = env("BACKUP_RUN_ON_START", "false").lower() in ("1", "true", "yes")
        self.prefix = env("BACKUP_NAME_PREFIX", "cacaboo")
        self.local_dir = Path(env("BACKUP_LOCAL_DIR", "/backups"))
        self.smb_host = env("SMB_HOST")
        self.smb_port = env("SMB_PORT", "445")
        self.smb_share = env("SMB_SHARE")
        self.smb_path = env("SMB_PATH", "/").strip("/")
        self.smb_username = env("SMB_USERNAME")
        self.smb_password = env("SMB_PASSWORD")
        self.smb_protocol = env("SMB_PROTOCOL", "SMB3")
        self.last_backup_date = None
        self.should_stop = False
        self.name_re = re.compile(
            rf"^{re.escape(self.prefix)}_(\d{{4}}-\d{{2}}-\d{{2}})_\d{{6}}\.sql\.gz$",
        )

    def stop(self) -> None:
        self.should_stop = True

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())

        logger.info(
            "Backup worker started (time=%s:%s, retention=%s days, share=%s/%s)",
            self.backup_time[0],
            self.backup_time[1],
            self.retention_days,
            self.smb_host or "(not configured)",
            self.smb_share or "",
        )

        while not self.should_stop:
            started_at = time.monotonic()

            try:
                self.process_cycle()
            except Exception:
                logger.exception("Backup cycle failed")

            elapsed = time.monotonic() - started_at
            time.sleep(max(1, 60 - elapsed))

        logger.info("Backup worker stopped")

    def process_cycle(self) -> None:
        now = datetime.now(self.timezone)

        if self.last_backup_date == now.date():
            return

        if not self.run_on_start and (now.hour, now.minute) < self.backup_time:
            return

        self.last_backup_date = now.date()
        self.run_backup(now)

    def run_backup(self, now: datetime) -> None:
        if not self.smb_host or not self.smb_share or not self.smb_username:
            logger.error(
                "SMB share is not configured (SMB_HOST, SMB_SHARE, SMB_USERNAME), skipping the backup",
            )
            return

        self.local_dir.mkdir(parents=True, exist_ok=True)

        dump_path = self.local_dir / f"{self.prefix}_{now:%Y-%m-%d}_{now:%H%M%S}.sql"
        archive_path = dump_path.with_suffix(".sql.gz")

        try:
            self.dump_database(dump_path)
            self.compress(dump_path, archive_path)
            self.upload(archive_path)
            self.prune_remote(now.date())
            logger.info("Backup uploaded: %s", archive_path.name)
        except Exception:
            logger.exception("Backup failed")
        finally:
            for path in (dump_path, archive_path):
                if path.exists():
                    path.unlink()

    def dump_database(self, destination: Path) -> None:
        subprocess_env = dict(os.environ)
        subprocess_env["MYSQL_PWD"] = self.db_config["password"]

        command = [
            "mysqldump",
            "--single-transaction",
            "--quick",
            "--no-tablespaces",
            "--default-character-set=utf8mb4",
            "-h",
            self.db_config["host"],
            "-P",
            self.db_config["port"],
            "-u",
            self.db_config["user"],
            self.db_config["database"],
        ]

        with open(destination, "wb") as dump_file:
            subprocess.run(
                command,
                env=subprocess_env,
                check=True,
                stdout=dump_file,
                stderr=subprocess.PIPE,
            )

    def compress(self, source: Path, destination: Path) -> None:
        with open(source, "rb") as source_file, gzip.open(destination, "wb") as destination_file:
            shutil.copyfileobj(source_file, destination_file)

    def smb_env(self) -> dict:
        subprocess_env = dict(os.environ)
        subprocess_env["PASSWD"] = self.smb_password
        return subprocess_env

    def smb_url(self) -> str:
        return f"//{self.smb_host}/{self.smb_share}"

    def smb_run(self, command: str) -> subprocess.CompletedProcess:
        args = [
            "smbclient",
            self.smb_url(),
            "-U",
            self.smb_username,
            "-m",
            self.smb_protocol,
            "-c",
            command,
        ]
        return subprocess.run(
            args,
            env=self.smb_env(),
            check=True,
            capture_output=True,
            text=True,
        )

    def remote_name(self, local_file: Path) -> str:
        return f"{self.smb_path}/{local_file.name}" if self.smb_path else local_file.name

    def upload(self, local_file: Path) -> None:
        remote = self.remote_name(local_file)
        self.smb_run(f'put {local_file} "{remote}"')

    def list_remote(self) -> list[str]:
        """List backup files on the share and return their names."""
        command = f"cd {self.smb_path}; ls" if self.smb_path else "ls"
        result = self.smb_run(command)

        files = []

        for line in result.stdout.splitlines():
            tokens = line.split()
            if not tokens:
                continue
            name = tokens[0]
            if self.name_re.match(name):
                files.append(name)

        return files

    def prune_remote(self, today) -> None:
        if self.retention_days <= 0:
            return

        try:
            files = self.list_remote()
        except Exception:
            logger.warning("Could not list remote files for pruning", exc_info=True)
            return

        for name in files:
            match = self.name_re.match(name)
            backup_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()

            if (today - backup_date) > timedelta(days=self.retention_days):
                command = f'del "{self.smb_path}/{name}"' if self.smb_path else f'del "{name}"'
                self.smb_run(command)
                logger.info("Removed old backup: %s", name)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    BackupWorker().run()


if __name__ == "__main__":
    main()