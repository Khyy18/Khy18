import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DB_PATH = "bot.db"
BASE_FEE_PER_DAY = 150.0
NDFL_RATE = 0.13
PFR_RATE = 0.22
OMS_RATE = 0.051
FSS_RATE = 0.029
FSS_NS_RATE = 0.002
WORKING_DAYS_MONTH = 22
AVG_DAYS_MONTH = 29.3

# Sentry DSN for error monitoring (no-op if empty)
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

# Backend API base URL
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
BACKEND_TOKEN = os.environ.get("BACKEND_TOKEN", "")

# Telegram Mini App URL (empty = no WebApp button)
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")

# Role-based access control: comma-separated chat IDs
BOT_ADMIN_IDS = os.environ.get("BOT_ADMIN_IDS", "")
BOT_CASHIER_IDS = os.environ.get("BOT_CASHIER_IDS", "")
BOT_DIRECTOR_IDS = os.environ.get("BOT_DIRECTOR_IDS", "")


def get_db_path() -> str:
    """Return the database path. Used by models to allow easy patching in tests."""
    return DB_PATH
