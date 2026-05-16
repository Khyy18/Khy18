"""Конфигурация бэкапов: S3, расписание, ретенция."""

import os

BACKUP_S3_BUCKET = os.getenv("BACKUP_S3_BUCKET", "")
BACKUP_S3_KEY = os.getenv("BACKUP_S3_KEY", "")
BACKUP_S3_SECRET = os.getenv("BACKUP_S3_SECRET", "")
BACKUP_S3_ENDPOINT = os.getenv("BACKUP_S3_ENDPOINT", "")
BACKUP_S3_REGION = os.getenv("BACKUP_S3_REGION", "us-east-1")
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
BACKUP_SCHEDULE_HOUR = int(os.getenv("BACKUP_SCHEDULE_HOUR", "3"))  # UTC
