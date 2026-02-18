import sqlite3

DB_NAME = "budget_simple.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

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

    # KYC TABLE
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kyc (
        user_id INTEGER PRIMARY KEY,
        bvn TEXT,
        nin TEXT,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # EXPENSES
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        amount INTEGER,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()
