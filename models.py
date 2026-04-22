# models.py — CREATE TABLE definitions, migrations, and indexes
#
# PERFORMANCE STRATEGY for Supabase free tier:
#   - CREATE TABLE / ADD COLUMN / CREATE INDEX all use IF NOT EXISTS → instant no-ops
#   - ALTER COLUMN TYPE (the slow ones) are guarded by an information_schema check
#     so they only run ONCE ever, never again after the column is already DATE/TIMESTAMP
#   - Each migration runs in its own small get_db() block so a timeout on one
#     never rolls back the others
#   - Index creation runs last, each in its own try/except

from db import get_db


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _col_type(cursor, table, column):
    """Return current data_type of a column, or '' if not found."""
    cursor.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s LIMIT 1
    """, (table, column))
    row = cursor.fetchone()
    return (row["data_type"] or "").lower() if row else ""


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Core tables  (IF NOT EXISTS → instant no-ops after first run)
# ─────────────────────────────────────────────────────────────────────────────

def _create_core_tables():
    with get_db() as (conn, cursor):
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            surname TEXT NOT NULL,
            other_names TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password BYTEA NOT NULL,
            email_verified INTEGER DEFAULT 0,
            verification_code TEXT,
            verification_code_expires_at TIMESTAMP,
            role TEXT DEFAULT 'user',
            monthly_spending_limit INTEGER DEFAULT 0,
            onboarding_complete INTEGER DEFAULT 0,
            allow_overdraft INTEGER DEFAULT 0,
            created_at DATE,
            last_login DATE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS banks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            bank_name TEXT NOT NULL,
            account_name TEXT NOT NULL,
            account_number TEXT NOT NULL,
            balance INTEGER DEFAULT 0,
            min_balance_alert INTEGER DEFAULT 0
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            bank_id INTEGER NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
            type TEXT CHECK(type IN ('credit','debit')),
            amount INTEGER NOT NULL,
            description TEXT,
            created_at DATE DEFAULT CURRENT_DATE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            bank_id INTEGER REFERENCES banks(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            category TEXT,
            amount INTEGER NOT NULL,
            created_at DATE DEFAULT CURRENT_DATE,
            tx_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            target_amount INTEGER NOT NULL,
            current_amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at DATE DEFAULT CURRENT_DATE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS goal_contributions (
            id SERIAL PRIMARY KEY,
            goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            bank_id INTEGER NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL,
            contributed_at DATE DEFAULT CURRENT_DATE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_logins (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            login_date DATE NOT NULL DEFAULT CURRENT_DATE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limit_log (
            id SERIAL PRIMARY KEY,
            identifier TEXT NOT NULL,
            action TEXT NOT NULL,
            attempted_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_budgets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            monthly_limit INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, category)
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_items (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type TEXT NOT NULL CHECK(type IN ('income','expense')),
            name TEXT NOT NULL,
            category TEXT,
            amount INTEGER NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'monthly'
                CHECK(frequency IN ('daily','weekly','monthly','yearly')),
            next_due DATE,
            bank_id INTEGER REFERENCES banks(id) ON DELETE SET NULL,
            auto_post INTEGER DEFAULT 0,
            allow_overdraft INTEGER DEFAULT 0,
            last_posted_at DATE,
            active INTEGER DEFAULT 1,
            created_at DATE DEFAULT CURRENT_DATE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS debts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'borrowed'
                CHECK(type IN ('borrowed','lent')),
            principal INTEGER NOT NULL,
            balance_remaining INTEGER NOT NULL,
            interest_rate NUMERIC(5,2) DEFAULT 0,
            monthly_payment INTEGER DEFAULT 0,
            due_date DATE,
            counterparty TEXT,
            notes TEXT,
            status TEXT DEFAULT 'active' CHECK(status IN ('active','paid')),
            created_at DATE DEFAULT CURRENT_DATE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS emergency_fund_plan (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            target_months INTEGER NOT NULL DEFAULT 6,
            monthly_expenses_estimate INTEGER DEFAULT 0,
            current_saved INTEGER DEFAULT 0,
            updated_at DATE,
            goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_streaks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            current_streak INTEGER NOT NULL DEFAULT 0,
            longest_streak INTEGER NOT NULL DEFAULT 0,
            last_active_date DATE,
            streak_updated_at TIMESTAMP DEFAULT NOW()
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type TEXT NOT NULL DEFAULT 'tip'
                CHECK(type IN ('reminder','tip','milestone','alert','nudge')),
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            icon TEXT DEFAULT '&#x1F514;',
            read INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_tips (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            tips_sent INTEGER NOT NULL DEFAULT 0,
            last_tip_at DATE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS debt_payments (
            id           SERIAL PRIMARY KEY,
            debt_id      INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            amount       INTEGER NOT NULL,
            payment_date DATE    NOT NULL DEFAULT CURRENT_DATE,
            note         TEXT,
            created_at   TIMESTAMP DEFAULT NOW()
        )""")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — ADD COLUMN migrations  (IF NOT EXISTS → instant no-ops)
