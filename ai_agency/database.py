"""Асинхронная работа с SQLite базой данных для AI-агентства."""

import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

import config


async def get_connection() -> aiosqlite.Connection:
    """Получить подключение к БД с WAL режимом и busy_timeout."""
    conn = await aiosqlite.connect(config.DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=5000")
    return conn


async def init_db() -> None:
    """Инициализация базы данных: создание таблиц, включение WAL."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # WAL-режим для лучшей конкурентности + busy_timeout для Docker multi-container
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                registered_at TEXT NOT NULL DEFAULT (datetime('now')),
                total_spent REAL NOT NULL DEFAULT 0.0,
                balance REAL NOT NULL DEFAULT 0.0,
                referred_by INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                input_text TEXT NOT NULL,
                output_text TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                price REAL NOT NULL DEFAULT 0.0,
                rating INTEGER,
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                method TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                bonus_amount REAL NOT NULL DEFAULT 0.0,
                paid INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (referrer_id) REFERENCES clients(telegram_id),
                FOREIGN KEY (referred_id) REFERENCES clients(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                tier TEXT NOT NULL DEFAULT 'none',
                status TEXT NOT NULL DEFAULT 'active',
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT,
                orders_used INTEGER NOT NULL DEFAULT 0,
                yookassa_subscription_id TEXT,
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS processed_payments (
                payment_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Миграция: добавляем last_notified_at если отсутствует
        try:
            await db.execute(
                "ALTER TABLE clients ADD COLUMN last_notified_at TEXT"
            )
        except Exception:
            pass  # Колонка уже существует
        # Миграция: добавляем last_upsell_at если отсутствует
        try:
            await db.execute(
                "ALTER TABLE clients ADD COLUMN last_upsell_at TEXT"
            )
        except Exception:
            pass  # Колонка уже существует
        # Миграция: добавляем free_trial_used если отсутствует
        try:
            await db.execute(
                "ALTER TABLE clients ADD COLUMN free_trial_used INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # Колонка уже существует
        # Миграция: добавляем language если отсутствует
        try:
            await db.execute(
                "ALTER TABLE clients ADD COLUMN language TEXT NOT NULL DEFAULT 'ru'"
            )
        except Exception:
            pass  # Колонка уже существует
        # Миграция: добавляем ab_variant_id к orders
        try:
            await db.execute(
                "ALTER TABLE orders ADD COLUMN ab_variant_id INTEGER"
            )
        except Exception:
            pass  # Колонка уже существует
        # Миграция: добавляем case_posted к orders
        try:
            await db.execute(
                "ALTER TABLE orders ADD COLUMN case_posted INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # Колонка уже существует
        # Таблица ab_variants для A/B тестирования
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ab_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_type TEXT NOT NULL,
                variant_name TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                total_uses INTEGER NOT NULL DEFAULT 0,
                total_score REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица parsed_leads для парсера лидов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS parsed_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                title TEXT,
                url TEXT,
                parsed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица api_keys для REST API аутентификации
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                client_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                rate_limit INTEGER NOT NULL DEFAULT 60,
                requests_today INTEGER NOT NULL DEFAULT 0,
                last_reset TEXT
            )
        """)
        # Таблица funnel_events для воронки продаж
        await db.execute("""
            CREATE TABLE IF NOT EXISTS funnel_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                stage TEXT NOT NULL,
                triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
                converted_at TEXT,
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id)
            )
        """)
        # Таблица expenses для финансов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица promo_codes
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                discount_type TEXT NOT NULL DEFAULT 'percentage',
                discount_value REAL NOT NULL,
                max_uses INTEGER NOT NULL DEFAULT 0,
                used_count INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица partner_earnings для партнёрской программы
        await db.execute("""
            CREATE TABLE IF NOT EXISTS partner_earnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_id INTEGER NOT NULL,
                referred_client_id INTEGER NOT NULL,
                order_id INTEGER,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (partner_id) REFERENCES clients(telegram_id),
                FOREIGN KEY (referred_client_id) REFERENCES clients(telegram_id)
            )
        """)
        # Таблица semantic_cache
        await db.execute("""
            CREATE TABLE IF NOT EXISTS semantic_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_type TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                embedding_hash TEXT,
                result_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Таблица unrecognized_requests
        await db.execute("""
            CREATE TABLE IF NOT EXISTS unrecognized_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id)
            )
        """)
        # Таблица reviews для системы отзывов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                rating INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                approved_at TEXT,
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id),
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        """)
        # Таблица ad_campaigns для рекламного менеджера
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ad_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_name TEXT NOT NULL,
                budget REAL NOT NULL DEFAULT 0,
                clicks INTEGER NOT NULL DEFAULT 0,
                conversions INTEGER NOT NULL DEFAULT 0,
                roi REAL NOT NULL DEFAULT 0,
                source TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица webhook_endpoints для B2B вебхуков
        await db.execute("""
            CREATE TABLE IF NOT EXISTS webhook_endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                secret TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица webhook_deliveries для доставки вебхуков
        await db.execute("""
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                FOREIGN KEY (webhook_id) REFERENCES webhook_endpoints(id)
            )
        """)
        # Таблица whitelabel_bots для white-label системы
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelabel_bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                bot_name TEXT NOT NULL,
                persona TEXT NOT NULL DEFAULT 'Assistant',
                allowed_services TEXT NOT NULL DEFAULT '[]',
                pricing_multiplier REAL NOT NULL DEFAULT 1.0,
                revenue_share REAL NOT NULL DEFAULT 0.3,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица whitelabel_revenue для доходов white-label
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelabel_revenue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL,
                order_id INTEGER,
                amount REAL NOT NULL,
                owner_share REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (bot_id) REFERENCES whitelabel_bots(id)
            )
        """)
        # Таблица templates для маркетплейса
        await db.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                preview TEXT NOT NULL,
                full_text TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 50.0,
                sales_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица template_purchases для покупок шаблонов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS template_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                template_id INTEGER NOT NULL,
                purchased_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id),
                FOREIGN KEY (template_id) REFERENCES templates(id)
            )
        """)
        # Таблица user_events для ретаргетинга
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                processed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица onboarding_events для отслеживания онбординга
        await db.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                step TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT 'view',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Таблица prompt_cache для кеша переводов промптов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS prompt_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_type TEXT NOT NULL,
                lang TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                user_prompt TEXT NOT NULL,
                cached_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(service_type, lang)
            )
        """)
        # Миграция: добавляем loyalty_notified_level если отсутствует
        try:
            await db.execute(
                "ALTER TABLE clients ADD COLUMN loyalty_notified_level TEXT DEFAULT 'bronze'"
            )
        except Exception:
            pass  # Колонка уже существует
        await db.commit()


