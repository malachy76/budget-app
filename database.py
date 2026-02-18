import sqlite3

DB_NAME = "budget_simple.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def create_tables():
    conn = get_conn()
    c = conn.cursor()

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

    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        amount REAL,
        date TEXT
    )
    """)

    conn.commit()
    conn.close()
