"""
Мост для приема задач от AI Office.

Принимает команды от оркестратора AI Office и координирует
поиск лидов, отправку кампаний и сбор метрик.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agents.ecosystem_promoter import ecosystem_promoter

logger = logging.getLogger(__name__)


class OfficeBridge:
    """Мост между AI Office и Outbound Sales для управления кампаниями."""

    def __init__(self) -> None:
        self.promoter = ecosystem_promoter
        self._active_campaigns: dict[str, dict[str, Any]] = {}

    def get_leads_for_product(
        self, product_name: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Получить лиды для продукта на основе ICP из ecosystem_promoter.

        В продакшене вызывает researcher agent для поиска реальных лидов.
        Пока возвращает mock-данные на основе ICP.
        """
        icp = self.promoter.get_icp_for_product(product_name)
        if not icp:
            logger.warning("ICP не найден для продукта: %s", product_name)
            return []

        logger.info(
            "Поиск лидов для %s (лимит: %d, ICP: %s)",
            product_name,
            limit,
            icp.get("industry", "не указана"),
        )

        # В продакшене: вызов researcher agent для реального поиска
        # leads = await researcher.search_leads(icp, limit=limit)
        # Пока mock на основе ICP
        leads = self._generate_mock_leads(product_name, icp, limit)

        logger.info("Найдено %d лидов для %s", len(leads), product_name)
        return leads

    def send_campaign(
        self,
        product_name: str,
        leads: list[dict[str, Any]],
        texts: list[dict[str, Any]],
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Запускает кампанию рассылки для продукта.

        В продакшене отправляет реальные письма через email/telegram каналы.
        Пока логирует и возвращает mock-результат.
        """
        if channels is None:
            channels = ["email"]

        campaign_id = f"{product_name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(
            "Запуск кампании %s: %d лидов, %d текстов, каналы: %s",
            campaign_id,
            len(leads),
            len(texts),
            channels,
        )

        # В продакшене: реальная отправка через каналы
        # for lead, text in zip(leads, texts):
        #     await channel_sender.send(lead, text, channels)

        result = {
            "campaign_id": campaign_id,
            "product_name": product_name,
            "sent": len(leads),
            "failed": 0,
            "channels": channels,
            "status": "sent",
            "timestamp": datetime.now().isoformat(),
        }

        self._active_campaigns[campaign_id] = result
        logger.info("Кампания %s завершена: отправлено %d", campaign_id, len(leads))
        return result

    def get_campaign_metrics(self, product_name: str) -> dict[str, Any]:
        """
        Получить метрики кампаний для продукта.

        В продакшене собирает реальные метрики из трекера открытий/ответов.
        Пока возвращает mock-данные.
        """
        # Найти активные кампании для этого продукта
        product_campaigns = [
            c for c in self._active_campaigns.values()
            if c.get("product_name") == product_name
        ]

        total_sent = sum(c.get("sent", 0) for c in product_campaigns)

        # В продакшене: реальные метрики из трекера
        # metrics = await metrics_tracker.get_metrics(product_name)
        metrics = {
            "product_name": product_name,
            "total_campaigns": len(product_campaigns),
            "total_sent": total_sent,
            "open_rate": 0.0,
            "reply_rate": 0.0,
            "conversions": 0,
            "status": "tracking",
            "last_updated": datetime.now().isoformat(),
        }

        logger.info(
            "Метрики для %s: %d кампаний, %d отправлено",
            product_name,
            len(product_campaigns),
            total_sent,
        )
        return metrics

    def get_supported_products(self) -> list[dict[str, str]]:
        """Получить список поддерживаемых продуктов для продвижения."""
        campaigns = self.promoter.get_product_campaigns()
        return [
            {
                "product_name": c["product_name"],
                "description": c["description"],
                "value_proposition": c["value_proposition"],
            }
            for c in campaigns
        ]

    # --- Приватные методы ---

    def _generate_mock_leads(
        self,
        product_name: str,
        icp: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Генерирует mock-лиды на основе ICP продукта."""
        titles = icp.get("titles", ["Менеджер"])
        industry = icp.get("industry", "Бизнес")

        leads = []
        mock_names = [
            "Алексей Петров", "Мария Иванова", "Дмитрий Сидоров",
            "Елена Козлова", "Сергей Новиков", "Анна Морозова",
            "Павел Волков", "Ольга Лебедева", "Игорь Соколов",
            "Наталья Попова",
        ]

        for i in range(min(limit, len(mock_names))):
            name = mock_names[i]
            title = titles[i % len(titles)]
            leads.append({
                "id": f"lead_{product_name.lower().replace(' ', '_')}_{i + 1}",
                "name": name,
                "email": f"{name.split()[0].lower()}@example.com",
                "company": f"ООО {industry.split(',')[0].strip()} {i + 1}",
                "title": title,
                "source": "ecosystem_promoter_icp",
            })

        return leads


# Синглтон для использования в API
office_bridge = OfficeBridge()