# --- Клиенты ---

async def get_or_create_client(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> dict:
    """Получить клиента или создать нового."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)

        await db.execute(
            "INSERT INTO clients (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return dict(row)


async def get_client_balance(telegram_id: int) -> float:
    """Получить баланс клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT balance FROM clients WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0.0


async def update_balance(telegram_id: int, new_balance: float) -> None:
    """Обновить баланс клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET balance = ? WHERE telegram_id = ?",
            (new_balance, telegram_id),
        )
        await db.commit()


async def atomic_deduct_balance(telegram_id: int, amount: float) -> bool:
    """Атомарно списать средства с баланса. Возвращает True при успехе."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE clients SET balance = balance - ? WHERE telegram_id = ? AND balance >= ?",
            (amount, telegram_id, amount),
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_total_spent(telegram_id: int, amount: float) -> None:
    """Увеличить общую сумму расходов клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET total_spent = total_spent + ? WHERE telegram_id = ?",
            (amount, telegram_id),
        )
        await db.commit()


async def get_all_clients() -> List[dict]:
    """Получить список всех клиентов."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM clients ORDER BY registered_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# --- Заказы ---

async def create_order(
    client_id: int,
    service_type: str,
    input_text: str,
    price: float,
) -> int:
    """Создать новый заказ, вернуть ID."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO orders (client_id, service_type, input_text, price, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (client_id, service_type, input_text, price),
        )
        await db.commit()
        return cursor.lastrowid


async def update_order_status(
    order_id: int,
    status: str,
    output_text: Optional[str] = None,
) -> None:
    """Обновить статус заказа."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        if output_text is not None:
            await db.execute(
                """UPDATE orders SET status = ?, output_text = ?,
                   completed_at = datetime('now') WHERE id = ?""",
                (status, output_text, order_id),
            )
        else:
            await db.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (status, order_id),
            )
        await db.commit()


