import streamlit as st
import bcrypt
from database import create_tables, get_connection

create_tables()
conn = get_connection()
cursor = conn.cursor()

st.title("💰 Budget App")

# Session state
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

# ---------------- LOGIN UI ----------------
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            if login(username, password):
                st.success("Logged in")
             st.rerun()
            else:
                st.error("Invalid credentials")

    with tab2:
        new_user = st.text_input("New Username")
        new_pass = st.text_input("New Password", type="password")

        if st.button("Register"):
            if register(new_user, new_pass):
                st.success("Account created. Login now.")
            else:
                st.error("Username already exists")

    st.stop()

# ---------------- LOGOUT ----------------
if st.button("Logout"):
    st.session_state.user_id = None
    st.experimental_rerun()

# ---------------- APP CONTENT ----------------
st.subheader("Add Income")
income = st.number_input("Income", min_value=0)

if st.button("Save Income"):
    cursor.execute("DELETE FROM income WHERE user_id=?", (st.session_state.user_id,))
    cursor.execute(
        "INSERT INTO income (user_id, amount) VALUES (?, ?)",
        (st.session_state.user_id, income)
    )
    conn.commit()

cursor.execute("SELECT amount FROM income WHERE user_id=?", (st.session_state.user_id,))
row = cursor.fetchone()
saved_income = row[0] if row else 0

st.subheader("Add Expense")
name = st.text_input("Expense name")
amount = st.number_input("Expense amount", min_value=0)

if st.button("Add Expense"):
    cursor.execute(
        "INSERT INTO expenses (user_id, name, amount) VALUES (?, ?, ?)",
        (st.session_state.user_id, name, amount)
    )
    conn.commit()

cursor.execute(
    "SELECT name, amount FROM expenses WHERE user_id=?",
    (st.session_state.user_id,)
)
expenses = cursor.fetchall()

total_expenses = sum(e[1] for e in expenses)
balance = saved_income - total_expenses

st.subheader("Summary")
st.write(f"Income: ₦{saved_income}")
st.write(f"Expenses: ₦{total_expenses}")
st.write(f"Balance: ₦{balance}")


