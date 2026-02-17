import streamlit as st
import bcrypt
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from database import get_connection, create_tables
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import io

st.set_page_config(
    page_title="Simple Budget App",
    page_icon="💰",
    layout="centered"
)

create_tables()
conn = get_connection()
cursor = conn.cursor()

st.title("💰 Simple Budget App")

# ---------------- SESSION ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- AUTH ----------------
def login(username, password):
    cursor.execute("SELECT id, password FROM users WHERE username=?", (username,))
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

# ---------------- LOGIN ----------------
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
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.rerun()

# ---------------- INCOME ----------------
st.subheader("💵 Income")
income = st.number_input("Monthly income", min_value=0)

if st.button("Save Income"):
    cursor.execute("DELETE FROM income WHERE user_id=?", (user_id,))
    cursor.execute(
        "INSERT INTO income (user_id, amount) VALUES (?, ?)",
        (user_id, income)
    )
    conn.commit()

cursor.execute("SELECT amount FROM income WHERE user_id=?", (user_id,))
row = cursor.fetchone()
saved_income = row[0] if row else 0

# ---------------- SAVINGS GOAL ----------------
st.subheader("🎯 Savings Goal")

goal = st.number_input("Monthly savings goal", min_value=0)

if st.button("Save Goal"):
    cursor.execute("DELETE FROM savings WHERE user_id=?", (user_id,))
    cursor.execute(
        "INSERT INTO savings (user_id, goal) VALUES (?, ?)",
        (user_id, goal)
    )
    conn.commit()

cursor.execute("SELECT goal FROM savings WHERE user_id=?", (user_id,))
row = cursor.fetchone()
savings_goal = row[0] if row else 0

# ---------------- ADD EXPENSE ----------------
st.subheader("➕ Add Expense")

ename = st.text_input("Expense name")
category = st.selectbox("Category", ["Food", "Rent", "Transport", "Entertainment", "Other"])
eamount = st.number_input("Amount", min_value=0)

if st.button("Add Expense"):
    if ename and eamount > 0:
        cursor.execute(
            "INSERT INTO expenses (user_id, name, category, amount, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, ename, category, eamount, datetime.now().strftime("%Y-%m"))
        )
        conn.commit()
        st.rerun()

# ---------------- EXPENSES ----------------
cursor.execute(
    "SELECT id, name, category, amount FROM expenses WHERE user_id=?",
    (user_id,)
)
expenses = cursor.fetchall()
total_spent = sum([e[3] for e in expenses])

st.subheader("📊 Dashboard")

st.metric("Income", f"₦{saved_income}")
st.metric("Expenses", f"₦{total_spent}")
st.metric("Balance", f"₦{saved_income - total_spent}")

df = pd.DataFrame(expenses, columns=["ID", "Name", "Category", "Amount"])
st.dataframe(df)

# ---------------- EDIT/DELETE ----------------
st.subheader("✏️ Manage Expenses")
for exp in expenses:
    exp_id, exp_name, exp_cat, exp_amt = exp
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button(f"Edit {exp_name}", key=f"edit_{exp_id}"):
            new_name = st.text_input("New name", exp_name, key=f"name_{exp_id}")
            new_cat = st.selectbox("New category", ["Food", "Rent", "Transport", "Entertainment", "Other"],
                                   index=["Food","Rent","Transport","Entertainment","Other"].index(exp_cat),
                                   key=f"cat_{exp_id}")
            new_amt = st.number_input("New amount", value=exp_amt, key=f"amt_{exp_id}")
            if st.button("Save Changes", key=f"save_{exp_id}"):
                cursor.execute(
                    "UPDATE expenses SET name=?, category=?, amount=? WHERE id=?",
                    (new_name, new_cat, new_amt, exp_id)
                )
                conn.commit()
                st.rerun()
    with col2:
        if st.button(f"Delete {exp_name}", key=f"del_{exp_id}"):
            cursor.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
            conn.commit()
            st.rerun()

# ---------------- ALERTS ----------------
st.subheader("🔔 Alerts")

if total_spent > saved_income:
    st.error("🚨 You have spent more than your income!")
elif total_spent >= saved_income * 0.8:
    st.warning("⚠️ You have used 80% of your income.")
else:
    st.success("✅ Your spending is under control.")

# ---------------- SAVINGS PROGRESS ----------------
if savings_goal > 0:
    savings = saved_income - total_spent
    progress = max(min(savings / savings_goal, 1), 0)

    st.subheader("💰 Savings Progress")
    st.progress(progress)

    if savings >= savings_goal:
        st.success("🎉 You reached your savings goal!")
    else:
        st.info(f"You need ₦{savings_goal - savings} more to reach your goal.")

# ---------------- MONTHLY BREAKDOWN ----------------
st.subheader("📅 Monthly Breakdown")

cursor.execute(
    "SELECT DISTINCT created_at FROM expenses WHERE user_id=? ORDER BY created_at DESC",
    (user_id,)
)
months = [m[0] for m in cursor.fetchall()]

if months:
    month = st.selectbox("Select month", months)

    cursor.execute(
        "SELECT name, category, amount FROM expenses WHERE user_id=? AND created_at=?",
        (user_id, month)
    )
    data = cursor.fetchall()

    df_month = pd.DataFrame(data, columns=["Expense", "Category", "Amount"])
    st.dataframe(df_month)

    fig, ax = plt.subplots()
    df_month.groupby("Category").sum().plot(kind="pie", y="Amount", ax=ax, autopct='%1.1f%%')
    st.pyplot(fig)

    # PDF export
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    text = c.beginText(40, 800)
    text.textLine(f"Monthly Report: {month}")
    text.textLine(f"Income: ₦{saved_income}")
    text.textLine(f"Spent: ₦{df_month['Amount'].sum()}")
    text.textLine("")

    for _, r in df_month.iterrows():
        text.textLine(f"{r['Expense']} ({r['Category']}) - ₦{r['Amount']}")

    c.drawText(text)
    c.showPage()
    c.save()

    st.download_button(
        "⬇️ Download PDF",
        pdf_buffer.getvalue(),
        file_name=f"budget_{month}.pdf
