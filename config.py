"""Конфигурация AI Text Agency.

Все секреты читаются из переменных окружения через os.getenv.
"""

import os


def _safe_int(value: str, default: int = 0) -> int:
    """Безопасное приведение строки к int."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# --- Секреты (только из окружения) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
_TELEGRAM_CHAT_ID_RAW = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_ID = _safe_int(_TELEGRAM_CHAT_ID_RAW, 0)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///agency.db")
REDIS_URL = os.getenv("REDIS_URL", "")

# --- CRM ---
CRM_DB_PATH = os.getenv("CRM_DB_PATH", "crm.db")

# --- Backup ---
BACKUP_S3_BUCKET = os.getenv("BACKUP_S3_BUCKET", "")
BACKUP_S3_KEY = os.getenv("BACKUP_S3_KEY", "")
BACKUP_S3_SECRET = os.getenv("BACKUP_S3_SECRET", "")
BACKUP_S3_ENDPOINT = os.getenv("BACKUP_S3_ENDPOINT", "")
BACKUP_S3_REGION = os.getenv("BACKUP_S3_REGION", "us-east-1")
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
BACKUP_SCHEDULE_HOUR = int(os.getenv("BACKUP_SCHEDULE_HOUR", "3"))

# --- Observability ---
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
LOG_FORMAT = os.getenv("LOG_FORMAT", "console")

# --- Alerting ---
ALERT_CHECK_INTERVAL_SEC = _safe_int(os.getenv("ALERT_CHECK_INTERVAL_SEC", "30"), 30)
ALERT_ERROR_RATE_THRESHOLD = float(os.getenv("ALERT_ERROR_RATE_THRESHOLD", "0.05"))
ALERT_LATENCY_P99_THRESHOLD = float(os.getenv("ALERT_LATENCY_P99_THRESHOLD", "2.0"))
ALERT_QUEUE_BACKLOG_THRESHOLD = float(os.getenv("ALERT_QUEUE_BACKLOG_THRESHOLD", "100"))

# --- Redis Sentinel ---
_REDIS_SENTINEL_HOSTS_RAW = os.getenv("REDIS_SENTINEL_HOSTS", "")
REDIS_SENTINEL_HOSTS: list[tuple[str, int]] = []
if _REDIS_SENTINEL_HOSTS_RAW.strip():
    for _pair in _REDIS_SENTINEL_HOSTS_RAW.split(","):
        _pair = _pair.strip()
        if ":" in _pair:
            _host, _port_str = _pair.rsplit(":", 1)
            REDIS_SENTINEL_HOSTS.append((_host.strip(), _safe_int(_port_str, 26379)))
        elif _pair:
            REDIS_SENTINEL_HOSTS.append((_pair, 26379))
REDIS_SENTINEL_MASTER = os.getenv("REDIS_SENTINEL_MASTER", "mymaster")

# --- Health & Rate Limiting ---
HEALTH_PORT = _safe_int(os.getenv("HEALTH_PORT", "8080"), 8080)
RATE_LIMIT_RPS = _safe_int(os.getenv("RATE_LIMIT_RPS", "10"), 10)
RATE_LIMIT_BURST = _safe_int(os.getenv("RATE_LIMIT_BURST", "20"), 20)

# --- Lead Scoring ---
LEAD_SCORE_AUTO_RESPOND_THRESHOLD = _safe_int(
    os.getenv("LEAD_SCORE_AUTO_RESPOND_THRESHOLD", "70"), 70
)
LEAD_SCORING_DB_PATH = os.getenv("LEAD_SCORING_DB_PATH", "lead_scoring.db")

# --- Content Generation ---
CONTENT_GENERATION_HOUR = _safe_int(
    os.getenv("CONTENT_GENERATION_HOUR", "10"), 10
)

# --- Pricing ---
PRICING_BASE_MULTIPLIER = float(os.getenv("PRICING_BASE_MULTIPLIER", "1.0"))

# --- Fraud Detection ---
FRAUD_SCORE_THRESHOLD = _safe_int(os.getenv("FRAUD_SCORE_THRESHOLD", "70"), 70)
FRAUD_DB_PATH = os.getenv("FRAUD_DB_PATH", "fraud.db")
FRAUD_FILTER_ENABLED = os.getenv("FRAUD_FILTER_ENABLED", "false").strip().lower() in (
    "1", "true", "yes", "on"
)

# --- Churn Prediction ---
CHURN_RISK_THRESHOLD = float(os.getenv("CHURN_RISK_THRESHOLD", "0.7"))

# --- Groq ---
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# --- Cerebras ---
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b")
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

# --- Gemini ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# --- Telegram ---
TELEGRAM_API_URL = "https://api.telegram.org"
