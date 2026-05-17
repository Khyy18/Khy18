from __future__ import annotations
#!/usr/bin/env python3
"""Standalone backup script for PostgreSQL databases.

Supports local file storage or S3 upload. Implements retention policies
for daily (7) and weekly (4) backups. Sends Telegram notifications on
success or failure.

Environment variables:
    DATABASE_URL        - PostgreSQL connection URL
    BACKUP_MODE         - 'local' or 's3' (default: local)
    BACKUP_DIR          - Directory for local backups (default: /backups)
    AWS_S3_BUCKET       - S3 bucket name (required if BACKUP_MODE=s3)
    AWS_S3_ENDPOINT     - S3 endpoint URL (optional, for S3-compatible storage)
    AWS_ACCESS_KEY_ID   - AWS access key
    AWS_SECRET_ACCESS_KEY - AWS secret key
    TELEGRAM_BOT_TOKEN  - Telegram bot token for notifications
    TELEGRAM_CHAT_ID    - Telegram chat ID for notifications
"""

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration from environment
DATABASE_URL = os.environ.get("DATABASE_URL", "")
BACKUP_MODE = os.environ.get("BACKUP_MODE", "local")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/backups")
AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET", "")
AWS_S3_ENDPOINT = os.environ.get("AWS_S3_ENDPOINT", "")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Retention: keep last 7 daily and 4 weekly
DAILY_RETENTION = 7
WEEKLY_RETENTION = 4


def parse_database_url(url: str) -> dict:
    """Parse a PostgreSQL URL into connection parameters."""
    cleaned = url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(cleaned)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/") or "postgres",
    }


def run_pg_dump(db_params: dict, output_path: str) -> bool:
    """Execute pg_dump and save to output_path.

    Returns True on success, False on failure.
    """
    env = os.environ.copy()
    env["PGPASSWORD"] = db_params["password"]

    cmd = [
        "pg_dump",
        "--no-owner",
        "--format=custom",
        "--compress=9",
        f"--host={db_params['host']}",
        f"--port={db_params['port']}",
        f"--username={db_params['user']}",
        f"--file={output_path}",
        db_params["dbname"],
    ]

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            logger.info("pg_dump completed: %s", output_path)
            return True
        else:
            logger.error("pg_dump failed: %s", result.stderr)
            return False
    except subprocess.TimeoutExpired:
        logger.error("pg_dump timed out after 600 seconds")
        return False
    except FileNotFoundError:
        logger.error("pg_dump not found - ensure PostgreSQL client tools are installed")
        return False


def upload_to_s3(file_path: str) -> bool:
    """Upload backup file to S3 using subprocess (aws cli).

    Returns True on success, False on failure.
    """
    if not AWS_S3_BUCKET:
        logger.error("AWS_S3_BUCKET not configured")
        return False

    filename = os.path.basename(file_path)
    s3_path = f"s3://{AWS_S3_BUCKET}/backups/{filename}"

    cmd = ["aws", "s3", "cp", file_path, s3_path]
    env = os.environ.copy()
    if AWS_S3_ENDPOINT:
        cmd.extend(["--endpoint-url", AWS_S3_ENDPOINT])
    if AWS_ACCESS_KEY_ID:
        env["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID
    if AWS_SECRET_ACCESS_KEY:
        env["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info("Uploaded to S3: %s", s3_path)
            return True
        else:
            logger.error("S3 upload failed: %s", result.stderr)
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.error("S3 upload error: %s", exc)
        return False


def apply_retention(backup_dir: str) -> None:
    """Apply retention policy: keep last 7 daily and 4 weekly backups.

    Daily backups are identified as one per calendar day (keeping the latest).
    Weekly backups are the latest backup from each ISO week.
    Files not in the retention set are deleted.
    """
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        return

    dump_files = sorted(
        backup_path.glob("backup_*.dump"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not dump_files:
        return

    # Group by date
    daily_buckets: dict[str, Path] = {}
    weekly_buckets: dict[str, Path] = {}

    for f in dump_files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        day_key = mtime.strftime("%Y-%m-%d")
        week_key = mtime.strftime("%Y-W%W")

        # Keep the newest file per day/week (list is sorted newest first)
        if day_key not in daily_buckets:
            daily_buckets[day_key] = f
        if week_key not in weekly_buckets:
            weekly_buckets[week_key] = f

    # Get the files to keep
    daily_keys = sorted(daily_buckets.keys(), reverse=True)[:DAILY_RETENTION]
    weekly_keys = sorted(weekly_buckets.keys(), reverse=True)[:WEEKLY_RETENTION]

    keep_files = set()
    for key in daily_keys:
        keep_files.add(daily_buckets[key])
    for key in weekly_keys:
        keep_files.add(weekly_buckets[key])

    # Delete files not in retention set
    deleted = 0
    for f in dump_files:
        if f not in keep_files:
            try:
                f.unlink()
                deleted += 1
                logger.info("Deleted old backup: %s", f.name)
            except OSError as exc:
                logger.error("Failed to delete %s: %s", f.name, exc)

    logger.info("Retention applied: deleted %d, kept %d", deleted, len(keep_files))


def send_telegram_notification(message: str) -> bool:
    """Send a notification message via Telegram bot.

    Returns True on success, False on failure or if not configured.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram notifications not configured")
        return False

    import urllib.request
    import json

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.error("Telegram notification failed: %s", exc)
        return False


def main() -> int:
    """Run backup workflow: dump, upload/store, apply retention, notify."""
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set")
        send_telegram_notification("[BACKUP FAILED] DATABASE_URL not configured")
        return 1

    db_params = parse_database_url(DATABASE_URL)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{db_params['dbname']}_{timestamp}.dump"

    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)
    output_path = os.path.join(BACKUP_DIR, filename)

    # Run pg_dump
    success = run_pg_dump(db_params, output_path)
    if not success:
        send_telegram_notification(
            f"[BACKUP FAILED] pg_dump failed for {db_params['dbname']}"
        )
        return 1

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

    # Upload to S3 if configured
    if BACKUP_MODE == "s3":
        s3_ok = upload_to_s3(output_path)
        if not s3_ok:
            send_telegram_notification(
                f"[BACKUP WARNING] pg_dump OK but S3 upload failed for {filename}"
            )
            return 1

    # Apply retention policy
    apply_retention(BACKUP_DIR)

    # Notify success
    size_mb = file_size / (1024 * 1024)
    send_telegram_notification(
        f"[BACKUP OK] {filename} ({size_mb:.1f} MB) - mode: {BACKUP_MODE}"
    )

    logger.info("Backup completed: %s (%.1f MB)", filename, size_mb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
