"""Определения фоновых задач для ARQ worker."""

from __future__ import annotations

from typing import Any


async def retry_webhook_task(
    ctx: dict[str, Any],
    payload: dict[str, Any],
    callback_url: str,
) -> str:
    """Задача повторной отправки вебхука через WebhookRetryQueue."""
    import aiohttp

    from payments.retry import WebhookPayload, WebhookRetryQueue

    queue = WebhookRetryQueue()
    item = WebhookPayload(payload=payload, callback_url=callback_url)

    async with aiohttp.ClientSession() as session:
        success = await queue.process_one(session, item)

    if success:
        return "webhook_delivered"
    return f"webhook_failed_to_dlq:url={callback_url}"


async def backup_task(ctx: dict[str, Any]) -> str:
    """Задача выполнения бэкапа базы данных."""
    from backup.backup import BackupService

    service = BackupService()
    success = await service.run_backup()
    return "backup_completed" if success else "backup_failed"


async def freelance_scan_task(ctx: dict[str, Any]) -> str:
    """Задача сканирования фриланс-площадок.

    Вызывает FreelanceScheduler.run_once() для одного прохода
    по всем подключённым площадкам.
    """
    from freelance_automation.config import KEYWORDS, PLATFORMS
    from freelance_automation.scheduler import FreelanceScheduler

    scheduler = FreelanceScheduler(platforms=PLATFORMS, keywords=KEYWORDS)
    await scheduler.run_once()
    return "freelance_scan_completed"


async def generate_offer_task(
    ctx: dict[str, Any],
    user_tg_id: int,
    user_name: str,
    amount: float,
    service_description: str,
) -> str:
    """Задача генерации PDF-оферты и отправки пользователю."""
    from legal.generator import OfferGenerator

    generator = OfferGenerator()
    pdf_bytes, offer_id = generator.generate_pdf(
        user_tg_id=user_tg_id,
        user_name=user_name,
        amount=amount,
        service_description=service_description,
    )
    return f"offer_generated:id={offer_id}"


async def content_generation_task(ctx: dict[str, Any]) -> str:
    """Задача ежедневной генерации контента."""
    import random

    import aiohttp

    from content_generator.generator import ContentGenerator

    topics = [
        "Автоматизация бизнес-процессов с помощью Telegram-ботов",
        "Как ИИ помогает фрилансерам находить заказы",
        "Тренды в разработке на Python в 2024 году",
        "Преимущества микросервисной архитектуры",
        "Как правильно оценивать стоимость IT-проекта",
        "SEO-оптимизация для технических блогов",
        "Парсинг данных: легальные способы и лучшие практики",
        "Криптотрейдинг и автоматизация: с чего начать",
    ]

    topic = random.choice(topics)
    generator = ContentGenerator()

    async with aiohttp.ClientSession() as session:
        post = await generator.generate_channel_post(session, topic)

    if post:
        return f"generated_post:topic={topic}"
    return "content_generation_failed"


async def viral_notification_task(
    ctx: dict[str, Any],
    referrer_tg_id: int,
    bonus_info: str,
) -> str:
    """Задача отправки реферальных уведомлений.

    Уведомляет реферера о новом бонусе.
    """
    import aiohttp

    import config

    url = (
        f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/sendMessage"
    )
    text = f"Вам начислен реферальный бонус: {bonus_info}"
    payload = {
        "chat_id": referrer_tg_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, timeout=15) as resp:
                if resp.status == 200:
                    return "notification_sent"
                return f"notification_failed:status={resp.status}"
    except Exception as e:
        return f"notification_error:{e}"
