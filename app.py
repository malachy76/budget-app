import streamlit as st
import bcrypt
import random
import pandas as pd
from datetime import datetime
from database import create_tables, get_conn

st.set_page_config(page_title="💰 Budget App", layout="centered")
create_tables()

# ---------- HELPERS ----------
def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt())
def check_pw(p, h): return bcrypt.checkpw(p.encode(), h)

def send_email_stub(email, msg):
    st.info(f"📧 Email sent to {email}: {msg}")

def send_sms_stub(phone, otp):
    st.info(f"📱 SMS OTP (SIMULATED): {otp}")

# ---------- SESSION ----------
if "user" not in st.session_state:
    st.session_state.user = None

menu = st.sidebar.radio(
    "Menu",
    ["Login", "Register", "Resend Verification", "Reset Password"]
    if not st.session_state.user
    else ["Bank", "Expenses", "Monthly Statement", "Logout"]
)

conn = get_conn()
c = conn.cursor()

# ---------- REGISTER ----------
if menu == "Register":
    st.header("📝 Register")

    surname = st.text_input("Surname", key="r1")
    other = st.text_input("Other Names", key="r2")
    email = st.text_input("Email", key="r3")
    username = st.text_input("Username", key="r4")
    password = st.text_input("Password", type="password", key="r5")

    if st.button("Create Account", key="r6"):
        hashed = hash_pw(password)
        try:
            c.execute("""
            INSERT INTO users (surname, other_names, email, username, password)
            VALUES (?, ?, ?, ?, ?)
            """, (surname, other, email, username, hashed))
            conn.commit()

            otp = str(random.randint(100000, 999999))
            c.execute("INSERT INTO otp VALUES (?, ?, ?)",
                      (c.lastrowid, otp, datetime.now().isoformat()))
            conn.commit()

            send_email_stub(email, f"Your verification code is {otp}")
            st.success("Account created. Verify your email.")
        except:
            st.error("User already exists")

# ---------- LOGIN ----------
elif menu == "Login":
    st.header("🔐 Login")

    u = st.text_input("Username", key="l1")
    p = st.text_input("Password", type="password", key="l2")

    if st.button("Login", key="l3"):
        c.execute("SELECT id, password, verified FROM users WHERE username=?", (u,))
        user = c.fetchone()

        if user and check_pw(p, user[1]):
            if user[2] == 0:
                st.error("Email not verified")
            else:
                st.session_state.user = user[0]
                st.success("Logged in")
                st.rerun()
        else:
            st.error("Login failed")

# ---------- RESEND ----------
elif menu == "Resend Verification":
    st.header("🔁 Resend Verification")
    email = st.text_input("Email", key="rv1")

    if st.button("Resend", key="rv2"):
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        user = c.fetchone()
        if user:
            otp = str(random.randint(100000, 999999))
            c.execute("INSERT INTO otp VALUES (?, ?, ?)",
                      (user[0], otp, datetime.now().isoformat()))
            conn.commit()
            send_email_stub(email, otp)
            st.success("Verification sent")

# ---------- RESET ----------
elif menu == "Reset Password":
    st.header("🔑 Reset Password")
    email = st.text_input("Email", key="rp1")

    if st.button("Send Reset", key="rp2"):
        send_email_stub(email, "Password reset link (SIMULATED)")
        st.success("Reset email sent")

# ---------- BANK ----------
elif menu == "Bank":
    st.header("🏦 Bank Accounts")

    bank = st.text_input("Bank Name", key="b1")
    if st.button("Add Bank", key="b2"):
        c.execute("INSERT INTO banks VALUES (NULL, ?, ?)",
                  (st.session_state.user, bank))
        conn.commit()
        st.success("Bank added")

    st.subheader("➕ Add Transaction")
    remark = st.text_input("Transaction Remark", key="b3")
    amount = st.number_input("Amount", key="b4")

    c.execute("SELECT id FROM banks WHERE user_id=?", (st.session_state.user,))
    banks = c.fetchall()

    if banks and st.button("Save Transaction", key="b5"):
        c.execute("""
        INSERT INTO transactions VALUES (NULL, ?, ?, ?, ?)
        """, (banks[0][0], remark, amount, datetime.now().date()))
        conn.commit()
        st.success("Transaction saved → Expenses auto-created")

        c.execute("""
        INSERT INTO expenses VALUES (NULL, ?, ?, ?, ?)
        """, (st.session_state.user, remark, amount, datetime.now().date()))
        conn.commit()

# ---------- EXPENSES ----------
elif menu == "Expenses":
    st.header("📉 Expenses")

    c.execute("SELECT name, amount, date FROM expenses WHERE user_id=?",
              (st.session_state.user,))
    df = pd.DataFrame(c.fetchall(), columns=["Name", "Amount", "Date"])
    st.dataframe(df)

# ---------- STATEMENT ----------
elif menu == "Monthly Statement":
    st.header("📊 Monthly Statement")

    c.execute("""
    SELECT amount, date FROM expenses WHERE user_id=?
    """, (st.session_state.user,))
    df = pd.DataFrame(c.fetchall(), columns=["Amount", "Date"])

    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
        monthly = df.groupby(df["Date"].dt.to_period("M")).sum()
        st.bar_chart(monthly)

# ---------- LOGOUT ----------
elif menu == "Logout":
    st.session_state.user = None
    st.rerun()
