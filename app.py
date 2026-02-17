import streamlit as st
import bcrypt
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from database import get_connection, create_tables

st.set_page_config(page_title="Simple Budget App", page_icon="💰")

create_tables()
conn = get_connection()
cursor = conn.cursor()

st.title("💰 Simple Budget App")

# ---------------- SESSION ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- AUTH ----------------
def login(username, password):
    cursor.execute(
        "SELECT id, password FROM users WHERE username=?",
        (username,)
    )
    user = cursor.fetchone()
    if user and bcrypt.checkpw(password.encode(), user[1]):
        st.session_state.user_id = user[0]
        return True
    return False

def register(username, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    try:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed)
        )
        conn.commit()
        return True
    except:
        return False

# ---------------- LOGIN UI ----------------
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if login(u, p):
                st.rerun()
            else:
                st.error("Invalid login")

    with tab2:
        u2 = st.text_input("New Username")
        p2 = st.text_input("New Password", type="password")
        if st.button("Register"):
            if register(u2, p2):
                st.success("Account created. Login now.")
            else:
                st.error("Username already exists")

    st.stop()

user_id = st.session_state.user_id

# ---------------- LOGOUT ----------------
if st.button("Logout"):
    st.session_state.user_id = None
    st.rerun()

# ---------------- INCOME ----------------
st.subheader("💵 Income")
income = st.number_input("Enter your income", min_value=0)

if st.button("Save Income"):
    cursor.execute("DELETE FROM income WHERE user_id=?", (user_id,))
    cursor.execute(
        "INSERT INTO income (user_id, amount) VALUES (?, ?)",
        (user_id, income)
    )
    conn.commit()
    st.success("Income saved")

cursor.execute("SELECT amount FROM income WHERE user_id=?", (user_id,))
row = cursor.fetchone()
saved_income = row[0] if row else 0

# ---------------- ADD EXPENSE ----------------
st.subheader("➕ Add Expense")

ename = st.text_input("Expense name")
eamount = st.number_input("Amount", min_value=0)

if st.button("Add Expense"):
    if ename and eamount > 0:
        cursor.execute(
            "INSERT INTO expenses (user_id, name, amount, created_at) VALUES (?, ?, ?, ?)",
            (user_id, ename, eamount, datetime.now().strftime("%Y-%m"))
        )
        conn.commit()
        st.success("Expense added")
        st.rerun()

# ---------------- EXPENSE LIST ----------------
st.subheader("📋 Expenses")

cursor.execute(
    "SELECT id, name, amount FROM expenses WHERE user_id=?",
    (user_id,)
)
expenses = cursor.fetchall()

total = 0

if expenses:
    for exp_id, name, amount in expenses:
        col1, col2, col3 = st.columns([4, 2, 1])

        with col1:
            st.write(name)

        with col2:
            new_amount = st.number_input(
                "₦",
                value=amount,
                key=f"amt_{exp_id}"
            )

        with col3:
            if st.button("🗑", key=f"del_{exp_id}"):
                cursor.execute(
                    "DELETE FROM expenses WHERE id=?",
                    (exp_id,)
                )
                conn.commit()
                st.rerun()

        if new_amount != amount:
            cursor.execute(
                "UPDATE expenses SET amount=? WHERE id=?",
                (new_amount, exp_id)
            )
            conn.commit()

        total += amount
else:
    st.info("No expenses yet")

# ---------------- SUMMARY ----------------
st.subheader("📊 Summary")
st.write(f"💵 Income: ₦{saved_income}")
st.write(f"📉 Total Expenses: ₦{total}")
st.write(f"💰 Balance: ₦{saved_income - total}")

# ---------------- MONTHLY BREAKDOWN ----------------
st.subheader("📅 Monthly Breakdown")

cursor.execute(
    "SELECT DISTINCT created_at FROM expenses WHERE user_id=? ORDER BY created_at DESC",
    (user_id,)
)
months = [m[0] for m in cursor.fetchall()]

if months:
    selected_month = st.selectbox("Select month", months)

    cursor.execute(
        "SELECT name, amount FROM expenses WHERE user_id=? AND created_at=?",
        (user_id, selected_month)
    )
    month_data = cursor.fetchall()

    df = pd.DataFrame(month_data, columns=["Expense", "Amount"])
    total_month = df["Amount"].sum()

    st.write(f"📉 Spent in {selected_month}: ₦{total_month}")
    st.write(f"💰 Balance: ₦{saved_income - total_month}")

    st.dataframe(df)

    fig, ax = plt.subplots()
    df.plot(kind="bar", x="Expense", y="Amount", ax=ax)
    st.pyplot(fig)
else:
    st.info("No monthly data yet.")
