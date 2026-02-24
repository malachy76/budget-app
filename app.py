import streamlit as st
import sqlite3
import bcrypt
import pandas as pd
from datetime import datetime, timedelta

# ---------------- DATABASE CONNECTION ----------------
DB_NAME = "budget_app.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

conn = get_connection()
cursor = conn.cursor()

# ---------------- SESSION STATE ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "show_forgot_password" not in st.session_state:
    st.session_state.show_forgot_password = False
if "show_reset_form" not in st.session_state:
    st.session_state.show_reset_form = False
if "reset_email" not in st.session_state:
    st.session_state.reset_email = ""
if "edit_exp_id" not in st.session_state:
    st.session_state.edit_exp_id = None
if "edit_bank_id" not in st.session_state:
    st.session_state.edit_bank_id = None
if "selected_goal" not in st.session_state:
    st.session_state.selected_goal = None
if "show_goal_contribution" not in st.session_state:
    st.session_state.show_goal_contribution = False
if "transfer_from_bank" not in st.session_state:
    st.session_state.transfer_from_bank = None
if "transfer_to_bank" not in st.session_state:
    st.session_state.transfer_to_bank = None

# ---------------- UTILITY FUNCTIONS ----------------
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

# Placeholder functions for user management (replace with your implementations)
def login_user(username, password):
    cursor.execute("SELECT id, password FROM users WHERE username=?", (username,))
    row = cursor.fetchone()
    if row and check_password(password, row[1]):
        return row[0]
    return None

