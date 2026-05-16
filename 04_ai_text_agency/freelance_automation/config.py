"""Конфигурация модуля автоматизации фриланса."""

import os

# Интервал сканирования (минуты)
SCAN_INTERVAL_MINUTES = 5

# Максимальное число откликов в час
MAX_RESPONSES_PER_HOUR = 10

# Пути к файлам cookies
KWORK_COOKIES_PATH = os.getenv("KWORK_COOKIES_PATH", "kwork_cookies.json")
FLRU_COOKIES_PATH = os.getenv("FLRU_COOKIES_PATH", "flru_cookies.json")

# Настройки антидетекта
PROXY_URL = os.getenv("FREELANCE_PROXY_URL", "")
STEALTH_ENABLED = os.getenv("FREELANCE_STEALTH_ENABLED", "true").lower() in ("1", "true", "yes")
MIN_ACTION_DELAY = float(os.getenv("FREELANCE_MIN_ACTION_DELAY", "1.0"))
MAX_ACTION_DELAY = float(os.getenv("FREELANCE_MAX_ACTION_DELAY", "3.0"))

# Шаблоны откликов (русский язык) с плейсхолдерами {title} и {budget}
RESPONSE_TEMPLATES = [
    (
        "Здравствуйте! Заинтересовал ваш проект \"{title}\". "
        "Имею большой опыт в данной области и готов приступить к работе. "
        "Бюджет {budget} руб. считаю адекватным. Буду рад сотрудничеству!"
    ),
    (
        "Добрый день! Ознакомился с вашим заданием \"{title}\". "
        "Могу выполнить качественно и в срок. "
        "Бюджет: {budget} руб. Давайте обсудим детали?"
    ),
    (
        "Приветствую! Проект \"{title}\" полностью соответствует моему опыту. "
        "Готов начать немедленно. Предложенный бюджет {budget} руб. устраивает. "
        "Свяжитесь со мной для обсуждения деталей."
    ),
]

# Ключевые слова для фильтрации заказов (из переменной окружения, через запятую)
_keywords_env = os.getenv("FREELANCE_KEYWORDS", "")
KEYWORDS: list[str] = [k.strip() for k in _keywords_env.split(",") if k.strip()]