# ─────────────────────────────────────────────────────────────────────────────

def _add_columns():
    with get_db() as (conn, cursor):
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_complete INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS allow_overdraft INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code_expires_at TIMESTAMP")
        cursor.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS category TEXT")
        cursor.execute("ALTER TABLE recurring_items ADD COLUMN IF NOT EXISTS allow_overdraft INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE recurring_items ADD COLUMN IF NOT EXISTS last_posted_at DATE")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — ALTER COLUMN TYPE  (each in own transaction, skipped if already done)
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_col(table, column, target_type, using_expr):
    """Only run ALTER if the column isn't already the target type."""
    try:
        with get_db() as (conn, cursor):
            current = _col_type(cursor, table, column)
            if current and current != target_type.lower():
                cursor.execute("""
                    DO $$ BEGIN
                        ALTER TABLE {t} ALTER COLUMN {c} TYPE {ty} USING {u};
                    EXCEPTION WHEN others THEN NULL; END $$;
                """.format(t=table, c=column, ty=target_type, u=using_expr))
    except Exception:
        pass


def _run_type_migrations():
    _migrate_col("users", "created_at", "DATE",
        "CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}' THEN created_at::DATE ELSE NULL END")
    _migrate_col("users", "last_login", "DATE",
        "CASE WHEN last_login ~ '^\\d{4}-\\d{2}-\\d{2}' THEN last_login::DATE ELSE NULL END")
    _migrate_col("transactions", "created_at", "DATE",
        "CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}' THEN created_at::DATE ELSE CURRENT_DATE END")
    _migrate_col("expenses", "created_at", "DATE",
        "CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}' THEN created_at::DATE ELSE CURRENT_DATE END")
    _migrate_col("goals", "created_at", "DATE",
        "CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}' THEN created_at::DATE ELSE CURRENT_DATE END")
    _migrate_col("analytics_logins", "login_date", "DATE",
        "CASE WHEN login_date ~ '^\\d{4}-\\d{2}-\\d{2}' THEN login_date::DATE ELSE CURRENT_DATE END")
    _migrate_col("session_tokens", "created_at", "TIMESTAMP",
        "CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}' THEN created_at::TIMESTAMP ELSE NOW() END")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Back-fill  (no-op once all rows have category filled)
# ─────────────────────────────────────────────────────────────────────────────

def _backfill():
    try:
        with get_db() as (conn, cursor):
            cursor.execute("UPDATE expenses SET category = name WHERE category IS NULL")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Indexes  (each in own transaction, errors silently skipped)
# ─────────────────────────────────────────────────────────────────────────────

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_banks_user_id ON banks(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_bank_id ON transactions(bank_id)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)",
    "CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_expenses_bank_id ON expenses(bank_id)",
    "CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)",
    "CREATE INDEX IF NOT EXISTS idx_goals_user_id ON goals(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status)",
    "CREATE INDEX IF NOT EXISTS idx_goal_contributions_goal_id ON goal_contributions(goal_id)",
    "CREATE INDEX IF NOT EXISTS idx_goal_contributions_user_id ON goal_contributions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_analytics_logins_user_id ON analytics_logins(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_analytics_logins_login_date ON analytics_logins(login_date)",
    "CREATE INDEX IF NOT EXISTS idx_session_tokens_user_id ON session_tokens(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_session_tokens_created_at ON session_tokens(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_rate_limit_identifier ON rate_limit_log(identifier, action, attempted_at)",
    "CREATE INDEX IF NOT EXISTS idx_category_budgets_user_id ON category_budgets(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_recurring_items_user_id ON recurring_items(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_recurring_items_next_due ON recurring_items(next_due)",
    "CREATE INDEX IF NOT EXISTS idx_debts_user_id ON debts(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_debt_payments_debt_id ON debt_payments(debt_id)",
    "CREATE INDEX IF NOT EXISTS idx_debt_payments_user_id ON debt_payments(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(user_id, read)",
    "CREATE INDEX IF NOT EXISTS idx_user_streaks_user_id ON user_streaks(user_id)",
]

def _create_indexes():
    for stmt in _INDEXES:
        try:
            with get_db() as (conn, cursor):
                cursor.execute(stmt)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def create_tables():
    _create_core_tables()    # instant after first run
    _add_columns()           # instant after first run
    _run_type_migrations()   # skipped automatically once columns are correct type
    _backfill()              # no-op once all rows filled
    _create_indexes()        # instant after first run


create_tables()
