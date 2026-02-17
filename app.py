import streamlit as st
import bcrypt
from database import create_tables, get_connection

# ---------------- SETUP ----------------
st.set_page_config(page_title="Budget App", page_icon="💰")

create_tables()
conn = get_connection()
cursor = conn.cursor()

st.title("💰 Budget App")

# ---------------- SESSION STATE ----------------
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
    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    try:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed_password)
        )
        conn.commit()
        return True
    except:
        return False

# ---------------- LOGIN / REGISTER ----------------
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            if login(username, password):
                st.success("Logged in successfully")
                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        new_username = st.text_input("New Username")
        new_password = st.text_input("New Password", type="password")

        if st.button("Register"):
            if register(new_username, new_password):
                st.success("Account created. Please login.")
            else:
                st.error("Username already exists")

    st.stop()

# ---------------- LOGOUT ----------------
if st.button("Logout"):
    st.session_state.user_id = None
    st.rerun()

user_id = st.session_state.user_id

# ---------------- INCOME ----------------
st.subheader("Add Income")
income = st.number_input("Enter income", min_value=0)

if st.button("Save Income"):
    cursor.execute("DELETE FROM income WHERE user_id=?", (user_id,))
    cursor.execute(
        "INSERT INTO income (user_id, amount) VALUES (?, ?)",
        (user_id, income)
    )
    conn.commit()
    st.success("Income saved")

cursor.execute(
    "SELECT amount FROM income WHERE user_id=?",
    (user_id,)
)
row = cursor.fetchone()
saved_income = row[0] if row else 0

# ---------------- EXPENSES ----------------
st.subheader("Add Expense")
expense_name = st.text_input("Expense name")
expense_amount = st.number_input("Expense amount", min_value=0)

if st.button("Add Expense"):
    if expense_name and expense_amount > 0:
        cursor.execute(
            "INSERT INTO expenses (user_id, name, amount) VALUES (?, ?, ?)",
            (user_id, expense_name, expense_amount)
        )
        conn.commit()
        st.success("Expense added")

cursor.execute(
    "SELECT name, amount FROM expenses WHERE user_id=?",
    (user_id,)
)
expenses = cursor.fetchall()

# ---------------- SUMMARY ----------------
total_expenses = sum(e[1] for e in expenses)
balance = saved_income - total_expenses

st.subheader("Summary")
st.write(f"💵 Income: ₦{saved_income}")
st.write(f"📉 Expenses: ₦{total_expenses}")
st.write(f"💰 Balance: ₦{balance}")

st.subheader("Expense List")
for name, amount in expenses:
    st.write(f"- {name}: ₦{amount}")
