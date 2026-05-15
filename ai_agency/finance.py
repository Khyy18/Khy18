"""Финансовый модуль AI-агентства: P&L, прогнозы, CAC, LTV, расходы."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import aiosqlite

import config
import database
from utils import _card, format_number

logger = logging.getLogger(__name__)


async def calculate_pnl(days: int = 30) -> Dict[str, float]:
    """
    Рассчитать P&L (прибыль и убытки) за указанный период.

    Выручка - стоимость API-токенов = чистая прибыль.
    """
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # Выручка
        cursor = await db.execute(
            """SELECT COALESCE(SUM(price), 0) FROM orders
               WHERE created_at >= ? AND status = 'completed'""",
            (since,),
        )
        row = await cursor.fetchone()
        revenue = row[0] if row else 0.0

        # Расходы на API (подсчитываем по количеству заказов * средняя стоимость)
        cursor2 = await db.execute(
            """SELECT COUNT(*) FROM orders
               WHERE created_at >= ? AND status = 'completed'""",
            (since,),
        )
        row2 = await cursor2.fetchone()
        order_count = row2[0] if row2 else 0

        # Средний расход токенов на заказ (приблизительно 2000 токенов)
        avg_tokens_per_order = 2000
        api_costs = order_count * avg_tokens_per_order / 1000 * config.OPENAI_TOKEN_COST_PER_1K

        # Другие расходы
        cursor3 = await db.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM expenses
               WHERE created_at >= ?""",
            (since,),
        )
        row3 = await cursor3.fetchone()
        other_expenses = row3[0] if row3 else 0.0

        total_expenses = api_costs + other_expenses
        net_profit = revenue - total_expenses

    return {
        "revenue": revenue,
        "api_costs": api_costs,
        "other_expenses": other_expenses,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "order_count": order_count,
        "period_days": days,
    }


async def forecast_revenue_month() -> Dict[str, float]:
    """
    Прогноз выручки на месяц по линейной экстраполяции из последних 7 дней.
    """
    revenue_data = await database.get_revenue_last_n_days(7)
    if not revenue_data:
        return {"daily_avg": 0.0, "monthly_forecast": 0.0, "data_days": 0}

    total_revenue = sum(r[1] for r in revenue_data)
    data_days = len(revenue_data)
    daily_avg = total_revenue / data_days if data_days > 0 else 0.0
    monthly_forecast = daily_avg * 30

    return {
        "daily_avg": daily_avg,
        "monthly_forecast": monthly_forecast,
        "data_days": data_days,
    }


async def calculate_cac(ad_spend: Optional[float] = None, days: int = 30) -> float:
    """
    Рассчитать CAC (стоимость привлечения клиента).

    CAC = рекламные расходы / количество новых клиентов за период.
    """
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    if ad_spend is None:
        # Берём из расходов категории 'advertising'
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM expenses
                   WHERE category = 'advertising' AND created_at >= ?""",
                (since,),
            )
            row = await cursor.fetchone()
            ad_spend = row[0] if row else 0.0

    # Количество новых клиентов
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM clients WHERE registered_at >= ?",
            (since,),
        )
        row = await cursor.fetchone()
        new_clients = row[0] if row else 0

    if new_clients == 0:
        return 0.0

    return ad_spend / new_clients


async def calculate_ltv_cac_ratio(days: int = 30) -> Dict[str, float]:
    """
    Рассчитать LTV/CAC ratio.

    LTV = средний чек * среднее количество заказов на клиента.
    """
    avg_check = await database.get_avg_check()

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # Среднее количество заказов на клиента
        cursor = await db.execute(
            """SELECT AVG(order_count) FROM (
                SELECT COUNT(*) as order_count FROM orders
                GROUP BY client_id
            )"""
        )
        row = await cursor.fetchone()
        avg_orders = row[0] if row and row[0] else 1.0

    ltv = avg_check * avg_orders
    cac = await calculate_cac(days=days)
    ratio = ltv / cac if cac > 0 else 0.0

    return {
        "ltv": ltv,
        "cac": cac,
        "ratio": ratio,
        "avg_check": avg_check,
        "avg_orders_per_client": avg_orders,
    }


async def get_service_margins() -> List[Dict[str, float]]:
    """Получить маржинальность по каждому типу услуги."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT service_type, COUNT(*) as cnt, COALESCE(SUM(price), 0) as revenue
               FROM orders WHERE status = 'completed'
               GROUP BY service_type
               ORDER BY revenue DESC"""
        )
        rows = await cursor.fetchall()

    margins = []
    avg_tokens_per_order = 2000
    cost_per_order = avg_tokens_per_order / 1000 * config.OPENAI_TOKEN_COST_PER_1K

    for row in rows:
        service_type = row[0]
        count = row[1]
        revenue = row[2]
        total_cost = count * cost_per_order
        margin = revenue - total_cost
        margin_percent = (margin / revenue * 100) if revenue > 0 else 0.0
        margins.append({
            "service_type": service_type,
            "order_count": count,
            "revenue": revenue,
            "cost": total_cost,
            "margin": margin,
            "margin_percent": margin_percent,
        })

    return margins


async def get_token_usage(days: int = 30) -> Dict[str, float]:
    """Получить расход токенов OpenAI за период."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM orders
               WHERE created_at >= ? AND status = 'completed'""",
            (since,),
        )
        row = await cursor.fetchone()
        order_count = row[0] if row else 0

    avg_tokens_per_order = 2000
    total_tokens = order_count * avg_tokens_per_order
    total_cost = total_tokens / 1000 * config.OPENAI_TOKEN_COST_PER_1K

    return {
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "orders_count": order_count,
        "cost_per_1k": config.OPENAI_TOKEN_COST_PER_1K,
        "period_days": days,
    }


async def add_expense(category: str, amount: float, description: str = "") -> int:
    """Добавить расход."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO expenses (category, amount, description) VALUES (?, ?, ?)",
            (category, amount, description),
        )
        await db.commit()
        return cursor.lastrowid


async def get_expenses(days: int = 30) -> List[Dict]:
    """Получить расходы за период."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM expenses WHERE created_at >= ?
               ORDER BY created_at DESC""",
            (since,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


def format_pnl_card(pnl: Dict) -> str:
    """Форматировать P&L как карточку для админ-бота."""
    body = [
        f"<b>Период:</b> {pnl['period_days']} дней",
        f"<b>Заказов:</b> {pnl['order_count']}",
        "",
        f"\U0001f4b0 Выручка: {format_number(pnl['revenue'])} \u20bd",
        f"\U0001f4bb API-расходы: {format_number(pnl['api_costs'])} \u20bd",
        f"\U0001f4c1 Прочие расходы: {format_number(pnl['other_expenses'])} \u20bd",
        "",
        f"\U0001f4b5 <b>Чистая прибыль: {format_number(pnl['net_profit'])} \u20bd</b>",
    ]
    return _card("P&L отчёт", "\U0001f4ca", body)


def format_forecast_card(forecast: Dict) -> str:
    """Форматировать прогноз как карточку."""
    body = [
        f"<b>Данные за:</b> {forecast['data_days']} дней",
        f"<b>Средняя выручка/день:</b> {format_number(forecast['daily_avg'])} \u20bd",
        f"<b>Прогноз на месяц:</b> {format_number(forecast['monthly_forecast'])} \u20bd",
    ]
    return _card("Прогноз выручки", "\U0001f4c8", body)
