import streamlit as st
import bcrypt
import pandas as pd
from datetime import date
from database import create_tables, get_conn

# ---------------- SETUP ----------------
st.set_page_config(page_title="💰 Budget App", layout="centered")
create_tables()

conn = get_conn()
c = conn.cursor()

# ---------------- SESSION ----------------
if "page" not in st.session_state:
    st.session_state.page = "login"

if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- HELPERS ----------------
def hash_pw(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_pw(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

# ---------------- LOGIN PAGE ----------------
def login_page():
    st.title("🔐 Login")

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login"):
        c.execute("SELECT id, password FROM users WHERE username=?", (username,))
        user = c.fetchone()

        if user and check_pw(password, user[1]):
            st.session_state.user_id = user[0]
            st.session_state.page = "dashboard"
            st.rerun()
        else:
            st.error("Invalid username or password")

    st.markdown("---")
    st.caption("Don’t have an account?")
    if st.button("Create account"):
        st.session_state.page = "register"
        st.rerun()

# ---------------- REGISTER PAGE ----------------
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

            st.success("Account created successfully. Please login.")
            st.session_state.page = "login"
            st.rerun()
        except:
            st.error("Username or email already exists")

    st.markdown("---")
    if st.button("Back to login"):
        st.session_state.page = "login"
        st.rerun()

# ---------------- DASHBOARD ----------------
def dashboard():
    st.title("💰 Budget Dashboard")

    st.subheader("➕ Add Expense")
    name = st.text_input("Expense name")
    amount = st.number_input("Amount", min_value=0.0)

    if st.button("Add Expense"):
        if name and amount > 0:
            c.execute("""
                INSERT INTO expenses (user_id, name, amount, date)
                VALUES (?, ?, ?, ?)
            """, (st.session_state.user_id, name, amount, date.today()))
            conn.commit()
            st.success("Expense added")
        else:
            st.error("Please enter expense name and amount")

    st.subheader("📉 Your Expenses")
    c.execute("""
        SELECT name, amount, date
        FROM expenses
        WHERE user_id=?
        ORDER BY date DESC
    """, (st.session_state.user_id,))
    rows = c.fetchall()

    if rows:
        df = pd.DataFrame(rows, columns=["Name", "Amount", "Date"])
        st.dataframe(df, use_container_width=True)

        st.subheader("📊 Expense Chart")
        st.bar_chart(df.groupby("Name")["Amount"].sum())
    else:
        st.info("No expenses yet")

    st.markdown("---")
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
