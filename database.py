import sqlite3

DB_NAME = "budget_app.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # USERS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        surname TEXT NOT NULL,
        other_names TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password BLOB NOT NULL,
        email_verified INTEGER DEFAULT 0,
        verification_code TEXT,
        created_at TEXT
    )
    """)

    # BANK ACCOUNTS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bank_name TEXT NOT NULL,
        account_name TEXT NOT NULL,
        account_number TEXT NOT NULL,
        balance INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # BANK TRANSACTIONS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_id INTEGER NOT NULL,
        type TEXT CHECK(type IN ('credit','debit')),
        amount INTEGER NOT NULL,
        description TEXT,
        created_at TEXT,
        FOREIGN KEY(bank_id) REFERENCES banks(id)
    )
    """)

    # EXPENSES (AUTO-LINKED TO BANKS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bank_id INTEGER,
        name TEXT NOT NULL,
        amount INTEGER NOT NULL,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(bank_id) REFERENCES banks(id)
    )
    """)

    conn.commit()
    conn.close()

