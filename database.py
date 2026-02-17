import sqlite3

def get_connection():
    return sqlite3.connect("budget.db", check_same_thread=False)

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password BLOB
    )
    """)

    # Income
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS income (
        user_id INTEGER,
        amount INTEGER
    )
    """)

    # Expense lists (categories)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expense_lists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT
    )
    """)

    # Expenses
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


