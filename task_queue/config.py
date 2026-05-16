"""Конфигурация ARQ worker: redis_settings, таймауты, очередь."""

from arq.connections import RedisSettings

import config


def get_redis_settings() -> RedisSettings:
    """Построить RedisSettings из config.REDIS_URL."""
    url = config.REDIS_URL
    if not url:
        # Дефолт: localhost без пароля
        return RedisSettings()
    # Парсим redis://[:password@]host:port/db
    return RedisSettings.from_dsn(url)


# Таймаут выполнения задачи (секунды)
JOB_TIMEOUT = 300

# Максимальное количество одновременных задач
MAX_JOBS = 10

# Имя очереди
QUEUE_NAME = "zenith:queue"
