import sqlite3

DB_NAME = "budget_v2.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")  # Enforce foreign key constraints
    return conn

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password BLOB NOT NULL
    )
    """)

    # Income table (one per user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS income (
        user_id INTEGER PRIMARY KEY,
        amount INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Expense lists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expense_lists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Expenses
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        list_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        amount INTEGER NOT NULL,
        FOREIGN KEY(list_id) REFERENCES expense_lists(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    conn.close()



