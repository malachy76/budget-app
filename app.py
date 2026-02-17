



import streamlit as st
import bcrypt
from database import create_tables, get_connection

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

cursor.execute(
    "SELECT amount FROM income WHERE user_id=?",
    (user_id,)
)
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
    selected_list = st.selectbox(
        "Select expense list",
        list_dict.keys()
    )
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

# ---------------- DISPLAY EXPENSES ----------------
total_expenses = 0

if selected_list_id:
    st.subheader("📋 Expenses in Selected List")
    cursor.execute(
        "SELECT name, amount FROM expenses WHERE list_id=?",
        (selected_list_id,)
    )
    expenses = cursor.fetchall()

    if expenses:
        for name, amount in expenses:
            st.write(f"- {name}: ₦{amount}")
            total_expenses += amount
    else:
        st.write("No expenses yet.")

# ---------------- SUMMARY ----------------
st.subheader("📊 Summary")
st.write(f"Income: ₦{saved_income}")
st.write(f"Expenses (selected list): ₦{total_expenses}")
st.write(f"Balance: ₦{saved_income - total_expenses}")
