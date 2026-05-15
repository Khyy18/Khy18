"""Аналитический дашборд AI-агентства: сбор метрик, форматирование."""

from typing import Dict, Any, List

import database
from utils import _card, format_number, sparkline


async def get_dashboard_data() -> Dict[str, Any]:
    """
    Собрать данные для дашборда администратора.

    Возвращает словарь с метриками:
    - total_revenue: общая выручка
    - avg_check: средний чек
    - conversion: конверсия (% клиентов с заказами)
    - popular_services: топ-5 услуг [(название, кол-во)]
    - revenue_last_7_days: выручка по дням (list of floats)
    - total_clients: всего клиентов
    - active_clients_7d: активных за 7 дней
    - ltv: lifetime value (выручка / клиенты)
    """
    # Общая выручка
    _, total_revenue = await database.get_stats_for_period(9999)

    # Средний чек
    avg_check = await database.get_avg_check()

    # Конверсия
    conversion_stats = await database.get_conversion_stats()
    total_clients = conversion_stats["total_clients"]
    conversion = conversion_stats["conversion_rate"]

    # Популярные услуги
    popular_services = await database.get_popular_services(limit=5)

    # Выручка за 7 дней
    revenue_days = await database.get_revenue_last_n_days(7)
    revenue_values = [r[1] for r in revenue_days] if revenue_days else [0.0]

    # Активные клиенты за 7 дней (все кроме неактивных)
    inactive = await database.get_clients_inactive_days(7)
    active_clients_7d = max(total_clients - len(inactive), 0)

    # LTV
    ltv = total_revenue / total_clients if total_clients > 0 else 0.0

    return {
        "total_revenue": total_revenue,
        "avg_check": avg_check,
        "conversion": conversion,
        "popular_services": popular_services,
        "revenue_last_7_days": revenue_values,
        "total_clients": total_clients,
        "active_clients_7d": active_clients_7d,
        "ltv": ltv,
    }


def format_dashboard(data: Dict[str, Any]) -> str:
    """
    Форматировать дашборд в HTML-карточку для Telegram.

    Использует sparkline для графика выручки, _card для обрамления.
    """
    revenue_spark = sparkline(data["revenue_last_7_days"])

    body: List[str] = [
        f"<b>Выручка (всего):</b> {format_number(data['total_revenue'])} \u20bd",
        f"<b>Средний чек:</b> {format_number(data['avg_check'])} \u20bd",
        f"<b>LTV:</b> {format_number(data['ltv'])} \u20bd",
        "",
        f"<b>Клиентов:</b> {data['total_clients']}",
        f"<b>Активных (7д):</b> {data['active_clients_7d']}",
        f"<b>Конверсия:</b> {data['conversion']:.1f}%",
        "",
        f"<b>Выручка за 7 дней:</b>",
        f"  {revenue_spark}",
        "",
        "<b>Популярные услуги:</b>",
    ]

    for i, (service_name, count) in enumerate(data["popular_services"], 1):
        body.append(f"  {i}. {service_name} \u2014 {count} заказов")

    if not data["popular_services"]:
        body.append("  \u2014 нет данных")

    return _card("Аналитика", "\U0001f4ca", body)
