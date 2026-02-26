import streamlit as st
st.set_page_config(page_title="Budgeting Smart", page_icon="💰", layout="wide")
import sqlite3
import bcrypt
import random
import re
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
import pandas as pd

from csv_import import csv_import_page
# ---------------- DATABASE ----------------
DB_NAME = "budgeting_Smsrt.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # USERS table with role column
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

    # BANK ACCOUNTS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bank_name TEXT NOT NULL,
        account_name TEXT NOT NULL,
        account_number TEXT NOT NULL,
        balance INTEGER DEFAULT 0,
        min_balance_alert INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # TRANSACTIONS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_id INTEGER NOT NULL,
        type TEXT CHECK(type IN ('credit','debit')),
        amount INTEGER NOT NULL,
        description TEXT,
        created_at TEXT,
        FOREIGN KEY(bank_id) REFERENCES banks(id)
    )
    """)

    # EXPENSES
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bank_id INTEGER,
        name TEXT NOT NULL,
        amount INTEGER NOT NULL,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(bank_id) REFERENCES banks(id)
    )
    """)

    # SAVINGS GOALS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        target_amount INTEGER NOT NULL,
        current_amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()

create_tables()
conn = get_connection()
cursor = conn.cursor()

# ---------------- SESSION ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "show_forgot_password" not in st.session_state:
    st.session_state.show_forgot_password = False
if "show_reset_form" not in st.session_state:
    st.session_state.show_reset_form = False
if "reset_email" not in st.session_state:
    st.session_state.reset_email = ""
if "edit_exp_id" not in st.session_state:
    st.session_state.edit_exp_id = None
if "edit_bank_id" not in st.session_state:
    st.session_state.edit_bank_id = None

# ---------------- AUTH FUNCTIONS ----------------
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

