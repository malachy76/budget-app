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
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if login(u, p):
                st.rerun()
            else:
                st.error("Invalid login")

    with tab2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        if st.button("Register"):
            if register(nu, np):
                st.success("Account created. Login now.")
            else:
                st.error("Username exists")

    st.stop()

user_id = st.session_state.user_id

# ---------------- LOGOUT ----------------
if st.button("Logout"):
    st.session_state.user_id = None
    st.rerun()

# ---------------- INCOME ----------------
st.subheader("💵 Income")
income = st.number_input("Enter income", min_value=0)

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

# ---------------- EXPENSE LISTS ----------------
st.subheader("📂 Expense Lists")

new_list = st.text_input("Create new expense list (e.g. Food, Transport)")
if st.button("Create List"):
    if new_list:
        cursor.execute(
            "INSERT INTO expense_lists (user_id, name) VALUES (?, ?)",
            (user_id, new_list)
        )
        conn.commit()
        st.success("List created")

cursor.execute(
    "SELECT id, name FROM expense_lists WHERE user_id=?",
    (user_id,)
)
lists = cursor.fetchall()

if not lists:
    st.info("Create an expense list to start adding expenses.")
    st.stop()

list_dict = {name: list_id for list_id, name in lists}
selected_list = st.selectbox("Select expense list", list_dict.keys())
selected_list_id = list_dict[selected_list]

# ---------------- ADD EXPENSE ----------------
st.subheader("➕ Add Expense")
ename = st.text_input("Expense name")
eamount = st.number_input("Amount", min_value=0)

if st.button("Add Expense"):
    if ename and eamount > 0:
        cursor.execute(
            "INSERT INTO expenses (list_id, name, amount) VALUES (?, ?, ?)",
            (selected_list_id, ename, eamount)
        )
        conn.commit()
        st.success("Expense added")

# ---------------- DISPLAY EXPENSES ----------------
st.subheader(f"📋 Expenses in {selected_list}")

cursor.execute(
    "SELECT name, amount FROM expenses WHERE list_id=?",
    (selected_list_id,)
)
expenses = cursor.fetchall()

total_expenses = 0
for name, amount in expenses:
    st.write(f"- {name}: ₦{amount}")
    total_expenses += amount

balance = saved_income - total_expenses

# ---------------- SUMMARY ----------------
st.subheader("📊 Summary")
st.write(f"Income: ₦{saved_income}")
st.write(f"Expenses (this list): ₦{total_expenses}")
st.write(f"Balance: ₦{balance}")






