"""Инструменты UI/UX дизайнера - записывают активность в БД."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Max."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Max")
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
async def review_design(description: str) -> str:
    """Провести структурированное ревью UI-решения.

    Args:
        description: Описание дизайн-решения для ревью

    Returns:
        Структурированный результат ревью по категориям
    """
    desc_lower = description.lower()

    categories = {
        "accessibility": {
            "title": "Доступность (Accessibility)",
            "recommendations": [],
        },
        "consistency": {
            "title": "Консистентность (Consistency)",
            "recommendations": [],
        },
        "mobile": {
            "title": "Мобильная адаптивность (Mobile-friendliness)",
            "recommendations": [],
        },
        "contrast": {
            "title": "Контраст и читаемость (Contrast)",
            "recommendations": [],
        },
    }

    # Accessibility recommendations
    if "изображен" in desc_lower or "картин" in desc_lower or "image" in desc_lower or "icon" in desc_lower:
        categories["accessibility"]["recommendations"].append(
            "Добавить alt-текст для всех изображений и иконок"
        )
    if "кнопк" in desc_lower or "button" in desc_lower:
        categories["accessibility"]["recommendations"].append(
            "Убедиться что кнопки имеют минимальный размер 44x44px для touch-target"
        )
    categories["accessibility"]["recommendations"].append(
        "Проверить навигацию с клавиатуры (Tab, Enter, Escape)"
    )
    categories["accessibility"]["recommendations"].append(
        "Добавить ARIA-метки для интерактивных элементов"
    )

    # Consistency recommendations
    if "модал" in desc_lower or "modal" in desc_lower or "диалог" in desc_lower:
        categories["consistency"]["recommendations"].append(
            "Использовать единый стиль модальных окон из дизайн-системы"
        )
    if "меню" in desc_lower or "навигац" in desc_lower or "menu" in desc_lower:
        categories["consistency"]["recommendations"].append(
            "Придерживаться единой структуры навигации на всех экранах"
        )
    categories["consistency"]["recommendations"].append(
        "Использовать токены дизайн-системы (цвета, отступы, шрифты)"
    )
    categories["consistency"]["recommendations"].append(
        "Соблюдать единый стиль иконографии"
    )

    # Mobile recommendations
    if "таблиц" in desc_lower or "table" in desc_lower or "список" in desc_lower:
        categories["mobile"]["recommendations"].append(
            "Адаптировать табличные данные для мобильного отображения (card layout)"
        )
    if "форм" in desc_lower or "form" in desc_lower or "ввод" in desc_lower:
        categories["mobile"]["recommendations"].append(
            "Оптимизировать формы для мобильного ввода (крупные поля, нативные контролы)"
        )
    categories["mobile"]["recommendations"].append(
        "Проверить отображение на экранах 320px-428px"
    )
    categories["mobile"]["recommendations"].append(
        "Учесть safe area для устройств с вырезом"
    )

    # Contrast recommendations
    if "темн" in desc_lower or "dark" in desc_lower:
        categories["contrast"]["recommendations"].append(
            "Обеспечить контраст текста не менее 4.5:1 в темной теме"
        )
    if "светл" in desc_lower or "light" in desc_lower or "бел" in desc_lower:
        categories["contrast"]["recommendations"].append(
            "Избегать светло-серого текста на белом фоне"
        )
    categories["contrast"]["recommendations"].append(
        "Минимальное соотношение контраста 4.5:1 для обычного текста (WCAG AA)"
    )
    categories["contrast"]["recommendations"].append(
        "Не использовать только цвет для передачи информации"
    )

    sections = [
        f"Ревью дизайна: {description[:80]}",
        "=" * 40,
    ]

    for cat_data in categories.values():
        sections.append(f"\n## {cat_data['title']}")
        for i, rec in enumerate(cat_data["recommendations"], 1):
            sections.append(f"  {i}. {rec}")

    result = "\n".join(sections)
    await _log_activity("design_reviewed", f"Ревью дизайна: {description[:50]}")
    return result


_WIREFRAME_TEMPLATES = {
    "list": (
        "+----------------------------------+\n"
        "|         {screen_name:^20}       |\n"
        "+----------------------------------+\n"
        "| [Search...                     ] |\n"
        "+----------------------------------+\n"
        "| [ ] Item 1            [action] > |\n"
        "|     Description text             |\n"
        "+----------------------------------+\n"
        "| [ ] Item 2            [action] > |\n"
        "|     Description text             |\n"
        "+----------------------------------+\n"
        "| [ ] Item 3            [action] > |\n"
        "|     Description text             |\n"
        "+----------------------------------+\n"
        "|        [Load More...]            |\n"
        "+----------------------------------+\n"
        "| [+] Add New                      |\n"
        "+----------------------------------+"
    ),
    "form": (
        "+----------------------------------+\n"
        "|         {screen_name:^20}       |\n"
        "+----------------------------------+\n"
        "| Label:                           |\n"
        "| [________________________]       |\n"
        "|                                  |\n"
        "| Label:                           |\n"
        "| [________________________]       |\n"
        "|                                  |\n"
        "| Label:                           |\n"
        "| [________________________]       |\n"
        "|                                  |\n"
        "| [  Cancel  ]  [   Submit   ]     |\n"
        "+----------------------------------+"
    ),
    "dashboard": (
        "+----------------------------------+\n"
        "|         {screen_name:^20}       |\n"
        "+----------------------------------+\n"
        "| +--------+ +--------+ +--------+|\n"
        "| | KPI  1 | | KPI  2 | | KPI  3 ||\n"
        "| |  123   | |  456   | |  789   ||\n"
        "| +--------+ +--------+ +--------+|\n"
        "+----------------------------------+\n"
        "| [Chart Area                    ] |\n"
        "| [                              ] |\n"
        "| [______________________________] |\n"
        "+----------------------------------+\n"
        "| Recent Activity:                 |\n"
        "|  - Action 1         10:00       |\n"
        "|  - Action 2         09:45       |\n"
        "+----------------------------------+"
    ),
    "detail": (
        "+----------------------------------+\n"
        "|  < Back    {screen_name:^14}    |\n"
        "+----------------------------------+\n"
        "| Title / Name                     |\n"
        "| ================================ |\n"
        "|                                  |\n"
        "| Status: [Active]                 |\n"
        "| Priority: [High]                 |\n"
        "| Created: 2024-01-01              |\n"
        "|                                  |\n"
        "| Description:                     |\n"
        "| Lorem ipsum dolor sit amet...    |\n"
        "|                                  |\n"
        "| [  Edit  ]  [  Delete  ]         |\n"
        "+----------------------------------+"
    ),
}


def _detect_pattern(requirements: str) -> str:
    """Определить тип UI-паттерна по ключевым словам."""
    req_lower = requirements.lower()

    if any(kw in req_lower for kw in ["список", "list", "таблиц", "table", "перечень", "каталог"]):
        return "list"
    if any(kw in req_lower for kw in ["форм", "form", "ввод", "input", "регистрац", "создан"]):
        return "form"
    if any(kw in req_lower for kw in ["дашборд", "dashboard", "панель", "статистик", "метрик", "обзор"]):
        return "dashboard"
    if any(kw in req_lower for kw in ["детал", "detail", "карточк", "просмотр", "профил"]):
        return "detail"

    return "dashboard"


@tool
async def generate_wireframe(screen_name: str, requirements: str) -> str:
    """Сгенерировать ASCII-вайрфрейм экрана на основе требований.

    Args:
        screen_name: Название экрана
        requirements: Требования к экрану

    Returns:
        ASCII-вайрфрейм с описанием компонентов
    """
    pattern = _detect_pattern(requirements)
    wireframe = _WIREFRAME_TEMPLATES[pattern].format(screen_name=screen_name[:20])

    sections = [
        f"Вайрфрейм: {screen_name}",
        f"Паттерн: {pattern}",
        f"Требования: {requirements[:100]}",
        "",
        wireframe,
        "",
        f"Тип экрана: {pattern}",
        "Рекомендации по реализации:",
    ]

    if pattern == "list":
        sections.extend([
            "  - Виртуализация списка для больших объемов данных",
            "  - Pull-to-refresh для обновления",
            "  - Скелетон при загрузке",
        ])
    elif pattern == "form":
        sections.extend([
            "  - Inline-валидация полей",
            "  - Автосохранение черновика",
            "  - Блокировка повторной отправки",
        ])
    elif pattern == "dashboard":
        sections.extend([
            "  - Ленивая загрузка виджетов",
            "  - Обновление данных по таймеру",
            "  - Адаптивная сетка для мобильных",
        ])
    elif pattern == "detail":
        sections.extend([
            "  - Ленивая подгрузка связанных данных",
            "  - Оптимистичное обновление статуса",
            "  - Подтверждение перед удалением",
        ])

    result = "\n".join(sections)
    await _log_activity("wireframe_created", f"Создан вайрфрейм: {screen_name}")
    return result


_UX_ANTIPATTERNS = {
    "too_many_steps": {
        "keywords": ["шаг", "step", "этап", "далее", "next", "потом", "затем"],
        "problem": "Слишком много шагов до цели",
        "fixes": [
            "Сократить количество шагов объединением связанных действий",
            "Добавить прогресс-бар для ориентации пользователя",
            "Предложить быстрый путь (shortcut) для опытных пользователей",
        ],
    },
    "no_feedback": {
        "keywords": ["отправ", "submit", "сохран", "save", "выполн", "нажим", "click"],
        "problem": "Отсутствие обратной связи",
        "fixes": [
            "Добавить индикатор загрузки при выполнении действий",
            "Показывать toast/snackbar с подтверждением",
            "Использовать анимации для визуальной обратной связи",
        ],
    },
    "no_undo": {
        "keywords": ["удал", "delete", "remove", "очист", "clear", "отмен"],
        "problem": "Невозможность отмены действий",
        "fixes": [
            "Добавить подтверждение перед деструктивными действиями",
            "Реализовать soft-delete с возможностью восстановления",
            "Добавить Undo-кнопку в toast после действия",
        ],
    },
    "no_error_states": {
        "keywords": ["ошибк", "error", "fail", "неуда", "пуст", "empty", "нет данных"],
        "problem": "Не предусмотрены состояния ошибок",
        "fixes": [
            "Спроектировать empty state с подсказкой действий",
            "Добавить понятные сообщения об ошибках с вариантами решения",
            "Реализовать graceful degradation при сбое сети",
        ],
    },
}


@tool
async def suggest_ux_improvements(current_flow: str) -> str:
    """Предложить улучшения UX для текущего флоу на основе анализа анти-паттернов.

    Args:
        current_flow: Описание текущего пользовательского флоу

    Returns:
        Рекомендации по улучшению UX
    """
    flow_lower = current_flow.lower()

    detected_issues = []
    for pattern_key, pattern_data in _UX_ANTIPATTERNS.items():
        for keyword in pattern_data["keywords"]:
            if keyword in flow_lower:
                detected_issues.append(pattern_data)
                break

    sections = [
        f"UX-аудит: {current_flow[:80]}",
        "=" * 40,
        f"\nОбнаружено проблем: {len(detected_issues)}",
    ]

    if detected_issues:
        for i, issue in enumerate(detected_issues, 1):
            sections.append(f"\n### Проблема {i}: {issue['problem']}")
            sections.append("  Рекомендации:")
            for fix in issue["fixes"]:
                sections.append(f"    - {fix}")
    else:
        sections.append("\nЯвных анти-паттернов не обнаружено.")
        sections.append("Общие рекомендации:")
        sections.append("  - Провести юзабилити-тестирование с реальными пользователями")
        sections.append("  - Замерить время выполнения ключевых сценариев")
        sections.append("  - Проверить доступность (a11y audit)")

    result = "\n".join(sections)
    await _log_activity("ux_audit", f"UX-аудит: {current_flow[:50]}")
    return result
