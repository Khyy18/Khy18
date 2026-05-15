"""Инструменты разработчика (имитация для MVP)."""

from langchain_core.tools import tool


@tool
def execute_code(code: str, language: str = "python") -> str:
    """Выполнить фрагмент кода (имитация).

    Args:
        code: Код для выполнения
        language: Язык программирования (python, javascript и т.д.)

    Returns:
        Результат выполнения
    """
    # Имитация выполнения кода для MVP
    return f"[Имитация] Код на {language} выполнен успешно. Результат: OK"


@tool
def review_code(code: str, context: str = "") -> str:
    """Провести ревью кода (имитация).

    Args:
        code: Код для ревью
        context: Контекст задачи

    Returns:
        Результат ревью
    """
    # Имитация ревью для MVP
    return (
        "[Имитация] Код проверен. "
        "Замечаний нет, качество соответствует стандартам."
    )


@tool
def search_docs(query: str, source: str = "general") -> str:
    """Поиск в документации (имитация).

    Args:
        query: Поисковый запрос
        source: Источник документации

    Returns:
        Найденная информация
    """
    # Имитация поиска для MVP
    return f"[Имитация] Результаты поиска по запросу '{query}': информация найдена в {source}."
