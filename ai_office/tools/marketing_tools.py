"""Инструменты маркетинга - SEO анализ, контент-план, A/B тесты."""

import httpx
from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Iris."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Iris")
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
async def analyze_seo(url: str) -> str:
    """Проанализировать SEO страницы по URL.

    Args:
        url: URL страницы для анализа

    Returns:
        SEO анализ: title, meta description, количество слов, рекомендации
    """
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(url)
            html = response.text

            # Извлекаем title
            title = ""
            if "<title>" in html.lower():
                start = html.lower().find("<title>") + 7
                end = html.lower().find("</title>")
                if end > start:
                    title = html[start:end].strip()

            # Извлекаем meta description
            meta_desc = ""
            meta_lower = html.lower()
            desc_pos = meta_lower.find('name="description"')
            if desc_pos == -1:
                desc_pos = meta_lower.find("name='description'")
            if desc_pos != -1:
                # Ищем content атрибут рядом
                tag_start = html.rfind("<", 0, desc_pos)
                tag_end = html.find(">", desc_pos)
                if tag_start != -1 and tag_end != -1:
                    tag = html[tag_start:tag_end + 1]
                    content_pos = tag.lower().find('content="')
                    if content_pos != -1:
                        content_start = content_pos + 9
                        content_end = tag.find('"', content_start)
                        if content_end != -1:
                            meta_desc = tag[content_start:content_end]

            # Считаем слова (убираем теги)
            import re
            text_only = re.sub(r'<[^>]+>', ' ', html)
            words = len(text_only.split())

            lines = [f"SEO-анализ: {url}"]
            lines.append(f"  Title: {title or '(не найден)'} [{len(title)} символов]")
            lines.append(f"  Meta Description: {meta_desc[:100] or '(не найдена)'}{'...' if len(meta_desc) > 100 else ''}")
            lines.append(f"  Количество слов на странице: ~{words}")
            lines.append("")
            lines.append("Рекомендации:")
            if not title:
                lines.append("  - Добавьте title тег (50-60 символов)")
            elif len(title) < 30:
                lines.append("  - Title слишком короткий, рекомендуется 50-60 символов")
            elif len(title) > 60:
                lines.append("  - Title слишком длинный, рекомендуется 50-60 символов")
            else:
                lines.append("  - Title в пределах нормы")

            if not meta_desc:
                lines.append("  - Добавьте meta description (120-160 символов)")
            elif len(meta_desc) < 120:
                lines.append("  - Meta description слишком короткая, рекомендуется 120-160 символов")
            else:
                lines.append("  - Meta description в пределах нормы")

            result = "\n".join(lines)

    except Exception as e:
        result = (
            f"Не удалось загрузить {url}: {str(e)}\n\n"
            f"Общие SEO-рекомендации для страницы:\n"
            f"  1. Убедитесь, что title содержит ключевые слова (50-60 символов)\n"
            f"  2. Добавьте meta description с призывом к действию (120-160 символов)\n"
            f"  3. Используйте H1-H3 заголовки с ключевыми словами\n"
            f"  4. Оптимизируйте изображения (alt-теги, сжатие)\n"
            f"  5. Обеспечьте скорость загрузки < 3 секунд\n"
            f"  6. Добавьте внутреннюю перелинковку"
        )

    await _log_activity("seo_analyzed", f"SEO-анализ: {url}")
    return result


