import streamlit as st
import bcrypt
import random
import re
import smtplib
import pandas as pd
from email.message import EmailMessage
from datetime import datetime, timedelta
from database import get_connection, create_tables

# ---------------- CONFIG ----------------
st.set_page_config("💰 Budget App", page_icon="💰", layout="centered")

# ---------- SCHEMA UPGRADE (adds missing columns/tables) ----------
def upgrade_schema():
    conn = get_connection()
    cursor = conn.cursor()

    # Add min_balance_alert to banks if not exists
    cursor.execute("PRAGMA table_info(banks)")
    columns = [col[1] for col in cursor.fetchall()]
    if "min_balance_alert" not in columns:
        cursor.execute("ALTER TABLE banks ADD COLUMN min_balance_alert INTEGER DEFAULT 0")

    # Add monthly_spending_limit to users if not exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if "monthly_spending_limit" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN monthly_spending_limit INTEGER")

    # Create goals table if not exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        target_amount INTEGER NOT NULL,
        current_amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active' CHECK(status IN ('active','completed')),
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()

# ---------------- INIT ----------------
create_tables()                # original tables from database.py
upgrade_schema()                # add new columns/tables

conn = get_connection()
cursor = conn.cursor()

# ---------------- SESSION ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "show_forgot_password" not in st.session_state:
    st.session_state.show_forgot_password = False
if "show_reset_form" not in st.session_state:
    st.session_state.show_reset_form = False
if "reset_email" not in st.session_state:
    st.session_state.reset_email = ""

# ---------------- PASSWORD STRENGTH CHECK ----------------
def is_strong_password(password):
    """Return (bool, message)"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character (!@#$%^&* etc.)."
    return True, "Strong password."

# ---------------- HELPER FUNCTIONS ----------------
def generate_code():
    return str(random.randint(100000, 999999))

def send_email(recipient, subject, body):
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = st.secrets["EMAIL_ADDRESS"]
        msg["To"] = recipient
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(st.secrets["EMAIL_ADDRESS"], st.secrets["EMAIL_PASSWORD"])
            smtp.send_message(msg)
        return True, "Email sent successfully!"
    except Exception as e:
        return False, str(e)

def send_verification_email(email, code):
    return send_email(email, "Verify Your Budget App Account", f"Your verification code is: {code}")

def send_reset_email(email, code):
    return send_email(email, "Password Reset Request",
                      f"Your password reset code is: {code}\n\nThis code will expire in 1 hour.")

# ------------------- PASSWORD RESET -------------------
def request_password_reset(email):
    cursor.execute("SELECT id FROM users WHERE email=?", (email,))
    user = cursor.fetchone()
    if not user:
        return False, "Email not found."

    user_id = user[0]
    token = generate_code()
    created_at = datetime.now().isoformat()
    expires_at = (datetime.now() + timedelta(hours=1)).isoformat()

    cursor.execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))
    cursor.execute("""
        INSERT INTO password_resets (user_id, token, created_at, expires_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, token, created_at, expires_at))
    conn.commit()

    success, message = send_reset_email(email, token)
    if success:
        return True, "Reset code sent to your email."
    else:
        return False, f"Failed to send email: {message}"

def reset_password(email, token, new_password):
    cursor.execute("SELECT id FROM users WHERE email=?", (email,))
    user = cursor.fetchone()
    if not user:
        return False, "Email not found."

    user_id = user[0]
    cursor.execute("""
        SELECT id FROM password_resets
        WHERE user_id=? AND token=? AND expires_at > ?
    """, (user_id, token, datetime.now().isoformat()))
    reset_record = cursor.fetchone()
    if not reset_record:
        return False, "Invalid or expired token."

    # Check password strength
    strong, msg = is_strong_password(new_password)
    if not strong:
        return False, msg

    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
    cursor.execute("UPDATE users SET password=? WHERE id=?", (hashed, user_id))
    cursor.execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))
    conn.commit()
    return True, "Password reset successfully. You can now log in."

