"""Общая настройка для всех тестов."""

import os
import sys
from pathlib import Path

# Добавляем корень репозитория в sys.path, чтобы можно было `import config`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Минимальные env, чтобы config.py успешно импортировался.
os.environ.setdefault("TELEGRAM_TOKEN", "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
