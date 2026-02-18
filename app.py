import streamlit as st
import bcrypt
import random
import smtplib
import pandas as pd
from email.message import EmailMessage
from datetime import datetime
from database import get_connection, create_tables

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="💰 Budget App",
    page_icon="💰",
    layout="centered"
)

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

    msg.set_content(f"""
Welcome to Budget App 💰

Your verification code is:

{code}

If you did not create this account, ignore this email.
""")

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
            surname,
            other,
            email,
            username,
            hashed,
            code,
            datetime.now().strftime("%Y-%m-%d")
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
            st.warning("⚠️ Please verify your email first")
            return None
        return user[0]
    return None

# ---------------- UI ----------------
st.title("💰 Simple Budget App")

# ================= AUTH =================
if st.session_state.user_id is None:
    tabs = st.tabs(["🔐 Login", "📝 Register", "📧 Verify Email"])

    # -------- LOGIN --------
    with tabs[0]:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            user_id = login_user(username, password)
            if user_id:
                st.session_state.user_id = user_id
                st.rerun()
            else:
                st.error("Invalid login details")

    # -------- REGISTER --------
    with tabs[1]:
        st.subheader("Create Account")

        surname = st.text_input("Surname")
        other = st.text_input("Other Names")
        email = st.text_input("Email Address")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Register"):
            if not all([surname, other, email, username, password]):
                st.error("All fields are required")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters")
            else:
                code = register_user(
                    surname, other, email, username, password
                )
                if code:
                    send_verification_email(email, code)
                    st.success("Account created! Check your email to verify.")
                else:
                    st.error("Username or email already exists")

    # -------- VERIFY EMAIL --------
    with tabs[2]:
        email = st.text_input("Registered Email")
        code = st.text_input("Verification Code")

        if st.button("Verify Email"):
            cursor.execute("""
            SELECT id FROM users
            WHERE email=? AND verification_code=?
            """, (email, code))
            user = cursor.fetchone()

            if user:
                cursor.execute("""
                UPDATE users
                SET email_verified=1, verification_code=NULL
                WHERE id=?
                """, (user[0],))
                conn.commit()
                st.success("✅ Email verified. You can now login.")
            else:
                st.error("Invalid verification code")

    st.stop()

# ================= DASHBOARD =================
user_id = st.session_state.user_id

cursor.execute("""
SELECT surname, other_names FROM users WHERE id=?
""", (user_id,))
user = cursor.fetchone()

st.success(f"Welcome {user[0]} {user[1]} 👋")

# ---------------- ADD EXPENSE ----------------
st.subheader("➕ Add Expense")

expense_name = st.text_input("Expense Name")
expense_amount = st.number_input("Amount (₦)", min_value=0)

if st.button("Add Expense"):
    if expense_name and expense_amount > 0:
        cursor.execute("""
        INSERT INTO expenses (user_id, name, amount, created_at)
        VALUES (?, ?, ?, ?)
        """, (
            user_id,
            expense_name,
            expense_amount,
            datetime.now().strftime("%Y-%m-%d")
        ))
        conn.commit()
        st.success("Expense added successfully")
    else:
        st.error("Please enter expense name and amount")

# ---------------- CHARTS & ALERTS ----------------
cursor.execute("""
SELECT name, amount FROM expenses WHERE user_id=?
""", (user_id,))
rows = cursor.fetchall()

if rows:
    df = pd.DataFrame(rows, columns=["Expense", "Amount"])

    st.subheader("📊 Expense Chart")
    st.bar_chart(df.groupby("Expense")["Amount"].sum())

    total = df["Amount"].sum()
    st.metric("💸 Total Spent", f"₦{total:,}")

    MONTHLY_LIMIT = 50000
    if total > MONTHLY_LIMIT:
        st.error("🚨 You have exceeded your budget!")
    elif total > MONTHLY_LIMIT * 0.8:
        st.warning("⚠️ You’ve used over 80% of your budget")
    else:
        st.success("✅ Spending is under control")

# ---------------- LOGOUT ----------------
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.rerun()
