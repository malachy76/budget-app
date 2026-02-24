import streamlit as st
st.set_page_config(page_title="💰 Budget App", page_icon="💰", layout="wide")

import sqlite3
import bcrypt
import random
import re
import pandas as pd
from datetime import datetime, timedelta

# ================= DATABASE =================
DB_NAME = "budget_app_v2.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_tables():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        surname TEXT,
        other_names TEXT,
        email TEXT UNIQUE,
        username TEXT UNIQUE,
        password BLOB,
        email_verified INTEGER DEFAULT 1,
        verification_code TEXT,
        role TEXT DEFAULT 'user',
        monthly_spending_limit INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        bank_name TEXT,
        account_name TEXT,
        account_number TEXT,
        balance INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_id INTEGER,
        type TEXT,
        amount INTEGER,
        description TEXT,
        created_at TEXT,
        FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        bank_id INTEGER,
        name TEXT,
        amount INTEGER,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    conn.close()

create_tables()
conn = get_connection()
cursor = conn.cursor()

# ================= SESSION =================
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "edit_exp_id" not in st.session_state:
    st.session_state.edit_exp_id = None

# ================= AUTH =================
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

def strong_password(password):
    return re.match(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d).{8,}$", password)

def register_user(s, o, e, u, p):
    if not strong_password(p):
        return None, "Password must contain uppercase, lowercase and number."

    try:
        cursor.execute("""
            INSERT INTO users (surname, other_names, email, username, password, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (s, o, e, u, hash_password(p), datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        return True, "Account created"
    except sqlite3.IntegrityError as err:
        return None, str(err)

def login_user(u, p):
    cursor.execute("SELECT id, password FROM users WHERE username=?", (u,))
    user = cursor.fetchone()
    if user:
        if check_password(p, user[1]):
            st.session_state.user_id = user[0]
            return True
    return False

# ================= LOGIN PAGE =================
if not st.session_state.user_id:

    st.title("💰 Simple Budget App")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Login")
        login_user_input = st.text_input("Username", key="login_user")
        login_pass_input = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login", key="login_btn"):
            if login_user(login_user_input, login_pass_input):
                st.success("Login successful")
                st.rerun()
            else:
                st.error("Invalid credentials")

    with col2:
        st.subheader("Register")
        s = st.text_input("Surname", key="reg_s")
        o = st.text_input("Other Names", key="reg_o")
        e = st.text_input("Email", key="reg_e")
        u = st.text_input("Username", key="reg_u")
        p = st.text_input("Password", type="password", key="reg_p")

        if st.button("Register", key="register_btn"):
            ok, msg = register_user(s, o, e, u, p)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    st.stop()

# ================= DASHBOARD =================
st.success("Welcome to your dashboard 👋")

user_id = st.session_state.user_id

# ===== ADD BANK =====
st.subheader("Add Bank Account")

bank_name = st.text_input("Bank Name", key="bank_name_input")
acc_name = st.text_input("Account Name", key="acc_name_input")
acc_number = st.text_input("Account Number", key="acc_number_input")
opening_balance = st.number_input("Opening Balance", min_value=0, key="open_bal_input")

if st.button("Add Bank", key="add_bank_btn"):
    cursor.execute("""
        INSERT INTO banks (user_id, bank_name, account_name, account_number, balance)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, bank_name, acc_name, acc_number[-4:], opening_balance))
    conn.commit()
    st.success("Bank added")
    st.rerun()

# ===== LIST BANKS =====
cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
banks = cursor.fetchall()

if banks:
    st.subheader("Your Banks")
    for b in banks:
        st.write(f"{b[1]} (****{b[2]}) - ₦{b[3]:,}")

# ===== ADD EXPENSE =====
st.subheader("Add Expense")

if banks:
    bank_dict = {f"{b[1]} (****{b[2]})": b[0] for b in banks}
    selected_bank = st.selectbox("Select Bank", list(bank_dict.keys()), key="expense_bank")
    exp_name = st.text_input("Expense Name", key="expense_name_input")
    exp_amount = st.number_input("Amount", min_value=1, key="expense_amount_input")

    if st.button("Add Expense", key="add_expense_btn"):
        bank_id = bank_dict[selected_bank]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO expenses (user_id, bank_id, name, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, bank_id, exp_name, exp_amount, now))

        cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (exp_amount, bank_id))

        cursor.execute("""
            INSERT INTO transactions (bank_id, type, amount, description, created_at)
            VALUES (?, 'debit', ?, ?, ?)
        """, (bank_id, exp_amount, f"EXPENSE::{exp_name}", now))

        conn.commit()
        st.success("Expense added")
        st.rerun()

# ===== EXPENSE LIST =====
cursor.execute("""
    SELECT id, name, amount, bank_id, created_at
    FROM expenses WHERE user_id=?
    ORDER BY created_at DESC
""", (user_id,))
expenses = cursor.fetchall()

if expenses:
    st.subheader("Expense History")
    for exp in expenses:
        exp_id, name, amount, bank_id, date = exp
        col1, col2 = st.columns([5,1])
        col1.write(f"{date} | {name} | ₦{amount:,}")

        if col2.button("Delete", key=f"delete_{exp_id}"):
            cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (amount, bank_id))
            cursor.execute("DELETE FROM transactions WHERE description=?", (f"EXPENSE::{name}",))
            cursor.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
            conn.commit()
            st.success("Deleted")
            st.rerun()

# ===== LOGOUT =====
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.rerun()
