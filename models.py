# models.py — all CREATE TABLE definitions, migrations, and indexes
from db import get_db

def create_tables():
    with get_db() as (conn, cursor):

        # ── users ────────────────────────────────────────────────────────────
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
        )
        """)

        # ── banks ─────────────────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS banks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            bank_name TEXT NOT NULL,
            account_name TEXT NOT NULL,
            account_number TEXT NOT NULL,
            balance INTEGER DEFAULT 0,
            min_balance_alert INTEGER DEFAULT 0
        )
        """)

        # ── transactions ──────────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            bank_id INTEGER NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
            type TEXT CHECK(type IN ('credit','debit')),
            amount INTEGER NOT NULL,
            description TEXT,
            created_at DATE DEFAULT CURRENT_DATE
        )
        """)

        # ── expenses ──────────────────────────────────────────────────────────
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
        )
        """)

        # ── goals ─────────────────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            target_amount INTEGER NOT NULL,
            current_amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at DATE DEFAULT CURRENT_DATE
        )
        """)

        # ── goal_contributions ────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS goal_contributions (
            id SERIAL PRIMARY KEY,
            goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            bank_id INTEGER NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL,
            contributed_at DATE DEFAULT CURRENT_DATE
        )
        """)

        # ── analytics_logins ──────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_logins (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            login_date DATE NOT NULL DEFAULT CURRENT_DATE
        )
        """)

        # ── session_tokens ────────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """)

        # ── rate_limit_log ────────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limit_log (
            id SERIAL PRIMARY KEY,
            identifier TEXT NOT NULL,
            action TEXT NOT NULL,
            attempted_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """)

        # ── category_budgets ─────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_budgets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            monthly_limit INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, category)
        )
        """)

        # ── recurring_items ──────────────────────────────────────────────────
        # type: 'income' or 'expense'
        # frequency: 'daily', 'weekly', 'monthly', 'yearly'
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
            active INTEGER DEFAULT 1,
            created_at DATE DEFAULT CURRENT_DATE
        )
        """)

        # ── debts ─────────────────────────────────────────────────────────────
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
        )
        """)

        # ── emergency_fund_plan ───────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS emergency_fund_plan (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            target_months INTEGER NOT NULL DEFAULT 6,
            monthly_expenses_estimate INTEGER DEFAULT 0,
            current_saved INTEGER DEFAULT 0,
            goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
            updated_at DATE DEFAULT CURRENT_DATE
        )
        """)

        # ── category_budgets ──────────────────────────────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_budgets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            monthly_limit INTEGER NOT NULL DEFAULT 0,
            UNIQUE (user_id, category)
        )
        """)

        # ── user_streaks ──────────────────────────────────────────────────────
        # Tracks consecutive daily login/tracking streaks per user.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_streaks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            current_streak INTEGER NOT NULL DEFAULT 0,
            longest_streak INTEGER NOT NULL DEFAULT 0,
            last_active_date DATE,
            streak_updated_at TIMESTAMP DEFAULT NOW()
        )
        """)

        # ── notifications ─────────────────────────────────────────────────────
        # In-app notification inbox. type: 'reminder'|'tip'|'milestone'|'alert'|'nudge'
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
        )
        """)

        # ── onboarding_tips ───────────────────────────────────────────────────
        # Tracks which tip sequence a new user is on (tip 1..N shown progressively).
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_tips (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            tips_sent INTEGER NOT NULL DEFAULT 0,
            last_tip_at DATE
        )
        """)

        # ── Migrate existing TEXT columns to proper date types ────────────────
        # These are safe to run repeatedly — IF NOT EXISTS / type checks protect them.

        # users
        cursor.execute("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS onboarding_complete INTEGER DEFAULT 0
        """)
        cursor.execute("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS allow_overdraft INTEGER DEFAULT 0
        """)
        cursor.execute("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS verification_code_expires_at TIMESTAMP
        """)
        cursor.execute("""
            DO $$ BEGIN
                ALTER TABLE users ALTER COLUMN created_at TYPE DATE
                    USING CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}'
                               THEN created_at::DATE ELSE NULL END;
            EXCEPTION WHEN others THEN NULL; END $$;
        """)
        cursor.execute("""
            DO $$ BEGIN
                ALTER TABLE users ALTER COLUMN last_login TYPE DATE
                    USING CASE WHEN last_login ~ '^\\d{4}-\\d{2}-\\d{2}'
                               THEN last_login::DATE ELSE NULL END;
            EXCEPTION WHEN others THEN NULL; END $$;
        """)

        # transactions
        cursor.execute("""
            DO $$ BEGIN
                ALTER TABLE transactions ALTER COLUMN created_at TYPE DATE
                    USING CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}'
                               THEN created_at::DATE ELSE CURRENT_DATE END;
            EXCEPTION WHEN others THEN NULL; END $$;
        """)

        # expenses — also add category column
        cursor.execute("""
            ALTER TABLE expenses
                ADD COLUMN IF NOT EXISTS category TEXT
        """)
        cursor.execute("""
            DO $$ BEGIN
                ALTER TABLE expenses ALTER COLUMN created_at TYPE DATE
                    USING CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}'
                               THEN created_at::DATE ELSE CURRENT_DATE END;
            EXCEPTION WHEN others THEN NULL; END $$;
        """)
        # Back-fill category from name for existing rows
        cursor.execute("""
            UPDATE expenses SET category = name WHERE category IS NULL
        """)

        # goals
        cursor.execute("""
            DO $$ BEGIN
                ALTER TABLE goals ALTER COLUMN created_at TYPE DATE
                    USING CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}'
                               THEN created_at::DATE ELSE CURRENT_DATE END;
            EXCEPTION WHEN others THEN NULL; END $$;
        """)

        # analytics_logins
        cursor.execute("""
            DO $$ BEGIN
                ALTER TABLE analytics_logins ALTER COLUMN login_date TYPE DATE
                    USING CASE WHEN login_date ~ '^\\d{4}-\\d{2}-\\d{2}'
                               THEN login_date::DATE ELSE CURRENT_DATE END;
            EXCEPTION WHEN others THEN NULL; END $$;
        """)

        # session_tokens
        cursor.execute("""
            DO $$ BEGIN
                ALTER TABLE session_tokens ALTER COLUMN created_at TYPE TIMESTAMP
                    USING CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}'
                               THEN created_at::TIMESTAMP ELSE NOW() END;
            EXCEPTION WHEN others THEN NULL; END $$;
        """)

        # ── Indexes for fast queries ──────────────────────────────────────────
        index_stmts = [
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
            "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(user_id, read)",
            "CREATE INDEX IF NOT EXISTS idx_user_streaks_user_id ON user_streaks(user_id)",
        ]
        for stmt in index_stmts:
            cursor.execute(stmt)

create_tables()
