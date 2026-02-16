import sqlite3

def get_connection():
    return sqlite3.connect("budget.db", check_same_thread=False)

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    # Income table (linked to user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS income (
        user_id INTEGER,
        amount INTEGER
    )
    """)

    # Expenses table (linked to user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        user_id INTEGER,
        name TEXT,
        amount INTEGER
    )
    """)

    conn.commit()
    conn.close()
