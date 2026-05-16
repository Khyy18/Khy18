"""Инструменты разработчика - записывают активность в БД."""

import os
import subprocess
import tempfile

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Sam."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Sam")
        )
        agent = result.scalar_one_or_none()
        if agent:
            log = ActivityLog(
                agent_id=agent.id,
                action_type=action_type,
                action_description=description,
            )
            session.add(log)
            await session.commit()


@tool
async def execute_python_code(code: str) -> str:
    """Выполнить Python код в изолированном subprocess.

    Args:
        code: Python код для выполнения

    Returns:
        Результат выполнения (stdout или stderr)
    """
    try:
        # Minimal safe environment - only PATH for Python to work
        safe_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=tmpdir,
                env=safe_env,
                stdin=subprocess.DEVNULL,
            )
        if result.returncode == 0:
            output = result.stdout.strip() or "(код выполнен без вывода)"
            await _log_activity("code_executed", f"Python код выполнен успешно")
            return output
        else:
            error = result.stderr.strip()
            await _log_activity("code_error", f"Ошибка выполнения кода")
            return f"Ошибка выполнения:\n{error}"
    except subprocess.TimeoutExpired:
        await _log_activity("code_timeout", "Превышено время выполнения кода (5 сек)")
        return "Ошибка: превышено время выполнения (таймаут 5 секунд)."
    except Exception as e:
        return f"Ошибка: {str(e)}"


# Обратная совместимость
@tool
async def execute_code(code: str, language: str = "python") -> str:
    """Выполнить фрагмент кода (обратная совместимость).

    Args:
        code: Код для выполнения
        language: Язык программирования (python, javascript и т.д.)

    Returns:
        Результат выполнения
    """
    if language == "python":
        return await execute_python_code.ainvoke({"code": code})
    result = f"Язык {language} не поддерживается напрямую. Используйте execute_python_code для Python."
    await _log_activity("code_executed", f"Попытка выполнить код на {language}")
    return result


@tool
async def review_code(code: str, context: str = "") -> str:
    """Провести базовый анализ кода.

    Args:
        code: Код для ревью
        context: Контекст задачи

    Returns:
        Результат ревью с замечаниями
    """
    lines = code.strip().split("\n")
    issues = []
    total_lines = len(lines)

    # Проверка на bare except
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped == "except:" or stripped == "except :":
            issues.append(f"  Строка {i}: bare except - укажите конкретный тип исключения")

    # Проверка на отсутствие docstring в функциях/классах
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            if i < total_lines:
                next_line = lines[i].strip() if i < total_lines else ""
                if not next_line.startswith('"""') and not next_line.startswith("'''"):
                    name = stripped.split("(")[0].replace("def ", "").replace("class ", "")
                    issues.append(f"  Строка {i}: '{name}' - отсутствует docstring")

    # Формируем результат
    report_parts = [f"Код проверен ({total_lines} строк)."]
    if context:
        report_parts.append(f"Контекст: {context}")

    if issues:
        report_parts.append(f"Найдено замечаний: {len(issues)}")
        report_parts.extend(issues)
    else:
        report_parts.append("Замечаний не найдено, код соответствует базовым стандартам.")

    result = "\n".join(report_parts)
    await _log_activity("code_reviewed", f"Проведено ревью кода. Контекст: {context or 'общий'}")
    return result


@tool
async def search_docs(query: str, source: str = "general") -> str:
    """Поиск в документации и справочных ресурсах.

    Args:
        query: Поисковый запрос
        source: Источник документации (python, fastapi, langchain, general)

    Returns:
        Информация о том, где найти документацию
    """
    sources_map = {
        "python": "https://docs.python.org/3/search.html?q=",
        "fastapi": "https://fastapi.tiangolo.com/search/?q=",
        "langchain": "https://python.langchain.com/docs/",
        "sqlalchemy": "https://docs.sqlalchemy.org/en/20/search.html?q=",
        "general": "https://docs.python.org/3/search.html?q=",
    }

    doc_source = source.lower() if source.lower() in sources_map else "general"
    doc_url = sources_map[doc_source]

    result = (
        f"Поиск по запросу '{query}' в документации {source}:\n"
        f"Ссылка: {doc_url}{query}\n"
        f"Рекомендации:\n"
        f"  - Проверьте официальную документацию: {doc_url}\n"
        f"  - Для примеров кода используйте web_search\n"
        f"  - Для Python stdlib: https://docs.python.org/3/library/"
    )
    await _log_activity("docs_searched", f"Поиск в документации: '{query}' (источник: {source})")
    return result
