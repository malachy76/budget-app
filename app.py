import streamlit as st
import bcrypt
import random
import pandas as pd
from datetime import date
from database import create_tables, get_conn

st.set_page_config("💰 Budget App", layout="centered")
create_tables()

conn = get_conn()
c = conn.cursor()

# ---------------- SESSION ----------------
if "page" not in st.session_state:
    st.session_state.page = "login"

if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- HELPERS ----------------
def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt())
def check_pw(p, h): return bcrypt.checkpw(p.encode(), h)

def send_email(email, subject, body):
    st.info(f"📧 EMAIL TO {email}\n{body}")  # replace with SMTP later

# ---------------- LOGIN ----------------
def login_page():
    st.title("🔐 Login")

    username = st.text_input("Username", key="login_user")
    password = st.text_input("Password", type="password", key="login_pass")

    if st.button("Login"):
        c.execute("SELECT id, password, verified FROM users WHERE username=?", (username,))
        user = c.fetchone()

        if user and check_pw(password, user[1]):
            if user[2] == 0:
                st.error("Please verify your email first")
            else:
                st.session_state.user_id = user[0]
                st.session_state.page = "dashboard"
                st.rerun()
        else:
            st.error("Invalid username or password")

    st.markdown("**Forgot password?**")
    if st.button("Create account"):
        st.session_state.page = "register"
        st.rerun()

# ---------------- REGISTER ----------------
def register_page():
    st.title("📝 Register")

    surname = st.text_input("Surname")
    other = st.text_input("Other Names")
    email = st.text_input("Email")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Create Account"):
        try:
            hashed = hash_pw(password)
            c.execute("""
            INSERT INTO users (surname, other_names, email, username, password)
            VALUES (?, ?, ?, ?, ?)
            """, (surname, other, email, username, hashed))
            conn.commit()

            code = str(random.randint(100000, 999999))
            c.execute("INSERT INTO verification VALUES (?, ?)", (c.lastrowid, code))
            conn.commit()

            send_email(email, "Verification Code", f"Your code is {code}")
            st.session_state.verify_user = c.lastrowid
            st.success("Account created. Enter verification code below.")

        except:
            st.error("Username or email already exists")

    if "verify_user" in st.session_state:
        st.subheader("📩 Verify Email")
        code_input = st.text_input("Verification Code")

        if st.button("Verify"):
            c.execute("SELECT code FROM verification WHERE user_id=?", (st.session_state.verify_user,))
            real = c.fetchone()

            if real and code_input == real[0]:
                c.execute("UPDATE users SET verified=1 WHERE id=?", (st.session_state.verify_user,))
                c.execute("DELETE FROM verification WHERE user_id=?", (st.session_state.verify_user,))
                conn.commit()

                del st.session_state.verify_user
                st.success("Verified successfully. Please login.")
                st.session_state.page = "login"
                st.rerun()
            else:
                st.error("Invalid code")

    if st.button("Back to login"):
        st.session_state.page = "login"
        st.rerun()

# ---------------- DASHBOARD ----------------
def dashboard():
    st.title("💰 Budget Dashboard")

    name = st.text_input("Expense name")
    amount = st.number_input("Amount", min_value=0.0)

    if st.button("Add Expense"):
        c.execute("""
        INSERT INTO expenses VALUES (NULL, ?, ?, ?, ?)
        """, (st.session_state.user_id, name, amount, date.today()))
        conn.commit()
        st.success("Expense added")

    st.subheader("📉 Your Expenses")
    c.execute("SELECT name, amount, date FROM expenses WHERE user_id=?", (st.session_state.user_id,))
    df = pd.DataFrame(c.fetchall(), columns=["Name", "Amount", "Date"])

    if not df.empty:
        st.dataframe(df)
        st.bar_chart(df.groupby("Name")["Amount"].sum())

    if st.button("Logout"):
        st.session_state.user_id = None
        st.session_state.page = "login"
        st.rerun()

# ---------------- ROUTER ----------------
if st.session_state.page == "login":
    login_page()
elif st.session_state.page == "register":
    register_page()
elif st.session_state.page == "dashboard":
    dashboard()
