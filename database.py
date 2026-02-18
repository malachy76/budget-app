import sqlite3

DB_NAME = "budget_final.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def create_tables():
    conn = get_conn()
    c = conn.cursor()

    # USERS
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        surname TEXT,
        other_names TEXT,
        email TEXT UNIQUE,
        username TEXT UNIQUE,
        password BLOB
    )
    """)

    # BANKS
    c.execute("""
    CREATE TABLE IF NOT EXISTS banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        bank_name TEXT
    )
    """)

    # TRANSACTIONS
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_id INTEGER,
        remark TEXT,
        amount REAL,
        date TEXT
    )
    """)

    # EXPENSES
    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        amount REAL,
        date TEXT
    )
    """)

    # SAVINGS GOALS
    c.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        target REAL
    )
    """)

    conn.commit()
    conn.close()