async def update_order_rating(order_id: int, rating: int) -> None:
    """Обновить рейтинг заказа."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE orders SET rating = ? WHERE id = ?",
            (rating, order_id),
        )
        await db.commit()


async def update_order_ab_variant(order_id: int, variant_id: int) -> None:
    """Сохранить ID A/B варианта, использованного для заказа."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE orders SET ab_variant_id = ? WHERE id = ?",
            (variant_id, order_id),
        )
        await db.commit()


async def get_orders_by_client(client_id: int, limit: int = 10) -> List[dict]:
    """Получить заказы клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE client_id = ? ORDER BY created_at DESC LIMIT ?",
            (client_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_order_by_id(order_id: int) -> Optional[dict]:
    """Получить заказ по ID."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_recent_orders(limit: int = 20) -> List[dict]:
    """Получить последние заказы."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_stats_for_period(days: int) -> Tuple[int, float]:
    """Получить статистику за период: (количество заказов, выручка)."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(price), 0) as revenue
               FROM orders WHERE created_at >= ? AND status = 'completed'""",
            (since,),
        )
        row = await cursor.fetchone()
        return (row[0], row[1]) if row else (0, 0.0)


async def get_client_order_count(client_id: int) -> int:
    """Получить количество заказов клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE client_id = ?",
            (client_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


# --- Платежи ---

async def add_payment(client_id: int, amount: float, method: str = "manual") -> int:
    """Добавить запись о платеже."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO payments (client_id, amount, method) VALUES (?, ?, ?)",
            (client_id, amount, method),
        )
        await db.commit()
        return cursor.lastrowid


# --- Рефералы ---

async def create_referral(referrer_id: int, referred_id: int, bonus_amount: float) -> int:
    """Создать запись реферала."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # Отмечаем referred_by у клиента
        await db.execute(
            "UPDATE clients SET referred_by = ? WHERE telegram_id = ?",
            (referrer_id, referred_id),
        )
        cursor = await db.execute(
            """INSERT INTO referrals (referrer_id, referred_id, bonus_amount)
               VALUES (?, ?, ?)""",
            (referrer_id, referred_id, bonus_amount),
        )
        await db.commit()
        return cursor.lastrowid


async def get_referral_stats(referrer_id: int) -> dict:
    """Получить статистику рефералов пользователя."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as total, COALESCE(SUM(bonus_amount), 0) as total_bonus "
            "FROM referrals WHERE referrer_id = ?",
            (referrer_id,),
        )
        row = await cursor.fetchone()
        total = row[0] if row else 0
        total_bonus = row[1] if row else 0.0
        cursor2 = await db.execute(
            "SELECT COALESCE(SUM(bonus_amount), 0) FROM referrals "
            "WHERE referrer_id = ? AND paid = 0",
            (referrer_id,),
        )
        row2 = await cursor2.fetchone()
        unpaid = row2[0] if row2 else 0.0
        return {"total": total, "total_bonus": total_bonus, "unpaid_bonus": unpaid}


# --- Подписки ---

async def get_subscription(client_id: int) -> Optional[dict]:
    """Получить активную подписку клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM subscriptions WHERE client_id = ? AND status = 'active' "
            "ORDER BY started_at DESC LIMIT 1",
            (client_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_subscription(
    client_id: int,
    tier: str,
    expires_at: str,
    yookassa_subscription_id: Optional[str] = None,
) -> int:
    """Создать подписку."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO subscriptions
               (client_id, tier, status, expires_at, yookassa_subscription_id)
               VALUES (?, ?, 'active', ?, ?)""",
            (client_id, tier, expires_at, yookassa_subscription_id),
        )
        await db.commit()
        return cursor.lastrowid


async def update_subscription(subscription_id: int, **kwargs) -> None:
    """Обновить поля подписки."""
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values())
    values.append(subscription_id)
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE subscriptions SET {fields} WHERE id = ?",
            values,
        )
        await db.commit()


