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
def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt())
def check_pw(p, h): return bcrypt.checkpw(p.encode(), h)

def naira(amount):
    return f"₦{amount:,.2f}"

CATEGORIES = [
    "Food",
    "Transport",
    "Rent",
    "Utilities",
    "Data / Airtime",
    "Shopping",
    "Health",
    "Entertainment",
    "Others"
]

# ---------------- LOGIN ----------------
def login_page():
    st.title("🔐 Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        c.execute("SELECT id, password FROM users WHERE username=?", (username,))
        user = c.fetchone()

        if user and check_pw(password, user[1]):
            st.session_state.user_id = user[0]
            st.session_state.page = "dashboard"
            st.rerun()
        else:
            st.error("Invalid login details")

    st.caption("No account?")
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
            c.execute("""
            INSERT INTO users (surname, other_names, email, username, password)
            VALUES (?, ?, ?, ?, ?)
            """, (surname, other, email, username, hash_pw(password)))
            conn.commit()

            st.success("Account created. Please login.")
            st.session_state.page = "login"
            st.rerun()
        except:
            st.error("Username or email already exists")

    if st.button("Back to login"):
        st.session_state.page = "login"
        st.rerun()

# ---------------- DASHBOARD ----------------
def dashboard():
    st.title("💰 Budget Dashboard")

    tab1, tab2, tab3, tab4 = st.tabs([
        "➕ Expenses", "🏦 Banks", "🎯 Goals", "📊 Reports"
    ])

    # -------- EXPENSES --------
    with tab1:
        name = st.text_input("Expense name")
        category = st.selectbox("Category", CATEGORIES)
        amount = st.number_input("Amount (₦)", min_value=0.0)

        if st.button("Add Expense"):
            if name and amount > 0:
                c.execute("""
                INSERT INTO expenses
                VALUES (NULL, ?, ?, ?, ?, ?)
                """, (st.session_state.user_id, name, category, amount, date.today()))
                conn.commit()
                st.success("Expense added")

        c.execute("""
        SELECT name, category, amount, date
        FROM expenses
        WHERE user_id=?
        ORDER BY date DESC
        """, (st.session_state.user_id,))
        rows = c.fetchall()

        if rows:
            df = pd.DataFrame(rows, columns=["Name", "Category", "Amount", "Date"])
            df["Amount"] = df["Amount"].apply(naira)
            st.dataframe(df, use_container_width=True)

    # -------- BANKS --------
    with tab2:
        bank = st.text_input("Bank name")
        if st.button("Add Bank"):
            c.execute("INSERT INTO banks VALUES (NULL, ?, ?)",
                      (st.session_state.user_id, bank))
            conn.commit()
            st.success("Bank added")

        c.execute("SELECT id, bank_name FROM banks WHERE user_id=?",
                  (st.session_state.user_id,))
        banks = c.fetchall()

        if banks:
            bank_map = {b[1]: b[0] for b in banks}
            selected = st.selectbox("Select bank", list(bank_map.keys()))

            remark = st.text_input("Transaction remark")
            amount = st.number_input("Transaction amount (₦)", min_value=0.0)
            category = st.selectbox("Transaction category", CATEGORIES)

            if st.button("Save transaction"):
                bank_id = bank_map[selected]
                c.execute("""
                INSERT INTO transactions VALUES (NULL, ?, ?, ?, ?)
                """, (bank_id, remark, amount, date.today()))
                conn.commit()

                # AUTO EXPENSE
                c.execute("""
                INSERT INTO expenses VALUES (NULL, ?, ?, ?, ?, ?)
                """, (st.session_state.user_id, remark, category, amount, date.today()))
                conn.commit()

                st.success("Transaction saved & expense created")

    # -------- GOALS --------
    with tab3:
        title = st.text_input("Goal title")
        target = st.number_input("Target amount (₦)", min_value=0.0)

        if st.button("Create Goal"):
            c.execute("""
            INSERT INTO goals VALUES (NULL, ?, ?, ?)
            """, (st.session_state.user_id, title, target))
            conn.commit()
            st.success("Goal added")

        c.execute("SELECT title, target FROM goals WHERE user_id=?",
                  (st.session_state.user_id,))
        goals = c.fetchall()

        c.execute("SELECT SUM(amount) FROM expenses WHERE user_id=?",
                  (st.session_state.user_id,))
        spent = c.fetchone()[0] or 0

        for g in goals:
            remaining = g[1] - spent
            if remaining <= 0:
                st.error(f"⚠️ {g[0]} exceeded!")
            else:
                st.info(f"{g[0]} → {naira(remaining)} remaining")

    # -------- REPORTS --------
    with tab4:
        c.execute("""
        SELECT category, amount, date FROM expenses WHERE user_id=?
        """, (st.session_state.user_id,))
        df = pd.DataFrame(c.fetchall(), columns=["Category", "Amount", "Date"])

        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            monthly = df.groupby(df["Date"].dt.to_period("M"))["Amount"].sum()
            st.subheader("Monthly Spending")
            st.bar_chart(monthly)

            st.subheader("Spending by Category")
            cat = df.groupby("Category")["Amount"].sum()
            st.bar_chart(cat)

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
