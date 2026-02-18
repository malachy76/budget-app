import sqlite3

DB_NAME = "budget_v4.db"

def get_conn():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

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
        password BLOB,
        verified INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS verification (
        user_id INTEGER,
        code TEXT
    )
    """)

    conn.commit()
    conn.close()