# --- Аналитика ---

async def get_clients_inactive_days(days: int) -> List[dict]:
    """Получить клиентов, неактивных более N дней."""
    threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT c.* FROM clients c
               WHERE c.telegram_id NOT IN (
                   SELECT DISTINCT client_id FROM orders WHERE created_at >= ?
               )""",
            (threshold,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_revenue_last_n_days(days: int) -> List[Tuple[str, float]]:
    """Получить выручку по дням за последние N дней."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT DATE(created_at) as day, COALESCE(SUM(price), 0) as revenue
               FROM orders
               WHERE created_at >= ? AND status = 'completed'
               GROUP BY DATE(created_at)
               ORDER BY day""",
            (since,),
        )
        rows = await cursor.fetchall()
        return [(row[0], row[1]) for row in rows]


async def get_popular_services(limit: int = 5) -> List[Tuple[str, int]]:
    """Получить самые популярные услуги."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT service_type, COUNT(*) as cnt
               FROM orders
               GROUP BY service_type
               ORDER BY cnt DESC
               LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [(row[0], row[1]) for row in rows]


async def get_conversion_stats() -> dict:
    """Получить конверсию: зарегистрированные vs сделавшие заказ."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM clients")
        total_row = await cursor.fetchone()
        total_clients = total_row[0] if total_row else 0

        cursor2 = await db.execute(
            "SELECT COUNT(DISTINCT client_id) FROM orders"
        )
        row2 = await cursor2.fetchone()
        clients_with_orders = row2[0] if row2 else 0

        return {
            "total_clients": total_clients,
            "clients_with_orders": clients_with_orders,
            "conversion_rate": (
                clients_with_orders / total_clients * 100
                if total_clients > 0 else 0.0
            ),
        }


async def get_avg_check() -> float:
    """Получить средний чек по завершённым заказам."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT AVG(price) FROM orders WHERE status = 'completed'"
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0.0


async def get_all_clients_with_orders() -> List[dict]:
    """Получить всех клиентов с количеством заказов."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT c.*, COUNT(o.id) as order_count
               FROM clients c
               LEFT JOIN orders o ON c.telegram_id = o.client_id
               GROUP BY c.telegram_id
               ORDER BY c.registered_at DESC"""
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# --- Идемпотентность вебхуков ---

async def is_payment_processed(payment_id: str) -> bool:
    """Проверить, был ли платёж уже обработан."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM processed_payments WHERE payment_id = ?",
            (payment_id,),
        )
        row = await cursor.fetchone()
        return row is not None


async def mark_payment_processed(payment_id: str) -> None:
    """Отметить платёж как обработанный."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO processed_payments (payment_id) VALUES (?)",
            (payment_id,),
        )
        await db.commit()


# --- Реферальный бонус (атомарная операция) ---

