import aiosqlite

from kindergarten_accountant_bot import config


async def init_db():
    """Initialize the database and create all tables."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fio TEXT NOT NULL,
                position TEXT NOT NULL,
                rate REAL NOT NULL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS timesheet_marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                mark_type TEXT NOT NULL,
                FOREIGN KEY (employee_id) REFERENCES employees (id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS children (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_fio TEXT NOT NULL,
                group_name TEXT NOT NULL,
                parent_fio TEXT NOT NULL,
                discount_percent REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS parent_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_id INTEGER NOT NULL,
                month INTEGER,
                year INTEGER,
                attendance_days INTEGER,
                amount_due REAL,
                amount_paid REAL DEFAULT 0,
                paid_at TIMESTAMP,
                FOREIGN KEY (child_id) REFERENCES children (id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                entry_type TEXT NOT NULL CHECK(entry_type IN ('income', 'expense')),
                counterparty TEXT,
                basis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                cron_type TEXT,
                day_of_month INTEGER,
                enabled INTEGER DEFAULT 1,
                chat_id INTEGER
            )
        """)

        await db.commit()