# ------------------- CHANGE PASSWORD -------------------
def change_password(user_id, current_password, new_password):
    cursor.execute("SELECT password FROM users WHERE id=?", (user_id,))
    result = cursor.fetchone()
    if not result:
        return False, "User not found."

    stored_hash = result[0]
    if not bcrypt.checkpw(current_password.encode(), stored_hash):
        return False, "Current password is incorrect."

    strong, msg = is_strong_password(new_password)
    if not strong:
        return False, msg

    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
    cursor.execute("UPDATE users SET password=? WHERE id=?", (hashed, user_id))
    conn.commit()
    return True, "Password changed successfully."

# ------------------- RESEND VERIFICATION -------------------
def resend_verification(email):
    cursor.execute("SELECT id, email_verified FROM users WHERE email=?", (email,))
    user = cursor.fetchone()
    if not user:
        return False, "Email not found."
    if user[1] == 1:
        return False, "Email already verified."

    new_code = generate_code()
    cursor.execute("UPDATE users SET verification_code=? WHERE email=?", (new_code, email))
    conn.commit()
    success, message = send_verification_email(email, new_code)
    if success:
        return True, "New verification code sent."
    else:
        return False, f"Failed to send email: {message}"

# ------------------- REGISTER -------------------
def register_user(surname, other, email, username, password):
    # Check password strength
    strong, msg = is_strong_password(password)
    if not strong:
        return None, msg

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    code = generate_code()
    try:
        cursor.execute("""
        INSERT INTO users
        (surname, other_names, email, username, password, verification_code, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            surname, other, email, username,
            hashed, code, datetime.now().strftime("%Y-%m-%d")
        ))
        conn.commit()
        return code, "Success"
    except Exception as e:
        return None, "Username or email already exists."

# ------------------- LOGIN -------------------
def login_user(username, password):
    cursor.execute("SELECT id, password, email_verified FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    if not user:
        st.error("❌ Username not found.")
        return None

    user_id, stored_hash, email_verified = user
    if not bcrypt.checkpw(password.encode(), stored_hash):
        st.error("❌ Incorrect password.")
        return None

    if email_verified == 0:
        st.warning("⚠️ Please verify your email first. Check your inbox or request a new code.")
        return None

    return user_id

# ------------------- ALERTS -------------------
def check_alerts(user_id):
    """Return list of warning messages based on current data."""
    warnings = []

    # 1. Bank balance below min_balance_alert
    cursor.execute("SELECT bank_name, balance, min_balance_alert FROM banks WHERE user_id=?", (user_id,))
    banks = cursor.fetchall()
    for bank in banks:
        name, balance, alert = bank
        if alert and balance < alert:
            warnings.append(f"⚠️ Bank '{name}' balance (₦{balance:,.0f}) is below your alert threshold (₦{alert:,.0f}).")

    # 2. Monthly spending vs limit
    cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=?", (user_id,))
    limit_row = cursor.fetchone()
    if limit_row and limit_row[0]:
        limit = limit_row[0]
        current_month = datetime.now().strftime("%Y-%m")
        cursor.execute("""
            SELECT SUM(t.amount)
            FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id=? AND t.type='debit' AND strftime('%Y-%m', t.created_at)=?
        """, (user_id, current_month))
        spent = cursor.fetchone()[0] or 0
        if spent > limit:
            warnings.append(f"⚠️ You have spent ₦{spent:,.0f} this month, exceeding your limit of ₦{limit:,.0f}.")

    return warnings

# ---------------- UI ----------------
st.title("💰 Simple Budget App")

# ================= AUTH =================
if st.session_state.user_id is None:
    tabs = st.tabs(["🔐 Login", "📝 Register", "📧 Verify Email"])

    # ---------- LOGIN TAB ----------
    with tabs[0]:
        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input("Password", type="password", key="login_password")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Login", key="login_btn"):
                user_id = login_user(login_username, login_password)
                if user_id:
                    st.session_state.user_id = user_id
                    st.rerun()
        with col2:
            if st.button("Forgot Password?", key="forgot_btn"):
                st.session_state.show_forgot_password = True

        # Forgot password overlay
        if st.session_state.show_forgot_password:
            with st.expander("Reset Password", expanded=True):
                email_input = st.text_input("Enter your email", key="reset_email_input")
                if st.button("Send Reset Code", key="send_reset_btn"):
                    if email_input:
                        success, msg = request_password_reset(email_input)
                        if success:
                            st.success(msg)
                            st.session_state.show_forgot_password = False
                            st.session_state.show_reset_form = True
                            st.session_state.reset_email = email_input
                        else:
                            st.error(msg)
                    else:
                        st.warning("Please enter your email.")
                if st.button("Cancel", key="cancel_reset_btn"):
                    st.session_state.show_forgot_password = False
                    st.rerun()

        # Show reset code form if requested
        if st.session_state.show_reset_form:
            with st.expander("Enter Reset Code", expanded=True):
                reset_code = st.text_input("Reset code", key="reset_code")
                new_pass = st.text_input("New password", type="password", key="new_pass")
                confirm_pass = st.text_input("Confirm new password", type="password", key="confirm_pass")
                if st.button("Reset Password", key="do_reset_btn"):
                    if reset_code and new_pass and confirm_pass:
                        if new_pass == confirm_pass:
                            success, msg = reset_password(st.session_state.reset_email, reset_code, new_pass)
                            if success:
                                st.success(msg)
                                st.session_state.show_reset_form = False
                                st.session_state.reset_email = ""
                            else:
                                st.error(msg)
                        else:
                            st.error("Passwords do not match.")
                    else:
                        st.warning("All fields required.")
                if st.button("Cancel Reset", key="cancel_reset_form"):
                    st.session_state.show_reset_form = False
                    st.session_state.reset_email = ""
                    st.rerun()

    # ---------- REGISTER TAB ----------
    with tabs[1]:
        reg_surname = st.text_input("Surname", key="reg_surname")
        reg_other = st.text_input("Other Names", key="reg_other")
        reg_email = st.text_input("Email", key="reg_email")
        reg_username = st.text_input("Username", key="reg_username")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        st.caption("Password must be at least 8 characters, include uppercase, lowercase, digit, and special character.")

        if st.button("Register", key="register_btn"):
            if not all([reg_surname, reg_other, reg_email, reg_username, reg_password]):
                st.error("All fields required")
            else:
                code, msg = register_user(reg_surname, reg_other, reg_email, reg_username, reg_password)
                if code:
                    success, email_msg = send_verification_email(reg_email, code)
                    if success:
                        st.success("Account created. Check email to verify.")
                    else:
                        st.error(f"Account created but email failed: {email_msg}")
                else:
                    st.error(msg)

    # ---------- VERIFY EMAIL TAB (with resend) ----------
    with tabs[2]:
        verify_email = st.text_input("Registered Email", key="verify_email")
        verify_code = st.text_input("Verification Code", key="verify_code")

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Verify Email", key="verify_btn"):
                cursor.execute("""
                SELECT id FROM users
                WHERE email=? AND verification_code=?
                """, (verify_email, verify_code))
                user = cursor.fetchone()
                if user:
                    cursor.execute("""
                    UPDATE users
                    SET email_verified=1, verification_code=NULL
                    WHERE id=?
                    """, (user[0],))
                    conn.commit()
                    st.success("✅ Email verified. You can now log in.")
                else:
                    st.error("Invalid email or code.")
        with col2:
            if st.button("Resend Code", key="resend_btn"):
                if verify_email:
                    success, msg = resend_verification(verify_email)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("Enter your email first.")

    st.stop()  # Stop here if not logged in

# ================= DASHBOARD (Logged In) =================
user_id = st.session_state.user_id

cursor.execute("SELECT surname, other_names FROM users WHERE id=?", (user_id,))
user = cursor.fetchone()
st.success(f"Welcome {user[0]} {user[1]} 👋")

# ---------- MOBILE OPTIMIZATION CSS ----------
st.markdown("""
<style>
    /* Better touch targets */
    .stButton button {
        min-height: 48px;
        font-size: 16px;
    }
    
    /* Responsive columns on small screens */
    @media (max-width: 640px) {
        div[data-testid="column"] {
            width: 100% !important;
            margin-bottom: 1rem;
        }
    }
    
    /* Optional: hide Streamlit branding for a cleaner look */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ---------- DASHBOARD SUMMARY CARDS ----------
cursor.execute("SELECT SUM(balance) FROM banks WHERE user_id=?", (user_id,))
total_balance = cursor.fetchone()[0] or 0

current_month = datetime.now().strftime("%Y-%m")
cursor.execute("""
    SELECT SUM(t.amount)
    FROM transactions t
    JOIN banks b ON t.bank_id = b.id
    WHERE b.user_id = ? AND t.type = 'debit' AND strftime('%Y-%m', t.created_at) = ?
""", (user_id, current_month))
expenses_this_month = cursor.fetchone()[0] or 0

cursor.execute("SELECT COUNT(*) FROM banks WHERE user_id=?", (user_id,))
num_banks = cursor.fetchone()[0] or 0

cursor.execute("""
    SELECT SUM(CASE WHEN type='credit' THEN amount ELSE -amount END)
    FROM transactions t
    JOIN banks b ON t.bank_id = b.id
    WHERE b.user_id = ?
""", (user_id,))
net_savings = cursor.fetchone()[0] or 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 Total Balance", f"₦{total_balance:,.0f}")
with col2:
    st.metric("📉 Expenses This Month", f"₦{expenses_this_month:,.0f}")
with col3:
    st.metric("🏦 Bank Accounts", num_banks)
with col4:
    st.metric("🎯 Net Savings", f"₦{net_savings:,.0f}")

st.divider()

# ---------- ALERTS ----------
warnings = check_alerts(user_id)
if warnings:
    with st.expander("⚠️ Alerts", expanded=True):
        for w in warnings:
            st.warning(w)

# ---------- CHANGE PASSWORD ----------
with st.expander("🔐 Change Password"):
    current_pw = st.text_input("Current Password", type="password", key="current_pw")
    new_pw = st.text_input("New Password", type="password", key="new_pw")
    confirm_pw = st.text_input("Confirm New Password", type="password", key="confirm_pw")
    if st.button("Update Password", key="change_pw_btn"):
        if current_pw and new_pw and confirm_pw:
            if new_pw == confirm_pw:
                success, msg = change_password(user_id, current_pw, new_pw)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.error("New passwords do not match.")
        else:
            st.warning("All fields required.")

# ---------- ADD BANK (with min balance alert) ----------
st.subheader("🏦 Add Bank Account")
bank_name = st.text_input("Bank Name", key="bank_name")
account_name = st.text_input("Account Name", key="acct_name")
account_number = st.text_input("Account Number (last 4 digits)", key="acct_num")
opening_balance = st.number_input("Opening Balance (₦)", min_value=0, key="open_bal")
min_alert = st.number_input("Alert me if balance falls below (₦)", min_value=0, value=0, key="min_alert")
if st.button("Add Bank", key="add_bank_btn"):
    if bank_name and account_name and account_number:
        cursor.execute("""
        INSERT INTO banks (user_id, bank_name, account_name, account_number, balance, min_balance_alert)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, bank_name, account_name, account_number[-4:], opening_balance, min_alert))
        conn.commit()
        st.success("Bank added")
    else:
        st.warning("Please fill all fields.")

# ---------- MANAGE BANKS ----------
st.subheader("🏦 Manage Bank Accounts")

cursor.execute("""
    SELECT id, bank_name, account_name, account_number, balance
    FROM banks
    WHERE user_id=?
""", (user_id,))
banks_manage = cursor.fetchall()

if banks_manage:
    for bank in banks_manage:
        bank_id, name, acc_name, acc_num, balance = bank

        col1, col2, col3 = st.columns([4,1,1])

        with col1:
            st.markdown(f"**{name}** (****{acc_num}) — ₦{balance:,.0f}")

        with col2:
            if st.button("✏️", key=f"edit_bank_{bank_id}"):
                st.session_state.edit_bank_id = bank_id

        with col3:
            if st.button("🗑", key=f"delete_bank_{bank_id}"):
                cursor.execute("DELETE FROM banks WHERE id=?", (bank_id,))
                conn.commit()
                st.success("Bank deleted.")
                st.rerun()

    # -------- EDIT BANK --------
    if st.session_state.get("edit_bank_id"):
        edit_id = st.session_state.edit_bank_id

        cursor.execute("""
            SELECT bank_name, account_name, account_number
            FROM banks WHERE id=?
        """, (edit_id,))
        bank = cursor.fetchone()

        if bank:
            old_name, old_acc_name, old_acc_num = bank

            st.markdown("### ✏️ Edit Bank")
            new_name = st.text_input("Bank Name", value=old_name)
            new_acc_name = st.text_input("Account Name", value=old_acc_name)
            new_acc_num = st.text_input("Account Number", value=old_acc_num)

            if st.button("Update Bank"):
                cursor.execute("""
                    UPDATE banks
                    SET bank_name=?, account_name=?, account_number=?
                    WHERE id=?
                """, (new_name, new_acc_name, new_acc_num, edit_id))
                conn.commit()
                st.success("Bank updated.")
                st.session_state.edit_bank_id = None
                st.rerun()
else:
    st.info("No bank accounts yet.")

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
cursor.execute("SELECT id, bank_name FROM banks WHERE user_id = ?", (st.session_state.user["id"],))
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


# ===============================
# TRANSFER BETWEEN BANKS
# ===============================

st.divider()
st.subheader("🔁 Transfer Between Banks")

if len(user_banks) >= 2:

    bank_labels = list(bank_dict.keys())

    from_bank_label = st.selectbox("From Bank", bank_labels, key="from_bank")
    to_bank_label = st.selectbox("To Bank", bank_labels, key="to_bank")

    transfer_amount = st.number_input("Transfer Amount", min_value=1)

    if st.button("Transfer Money"):

        if from_bank_label == to_bank_label:
            st.error("Cannot transfer to same bank.")
        else:
            from_id = bank_dict[from_bank_label]
            to_id = bank_dict[to_bank_label]

            # Check balance
            cursor.execute("SELECT balance FROM banks WHERE id = ?", (from_id,))
            from_balance = cursor.fetchone()[0]

            if from_balance < transfer_amount:
                st.error("Insufficient balance.")
            else:
                # Deduct from source
                cursor.execute("UPDATE banks SET balance = balance - ? WHERE id = ?", (transfer_amount, from_id))

                # Add to destination
                cursor.execute("UPDATE banks SET balance = balance + ? WHERE id = ?", (transfer_amount, to_id))

                # Record transactions
                from datetime import datetime
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute("""
                    INSERT INTO transactions (bank_id, type, amount, description, created_at)
                    VALUES (?, 'debit', ?, 'Transfer to another bank', ?)
                """, (from_id, transfer_amount, now))

                cursor.execute("""
                    INSERT INTO transactions (bank_id, type, amount, description, created_at)
                    VALUES (?, 'credit', ?, 'Transfer from another bank', ?)
                """, (to_id, transfer_amount, now))

                conn.commit()
                st.success("Transfer successful!")
                st.rerun()

else:
    st.info("You need at least two banks to make a transfer.")

# ---------- LOGOUT ----------
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.rerun()



