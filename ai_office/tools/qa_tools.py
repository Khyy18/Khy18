"""Инструменты QA инженера - записывают активность в БД."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent, Task


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Leo."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Leo")
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


def _generate_test_scenarios(feature: str) -> dict:
    """Генерация тест-сценариев на основе ключевых слов фичи."""
    feature_lower = feature.lower()

    positive_cases = ["Основной сценарий выполняется успешно"]
    negative_cases = ["Обработка пустых входных данных"]
    edge_cases = ["Предельные значения параметров"]
    performance = ["Время отклика в пределах допустимого"]

    if "авториз" in feature_lower or "auth" in feature_lower or "логин" in feature_lower:
        positive_cases.extend([
            "Успешный вход с корректными учетными данными",
            "Сессия создается после авторизации",
        ])
        negative_cases.extend([
            "Отклонение неверного пароля",
            "Блокировка после множественных неудачных попыток",
        ])
        edge_cases.extend([
            "Истечение срока сессии",
            "Одновременные сессии одного пользователя",
        ])
        performance.append("Авторизация завершается менее чем за 1 секунду")

    if "поиск" in feature_lower or "search" in feature_lower or "фильтр" in feature_lower:
        positive_cases.extend([
            "Поиск возвращает релевантные результаты",
            "Фильтрация работает по всем указанным критериям",
        ])
        negative_cases.extend([
            "Пустой запрос обрабатывается корректно",
            "Специальные символы в запросе не вызывают ошибок",
        ])
        edge_cases.extend([
            "Поиск при пустой базе данных",
            "Очень длинная строка запроса",
        ])
        performance.append("Поиск выполняется менее чем за 500мс")

    if "форм" in feature_lower or "form" in feature_lower or "ввод" in feature_lower:
        positive_cases.extend([
            "Форма принимает валидные данные",
            "Данные корректно сохраняются после отправки",
        ])
        negative_cases.extend([
            "Валидация обязательных полей",
            "Отклонение данных неверного формата",
        ])
        edge_cases.extend([
            "Максимальная длина полей",
            "Двойная отправка формы",
        ])
        performance.append("Отправка формы менее чем за 2 секунды")

    if "api" in feature_lower or "запрос" in feature_lower or "endpoint" in feature_lower:
        positive_cases.extend([
            "Эндпоинт возвращает корректный ответ (200)",
            "Формат ответа соответствует спецификации",
        ])
        negative_cases.extend([
            "Некорректный HTTP-метод возвращает 405",
            "Невалидное тело запроса возвращает 422",
        ])
        edge_cases.extend([
            "Большой объем данных в запросе",
            "Параллельные запросы к одному ресурсу",
        ])
        performance.append("API отвечает менее чем за 200мс под нагрузкой")

    if "уведомлен" in feature_lower or "notification" in feature_lower:
        positive_cases.extend([
            "Уведомление доставляется получателю",
            "Содержимое уведомления корректно",
        ])
        negative_cases.extend([
            "Обработка недоступного получателя",
            "Повторная отправка при сбое",
        ])
        edge_cases.extend([
            "Массовая рассылка уведомлений",
            "Уведомление с максимальной длиной текста",
        ])
        performance.append("Уведомление доставляется в течение 5 секунд")

    return {
        "positive_cases": positive_cases,
        "negative_cases": negative_cases,
        "edge_cases": edge_cases,
        "performance": performance,
    }


@tool
async def create_test_plan(feature: str) -> str:
    """Создать структурированный тест-план для фичи.

    Args:
        feature: Описание фичи для тестирования

    Returns:
        Структурированный тест-план с разделами
    """
    scenarios = _generate_test_scenarios(feature)

    sections = []
    sections.append(f"Тест-план: {feature}")
    sections.append("=" * 40)

    sections.append("\n## Позитивные сценарии")
    for i, case in enumerate(scenarios["positive_cases"], 1):
        sections.append(f"  {i}. {case}")

    sections.append("\n## Негативные сценарии")
    for i, case in enumerate(scenarios["negative_cases"], 1):
        sections.append(f"  {i}. {case}")

    sections.append("\n## Граничные случаи")
    for i, case in enumerate(scenarios["edge_cases"], 1):
        sections.append(f"  {i}. {case}")

    sections.append("\n## Производительность")
    for i, case in enumerate(scenarios["performance"], 1):
        sections.append(f"  {i}. {case}")

    result = "\n".join(sections)
    await _log_activity("test_plan_created", f"Тест-план: {feature}")
    return result


_SEVERITY_PRIORITY_MAP = {
    "blocker": "critical",
    "critical": "high",
    "major": "medium",
    "minor": "low",
}


@tool
async def report_bug(title: str, steps: str, expected: str, actual: str, severity: str) -> str:
    """Зарегистрировать баг-репорт и создать задачу в БД.

    Args:
        title: Заголовок бага
        steps: Шаги воспроизведения
        expected: Ожидаемое поведение
        actual: Фактическое поведение
        severity: Серьезность (blocker, critical, major, minor)

    Returns:
        Подтверждение регистрации бага с ID задачи
    """
    priority = _SEVERITY_PRIORITY_MAP.get(severity.lower(), "medium")

    task_id = None
    async with async_session() as session:
        task = Task(
            description=f"[BUG] {title}\n\nШаги: {steps}\nОжидание: {expected}\nРеальность: {actual}",
            creator_type="agent",
            creator_id="Leo",
            status="open",
            priority=priority,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id

    report = (
        f"Баг-репорт #{task_id}\n"
        f"{'=' * 40}\n"
        f"Заголовок: {title}\n"
        f"Серьезность: {severity}\n"
        f"Приоритет: {priority}\n"
        f"Статус: open\n"
        f"\nШаги воспроизведения:\n{steps}\n"
        f"\nОжидаемое поведение:\n{expected}\n"
        f"\nФактическое поведение:\n{actual}\n"
    )

    await _log_activity("bug_reported", f"Баг #{task_id}: {title}")
    return report


@tool
async def verify_fix(bug_id: str) -> str:
    """Верифицировать исправление бага по ID задачи.

    Args:
        bug_id: Идентификатор задачи (бага)

    Returns:
        Результат верификации с чеклистом
    """
    task = None
    async with async_session() as session:
        result = await session.execute(
            select(Task).where(Task.id == int(bug_id))
        )
        task = result.scalar_one_or_none()

    if not task:
        await _log_activity("fix_verification_failed", f"Баг #{bug_id} не найден")
        return f"Задача #{bug_id} не найдена в базе данных."

    checklist = [
        f"Верификация бага #{bug_id}",
        "=" * 40,
        f"Описание: {task.description[:100]}",
        f"Текущий статус: {task.status}",
        f"Приоритет: {task.priority}",
        "",
        "Чеклист верификации:",
        f"  [ ] Баг воспроизводился до исправления",
        f"  [ ] Исправление применено",
        f"  [ ] Баг больше не воспроизводится",
        f"  [ ] Регрессионные тесты пройдены",
        f"  [ ] Побочные эффекты отсутствуют",
    ]

    if task.status == "closed":
        checklist.append("\nСтатус: Задача уже закрыта.")
    elif task.status == "in_progress":
        checklist.append("\nСтатус: Исправление в процессе.")
    else:
        checklist.append("\nСтатус: Ожидает исправления.")

    result_text = "\n".join(checklist)
    await _log_activity("fix_verified", f"Верификация бага #{bug_id}")
    return result_text
