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
if "selected_list_id" not in st.session_state:
    st.session_state.selected_list_id = None

# ---------------- AUTH FUNCTIONS ----------------
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
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        conn.commit()
        return True
    except:
        return False

# ---------------- LOGIN / REGISTER ----------------
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                if login(u, p):
                    st.success("Logged in successfully")
                    st.rerun()
                else:
                    st.error("Invalid username or password")

    with tab2:
        with st.form("register_form"):
            nu = st.text_input("New Username")
            np = st.text_input("New Password", type="password")
            submitted = st.form_submit_button("Register")
            if submitted:
                if register(nu, np):
                    st.success("Account created. Please login.")
                else:
                    st.error("Username already exists")
    st.stop()

user_id = st.session_state.user_id

# ---------------- LOGOUT ----------------
if st.button("Logout"):
    st.session_state.user_id = None
    st.session_state.selected_list_id = None
    st.rerun()

# ---------------- INCOME ----------------
st.subheader("💵 Income")
with st.form("income_form"):
    cursor.execute("SELECT amount FROM income WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    saved_income = row[0] if row else 0
    income = st.number_input("Enter your income", value=saved_income, min_value=0)
    if st.form_submit_button("Save Income"):
        if row:
            cursor.execute("UPDATE income SET amount=? WHERE user_id=?", (income, user_id))
        else:
            cursor.execute("INSERT INTO income (user_id, amount) VALUES (?, ?)", (user_id, income))
        conn.commit()
        st.success("Income saved")

# ---------------- EXPENSE LISTS ----------------
st.subheader("📂 Expense Lists")
with st.form("expense_list_form"):
    new_list = st.text_input("Create new expense list (e.g. Food, Transport)")
    if st.form_submit_button("Create Expense List") and new_list:
        cursor.execute("INSERT INTO expense_lists (user_id, name) VALUES (?, ?)", (user_id, new_list))
        conn.commit()
        st.success("Expense list created")

cursor.execute("SELECT id, name FROM expense_lists WHERE user_id=?", (user_id,))
lists = cursor.fetchall()
list_dict = {name: list_id for list_id, name in lists}

if lists:
    selected_list = st.selectbox("Select expense list", list_dict.keys())
    st.session_state.selected_list_id = list_dict[selected_list]
else:
    st.info("👆 Create your first expense list to start adding expenses.")

# ---------------- ADD EXPENSE ----------------
if st.session_state.selected_list_id:
    st.subheader("➕ Add Expense")
    with st.form("add_expense_form"):
        ename = st.text_input("Expense name")
        eamount = st.number_input("Expense amount", min_value=0)
        if st.form_submit_button("Add Expense"):
            if ename and eamount > 0:
                cursor.execute(
                    "INSERT INTO expenses (list_id, name, amount) VALUES (?, ?, ?)",
                    (st.session_state.selected_list_id, ename, eamount)
                )
                conn.commit()
                st.success("Expense added")

# ---------------- DISPLAY EXPENSES ----------------
total_expenses = 0
if st.session_state.selected_list_id:
    st.subheader("📋 Expenses in Selected List")
    cursor.execute("SELECT name, amount FROM expenses WHERE list_id=?", (st.session_state.selected_list_id,))
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
