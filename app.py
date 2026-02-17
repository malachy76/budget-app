import streamlit as st
import bcrypt
import pandas as pd
import matplotlib.pyplot as plt
from database import create_tables, get_connection

# ---------------- PAGE SETUP ----------------
st.set_page_config(page_title="Budget App", page_icon="💰")

create_tables()
conn = get_connection()
cursor = conn.cursor()

st.title("💰 Budget App")

# ---------------- SESSION ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- AUTH FUNCTIONS ----------------
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

# ---------------- LOGIN / REGISTER ----------------
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if login(u, p):
                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        if st.button("Register"):
            if register(nu, np):
                st.success("Account created. Please login.")
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

# ---------------- EXPENSE LISTS ----------------
st.subheader("📂 Expense Lists")

new_list = st.text_input("Create new expense list (e.g. Food, Transport)")
if st.button("Create Expense List"):
    if new_list:
        cursor.execute(
            "INSERT INTO expense_lists (user_id, name) VALUES (?, ?)",
            (user_id, new_list)
        )
        conn.commit()
        st.success("Expense list created")

cursor.execute(
    "SELECT id, name FROM expense_lists WHERE user_id=?",
    (user_id,)
)
lists = cursor.fetchall()

selected_list_id = None

if not lists:
    st.info("👆 Create your first expense list to start adding expenses.")
else:
    list_dict = {name: list_id for list_id, name in lists}
    selected_list = st.selectbox("Select expense list", list_dict.keys())
    selected_list_id = list_dict[selected_list]

# ---------------- ADD EXPENSE ----------------
if selected_list_id:
    st.subheader("➕ Add Expense")
    ename = st.text_input("Expense name")
    eamount = st.number_input("Expense amount", min_value=0)

    if st.button("Add Expense"):
        if ename and eamount > 0:
            cursor.execute(
                "INSERT INTO expenses (list_id, name, amount) VALUES (?, ?, ?)",
                (selected_list_id, ename, eamount)
            )
            conn.commit()
            st.success("Expense added")
            st.rerun()

# ---------------- EDIT / DELETE EXPENSES ----------------
st.subheader("📋 Expenses (Edit / Delete)")

cursor.execute("""
SELECT e.id, el.name, e.name, e.amount
FROM expenses e
JOIN expense_lists el ON e.list_id = el.id
WHERE el.user_id = ?
""", (user_id,))

expenses = cursor.fetchall()
total_expenses = 0

if expenses:
    for exp_id, category, name, amount in expenses:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

        with col1:
            st.write(f"**{category}** – {name}")

        with col2:
            new_amount = st.number_input(
                "₦",
                value=amount,
                min_value=0,
                key=f"edit_{exp_id}"
            )

        with col3:
            if st.button("💾 Save", key=f"save_{exp_id}"):
                cursor.execute(
                    "UPDATE expenses SET amount=? WHERE id=?",
                    (new_amount, exp_id)
                )
                conn.commit()
                st.success("Updated")
                st.rerun()

        with col4:
            if st.button("🗑 Delete", key=f"delete_{exp_id}"):
                cursor.execute(
                    "DELETE FROM expenses WHERE id=?",
                    (exp_id,)
                )
                conn.commit()
                st.warning("Deleted")
                st.rerun()

        total_expenses += amount
else:
    st.info("No expenses added yet.")

# ---------------- SUMMARY ----------------
st.subheader("📊 Summary")
st.write(f"💵 Income: ₦{saved_income}")
st.write(f"📉 Total Expenses: ₦{total_expenses}")
st.write(f"💰 Balance: ₦{saved_income - total_expenses}")

# ---------------- CHARTS ----------------
st.subheader("📈 Expense Analytics")

if expenses:
    df = pd.DataFrame(expenses, columns=["ID", "Category", "Expense", "Amount"])

    fig1, ax1 = plt.subplots()
    df.groupby("Category")["Amount"].sum().plot(
        kind="pie",
        autopct="%1.1f%%",
        ax=ax1
    )
    ax1.set_ylabel("")
    st.pyplot(fig1)

    fig2, ax2 = plt.subplots()
    df.groupby("Category")["Amount"].sum().plot(
        kind="bar",
        ax=ax2
    )
    ax2.set_ylabel("Amount (₦)")
    st.pyplot(fig2)

# ---------------- MONTHLY REPORT ----------------
st.subheader("📅 Monthly Report")
st.write(f"💵 Income: ₦{saved_income}")
st.write(f"📉 Spent: ₦{total_expenses}")
st.write(f"💰 Savings: ₦{saved_income - total_expenses}")
