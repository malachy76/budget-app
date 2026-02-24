import streamlit as st
st.set_page_config("💰 Budget App", page_icon="💰", layout="wide")

import sqlite3
import bcrypt
import random
import re
import pandas as pd
from datetime import datetime, timedelta

# ---------------- DATABASE ----------------
DB_NAME = "budget_app.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

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
        role TEXT DEFAULT 'user',
        monthly_spending_limit INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bank_name TEXT NOT NULL,
        account_name TEXT NOT NULL,
        account_number TEXT NOT NULL,
        balance INTEGER DEFAULT 0,
        min_balance_alert INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_id INTEGER NOT NULL,
        type TEXT CHECK(type IN ('credit','debit')),
        amount INTEGER NOT NULL,
        description TEXT,
        created_at TEXT,
        FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bank_id INTEGER,
        name TEXT NOT NULL,
        amount INTEGER NOT NULL,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        target_amount INTEGER NOT NULL,
        current_amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    conn.close()

create_tables()
conn = get_connection()
cursor = conn.cursor()

# ---------------- SESSION ----------------
for key in [
    "user_id","user_role","edit_exp_id","edit_bank_id",
    "show_goal_contribution","selected_goal"
]:
    if key not in st.session_state:
        st.session_state[key] = None

# ---------------- AUTH ----------------
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

def strong_password(password):
    return re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$", password)

def register_user(surname, other, email, username, password):
    if not strong_password(password):
        return None, "Password too weak."

    code = str(random.randint(100000, 999999))
    try:
        cursor.execute("""
            INSERT INTO users (surname, other_names, email, username, password, verification_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (surname, other, email, username, hash_password(password), code, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        return code, "User created"
    except sqlite3.IntegrityError as e:
        return None, str(e)

def login_user(username, password):
    cursor.execute("SELECT id, password, role, email_verified FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    if user:
        user_id, pw_hash, role, verified = user
        if verified == 0:
            st.warning("Email not verified.")
            return None
        if check_password(password, pw_hash):
            st.session_state.user_id = user_id
            st.session_state.user_role = role
            return user_id
    return None

# ---------------- LOGIN SCREEN ----------------
if not st.session_state.user_id:
    st.title("💰 Simple Budget App")

    # LOGIN
    login_username = st.text_input("Username", key="login_username")
    login_password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login", key="login_btn"):
        if login_user(login_username, login_password):
            st.success("Logged in")
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.divider()

    # REGISTER
    st.subheader("Register")
    s = st.text_input("Surname", key="reg_surname")
    o = st.text_input("Other Names", key="reg_other")
    e = st.text_input("Email", key="reg_email")
    u = st.text_input("Username", key="reg_username")
    p = st.text_input("Password", type="password", key="reg_password")

    if st.button("Register", key="register_btn"):
        code, msg = register_user(s, o, e, u, p)
        if code:
            st.success("Account created")
        else:
            st.error(msg)

    st.stop()

# ---------------- DASHBOARD ----------------
user_id = st.session_state.user_id
cursor.execute("SELECT surname, other_names FROM users WHERE id=?", (user_id,))
user = cursor.fetchone()
if not user:
    st.error("User not found")
    st.stop()

st.success(f"Welcome {user[0]} {user[1]} 👋")

# ---------------- ADD BANK ----------------
st.subheader("Add Bank")
bank_name = st.text_input("Bank Name")
account_name = st.text_input("Account Name")
account_number = st.text_input("Account Number")
opening_balance = st.number_input("Opening Balance", min_value=0)

if st.button("Add Bank"):
    cursor.execute("""
        INSERT INTO banks (user_id, bank_name, account_name, account_number, balance)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, bank_name, account_name, account_number[-4:], opening_balance))
    conn.commit()
    st.success("Bank added")
    st.experimental_rerun()

# ---------------- ADD EXPENSE ----------------
st.subheader("Add Expense")

cursor.execute("SELECT id, bank_name, account_number FROM banks WHERE user_id=?", (user_id,))
banks = cursor.fetchall()

if banks:
    bank_map = {f"{b[1]} (****{b[2]})": b[0] for b in banks}
    selected = st.selectbox("Select Bank", list(bank_map.keys()))
    name = st.text_input("Expense Name")
    amount = st.number_input("Amount", min_value=1)

    if st.button("Add Expense"):
        bank_id = bank_map[selected]
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO expenses (user_id, bank_id, name, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, bank_id, name, amount, date_now))

        cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (amount, bank_id))

        cursor.execute("""
            INSERT INTO transactions (bank_id, type, amount, description, created_at)
            VALUES (?, 'debit', ?, ?, ?)
        """, (bank_id, amount, f"EXPENSE::{name}", date_now))

        conn.commit()
        st.success("Expense added")
        st.experimental_rerun()

# ---------------- DELETE + EDIT EXPENSE ----------------
st.subheader("Expense List")

cursor.execute("""
    SELECT id, name, amount, bank_id, created_at
    FROM expenses
    WHERE user_id=?
    ORDER BY created_at DESC
""", (user_id,))
expenses = cursor.fetchall()

for exp in expenses:
    exp_id, name, amount, bank_id, created_at = exp
    col1, col2, col3 = st.columns([4,1,1])
    col1.write(f"{created_at} | {name} | ₦{amount:,}")

    if col2.button("Delete", key=f"del{exp_id}"):

        cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (amount, bank_id))

        cursor.execute("""
            DELETE FROM transactions
            WHERE bank_id=? AND type='debit' AND description=? 
        """, (bank_id, f"EXPENSE::{name}"))

        cursor.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
        conn.commit()
        st.success("Deleted")
        st.experimental_rerun()

    if col3.button("Edit", key=f"edit{exp_id}"):
        st.session_state.edit_exp_id = exp_id

if st.session_state.edit_exp_id:
    cursor.execute("SELECT name, amount, bank_id FROM expenses WHERE id=?", (st.session_state.edit_exp_id,))
    old = cursor.fetchone()
    if old:
        old_name, old_amount, old_bank = old
        new_name = st.text_input("New Name", value=old_name)
        new_amount = st.number_input("New Amount", min_value=1, value=old_amount)

        if st.button("Update Expense"):
            diff = new_amount - old_amount
            cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (diff, old_bank))

            cursor.execute("""
                UPDATE transactions
                SET amount=?, description=?
                WHERE bank_id=? AND description=?
            """, (new_amount, f"EXPENSE::{new_name}", old_bank, f"EXPENSE::{old_name}"))

            cursor.execute("""
                UPDATE expenses SET name=?, amount=?
                WHERE id=?
            """, (new_name, new_amount, st.session_state.edit_exp_id))

            conn.commit()
            st.session_state.edit_exp_id = None
            st.success("Updated")
            st.experimental_rerun()

# ---------------- LOGOUT ----------------
if st.button("Logout"):
    st.session_state.user_id = None
    st.experimental_rerun()