def register_user(surname, other, email, username, password):
    code = str(random.randint(100000, 999999))
    try:
        hashed_pw = hash_password(password)
        cursor.execute("""
            INSERT INTO users (surname, other_names, email, username, password, verification_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (surname, other, email, username, hashed_pw, code, datetime.now().strftime("%Y-%m-%d")))
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
            st.warning("Email not verified. Please verify before logging in.")
            return None
        if check_password(password, pw_hash):
            st.session_state.user_id = user_id
            st.session_state.user_role = role
            return user_id
    return None

def send_verification_email(email, code):
    try:
        msg = EmailMessage()
        msg["Subject"] = "Verify your Budget Smart account"
        msg["From"] = st.secrets["EMAIL_SENDER"]
        msg["To"] = email
        msg.set_content(f"Your verification code is: {code}")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(st.secrets["EMAIL_SENDER"], st.secrets["EMAIL_APP_PASSWORD"])
            server.send_message(msg)
 
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

def request_password_reset(email):
    try:
        code = str(random.randint(100000, 999999))
        cursor.execute(
            "UPDATE users SET verification_code=? WHERE email=?",
            (code, email)
        )
        if cursor.rowcount == 0:
            return False, "Email not found"

        conn.commit()
        return send_verification_email(email, code)
    except Exception as e:
        return False, str(e)

def reset_password(email, code, new_password):
    try:
        cursor.execute(
            "SELECT id FROM users WHERE email=? AND verification_code=?",
            (email, code)
        )
        user = cursor.fetchone()
        if not user:
            return False, "Invalid reset code"

        hashed_pw = hash_password(new_password)
        cursor.execute("""
            UPDATE users
            SET password=?, verification_code=NULL
            WHERE email=?
        """, (hashed_pw, email))
        conn.commit()
        return True, "Password reset successful"
    except Exception as e:
        return False, str(e)

def resend_verification(email):
    try:
        code = str(random.randint(100000, 999999))
        cursor.execute(
            "UPDATE users SET verification_code=? WHERE email=?",
            (code, email)
        )
        if cursor.rowcount == 0:
            return False, "Email not found"

        conn.commit()
        return send_verification_email(email, code)
    except Exception as e:
        return False, str(e)

def reset_password(email, code, new_password):
    try:
        cursor.execute(
            "SELECT id FROM users WHERE email=? AND verification_code=?",
            (email, code)
        )

        user = cursor.fetchone()

        if not user:
            return False, "Invalid reset code"

        hashed_pw = hash_password(new_password)

        cursor.execute(
            "UPDATE users SET password=?, verification_code=NULL WHERE email=?",
            (hashed_pw, email)
        )

        conn.commit()

        return True, "Password reset successful"

    except Exception as e:
        return False, str(e)


def resend_verification(email):
    try:
        code = str(random.randint(100000, 999999))

        cursor.execute(
            "UPDATE users SET verification_code=? WHERE email=?",
            (code, email)
        )

        if cursor.rowcount == 0:
            return False, "Email not found"

        conn.commit()

        return send_verification_email(email, code)

    except Exception as e:
        return False, str(e)

def change_password(user_id, current_pw, new_pw):
    cursor.execute("SELECT password FROM users WHERE id=?", (user_id,))
    hashed = cursor.fetchone()[0]
    if check_password(current_pw, hashed):
        cursor.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_pw), user_id))
        conn.commit()
        return True, "Password updated"
    else:
        return False, "Current password incorrect"

# ---------------- UI ----------------

st.title("Budget Right")

# ================= AUTH =================
if st.session_state.user_id is None:
    tabs = st.tabs(["🔐 Login", "📝 Register", "📧 Verify Email"])

    # ---------- LOGIN ----------
    with tabs[0]:
        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input("Password", type="password", key="login_password")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Login", key="login_btn"):
                user_id = login_user(login_username, login_password)
                if user_id:
                    st.success("Logged in!")
                    st.rerun()
                else:
                    st.error("Invalid credentials or email not verified")
        with col2:
            if st.button("Forgot Password?", key="forgot_btn"):
                st.session_state.show_forgot_password = True

        # Forgot password overlay
        if st.session_state.show_forgot_password:
            with st.expander("Reset Password", expanded=True):
                email_input = st.text_input("Enter your email", key="reset_email_input")
                if st.button("Send Reset Code", key="send_reset_btn"):
                    if email_input:
                        success, msg = request_password_reset(email_input)
                        if success:
                            st.success(msg)
                            st.session_state.show_forgot_password = False
                            st.session_state.show_reset_form = True
                            st.session_state.reset_email = email_input
                        else:
                            st.error(msg)
                    else:
                        st.warning("Enter your email.")
                if st.button("Cancel", key="cancel_reset_btn"):
                    st.session_state.show_forgot_password = False
                    st.rerun()

        # Show reset code form if requested
        if st.session_state.show_reset_form:
            with st.expander("Enter Reset Code", expanded=True):
                reset_code = st.text_input("Reset code", key="reset_code")
                new_pass = st.text_input("New password", type="password", key="new_pass")
                confirm_pass = st.text_input("Confirm new password", type="password", key="confirm_pass")
                if st.button("Reset Password", key="do_reset_btn"):
                    if reset_code and new_pass and confirm_pass:
                        if new_pass == confirm_pass:
                            success, msg = reset_password(st.session_state.reset_email, reset_code, new_pass)
                            if success:
                                st.success(msg)
                                st.session_state.show_reset_form = False
                                st.session_state.reset_email = ""
                            else:
                                st.error(msg)
                        else:
                            st.error("Passwords do not match.")
                    else:
                        st.warning("All fields required.")
                if st.button("Cancel Reset", key="cancel_reset_form"):
                    st.session_state.show_reset_form = False
                    st.session_state.reset_email = ""
                    st.st.rerun()

    # ---------- REGISTER ----------
    with tabs[1]:
        reg_surname = st.text_input("Surname", key="reg_surname")
        reg_other = st.text_input("Other Names", key="reg_other")
        reg_email = st.text_input("Email", key="reg_email")
        reg_username = st.text_input("Username", key="reg_username")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        st.caption("Password must be at least 8 characters, include uppercase, lowercase, digit, and special character.")
        if st.button("Register", key="register_btn"):
            if not all([reg_surname, reg_other, reg_email, reg_username, reg_password]):
                st.error("All fields required")
            else:
                code, msg = register_user(reg_surname, reg_other, reg_email, reg_username, reg_password)
                if code:
                    success, email_msg = send_verification_email(reg_email, code)
                    if success:
                        st.success("Account created. Check email to verify.")
                    else:
                        st.error(f"Account created but email failed: {email_msg}")
                else:
                    st.error(msg)

    # ---------- VERIFY EMAIL ----------
    with tabs[2]:
        verify_email = st.text_input("Registered Email", key="verify_email")
        verify_code = st.text_input("Verification Code", key="verify_code")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Verify Email", key="verify_btn"):
                cursor.execute("""
                SELECT id FROM users
                WHERE email=? AND verification_code=?
                """, (verify_email, verify_code))
                user = cursor.fetchone()
                if user:
                    cursor.execute("""
                    UPDATE users
                    SET email_verified=1, verification_code=NULL
                    WHERE id=?
                    """, (user[0],))
                    conn.commit()
                    st.success("✅ Email verified. You can now log in.")
                else:
                    st.error("Invalid email or code.")
        with col2:
            if st.button("Resend Code", key="resend_btn"):
                if verify_email:
                    success, msg = resend_verification(verify_email)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("Enter your email first.")
    st.stop()  # Stop here if not logged in

# ---------------- DASHBOARD ----------------
user_id = st.session_state.user_id
cursor.execute("SELECT surname, other_names, role FROM users WHERE id=?", (user_id,))
user = cursor.fetchone()
st.session_state.user_role = user[2]
st.success(f"Welcome {user[0]} {user[1]} 👋")

# ---------- ADMIN PANEL ----------
if st.session_state.user_role == "admin":
    st.subheader("🛠 Admin Panel")
    tabs_admin = st.tabs(["Users", "Banks", "Expenses & Income"])
    with tabs_admin[0]:
        st.write("All Users:")
        cursor.execute("SELECT id, surname, other_names, username, email, role FROM users")
        all_users = cursor.fetchall()
        for u in all_users:
            st.write(f"{u[1]} {u[2]} | {u[3]} | {u[4]} | Role: {u[5]}")
    with tabs_admin[1]:
        st.write("All Bank Accounts:")
        cursor.execute("SELECT b.id, u.username, bank_name, account_name, account_number, balance FROM banks b JOIN users u ON b.user_id = u.id")
        for b in cursor.fetchall():
            st.write(b)
    with tabs_admin[2]:
        st.info("You can paste your existing Expenses & Income code here for admin view.")

# ---------- USER DASHBOARD ----------
# Place your full user dashboard code here (banks, expenses, income, goals, transactions, charts)
# This is where you keep all your previous dashboard code as is for normal users

# ---------------- USER DASHBOARD ----------------
st.markdown("## 💳 My Dashboard")

# ---------- DASHBOARD SUMMARY CARDS ----------
cursor.execute("SELECT SUM(balance) FROM banks WHERE user_id=?", (user_id,))
total_balance = cursor.fetchone()[0] or 0

current_month = datetime.now().strftime("%Y-%m")
cursor.execute("""
    SELECT SUM(t.amount)
    FROM transactions t
    JOIN banks b ON t.bank_id = b.id
    WHERE b.user_id = ? AND t.type = 'debit' AND strftime('%Y-%m', t.created_at) = ?
""", (user_id, current_month))
expenses_this_month = cursor.fetchone()[0] or 0

cursor.execute("SELECT COUNT(*) FROM banks WHERE user_id=?", (user_id,))
num_banks = cursor.fetchone()[0] or 0

cursor.execute("""
    SELECT SUM(CASE WHEN type='credit' THEN amount ELSE -amount END)
    FROM transactions t
    JOIN banks b ON t.bank_id = b.id
    WHERE b.user_id = ?
""", (user_id,))
net_savings = cursor.fetchone()[0] or 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 Total Balance", f"₦{total_balance:,.0f}")
with col2:
    st.metric("📉 Expenses This Month", f"₦{expenses_this_month:,.0f}")
with col3:
    st.metric("🏦 Bank Accounts", num_banks)
with col4:
    st.metric("🎯 Net Savings", f"₦{net_savings:,.0f}")

st.divider()

# ---------- ADD BANK ----------
st.subheader("🏦 Add Bank Account")
bank_name = st.text_input("Bank Name", key="bank_name")
account_name = st.text_input("Account Name", key="acct_name")
account_number = st.text_input("Account Number (last 4 digits)", key="acct_num")
opening_balance = st.number_input("Opening Balance (₦)", min_value=0, key="open_bal")
min_alert = st.number_input("Alert me if balance falls below (₦)", min_value=0, value=0, key="min_alert")
if st.button("Add Bank", key="add_bank_btn"):
    if bank_name and account_name and account_number:
        cursor.execute("""
        INSERT INTO banks (user_id, bank_name, account_name, account_number, balance, min_balance_alert)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, bank_name, account_name, account_number[-4:], opening_balance, min_alert))
        conn.commit()
        st.success("Bank added")
        st.st.rerun()
    else:
        st.warning("Please fill all fields.")