def register_user(surname, other_names, email, username, password):
    try:
        hashed = hash_password(password)
        cursor.execute("""
            INSERT INTO users (surname, other_names, email, username, password, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (surname, other_names, email, username, hashed, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        return True, "Registered successfully"
    except Exception as e:
        return False, str(e)

# ---------------- UI ----------------
st.set_page_config("💰 Budget App", layout="wide")

st.title("💰 Simple Budget App")

# ================= AUTH =================
if st.session_state.user_id is None:
    tabs = st.tabs(["🔐 Login", "📝 Register"])
    # ---------- LOGIN ----------
    with tabs[0]:
        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            user_id = login_user(login_username, login_password)
            if user_id:
                st.session_state.user_id = user_id
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    # ---------- REGISTER ----------
    with tabs[1]:
        reg_surname = st.text_input("Surname", key="reg_surname")
        reg_other = st.text_input("Other Names", key="reg_other")
        reg_email = st.text_input("Email", key="reg_email")
        reg_username = st.text_input("Username", key="reg_username")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        if st.button("Register"):
            success, msg = register_user(reg_surname, reg_other, reg_email, reg_username, reg_password)
            if success:
                st.success(msg)
            else:
                st.error(msg)
    st.stop()

user_id = st.session_state.user_id

# ---------------- DASHBOARD ----------------
st.header("🏠 Dashboard")

# Fetch user
cursor.execute("SELECT surname, other_names, email FROM users WHERE id=?", (user_id,))
user = cursor.fetchone()
st.success(f"Welcome {user[0]} {user[1]} 👋")

# ---------------- DASHBOARD CARDS ----------------
col1, col2, col3, col4 = st.columns(4)
cursor.execute("SELECT SUM(balance) FROM banks WHERE user_id=?", (user_id,))
total_balance = cursor.fetchone()[0] or 0
col1.metric("💰 Total Balance", f"₦{total_balance:,.0f}")

current_month = datetime.now().strftime("%Y-%m")
cursor.execute("""
    SELECT SUM(t.amount)
    FROM transactions t
    JOIN banks b ON t.bank_id=b.id
    WHERE b.user_id=? AND t.type='debit' AND strftime('%Y-%m', t.created_at)=?
""", (user_id, current_month))
expenses_this_month = cursor.fetchone()[0] or 0
col2.metric("📉 Expenses This Month", f"₦{expenses_this_month:,.0f}")

cursor.execute("SELECT COUNT(*) FROM banks WHERE user_id=?", (user_id,))
num_banks = cursor.fetchone()[0] or 0
col3.metric("🏦 Bank Accounts", num_banks)

cursor.execute("""
    SELECT SUM(CASE WHEN type='credit' THEN amount ELSE -amount END)
    FROM transactions t
    JOIN banks b ON t.bank_id=b.id
    WHERE b.user_id=?
""", (user_id,))
net_savings = cursor.fetchone()[0] or 0
col4.metric("🎯 Net Savings", f"₦{net_savings:,.0f}")

st.divider()

# ---------------- BANK MANAGEMENT ----------------
st.subheader("🏦 Your Banks")
cursor.execute("SELECT id, bank_name, account_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
banks = cursor.fetchall()
for b in banks:
    bank_id, bank_name, acc_name, acc_num, balance = b
    col1, col2, col3 = st.columns([4,1,1])
    with col1:
        st.write(f"**{bank_name}** (****{acc_num}) — ₦{balance:,.0f}")
    with col2:
        if st.button("✏️", key=f"edit_bank_{bank_id}"):
            st.session_state.edit_bank_id = bank_id
    with col3:
        if st.button("🗑", key=f"delete_bank_{bank_id}"):
            cursor.execute("DELETE FROM banks WHERE id=?", (bank_id,))
            conn.commit()
            st.success("Bank deleted")
            st.experimental_rerun()

# Edit bank form
if st.session_state.edit_bank_id:
    cursor.execute("SELECT bank_name, account_name, account_number FROM banks WHERE id=?", (st.session_state.edit_bank_id,))
    bank = cursor.fetchone()
    new_name = st.text_input("Bank Name", value=bank[0])
    new_acc_name = st.text_input("Account Name", value=bank[1])
    new_acc_num = st.text_input("Account Number", value=bank[2])
    if st.button("Update Bank"):
        cursor.execute("UPDATE banks SET bank_name=?, account_name=?, account_number=? WHERE id=?",
                       (new_name, new_acc_name, new_acc_num, st.session_state.edit_bank_id))
        conn.commit()
        st.success("Bank updated")
        st.session_state.edit_bank_id = None
        st.experimental_rerun()

# ---------------- BANK TO BANK TRANSFER ----------------
st.subheader("💸 Transfer Between Banks")
cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
banks_list = cursor.fetchall()
if banks_list and len(banks_list) > 1:
    bank_options = {f"{b[1]} (****{b[2]}) — ₦{b[3]:,.0f}": b[0] for b in banks_list}
    from_bank_name = st.selectbox("From Bank", list(bank_options.keys()), key="from_bank_select")
    to_bank_name = st.selectbox("To Bank", list(bank_options.keys()), key="to_bank_select")
    transfer_amount = st.number_input("Amount (₦)", min_value=1, key="transfer_amt")
    if st.button("Transfer"):
        from_id = bank_options[from_bank_name]
        to_id = bank_options[to_bank_name]
        if from_id == to_id:
            st.warning("Cannot transfer to the same bank.")
        else:
            # Check balance
            cursor.execute("SELECT balance FROM banks WHERE id=?", (from_id,))
            from_balance = cursor.fetchone()[0]
            if transfer_amount > from_balance:
                st.error("Insufficient funds.")
            else:
                # Deduct and add
                cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (transfer_amount, from_id))
                cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (transfer_amount, to_id))
                # Record transactions
                cursor.execute("INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (?, 'debit', ?, ?, ?)",
                               (from_id, transfer_amount, f"Transfer to bank {to_id}", datetime.now().strftime("%Y-%m-%d")))
                cursor.execute("INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (?, 'credit', ?, ?, ?)",
                               (to_id, transfer_amount, f"Transfer from bank {from_id}", datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.success("Transfer successful")
else:
    st.info("You need at least 2 bank accounts to transfer between them.")

# ---------------- EXPENSES / INCOME ----------------
# (You can paste your existing expense & income code here. It will work safely.)

# ---------- ADD EXPENSE ----------
st.subheader("➕ Add Expense (Auto Bank Debit)")
expense_name = st.text_input("Expense Name", key="exp_name")
expense_amount = st.number_input("Amount (₦)", min_value=1, key="exp_amt")

cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
banks = cursor.fetchall()

if banks:
    bank_map = {f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0] for b in banks}
    selected_bank = st.selectbox("Pay From Bank", list(bank_map.keys()), key="bank_select")
    if st.button("Add Expense", key="add_expense_btn"):
        if expense_name and expense_amount > 0:
            bank_id = bank_map[selected_bank]
            cursor.execute("""
                INSERT INTO expenses (user_id, bank_id, name, amount, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, bank_id, expense_name, expense_amount, datetime.now().strftime("%Y-%m-%d")))
            cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (expense_amount, bank_id))
            cursor.execute("""
                INSERT INTO transactions (bank_id, type, amount, description, created_at)
                VALUES (?, 'debit', ?, ?, ?)
            """, (bank_id, expense_amount, f"Expense: {expense_name}", datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success("Expense added & bank debited")
            st.rerun()   # to refresh alerts
        else:
            st.warning("Please enter a name and amount.")
else:
    st.info("Add a bank account first")

# ---------- EXPENSE SUMMARY (EDIT & DELETE SAFE VERSION) ----------
st.subheader("📋 Expense Summary")

cursor.execute("""
    SELECT e.id, e.created_at, e.name, e.amount, e.bank_id,
           b.bank_name, b.account_number
    FROM expenses e
    JOIN banks b ON e.bank_id = b.id
    WHERE e.user_id = ?
    ORDER BY e.created_at DESC
""", (user_id,))
expenses_data = cursor.fetchall()

if expenses_data:
    for exp in expenses_data:
        exp_id, date, name, amount, bank_id, bank_name, acc_num = exp

        col1, col2, col3, col4, col5, col6 = st.columns([2,2,2,2,1,1])
        col1.write(date)
        col2.write(name)
        col3.write(f"₦{amount:,.0f}")
        col4.write(f"{bank_name} (****{acc_num})")

        if col5.button("✏️", key=f"edit_exp_{exp_id}"):
            st.session_state.edit_exp_id = exp_id

        if col6.button("🗑", key=f"delete_exp_{exp_id}"):
            # Refund bank first
            cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (amount, bank_id))
            cursor.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
            conn.commit()
            st.success("Expense deleted & bank refunded.")
            st.rerun()

    # -------- EDIT FORM --------
    if st.session_state.get("edit_exp_id"):
        edit_id = st.session_state.edit_exp_id

        cursor.execute("""
            SELECT name, amount, bank_id
            FROM expenses WHERE id=?
        """, (edit_id,))
        exp = cursor.fetchone()

        if exp:
            old_name, old_amount, old_bank_id = exp

            st.markdown("### ✏️ Edit Expense")
            new_name = st.text_input("Expense Name", value=old_name)
            new_amount = st.number_input("Amount (₦)", min_value=1, value=old_amount)

            if st.button("Update Expense"):
                difference = new_amount - old_amount

                # Adjust bank balance correctly
                cursor.execute(
                    "UPDATE banks SET balance = balance - ? WHERE id=?",
                    (difference, old_bank_id)
                )

                cursor.execute("""
                    UPDATE expenses
                    SET name=?, amount=?
                    WHERE id=?
                """, (new_name, new_amount, edit_id))

                conn.commit()
                st.success("Expense updated safely.")
                st.session_state.edit_exp_id = None
                st.rerun()
else:
    st.info("No expenses recorded yet.")

# ---------- ADD INCOME ----------
st.subheader("💰 Add Income (Credit to Bank)")
income_source = st.text_input("Income Source", key="income_source")
income_amount = st.number_input("Amount (₦)", min_value=1, key="income_amt")

cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
banks_for_income = cursor.fetchall()
if banks_for_income:
    bank_map_income = {f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0] for b in banks_for_income}
    selected_bank_income = st.selectbox("Deposit To Bank", list(bank_map_income.keys()), key="bank_income_select")
    if st.button("Add Income", key="add_income_btn"):
        if income_source and income_amount > 0:
            bank_id = bank_map_income[selected_bank_income]
            cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (income_amount, bank_id))
            cursor.execute("""
                INSERT INTO transactions (bank_id, type, amount, description, created_at)
                VALUES (?, 'credit', ?, ?, ?)
            """, (bank_id, income_amount, f"Income: {income_source}", datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success(f"Income of ₦{income_amount:,} added.")
        else:
            st.warning("Please enter a source and amount.")
else:
    st.info("You need at least one bank account to add income.")

# ---------- SAVINGS GOALS ----------
st.subheader("🎯 Savings Goals")

# Display existing goals
cursor.execute("""
    SELECT id, name, target_amount, current_amount, status
    FROM goals
    WHERE user_id=?
    ORDER BY status, created_at DESC
""", (user_id,))
goals = cursor.fetchall()

if goals:
    for goal in goals:
        goal_id, name, target, current, status = goal
        progress = (current / target) * 100 if target > 0 else 0
    with st.container():
        col1, col2, col3, col4 = st.columns([3,1,1,1])

    with col1:
        st.markdown(f"**{name}**")
        st.progress(min(progress/100, 1.0), text=f"₦{current:,.0f} / ₦{target:,.0f} ({progress:.1f}%)")

    with col2:
        st.markdown(f"Status: **{status}**")

    with col3:
        if status == "active":
            if st.button("Add Money", key=f"add_goal_{goal_id}"):
                st.session_state.selected_goal = goal_id
                st.session_state.show_goal_contribution = True

    with col4:
        if st.button("🗑", key=f"delete_goal_{goal_id}"):
            cursor.execute("DELETE FROM goals WHERE id=?", (goal_id,))
            conn.commit()
            st.success("Goal deleted.")
            st.rerun()
        st.divider()
else:
    st.info("No savings goals yet. Create one below.")

# Create new goal form
with st.expander("➕ Create New Goal"):
    goal_name = st.text_input("Goal Name", key="goal_name")
    goal_target = st.number_input("Target Amount (₦)", min_value=1, key="goal_target")
    if st.button("Create Goal", key="create_goal_btn"):
        if goal_name and goal_target > 0:
            cursor.execute("""
                INSERT INTO goals (user_id, name, target_amount, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, goal_name, goal_target, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success("Goal created!")
            st.rerun()
        else:
            st.warning("Please enter a name and target.")

# Contribution form (shown when Add Money clicked)
if st.session_state.get("show_goal_contribution") and st.session_state.get("selected_goal"):
    goal_id = st.session_state.selected_goal
    # Fetch goal details
    cursor.execute("SELECT name, target_amount, current_amount FROM goals WHERE id=?", (goal_id,))
    g = cursor.fetchone()
    if g:
        g_name, g_target, g_current = g
        st.write(f"**Add money to '{g_name}'**")
        # Get user's banks
        cursor.execute("SELECT id, bank_name, balance FROM banks WHERE user_id=?", (user_id,))
        bank_list = cursor.fetchall()
        if bank_list:
            bank_options = {f"{b[1]} (₦{b[2]:,})": b[0] for b in bank_list}
            selected_bank = st.selectbox("From Bank", list(bank_options.keys()), key="goal_bank")
            contrib_amount = st.number_input("Amount to add (₦)", min_value=1, key="goal_amount")
            if st.button("Confirm Contribution", key="confirm_goal_contrib"):
                bank_id = bank_options[selected_bank]
                # Check bank balance
                cursor.execute("SELECT balance FROM banks WHERE id=?", (bank_id,))
                bank_balance = cursor.fetchone()[0]
                if contrib_amount > bank_balance:
                    st.error("Insufficient funds in selected bank.")
                else:
                    # Deduct from bank, add to goal
                    cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (contrib_amount, bank_id))
                    new_current = g_current + contrib_amount
                    new_status = "completed" if new_current >= g_target else "active"
                    cursor.execute("""
                        UPDATE goals
                        SET current_amount = ?, status = ?
                        WHERE id = ?
                    """, (new_current, new_status, goal_id))
                    # Record transaction (optional - we can record as a transfer, but for simplicity we skip)
                    conn.commit()
                    st.success(f"Added ₦{contrib_amount:,.0f} to goal.")
                    st.session_state.show_goal_contribution = False
                    st.rerun()
        else:
            st.warning("You need a bank account to transfer from.")
    else:
        st.session_state.show_goal_contribution = False

# ---------- ALERT SETTINGS ----------
with st.expander("🔔 Alert Settings"):
    # Monthly spending limit
    cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=?", (user_id,))
    current_limit = cursor.fetchone()[0]
    new_limit = st.number_input("Monthly Spending Limit (₦) – 0 = no limit", min_value=0, value=current_limit or 0, key="monthly_limit")
    if st.button("Update Spending Limit", key="update_limit_btn"):
        cursor.execute("UPDATE users SET monthly_spending_limit = ? WHERE id=?", (new_limit, user_id))
        conn.commit()
        st.success("Monthly limit updated.")
        st.rerun()

    # Note: per‑bank alerts are set when adding/editing bank. Editing not yet implemented.

# ---------- INCOME VS EXPENSES CHART ----------
st.subheader("📊 Income vs Expenses Over Time")
period_map = {
    "Last 30 Days": timedelta(days=30),
    "Last 3 Months": timedelta(days=90),
    "Last 6 Months": timedelta(days=180),
    "Last Year": timedelta(days=365),
    "All Time": None
}
selected_period = st.selectbox("Select Period", list(period_map.keys()), key="period_select")
if period_map[selected_period]:
    start_date = (datetime.now() - period_map[selected_period]).date()
else:
    start_date = datetime(2000, 1, 1).date()
start_str = start_date.strftime("%Y-%m-%d")

cursor.execute("""
    SELECT t.created_at, t.type, t.amount
    FROM transactions t
    JOIN banks b ON t.bank_id = b.id
    WHERE b.user_id = ? AND t.created_at >= ?
    ORDER BY t.created_at
""", (user_id, start_str))
rows = cursor.fetchall()
if rows:
    df = pd.DataFrame(rows, columns=["date", "type", "amount"])
    df["date"] = pd.to_datetime(df["date"])
    df_pivot = df.pivot_table(index="date", columns="type", values="amount", aggfunc="sum", fill_value=0)
    for col in ["credit", "debit"]:
        if col not in df_pivot.columns:
            df_pivot[col] = 0
    df_pivot = df_pivot.rename(columns={"credit": "Income", "debit": "Expenses"}).sort_index()
    st.line_chart(df_pivot[["Income", "Expenses"]])
    st.bar_chart(df_pivot[["Income", "Expenses"]])
else:
    st.info("No transactions in this period.")
# ===============================
# TRANSACTION MANAGEMENT SECTION
# ===============================

st.divider()
st.subheader("💳 Transaction Management")

conn = get_connection()
cursor = conn.cursor()

# Get user banks
cursor.execute("SELECT id, bank_name FROM banks WHERE user_id = ?", (st.session_state.user_id,))
user_banks = cursor.fetchall()

if user_banks:

    bank_dict = {f"{b[1]} (ID:{b[0]})": b[0] for b in user_banks}

    selected_bank_label = st.selectbox("Select Bank", list(bank_dict.keys()))
    selected_bank_id = bank_dict[selected_bank_label]

    # Show Transactions
    cursor.execute("""
        SELECT id, type, amount, description, created_at
        FROM transactions
        WHERE bank_id = ?
        ORDER BY id DESC
    """, (selected_bank_id,))
    
    transactions = cursor.fetchall()

    if transactions:
        st.write("### 📜 Transactions")

        for t in transactions:
            t_id, t_type, t_amount, t_desc, t_date = t
            
            col1, col2, col3, col4 = st.columns([3,1,1,1])
            
            with col1:
                st.write(f"**{t_type.upper()}** - ₦{t_amount} | {t_desc} | {t_date}")

            # EDIT
            with col2:
                if st.button("✏️ Edit", key=f"edit_tx_{t_id}"):
                    st.session_state.edit_tx_id = t_id

            # DELETE
            with col3:
                if st.button("🗑 Delete", key=f"delete_tx_{t_id}"):

                    # Reverse balance first
                    cursor.execute("SELECT type, amount FROM transactions WHERE id = ?", (t_id,))
                    old = cursor.fetchone()

                    if old:
                        old_type, old_amount = old

                        if old_type == "credit":
                            cursor.execute("UPDATE banks SET balance = balance - ? WHERE id = ?", (old_amount, selected_bank_id))
                        else:
                            cursor.execute("UPDATE banks SET balance = balance + ? WHERE id = ?", (old_amount, selected_bank_id))

                    cursor.execute("DELETE FROM transactions WHERE id = ?", (t_id,))
                    conn.commit()
                    st.success("Transaction deleted successfully")
                    st.rerun()

        # EDIT FORM
        if "edit_tx_id" in st.session_state:

            st.write("### ✏️ Edit Transaction")

            cursor.execute("""
                SELECT type, amount, description
                FROM transactions
                WHERE id = ?
            """, (st.session_state.edit_tx_id,))
            
            old_data = cursor.fetchone()

            if old_data:
                old_type, old_amount, old_desc = old_data

                new_type = st.selectbox("Type", ["credit", "debit"], index=0 if old_type=="credit" else 1)
                new_amount = st.number_input("Amount", value=old_amount)
                new_desc = st.text_input("Description", value=old_desc)

                if st.button("Update Transaction"):

                    # Reverse old balance
                    if old_type == "credit":
                        cursor.execute("UPDATE banks SET balance = balance - ? WHERE id = ?", (old_amount, selected_bank_id))
                    else:
                        cursor.execute("UPDATE banks SET balance = balance + ? WHERE id = ?", (old_amount, selected_bank_id))

                    # Apply new balance
                    if new_type == "credit":
                        cursor.execute("UPDATE banks SET balance = balance + ? WHERE id = ?", (new_amount, selected_bank_id))
                    else:
                        cursor.execute("UPDATE banks SET balance = balance - ? WHERE id = ?", (new_amount, selected_bank_id))

                    cursor.execute("""
                        UPDATE transactions
                        SET type = ?, amount = ?, description = ?
                        WHERE id = ?
                    """, (new_type, new_amount, new_desc, st.session_state.edit_tx_id))

                    conn.commit()
                    del st.session_state.edit_tx_id
                    st.success("Transaction updated successfully")
                    st.rerun()

    else:
        st.info("No transactions found for this bank.")

else:
    st.warning("You have no bank accounts yet.")


# ---------------- ADMIN PANEL ----------------
st.subheader("🛠 Admin Control (Users & Banks)")
if user[2] == "budgetingsmart00@gmail.com":  # replace this with your admin check
    st.markdown("### Users")
    cursor.execute("SELECT id, surname, other_names, username, email FROM users")
    all_users = cursor.fetchall()
    st.table(all_users)
    st.markdown("### All Banks")
    cursor.execute("SELECT id, user_id, bank_name, balance FROM banks")
    all_banks = cursor.fetchall()
    st.table(all_banks)
    st.markdown("### All Transactions")
    cursor.execute("SELECT id, bank_id, type, amount, description, created_at FROM transactions ORDER BY created_at DESC")
    all_tx = cursor.fetchall()
    st.table(all_tx)

# ---------------- LOGOUT ----------------
if st.button("Logout"):
    st.session_state.user_id = None
    st.experimental_rerun()
