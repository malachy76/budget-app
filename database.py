  import sqlite3

DB_NAME = "budget_v2.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password BLOB
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS income (
        user_id INTEGER,
        amount INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expense_lists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        list_id INTEGER,
        name TEXT,
        amount INTEGER
    )
    """)

    conn.commit()
    conn.close()
