"""Ecosystem Promoter - продвигает все продукты экосистемы через outbound."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProductCampaign:
    """Конфигурация кампании для одного продукта."""
    product_name: str
    product_description: str
    target_icp: dict[str, Any]
    value_proposition: str
    sequence: list[dict[str, str]]


# Каталог продуктов для продвижения
ECOSYSTEM_PRODUCTS: list[ProductCampaign] = [
    ProductCampaign(
        product_name="Price Monitor",
        product_description="Мониторинг цен конкурентов на WB/Ozon с ИИ-аналитикой",
        target_icp={
            "industry": "E-commerce, Маркетплейсы",
            "titles": ["Селлер", "Менеджер маркетплейсов", "Владелец магазина", "Категорийный менеджер"],
            "signals": ["продаёт на Wildberries", "продаёт на Ozon", "маркетплейс в описании"],
            "company_size": "1-50",
        },
        value_proposition=(
            "Автоматический мониторинг цен конкурентов на WB и Ozon. "
            "ИИ анализирует скидки, предсказывает тренды, рекомендует оптимальную цену. "
            "От 990 ₽/мес."
        ),
        sequence=[
            {
                "step_type": "initial",
                "delay_days": "0",
                "subject": "Знаете, по какой цене продают ваши конкуренты?",
                "body": (
                    "Здравствуйте, {{first_name}}!\n\n"
                    "Заметил, что {{company}} продаёт на маркетплейсах. "
                    "Вопрос: как часто вы проверяете цены конкурентов?\n\n"
                    "Наш бот делает это автоматически каждые 30 минут и присылает алерт, "
                    "когда конкурент снижает цену. Плюс ИИ подсказывает оптимальную цену "
                    "для максимума продаж.\n\n"
                    "Бесплатный тест 7 дней — хотите попробовать?\n\n"
                    "С уважением"
                ),
            },
            {
                "step_type": "follow_up_1",
                "delay_days": "3",
                "subject": "Re: Мониторинг конкурентов на WB/Ozon",
                "body": (
                    "{{first_name}}, добрый день!\n\n"
                    "Пишу повторно. Наши клиенты в среднем увеличивают продажи на 15-20% "
                    "за первый месяц — просто потому что реагируют на изменения цен "
                    "конкурентов в реальном времени, а не раз в неделю вручную.\n\n"
                    "Могу показать на примере вашей ниши. 5 минут в Telegram?\n\n"
                    "С уважением"
                ),
            },
            {
                "step_type": "follow_up_2",
                "delay_days": "5",
                "subject": "Последнее сообщение — Price Monitor",
                "body": (
                    "{{first_name}}, не буду больше беспокоить.\n\n"
                    "Оставлю ссылку на бесплатный тест: @PriceMonitorBot\n"
                    "7 дней бесплатно, карта не нужна.\n\n"
                    "Если тема станет актуальна — буду рад помочь.\n\n"
                    "Удачных продаж!"
                ),
            },
        ],
    ),
    ProductCampaign(
        product_name="AI Text Agency",
        product_description="ИИ-копирайтер для бизнеса — тексты, посты, рассылки",
        target_icp={
            "industry": "Маркетинг, Digital-агентства, E-commerce",
            "titles": ["Маркетолог", "SMM-менеджер", "Контент-менеджер", "Владелец бизнеса"],
            "signals": ["ведёт соцсети", "нанимает копирайтера", "контент-маркетинг"],
            "company_size": "1-100",
        },
        value_proposition=(
            "ИИ-копирайтер, который пишет как человек: посты, рассылки, описания товаров, "
            "SEO-тексты. 100 текстов в месяц за стоимость одного фрилансера."
        ),
        sequence=[
            {
                "step_type": "initial",
                "delay_days": "0",
                "subject": "Сколько вы тратите на тексты в месяц?",
                "body": (
                    "Здравствуйте, {{first_name}}!\n\n"
                    "Вижу, что {{company}} активно ведёт контент. Вопрос: "
                    "сколько времени/денег уходит на тексты в месяц?\n\n"
                    "Наш ИИ-копирайтер генерирует посты, рассылки, описания товаров "
                    "в вашем tone of voice. Обучается на ваших примерах.\n\n"
                    "Средний клиент экономит 40-60 тысяч ₽/мес на копирайтинге.\n\n"
                    "Интересно посмотреть демо?\n\n"
                    "С уважением"
                ),
            },
            {
                "step_type": "follow_up_1",
                "delay_days": "3",
                "subject": "Re: ИИ-копирайтер для {{company}}",
                "body": (
                    "{{first_name}}, добрый день!\n\n"
                    "Дополню: бот генерирует не шаблонные тексты, а адаптируется "
                    "под стиль вашего бренда. Можете загрузить 5-10 примеров — "
                    "и он будет писать так же.\n\n"
                    "Первые 10 текстов — бесплатно. Попробуете?\n\n"
                    "С уважением"
                ),
            },
            {
                "step_type": "follow_up_2",
                "delay_days": "5",
                "subject": "Последнее — AI Text Agency",
                "body": (
                    "{{first_name}}, не настаиваю.\n\n"
                    "Бот: @AITextAgencyBot — попробуйте когда будет удобно.\n"
                    "Бесплатно первые 10 текстов, без привязки карты.\n\n"
                    "Хороших продаж!"
                ),
            },
        ],
    ),
    ProductCampaign(
        product_name="AI Office",
        product_description="Мульти-агентная ИИ-система для автоматизации офисной рутины",
        target_icp={
            "industry": "Любая (B2B, услуги, IT)",
            "titles": ["CEO", "COO", "Операционный директор", "Руководитель отдела"],
            "signals": ["растёт команда", "ищет автоматизацию", "перегружен рутиной"],
            "company_size": "5-200",
        },
        value_proposition=(
            "ИИ-ассистенты для вашей команды: отвечают на письма, готовят отчёты, "
            "ведут CRM, планируют встречи. Экономия 20+ часов в неделю на рутине."
        ),
        sequence=[
            {
                "step_type": "initial",
                "delay_days": "0",
                "subject": "20 часов в неделю на рутине — можно вернуть",
                "body": (
                    "Здравствуйте, {{first_name}}!\n\n"
                    "Команды из 5-50 человек обычно тратят 30-40% времени на рутину: "
                    "отчёты, письма, обновление CRM, планирование.\n\n"
                    "Наши ИИ-агенты берут это на себя. Буквально: пишут письма, "
                    "заполняют таблицы, готовят дайджесты — и стоят дешевле одного сотрудника.\n\n"
                    "Есть 5 минут посмотреть как это работает?\n\n"
                    "С уважением"
                ),
            },
            {
                "step_type": "follow_up_1",
                "delay_days": "4",
                "subject": "Re: Автоматизация рутины для {{company}}",
                "body": (
                    "{{first_name}}, добрый день!\n\n"
                    "Конкретный пример: один из клиентов (IT-компания, 15 человек) "
                    "подключил AI Office — и сэкономил 80 часов/мес на переписке и отчётах.\n\n"
                    "Подключение занимает 30 минут. Пробный период 14 дней.\n\n"
                    "Хотите попробовать?\n\n"
                    "С уважением"
                ),
            },
            {
                "step_type": "follow_up_2",
                "delay_days": "5",
                "subject": "Последнее — AI Office",
                "body": (
                    "{{first_name}}, больше не пишу.\n\n"
                    "Если тема актуальна — бот @AIOfficeBot, 14 дней бесплатно.\n\n"
                    "Удачи!"
                ),
            },
        ],
    ),
]


class EcosystemPromoter:
    """Запускает outbound-кампании для продвижения продуктов экосистемы."""

    def __init__(self) -> None:
        self.products = ECOSYSTEM_PRODUCTS

    def get_product_campaigns(self) -> list[dict[str, Any]]:
        """Получить список всех кампаний для продуктов."""
        return [
            {
                "product_name": p.product_name,
                "description": p.product_description,
                "target_icp": p.target_icp,
                "value_proposition": p.value_proposition,
                "sequence_steps": len(p.sequence),
            }
            for p in self.products
        ]

    def get_campaign_config(self, product_name: str) -> ProductCampaign | None:
        """Получить конфигурацию кампании по имени продукта."""
        for p in self.products:
            if p.product_name.lower() == product_name.lower():
                return p
        return None

    def get_icp_for_product(self, product_name: str) -> dict[str, Any] | None:
        """Получить ICP (идеальный профиль клиента) для продукта."""
        campaign = self.get_campaign_config(product_name)
        if campaign:
            return campaign.target_icp
        return None

    def get_sequence_for_product(self, product_name: str) -> list[dict[str, str]] | None:
        """Получить email-последовательность для продукта."""
        campaign = self.get_campaign_config(product_name)
        if campaign:
            return campaign.sequence
        return None

    def generate_campaign_summary(self) -> str:
        """Генерировать текстовый отчёт по всем кампаниям."""
        lines = ["=" * 50, "ECOSYSTEM PROMOTION CAMPAIGNS", "=" * 50, ""]
        for p in self.products:
            lines.append(f"📦 {p.product_name}")
            lines.append(f"   {p.product_description}")
            lines.append(f"   ICP: {p.target_icp.get('titles', [])}")
            lines.append(f"   Шагов в последовательности: {len(p.sequence)}")
            lines.append("")
        lines.append("=" * 50)
        return "\n".join(lines)


ecosystem_promoter = EcosystemPromoter()
