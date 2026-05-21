"""Общая настройка для всех тестов."""

import os
import sys
from pathlib import Path

# Добавляем корень репозитория в sys.path, чтобы можно было `import config`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Добавляем 08_funding_arbitrage для общих модулей (api_engine, arbitrage_engine, etc.)
# Вставляем ПОСЛЕ _REPO_ROOT, чтобы локальные модули (optimize.py) находились первыми.
_FUNDING_ARB = _REPO_ROOT.parent / "08_funding_arbitrage"
if str(_FUNDING_ARB) not in sys.path:
    sys.path.append(str(_FUNDING_ARB))

# Минимальные env, чтобы config.py успешно импортировался.
os.environ.setdefault("TELEGRAM_TOKEN", "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "1")

# Отключаем фильтр торговой сессии для тестов (зависит от текущего UTC часа).
os.environ.setdefault("MOMENTUM_SESSION_FILTER_ENABLED", "false")
