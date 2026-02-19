import streamlit as st
import bcrypt
import random
import smtplib
import pandas as pd
from email.message import EmailMessage
from datetime import datetime
from database import get_connection, create_tables

# ---------------- CONFIG ----------------
st.set_page_config("💰 Budget App", page_icon="💰", layout="centered")

create_tables()
conn = get_connection()
cursor = conn.cursor()

# ---------------- SESSION ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- HELPERS ----------------
def generate_code():
    return str(random.randint(100000, 999999))

def send_verification_email(email, code):
    msg = EmailMessage()
    msg["Subject"] = "Verify Your Budget App Account"
    msg["From"] = st.secrets["EMAIL_ADDRESS"]
    msg["To"] = email
    msg.set_content(f"Your verification code is: {code}")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(
            st.secrets["EMAIL_ADDRESS"],
            st.secrets["EMAIL_PASSWORD"]
        )
        smtp.send_message(msg)

def register_user(surname, other, email, username, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    code = generate_code()

    try:
        cursor.execute("""
        INSERT INTO users
        (surname, other_names, email, username, password, verification_code, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            surname, other, email, username,
            hashed, code, datetime.now().strftime("%Y-%m-%d")
        ))
        conn.commit()
        return code
    except:
        return None

def login_user(username, password):
    cursor.execute("""
    SELECT id, password, email_verified
    FROM users WHERE username=?
    """, (username,))
    user = cursor.fetchone()

    if user and bcrypt.checkpw(password.encode(), user[1]):
        if user[2] == 0:
            st.warning("Verify your email first")
            return None
        return user[0]
    return None

# ---------------- UI ----------------
st.title("💰 Simple Budget App")

# ================= AUTH =================
if st.session_state.user_id is None:
    tabs = st.tabs(["🔐 Login", "📝 Register", "📧 Verify Email"])

    # LOGIN
    with tabs[0]:
        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input("Password", type="password", key="login_password")

        if st.button("Login", key="login_btn"):
            user_id = login_user(login_username, login_password)
            if user_id:
                st.session_state.user_id = user_id
                st.rerun()
            else:
                st.error("Login failed")

    # REGISTER
    with tabs[1]:
        reg_surname = st.text_input("Surname", key="reg_surname")
        reg_other = st.text_input("Other Names", key="reg_other")
        reg_email = st.text_input("Email", key="reg_email")
        reg_username = st.text_input("Username", key="reg_username")
        reg_password = st.text_input("Password", type="password", key="reg_password")

        if st.button("Register", key="register_btn"):
            if not all([reg_surname, reg_other, reg_email, reg_username, reg_password]):
                st.error("All fields required")
            else:
                code = register_user(
                    reg_surname, reg_other, reg_email,
                    reg_username, reg_password
                )
                if code:
                    send_verification_email(reg_email, code)
                    st.success("Account created. Check email to verify.")
                else:
                    st.error("Username or email exists")

    # VERIFY EMAIL
    with tabs[2]:
        verify_email = st.text_input("Registered Email", key="verify_email")
        verify_code = st.text_input("Verification Code", key="verify_code")

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
                st.success("Email verified")
            else:
                st.error("Invalid code")

    st.stop()

# ================= DASHBOARD =================
user_id = st.session_state.user_id

cursor.execute("SELECT surname, other_names FROM users WHERE id=?", (user_id,))
user = cursor.fetchone()
st.success(f"Welcome {user[0]} {user[1]} 👋")

# ---------------- ADD BANK ----------------
st.subheader("🏦 Add Bank Account")

bank_name = st.text_input("Bank Name", key="bank_name")
account_name = st.text_input("Account Name", key="acct_name")
account_number = st.text_input("Account Number (last 4 digits)", key="acct_num")
opening_balance = st.number_input("Opening Balance (₦)", min_value=0, key="open_bal")

if st.button("Add Bank", key="add_bank_btn"):
    if bank_name and account_name and account_number:
        cursor.execute("""
        INSERT INTO banks (user_id, bank_name, account_name, account_number, balance)
        VALUES (?, ?, ?, ?, ?)
        """, (
            user_id, bank_name, account_name,
            account_number[-4:], opening_balance
        ))
        conn.commit()
        st.success("Bank added")

# ---------------- ADD EXPENSE (AUTO DEBIT) ----------------
st.subheader("➕ Add Expense (Auto Bank Debit)")

expense_name = st.text_input("Expense Name", key="exp_name")
expense_amount = st.number_input("Amount (₦)", min_value=1, key="exp_amt")

cursor.execute("""
SELECT id, bank_name, account_number, balance
FROM banks WHERE user_id=?
""", (user_id,))
banks = cursor.fetchall()

if banks:
    bank_map = {
        f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0]
        for b in banks
    }

    selected_bank = st.selectbox(
        "Pay From Bank",
        list(bank_map.keys()),
        key="bank_select"
    )

    if st.button("Add Expense", key="add_expense_btn"):
        bank_id = bank_map[selected_bank]

        cursor.execute("""
        INSERT INTO expenses
        (user_id, bank_id, name, amount, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (
            user_id, bank_id, expense_name,
            expense_amount, datetime.now().strftime("%Y-%m-%d")
        ))

        cursor.execute("""
        UPDATE banks SET balance = balance - ?
        WHERE id=?
        """, (expense_amount, bank_id))

        cursor.execute("""
        INSERT INTO transactions
        (bank_id, type, amount, description, created_at)
        VALUES (?, 'debit', ?, ?, ?)
        """, (
            bank_id, expense_amount,
            f"Expense: {expense_name}",
            datetime.now().strftime("%Y-%m-%d")
        ))

        conn.commit()
        st.success("Expense added & bank debited")
else:
    st.info("Add a bank account first")

# ---------------- LOGOUT ----------------
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.rerun()