@tool
async def generate_content_plan(topic: str, period: str) -> str:
    """Сгенерировать контент-план по теме.

    Args:
        topic: Тема/ниша для контент-плана
        period: Период планирования (неделя, месяц)

    Returns:
        Структурированный контент-план с типами контента и расписанием
    """
    period_lower = period.lower()

    if "недел" in period_lower or "week" in period_lower:
        lines = [
            f"Контент-план на неделю: {topic}",
            "",
            "Понедельник:",
            f"  - Статья: Введение в {topic} - основные понятия",
            "  - Формат: лонгрид (1500+ слов), SEO-оптимизированный",
            "",
            "Вторник:",
            f"  - Пост в соцсетях: Факт дня о {topic}",
            "  - Формат: карусель/инфографика",
            "",
            "Среда:",
            f"  - Видео: Практический гайд по {topic}",
            "  - Формат: 5-10 минут, с субтитрами",
            "",
            "Четверг:",
            f"  - Email-рассылка: Подборка ресурсов по {topic}",
            "  - Формат: дайджест с 5-7 полезными ссылками",
            "",
            "Пятница:",
            f"  - Пост в соцсетях: Кейс/история успеха в {topic}",
            "  - Формат: сторителлинг с визуалом",
            "",
            "Суббота:",
            f"  - Stories/Reels: Закулисье работы над {topic}",
            "  - Формат: 3-5 коротких видео",
            "",
            "Воскресенье:",
            f"  - Опрос/интерактив: Вопросы аудитории о {topic}",
            "  - Формат: Q&A или голосование",
            "",
            "KPI:",
            "  - Охват: +15% к предыдущей неделе",
            "  - Вовлечённость: ER > 3%",
            "  - Трафик на сайт: +10%",
        ]
    else:
        lines = [
            f"Контент-план на месяц: {topic}",
            "",
            "Неделя 1 - Осведомлённость:",
            f"  - 2 статьи: основы {topic}, тренды",
            "  - 5 постов в соцсетях: факты, инфографики",
            "  - 1 видео: обзор темы",
            "",
            "Неделя 2 - Вовлечение:",
            f"  - 1 статья: глубокий разбор аспекта {topic}",
            "  - 5 постов: кейсы, примеры, отзывы",
            "  - 1 вебинар/прямой эфир",
            "",
            "Неделя 3 - Конверсия:",
            f"  - 2 статьи: практические гайды по {topic}",
            "  - 5 постов: результаты клиентов, сравнения",
            "  - 1 email-серия (3 письма)",
            "",
            "Неделя 4 - Удержание:",
            f"  - 1 статья: продвинутые техники {topic}",
            "  - 5 постов: закулисье, команда, планы",
            "  - 1 видео: итоги месяца и планы",
            "",
            "Форматы контента:",
            "  - Лонгриды (1500+ слов): 6 шт.",
            "  - Посты соцсети: 20 шт.",
            "  - Видео: 3 шт.",
            "  - Email: 4 шт.",
            "",
            "KPI месяца:",
            "  - Рост подписчиков: +20%",
            "  - Органический трафик: +25%",
            "  - Конверсия в лиды: +10%",
        ]

    result = "\n".join(lines)
    await _log_activity("content_plan_generated", f"Контент-план: {topic} ({period})")
    return result


@tool
async def suggest_ab_test(feature: str) -> str:
    """Предложить A/B тест для функции или элемента.

    Args:
        feature: Функция или элемент для тестирования

    Returns:
        Предложение A/B теста с вариантами, гипотезой и метриками
    """
    lines = [
        f"A/B тест: {feature}",
        "",
        "Гипотеза:",
        f"  Изменение '{feature}' увеличит конверсию на 10-15%",
        "",
        "Варианты:",
        f"  A (контроль): текущая версия '{feature}'",
        f"  B (тест): модифицированная версия с улучшениями",
        "",
        "Рекомендуемые изменения для варианта B:",
        "  1. Упростить визуальное оформление",
        "  2. Добавить социальное доказательство",
        "  3. Усилить призыв к действию (CTA)",
        "",
        "Метрики для отслеживания:",
        "  - Основная: конверсия (CTR / заявки / покупки)",
        "  - Вторичные: время на странице, глубина просмотра, bounce rate",
        "",
        "Параметры теста:",
        "  - Минимальный размер выборки: 1000 пользователей на вариант",
        "  - Длительность: 7-14 дней",
        "  - Уровень значимости: 95% (p < 0.05)",
        "  - Разделение трафика: 50/50",
        "",
        "Критерии успеха:",
        "  - Статистическая значимость достигнута",
        "  - Вариант B показывает улучшение основной метрики >= 5%",
        "  - Нет деградации вторичных метрик",
    ]

    result = "\n".join(lines)
    await _log_activity("ab_test_suggested", f"A/B тест предложен: {feature}")
    return result
