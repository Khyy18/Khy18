"""
Генератор контента для экосистемы.

Создает персонализированные тексты для outbound-кампаний
по продуктам экосистемы. Тексты написаны живым человеческим языком,
без шаблонности и канцелярита.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Шаблоны для каждого продукта экосистемы
PRODUCT_TEMPLATES: dict[str, dict[str, Any]] = {
    "Price Monitor": {
        "subject": "Конкуренты снижают цены - вы в курсе?",
        "tone": "дружелюбный, экспертный, без давления",
        "key_points": [
            "Мониторинг цен конкурентов на WB/Ozon каждые 30 минут",
            "ИИ-рекомендации оптимальной цены",
            "Алерты при изменении цен в Telegram",
            "Бесплатный тест 7 дней",
        ],
    },
    "AI Text Agency": {
        "subject": "Тексты для бизнеса без копирайтера",
        "tone": "креативный, легкий, с примерами",
        "key_points": [
            "Генерация постов, рассылок, описаний товаров",
            "Обучается на вашем tone of voice",
            "100 текстов в месяц дешевле одного фрилансера",
            "Первые 10 текстов бесплатно",
        ],
    },
    "AI Office": {
        "subject": "ИИ-ассистент для вашей команды",
        "tone": "деловой, конкретный, с цифрами",
        "key_points": [
            "Автоматизация писем, отчетов, CRM",
            "Экономия 20+ часов в неделю на рутине",
            "Подключение за 30 минут",
            "Пробный период 14 дней",
        ],
    },
}


class EcosystemContentGenerator:
    """Генерирует персонализированный контент для outbound-кампаний экосистемы."""

    def __init__(self) -> None:
        self.templates = PRODUCT_TEMPLATES

    def generate_outreach_email(
        self, product_name: str, lead: dict[str, Any]
    ) -> dict[str, str]:
        """
        Генерирует персонализированное письмо для конкретного лида.

        Текст звучит естественно, как будто написан живым человеком,
        а не шаблонной рассылкой.
        """
        template = self.templates.get(product_name)
        if not template:
            logger.warning("Шаблон для продукта '%s' не найден", product_name)
            template = {
                "subject": f"Попробуйте {product_name}",
                "tone": "дружелюбный",
                "key_points": [f"Узнайте больше о {product_name}"],
            }

        lead_name = lead.get("name", "").split()[0] if lead.get("name") else "коллега"
        company = lead.get("company", "вашей компании")
        title = lead.get("title", "")

        # Персонализация обращения
        greeting = self._make_greeting(lead_name)

        # Контекст на основе должности
        context_line = self._make_context_line(product_name, title, company)

        # Основная ценность
        key_points = template["key_points"]
        value_line = key_points[0] if key_points else ""

        # Призыв к действию без давления
        cta = self._make_cta(product_name)

        subject = self._personalize_subject(template["subject"], company)

        body = (
            f"{greeting}\n\n"
            f"{context_line}\n\n"
            f"{value_line}.\n\n"
            f"{cta}\n\n"
            f"С уважением"
        )

        logger.debug(
            "Сгенерировано письмо для %s (%s)", lead_name, product_name
        )

        return {
            "subject": subject,
            "body": body,
            "tone": template["tone"],
        }

    def generate_batch(
        self, product_name: str, leads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Генерирует пакет персонализированных писем для списка лидов.

        Каждое письмо уникально - меняется обращение, контекст,
        формулировка ценности.
        """
        results = []
        for lead in leads:
            email = self.generate_outreach_email(product_name, lead)
            results.append(
                {
                    "lead_id": lead.get("id", ""),
                    "lead_name": lead.get("name", ""),
                    "subject": email["subject"],
                    "body": email["body"],
                    "tone": email["tone"],
                    "channel": "email",
                }
            )

        logger.info(
            "Сгенерирован пакет из %d писем для %s", len(results), product_name
        )
        return results

    def generate_social_post(self, product_name: str) -> dict[str, str]:
        """
        Генерирует пост для социальных сетей.

        Короткий, цепляющий, с эмодзи и призывом к действию.
        Написан живым языком, не как реклама.
        """
        template = self.templates.get(product_name)
        if not template:
            return {
                "text": f"Попробуйте {product_name} - новый инструмент для бизнеса",
                "hashtags": "#бизнес #автоматизация",
            }

        key_points = template["key_points"]

        posts = {
            "Price Monitor": {
                "text": (
                    "Знаете момент, когда конкурент тихо снижает цену, "
                    "а вы узнаете через неделю? 😅\n\n"
                    "Теперь бот присылает алерт через 30 минут после изменения. "
                    "Плюс ИИ подсказывает, какую цену поставить для максимума продаж.\n\n"
                    f"🔑 {key_points[0]}\n"
                    f"📊 {key_points[1]}\n"
                    f"🔔 {key_points[2]}\n\n"
                    "Попробуйте бесплатно 7 дней 👇"
                ),
                "hashtags": "#маркетплейсы #wildberries #ozon #мониторингцен #ecommerce",
            },
            "AI Text Agency": {
                "text": (
                    "Копирайтер заболел, дедлайн горит, а текст нужен вчера? "
                    "Знакомо? 🙈\n\n"
                    "ИИ-копирайтер пишет в вашем стиле: посты, рассылки, "
                    "описания товаров. Обучается на ваших примерах.\n\n"
                    f"✍️ {key_points[0]}\n"
                    f"🎯 {key_points[1]}\n"
                    f"💰 {key_points[2]}\n\n"
                    "Первые 10 текстов бесплатно 👇"
                ),
                "hashtags": "#копирайтинг #контент #smm #маркетинг #нейросети",
            },
            "AI Office": {
                "text": (
                    "Сколько часов в неделю ваша команда тратит на рутину? "
                    "Отчеты, письма, CRM... 😫\n\n"
                    "ИИ-ассистенты берут это на себя. Не абстрактно, а конкретно: "
                    "отвечают на письма, заполняют таблицы, готовят дайджесты.\n\n"
                    f"🤖 {key_points[0]}\n"
                    f"⏰ {key_points[1]}\n"
                    f"🚀 {key_points[2]}\n\n"
                    "14 дней бесплатно 👇"
                ),
                "hashtags": "#автоматизация #бизнес #ии #продуктивность #офис",
            },
        }

        post = posts.get(product_name, {
            "text": f"Попробуйте {product_name}",
            "hashtags": "#бизнес",
        })

        logger.info("Сгенерирован пост для соцсетей: %s", product_name)
        return post

    # --- Приватные методы персонализации ---

    def _make_greeting(self, name: str) -> str:
        """Создает естественное приветствие."""
        if name and name != "коллега":
            return f"{name}, добрый день!"
        return "Добрый день!"

    def _make_context_line(
        self, product_name: str, title: str, company: str
    ) -> str:
        """Создает контекстную строку на основе должности и компании."""
        contexts = {
            "Price Monitor": (
                f"Заметил, что {company} продает на маркетплейсах. "
                "Вопрос: как часто проверяете цены конкурентов?"
            ),
            "AI Text Agency": (
                f"Вижу, что {company} активно ведет контент. "
                "Сколько времени уходит на тексты?"
            ),
            "AI Office": (
                f"Команды вроде {company} обычно тратят 30-40% времени на рутину. "
                "Есть способ это сократить"
            ),
        }
        return contexts.get(
            product_name,
            f"Думаю, {product_name} может быть полезен для {company}",
        )

    def _make_cta(self, product_name: str) -> str:
        """Создает мягкий призыв к действию."""
        ctas = {
            "Price Monitor": "Могу показать на примере вашей ниши - 5 минут в Telegram?",
            "AI Text Agency": "Хотите попробовать? Первые 10 текстов бесплатно",
            "AI Office": "Есть 5 минут посмотреть как это работает?",
        }
        return ctas.get(product_name, "Интересно узнать подробнее?")

    def _personalize_subject(self, subject: str, company: str) -> str:
        """Персонализирует тему письма."""
        if company and company != "вашей компании":
            return f"{subject} | {company}"
        return subject