# ---------- MANAGE BANKS ----------
st.subheader("🏦 Manage Bank Accounts")
cursor.execute("SELECT id, bank_name, account_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
banks_manage = cursor.fetchall()

if banks_manage:
    for bank in banks_manage:
        bank_id, name, acc_name, acc_num, balance = bank
        col1, col2, col3 = st.columns([4,1,1])
        with col1:
            st.markdown(f"**{name}** (****{acc_num}) — ₦{balance:,.0f}")
        with col2:
            if st.button("✏️", key=f"edit_bank_{bank_id}"):
                st.session_state.edit_bank_id = bank_id
        with col3:
            if st.button("🗑", key=f"delete_bank_{bank_id}"):
                cursor.execute("DELETE FROM banks WHERE id=?", (bank_id,))
                conn.commit()
                st.success("Bank deleted.")
                st.st.rerun()

    # -------- EDIT BANK --------
    if st.session_state.get("edit_bank_id"):
        edit_id = st.session_state.edit_bank_id
        cursor.execute("SELECT bank_name, account_name, account_number FROM banks WHERE id=?", (edit_id,))
        bank = cursor.fetchone()
        if bank:
            old_name, old_acc_name, old_acc_num = bank
            st.markdown("### ✏️ Edit Bank")
            new_name = st.text_input("Bank Name", value=old_name)
            new_acc_name = st.text_input("Account Name", value=old_acc_name)
            new_acc_num = st.text_input("Account Number", value=old_acc_num)
            if st.button("Update Bank"):
                cursor.execute("""
                    UPDATE banks SET bank_name=?, account_name=?, account_number=?
                    WHERE id=?
                """, (new_name, new_acc_name, new_acc_num, edit_id))
                conn.commit()
                st.success("Bank updated.")
                st.session_state.edit_bank_id = None
                st.st.rerun()
else:
    st.info("No bank accounts yet.")

# ---------- ADD EXPENSE ----------
st.subheader("➕ Add Expense")
expense_name = st.text_input("Expense Name", key="exp_name")
expense_amount = st.number_input("Amount (₦)", min_value=1, key="exp_amt")
cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
banks = cursor.fetchall()
if banks:
    bank_map = {f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0] for b in banks}
    selected_bank = st.selectbox("Pay From Bank", list(bank_map.keys()), key="bank_select")
    if st.button("Add Expense", key="add_expense_btn"):
        if expense_name and expense_amount > 0:
            bank_id = bank_map[selected_bank]
            cursor.execute("""
                INSERT INTO expenses (user_id, bank_id, name, amount, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, bank_id, expense_name, expense_amount, datetime.now().strftime("%Y-%m-%d")))
            cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (expense_amount, bank_id))
            cursor.execute("""
                INSERT INTO transactions (bank_id, type, amount, description, created_at)
                VALUES (?, 'debit', ?, ?, ?)
            """, (bank_id, expense_amount, f"Expense: {expense_name}", datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success("Expense added & bank debited")
            st.st.rerun()
        else:
            st.warning("Please enter a name and amount.")
else:
    st.info("Add a bank account first")

# ---------- EXPENSE SUMMARY (EDIT & DELETE) ----------
st.subheader("📋 Expense Summary")
cursor.execute("""
    SELECT e.id, e.created_at, e.name, e.amount, e.bank_id, b.bank_name, b.account_number
    FROM expenses e JOIN banks b ON e.bank_id = b.id
    WHERE e.user_id = ? ORDER BY e.created_at DESC
""", (user_id,))
expenses_data = cursor.fetchall()

if expenses_data:
    for exp in expenses_data:
        exp_id, date, name, amount, bank_id, bank_name, acc_num = exp
        col1, col2, col3, col4, col5, col6 = st.columns([2,2,2,2,1,1])
        col1.write(date)
        col2.write(name)
        col3.write(f"₦{amount:,.0f}")
        col4.write(f"{bank_name} (****{acc_num})")
        if col5.button("✏️", key=f"edit_exp_{exp_id}"):
            st.session_state.edit_exp_id = exp_id
        if col6.button("🗑", key=f"delete_exp_{exp_id}"):
            cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (amount, bank_id))
            cursor.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
            conn.commit()
            st.success("Expense deleted & bank refunded")
            st.st.rerun()

    # -------- EDIT EXPENSE --------
    if st.session_state.get("edit_exp_id"):
        edit_id = st.session_state.edit_exp_id
        cursor.execute("SELECT name, amount, bank_id FROM expenses WHERE id=?", (edit_id,))
        exp = cursor.fetchone()
        if exp:
            old_name, old_amount, old_bank_id = exp
            st.markdown("### ✏️ Edit Expense")
            new_name = st.text_input("Expense Name", value=old_name)
            new_amount = st.number_input("Amount (₦)", min_value=1, value=old_amount)
            if st.button("Update Expense"):
                diff = new_amount - old_amount
                cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (diff, old_bank_id))
                cursor.execute("UPDATE expenses SET name=?, amount=? WHERE id=?", (new_name, new_amount, edit_id))
                conn.commit()
                st.success("Expense updated")
                st.session_state.edit_exp_id = None
                st.st.rerun()

# ---------- ADD INCOME ----------
st.subheader("💰 Add Income")
income_source = st.text_input("Income Source", key="income_source")
income_amount = st.number_input("Amount (₦)", min_value=1, key="income_amt")
if banks:
    bank_map_income = {f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0] for b in banks}
    selected_bank_income = st.selectbox("Deposit To Bank", list(bank_map_income.keys()), key="bank_income_select")
    if st.button("Add Income", key="add_income_btn"):
        if income_source and income_amount > 0:
            bank_id = bank_map_income[selected_bank_income]
            cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (income_amount, bank_id))
            cursor.execute("""
                INSERT INTO transactions (bank_id, type, amount, description, created_at)
                VALUES (?, 'credit', ?, ?, ?)
            """, (bank_id, income_amount, f"Income: {income_source}", datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success(f"Income of ₦{income_amount:,} added")
            st.st.rerun()
else:
    st.info("You need at least one bank account to add income")

# ---------- TRANSFER BETWEEN BANKS ----------
st.subheader("💸 Transfer Between Banks")
if len(banks) >= 2:
    bank_map_transfer = {f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0] for b in banks}
    from_bank = st.selectbox("From Bank", list(bank_map_transfer.keys()), key="from_bank")
    to_bank = st.selectbox("To Bank", list(bank_map_transfer.keys()), key="to_bank")
    transfer_amount = st.number_input("Amount to Transfer (₦)", min_value=1, key="transfer_amt")
    if st.button("Transfer", key="transfer_btn"):
        if from_bank == to_bank:
            st.warning("Cannot transfer to the same bank")
        else:
            from_id = bank_map_transfer[from_bank]
            to_id = bank_map_transfer[to_bank]
            cursor.execute("SELECT balance FROM banks WHERE id=?", (from_id,))
            from_balance = cursor.fetchone()[0]
            if transfer_amount > from_balance:
                st.error("Insufficient funds")
            else:
                cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (transfer_amount, from_id))
                cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (transfer_amount, to_id))
                cursor.execute("""
                    INSERT INTO transactions (bank_id, type, amount, description, created_at)
                    VALUES (?, 'debit', ?, ?, ?)
                """, (from_id, transfer_amount, f"Transfer to bank {to_id}", datetime.now().strftime("%Y-%m-%d")))
                cursor.execute("""
                    INSERT INTO transactions (bank_id, type, amount, description, created_at)
                    VALUES (?, 'credit', ?, ?, ?)
                """, (to_id, transfer_amount, f"Transfer from bank {from_id}", datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.success("Transfer completed")
                st.st.rerun()
else:
    st.info("Add at least two bank accounts to enable transfers")


# ---------- SAVINGS GOALS ----------
st.subheader("🎯 Savings Goals")

# Display existing goals
cursor.execute("""
    SELECT id, name, target_amount, current_amount, status
    FROM goals
    WHERE user_id=?
    ORDER BY status, created_at DESC
""", (user_id,))
goals = cursor.fetchall()

if goals:
    for goal in goals:
        goal_id, name, target, current, status = goal
        progress = (current / target) * 100 if target > 0 else 0
        col1, col2, col3, col4 = st.columns([3,1,1,1])
        with col1:
            st.markdown(f"**{name}**")
            st.progress(min(progress/100, 1.0), text=f"₦{current:,.0f} / ₦{target:,.0f} ({progress:.1f}%)")
        with col2:
            st.markdown(f"Status: **{status}**")
        with col3:
            if status == "active":
                if st.button("Add Money", key=f"add_goal_{goal_id}"):
                    st.session_state.selected_goal = goal_id
                    st.session_state.show_goal_contribution = True
        with col4:
            if st.button("🗑", key=f"delete_goal_{goal_id}"):
                cursor.execute("DELETE FROM goals WHERE id=?", (goal_id,))
                conn.commit()
                st.success("Goal deleted.")
                st.st.rerun()
        st.divider()
else:
    st.info("No savings goals yet. Create one below.")

# Create new goal form
with st.expander("➕ Create New Goal"):
    goal_name = st.text_input("Goal Name", key="goal_name")
    goal_target = st.number_input("Target Amount (₦)", min_value=1, key="goal_target")
    if st.button("Create Goal", key="create_goal_btn"):
        if goal_name and goal_target > 0:
            cursor.execute("""
                INSERT INTO goals (user_id, name, target_amount, created_at, current_amount, status)
                VALUES (?, ?, ?, ?, 0, 'active')
            """, (user_id, goal_name, goal_target, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success("Goal created!")
            st.st.rerun()
        else:
            st.warning("Please enter a name and target.")

# Contribution form (shown when Add Money clicked)
if st.session_state.get("show_goal_contribution") and st.session_state.get("selected_goal"):
    goal_id = st.session_state.selected_goal
    cursor.execute("SELECT name, target_amount, current_amount FROM goals WHERE id=?", (goal_id,))
    g = cursor.fetchone()
    if g:
        g_name, g_target, g_current = g
        st.write(f"**Add money to '{g_name}'**")
        cursor.execute("SELECT id, bank_name, balance FROM banks WHERE user_id=?", (user_id,))
        bank_list = cursor.fetchall()
        if bank_list:
            bank_options = {f"{b[1]} (₦{b[2]:,})": b[0] for b in bank_list}
            selected_bank = st.selectbox("From Bank", list(bank_options.keys()), key="goal_bank")
            contrib_amount = st.number_input("Amount to add (₦)", min_value=1, key="goal_amount")
            if st.button("Confirm Contribution", key="confirm_goal_contrib"):
                bank_id = bank_options[selected_bank]
                cursor.execute("SELECT balance FROM banks WHERE id=?", (bank_id,))
                bank_balance = cursor.fetchone()[0]
                if contrib_amount > bank_balance:
                    st.error("Insufficient funds in selected bank.")
                else:
                    cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (contrib_amount, bank_id))
                    new_current = g_current + contrib_amount
                    new_status = "completed" if new_current >= g_target else "active"
                    cursor.execute("""
                        UPDATE goals
                        SET current_amount = ?, status = ?
                        WHERE id = ?
                    """, (new_current, new_status, goal_id))
                    conn.commit()
                    st.success(f"Added ₦{contrib_amount:,.0f} to goal.")
                    st.session_state.show_goal_contribution = False
                    st.st.rerun()
        else:
            st.warning("You need a bank account to transfer from.")
    else:
        st.session_state.show_goal_contribution = False

# ---------- ALERT SETTINGS ----------
with st.expander("🔔 Alert Settings"):
    cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=?", (user_id,))
    current_limit = cursor.fetchone()[0] or 0
    new_limit = st.number_input("Monthly Spending Limit (₦) – 0 = no limit", min_value=0, value=current_limit, key="monthly_limit")
    if st.button("Update Spending Limit", key="update_limit_btn"):
        cursor.execute("UPDATE users SET monthly_spending_limit = ? WHERE id=?", (new_limit, user_id))
        conn.commit()
        st.success("Monthly limit updated.")
        st.st.rerun()

# ---------- INCOME VS EXPENSES CHART ----------
st.subheader("📊 Income vs Expenses Over Time")
period_map = {
    "Last 30 Days": timedelta(days=30),
    "Last 3 Months": timedelta(days=90),
    "Last 6 Months": timedelta(days=180),
    "Last Year": timedelta(days=365),
    "All Time": None
}
selected_period = st.selectbox("Select Period", list(period_map.keys()), key="period_select")
if period_map[selected_period]:
    start_date = (datetime.now() - period_map[selected_period]).date()
else:
    start_date = datetime(2000,1,1).date()
start_str = start_date.strftime("%Y-%m-%d")

cursor.execute("""
    SELECT t.created_at, t.type, t.amount
    FROM transactions t
    JOIN banks b ON t.bank_id = b.id
    WHERE b.user_id = ? AND t.created_at >= ?
    ORDER BY t.created_at
""", (user_id, start_str))
rows = cursor.fetchall()

if rows:
    df = pd.DataFrame(rows, columns=["date", "type", "amount"])
    df["date"] = pd.to_datetime(df["date"])
    df_pivot = df.pivot_table(index="date", columns="type", values="amount", aggfunc="sum", fill_value=0)
    for col in ["credit","debit"]:
        if col not in df_pivot.columns:
            df_pivot[col] = 0
    df_pivot = df_pivot.rename(columns={"credit":"Income","debit":"Expenses"}).sort_index()
    st.line_chart(df_pivot[["Income","Expenses"]])
    st.bar_chart(df_pivot[["Income","Expenses"]])
else:
    st.info("No transactions in this period.")

# ---------- IMPORT BANK STATEMENT CSV ----------
st.divider()
st.subheader("📥 Import Bank Statement (CSV)")

with st.expander("Click here to import your bank CSV safely"):
    csv_import_page(conn, user_id)

# ---------- LOGOUT ----------
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.session_state.user_role = None
    st.st.rerun()











