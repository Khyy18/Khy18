"""Инструменты бизнес-аналитика - записывают активность в БД."""

from datetime import datetime, timedelta

from langchain_core.tools import tool
from sqlalchemy import func, select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent, Task, TokenUsage


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Eva."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Eva")
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
async def create_user_story(role: str, action: str, benefit: str) -> str:
    """Создать user story в стандартном формате с критериями приемки.

    Args:
        role: Роль пользователя
        action: Желаемое действие
        benefit: Ожидаемая выгода

    Returns:
        Сформулированная user story с acceptance criteria
    """
    story = (
        f"User Story\n"
        f"{'=' * 40}\n"
        f"Как {role}, я хочу {action}, чтобы {benefit}.\n"
        f"\nAcceptance Criteria:\n"
        f"\n  Given: {role} находится в системе\n"
        f"  When: {role} выполняет действие \"{action}\"\n"
        f"  Then: {benefit}\n"
        f"\nДополнительные критерии:\n"
        f"  - Функциональность доступна для роли \"{role}\"\n"
        f"  - Действие завершается с подтверждением\n"
        f"  - Ошибки обрабатываются с понятным сообщением"
    )
    await _log_activity("user_story_created", f"User story: {role} - {action}")
    return story


_FUNCTIONAL_KEYWORDS = [
    "должен", "должна", "отображ", "позволя", "создa", "удаля", "редактир",
    "сохран", "загруж", "отправля", "показыва", "выполня", "поддержива",
    "генерир", "формир", "вычисля", "рассчит", "авториз", "регистр",
    "must", "shall", "display", "allow", "create", "delete", "show",
]

_NON_FUNCTIONAL_KEYWORDS = [
    "производительн", "безопасн", "масштабир", "доступн", "надежн",
    "время отклика", "нагруз", "шифрован", "резервн", "backup",
    "performance", "security", "scalab", "reliab", "availability",
    "latency", "throughput",
]

_CONSTRAINT_KEYWORDS = [
    "ограничен", "не более", "не менее", "максимум", "минимум",
    "только", "запрещ", "обязательн", "не допуска", "исключ",
    "constraint", "limit", "maximum", "minimum", "required", "forbidden",
]


@tool
async def analyze_requirements(text: str) -> str:
    """Проанализировать текст требований и категоризировать их.

    Args:
        text: Текст требований для анализа

    Returns:
        Структурированный результат анализа требований
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        lines = [s.strip() for s in text.split(".") if s.strip()]

    functional = []
    non_functional = []
    constraints = []
    uncategorized = []

    for line in lines:
        line_lower = line.lower()
        categorized = False

        for keyword in _CONSTRAINT_KEYWORDS:
            if keyword in line_lower:
                constraints.append(line)
                categorized = True
                break

        if not categorized:
            for keyword in _NON_FUNCTIONAL_KEYWORDS:
                if keyword in line_lower:
                    non_functional.append(line)
                    categorized = True
                    break

        if not categorized:
            for keyword in _FUNCTIONAL_KEYWORDS:
                if keyword in line_lower:
                    functional.append(line)
                    categorized = True
                    break

        if not categorized:
            uncategorized.append(line)

    sections = [
        "Анализ требований",
        "=" * 40,
        f"\nИсходный текст: {text[:200]}{'...' if len(text) > 200 else ''}",
        f"\nВсего требований обнаружено: {len(functional) + len(non_functional) + len(constraints)}",
    ]

    sections.append(f"\n## Функциональные требования ({len(functional)})")
    for i, req in enumerate(functional, 1):
        sections.append(f"  {i}. {req}")
    if not functional:
        sections.append("  (не обнаружены)")

    sections.append(f"\n## Нефункциональные требования ({len(non_functional)})")
    for i, req in enumerate(non_functional, 1):
        sections.append(f"  {i}. {req}")
    if not non_functional:
        sections.append("  (не обнаружены)")

    sections.append(f"\n## Ограничения ({len(constraints)})")
    for i, req in enumerate(constraints, 1):
        sections.append(f"  {i}. {req}")
    if not constraints:
        sections.append("  (не обнаружены)")

    if uncategorized:
        sections.append(f"\n## Требуют уточнения ({len(uncategorized)})")
        for i, req in enumerate(uncategorized, 1):
            sections.append(f"  {i}. {req}")

    result = "\n".join(sections)
    await _log_activity("requirements_analyzed", f"Анализ требований: {text[:50]}")
    return result


def _parse_period(period: str) -> datetime:
    """Определить начальную дату периода."""
    period_lower = period.lower()
    now = datetime.utcnow()

    if "день" in period_lower or "day" in period_lower or "сегодня" in period_lower:
        return now - timedelta(days=1)
    elif "недел" in period_lower or "week" in period_lower:
        return now - timedelta(weeks=1)
    elif "месяц" in period_lower or "month" in period_lower:
        return now - timedelta(days=30)
    elif "год" in period_lower or "year" in period_lower:
        return now - timedelta(days=365)
    else:
        return now - timedelta(weeks=1)


@tool
async def generate_report(type: str, period: str) -> str:
    """Сгенерировать аналитический отчет на основе реальных данных из БД.

    Args:
        type: Тип отчета (tasks, activity, tokens, summary)
        period: Период (день, неделя, месяц, год)

    Returns:
        Аналитический отчет с данными
    """
    period_start = _parse_period(period)

    async with async_session() as session:
        # Задачи по статусам
        task_result = await session.execute(
            select(Task.status, func.count(Task.id)).group_by(Task.status)
        )
        task_stats = dict(task_result.all())

        # Количество логов активности за период
        activity_result = await session.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.timestamp >= period_start
            )
        )
        activity_count = activity_result.scalar() or 0

        # Использование токенов за период
        token_result = await session.execute(
            select(
                func.sum(TokenUsage.prompt_tokens),
                func.sum(TokenUsage.completion_tokens),
                func.sum(TokenUsage.estimated_cost_usd),
            ).where(TokenUsage.timestamp >= period_start)
        )
        token_row = token_result.one()
        prompt_tokens = token_row[0] or 0
        completion_tokens = token_row[1] or 0
        total_cost = token_row[2] or 0.0

    total_tasks = sum(task_stats.values())

    sections = [
        f"Аналитический отчет: {type}",
        f"Период: {period}",
        "=" * 40,
        "",
        "## Задачи",
        f"  Всего: {total_tasks}",
    ]

    for status, count in task_stats.items():
        sections.append(f"  {status}: {count}")

    sections.extend([
        "",
        "## Активность",
        f"  Действий за период: {activity_count}",
        "",
        "## Использование токенов",
        f"  Prompt tokens: {prompt_tokens}",
        f"  Completion tokens: {completion_tokens}",
        f"  Общая стоимость: ${total_cost:.4f}",
    ])

    result = "\n".join(sections)
    await _log_activity("report_generated", f"Отчет: {type} за {period}")
    return result