async def credit_referral_bonus(user_id: int, order_price: float, bonus_percent: int) -> Optional[float]:
    """
    Начислить реферальный бонус реферреру при первом заказе.

    Возвращает сумму бонуса если начислен, None иначе.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id = ? AND paid = 0",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        referrer_id = row["referrer_id"]
        bonus = order_price * bonus_percent / 100
        await db.execute(
            "UPDATE clients SET balance = balance + ? WHERE telegram_id = ?",
            (bonus, referrer_id),
        )
        await db.execute(
            "UPDATE referrals SET bonus_amount = ?, paid = 1 WHERE referred_id = ? AND referrer_id = ?",
            (bonus, user_id, referrer_id),
        )
        await db.commit()
        return bonus


# --- Планировщик: дедупликация уведомлений ---

async def get_clients_inactive_days_not_notified(days: int, cooldown_hours: int = 168) -> List[dict]:
    """
    Получить клиентов, неактивных более N дней, которым не отправлялось
    уведомление в течение cooldown_hours часов.
    """
    threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cooldown_threshold = (datetime.utcnow() - timedelta(hours=cooldown_hours)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT c.* FROM clients c
               WHERE c.telegram_id NOT IN (
                   SELECT DISTINCT client_id FROM orders WHERE created_at >= ?
               )
               AND (c.last_notified_at IS NULL OR c.last_notified_at < ?)""",
            (threshold, cooldown_threshold),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_client_last_notified(telegram_id: int) -> None:
    """Обновить время последнего retention-уведомления клиента."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET last_notified_at = ? WHERE telegram_id = ?",
            (now, telegram_id),
        )
        await db.commit()


async def get_clients_for_upsell_not_notified(min_orders: int, cooldown_hours: int = 168) -> List[dict]:
    """
    Получить клиентов с min_orders+ заказов, которым не отправлялось
    upsell-уведомление в течение cooldown_hours часов.
    """
    cooldown_threshold = (datetime.utcnow() - timedelta(hours=cooldown_hours)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT c.*, COUNT(o.id) as order_count
               FROM clients c
               LEFT JOIN orders o ON c.telegram_id = o.client_id
               GROUP BY c.telegram_id
               HAVING order_count >= ?
               AND (c.last_upsell_at IS NULL OR c.last_upsell_at < ?)""",
            (min_orders, cooldown_threshold),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_client_last_upsell(telegram_id: int) -> None:
    """Обновить время последнего upsell-уведомления клиента."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET last_upsell_at = ? WHERE telegram_id = ?",
            (now, telegram_id),
        )
        await db.commit()


# --- Подписки: истечение через database ---

async def expire_active_subscriptions() -> int:
    """
    Пометить истёкшие подписки как expired.
    Возвращает количество обновлённых записей.
    """
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """UPDATE subscriptions SET status = 'expired'
               WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at < ?""",
            (now,),
        )
        count = cursor.rowcount
        await db.commit()
    return count


# --- Подписки: атомарный инкремент с проверкой лимита ---

async def atomic_increment_subscription_usage(client_id: int, order_limit: int) -> bool:
    """
    Атомарно инкрементировать orders_used подписки с проверкой лимита.

    Использует UPDATE ... WHERE orders_used < limit для атомарности.
    Возвращает True если инкремент выполнен, False если лимит исчерпан.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """UPDATE subscriptions
               SET orders_used = orders_used + 1
               WHERE client_id = ? AND status = 'active' AND orders_used < ?""",
            (client_id, order_limit),
        )
        success = cursor.rowcount > 0
        await db.commit()
    return success


async def atomic_increment_subscription_usage_unlimited(client_id: int) -> bool:
    """
    Атомарно инкрементировать orders_used подписки (PRO, без лимита).
    Возвращает True если инкремент выполнен.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """UPDATE subscriptions
               SET orders_used = orders_used + 1
               WHERE client_id = ? AND status = 'active'""",
            (client_id,),
        )
        success = cursor.rowcount > 0
        await db.commit()
    return success


# --- Free Trial ---

async def get_client_trial_used(telegram_id: int) -> bool:
    """Проверить, использовал ли клиент бесплатный пробный заказ."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT free_trial_used FROM clients WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return bool(row[0]) if row else False


async def mark_trial_used(telegram_id: int) -> None:
    """Отметить бесплатный пробный заказ как использованный."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET free_trial_used = 1 WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()


# --- Language ---

async def get_client_language(telegram_id: int) -> str:
    """Получить язык клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT language FROM clients WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else "ru"


async def set_client_language(telegram_id: int, lang: str) -> None:
    """Установить язык клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET language = ? WHERE telegram_id = ?",
            (lang, telegram_id),
        )
        await db.commit()
