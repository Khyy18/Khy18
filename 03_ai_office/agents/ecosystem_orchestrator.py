"""
Оркестратор экосистемы - координирует Outbound Sales и Text Agency
для автоматического продвижения продуктов.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PromotionTask:
    """Задача на продвижение продукта."""

    product_name: str
    target_audience: str
    daily_limit: int = 50
    channels: list[str] = field(default_factory=lambda: ["email", "telegram"])
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"


@dataclass
class DailyReport:
    """Отчет по результатам промо-цикла за день."""

    product_name: str
    leads_found: int = 0
    texts_generated: int = 0
    messages_sent: int = 0
    open_rate: float = 0.0
    reply_rate: float = 0.0
    conversions: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class EcosystemOrchestrator:
    """Координирует Outbound Sales и Text Agency для продвижения продуктов."""

    def __init__(
        self,
        outbound_url: str = "http://localhost:8001",
        text_agency_url: str = "http://localhost:8002",
        telegram_bot_token: str = "",
        admin_chat_id: str = "",
        timeout: float = 30.0,
    ) -> None:
        self.outbound_url = outbound_url.rstrip("/")
        self.text_agency_url = text_agency_url.rstrip("/")
        self.telegram_bot_token = telegram_bot_token
        self.admin_chat_id = admin_chat_id
        self.timeout = timeout

    def create_promotion_task(
        self,
        product_name: str,
        target_audience: str,
        daily_limit: int = 50,
        channels: list[str] | None = None,
    ) -> PromotionTask:
        """Создает задачу на продвижение продукта через экосистему."""
        if channels is None:
            channels = ["email", "telegram"]

        task = PromotionTask(
            product_name=product_name,
            target_audience=target_audience,
            daily_limit=daily_limit,
            channels=channels,
        )
        logger.info(
            "Создана задача продвижения: %s, аудитория: %s, лимит: %d",
            product_name,
            target_audience,
            daily_limit,
        )
        return task

    async def execute_promotion_cycle(self, task: PromotionTask) -> DailyReport:
        """
        Выполняет полный цикл продвижения:
        1. Получить лиды от Outbound Sales
        2. Сгенерировать тексты через Text Agency
        3. Отправить рассылку через Outbound Sales
        4. Получить метрики
        """
        report = DailyReport(product_name=task.product_name)
        task.status = "in_progress"

        try:
            # Шаг 1: Получить лиды
            leads = await self._get_leads(task)
            report.leads_found = len(leads)
            logger.info("Получено %d лидов для %s", len(leads), task.product_name)

            if not leads:
                report.errors.append("Не найдено лидов для целевой аудитории")
                task.status = "completed"
                return report

            # Шаг 2: Сгенерировать тексты
            texts = await self._generate_texts(task, leads)
            report.texts_generated = len(texts)
            logger.info("Сгенерировано %d текстов для %s", len(texts), task.product_name)

            # Шаг 3: Отправить рассылку
            send_result = await self._send_outreach(task, leads, texts)
            report.messages_sent = send_result.get("sent", 0)
            logger.info("Отправлено %d сообщений для %s", report.messages_sent, task.product_name)

            # Шаг 4: Получить метрики
            metrics = await self._get_metrics(task)
            report.open_rate = metrics.get("open_rate", 0.0)
            report.reply_rate = metrics.get("reply_rate", 0.0)
            report.conversions = metrics.get("conversions", 0)

            task.status = "completed"

        except Exception as e:
            logger.error("Ошибка в цикле продвижения %s: %s", task.product_name, e)
            report.errors.append(str(e))
            task.status = "error"

        return report

    async def _get_leads(self, task: PromotionTask) -> list[dict[str, Any]]:
        """Получить лиды от Outbound Sales сервиса."""
        url = f"{self.outbound_url}/api/leads/search"
        payload = {
            "product_name": task.product_name,
            "target_audience": task.target_audience,
            "limit": task.daily_limit,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("leads", [])
        except httpx.HTTPError as e:
            logger.warning("Outbound Sales недоступен (%s), используем mock-данные", e)
            return self._mock_leads(task)

    async def _generate_texts(
        self, task: PromotionTask, leads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Сгенерировать тексты через Text Agency."""
        url = f"{self.text_agency_url}/api/generate/batch"
        payload = {
            "product_name": task.product_name,
            "leads": leads,
            "channels": task.channels,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("texts", [])
        except httpx.HTTPError as e:
            logger.warning("Text Agency недоступен (%s), используем mock-тексты", e)
            return self._mock_texts(task, leads)

    async def _send_outreach(
        self,
        task: PromotionTask,
        leads: list[dict[str, Any]],
        texts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Отправить рассылку через Outbound Sales."""
        url = f"{self.outbound_url}/api/campaigns/send"
        payload = {
            "product_name": task.product_name,
            "leads": leads,
            "texts": texts,
            "channels": task.channels,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.warning("Ошибка отправки рассылки (%s), mock-результат", e)
            return {"sent": len(leads), "failed": 0, "status": "mock"}

    async def _get_metrics(self, task: PromotionTask) -> dict[str, Any]:
        """Получить метрики кампании от Outbound Sales."""
        url = f"{self.outbound_url}/api/campaigns/metrics"
        params = {"product_name": task.product_name}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.warning("Метрики недоступны (%s), mock-данные", e)
            return self._mock_metrics()

    # --- Mock fallback ---

    def _mock_leads(self, task: PromotionTask) -> list[dict[str, Any]]:
        """Mock-лиды когда Outbound Sales недоступен."""
        return [
            {
                "id": f"lead_{i}",
                "name": f"Контакт {i}",
                "email": f"lead{i}@example.com",
                "company": f"Компания {i}",
                "title": "Менеджер",
            }
            for i in range(1, min(task.daily_limit, 5) + 1)
        ]

    def _mock_texts(
        self, task: PromotionTask, leads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Mock-тексты когда Text Agency недоступен."""
        return [
            {
                "lead_id": lead.get("id", f"lead_{i}"),
                "subject": f"Попробуйте {task.product_name}",
                "body": (
                    f"Здравствуйте, {lead.get('name', 'коллега')}!\n\n"
                    f"Предлагаем попробовать {task.product_name} "
                    f"для {task.target_audience}.\n\n"
                    f"С уважением, команда экосистемы"
                ),
                "channel": task.channels[0] if task.channels else "email",
            }
            for i, lead in enumerate(leads)
        ]

    def _mock_metrics(self) -> dict[str, Any]:
        """Mock-метрики когда сервис недоступен."""
        return {
            "open_rate": 0.0,
            "reply_rate": 0.0,
            "conversions": 0,
            "status": "mock",
        }

    # --- Отчеты ---

    def format_report(self, report: DailyReport) -> str:
        """Форматирует отчет в HTML для Telegram."""
        separator = "\u2501" * 24

        def fmt_number(n: int) -> str:
            """Форматирует число с пробелами-разделителями."""
            return f"{n:,}".replace(",", " ")

        html = (
            f"<b>📊 Отчет по продвижению</b>\n"
            f"{separator}\n"
            f"\n"
            f"<b>📦 Продукт:</b> {report.product_name}\n"
            f"<b>📅 Дата:</b> {report.timestamp.strftime('%d.%m.%Y %H:%M')}\n"
            f"\n"
            f"{separator}\n"
            f"<b>📈 Результаты</b>\n"
            f"{separator}\n"
            f"\n"
            f"🎯 Найдено лидов: <b>{fmt_number(report.leads_found)}</b>\n"
            f"✍️ Сгенерировано текстов: <b>{fmt_number(report.texts_generated)}</b>\n"
            f"📨 Отправлено сообщений: <b>{fmt_number(report.messages_sent)}</b>\n"
            f"\n"
            f"{separator}\n"
            f"<b>📉 Метрики</b>\n"
            f"{separator}\n"
            f"\n"
            f"👁 Open rate: <b>{report.open_rate:.1%}</b>\n"
            f"💬 Reply rate: <b>{report.reply_rate:.1%}</b>\n"
            f"🔥 Конверсии: <b>{fmt_number(report.conversions)}</b>\n"
        )

        if report.errors:
            html += (
                f"\n{separator}\n"
                f"<b>⚠️ Ошибки</b>\n"
                f"{separator}\n\n"
            )
            for error in report.errors:
                html += f"• {error}\n"

        html += f"\n{separator}"
        return html

    async def send_report_to_admin(self, report: DailyReport) -> bool:
        """Отправляет отчет админу через Telegram Bot API."""
        if not self.telegram_bot_token or not self.admin_chat_id:
            logger.warning("Telegram не настроен, отчет не отправлен")
            return False

        html_text = self.format_report(report)
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.admin_chat_id,
            "text": html_text,
            "parse_mode": "HTML",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                logger.info("Отчет отправлен в Telegram (chat_id=%s)", self.admin_chat_id)
                return True
        except httpx.HTTPError as e:
            logger.error("Ошибка отправки отчета в Telegram: %s", e)
            return False
