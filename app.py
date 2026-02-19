import streamlit as st
import bcrypt
import random
import smtplib
import pandas as pd
from email.message import EmailMessage
from datetime import datetime, timedelta
from database import get_connection, create_tables

# ---------------- CONFIG ----------------
st.set_page_config("💰 Budget App", page_icon="💰", layout="centered")

# Create all tables (including password_resets if missing)
create_tables()
conn = get_connection()
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")
conn.commit()
conn.close()

# Reopen connection for the app
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
        return code
    except Exception:
        return None

# ------------------- LOGIN (WITH CLEAR FEEDBACK) -------------------
def login_user(username, password):
    """
    Returns:
        - user_id (int) on success
        - None on failure (error message is shown via st.error/warning inside the function)
    """
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

        if st.button("Register", key="register_btn"):
            if not all([reg_surname, reg_other, reg_email, reg_username, reg_password]):
                st.error("All fields required")
            else:
                code = register_user(reg_surname, reg_other, reg_email, reg_username, reg_password)
                if code:
                    success, msg = send_verification_email(reg_email, code)
                    if success:
                        st.success("Account created. Check email to verify.")
                    else:
                        st.error(f"Account created but email failed: {msg}")
                else:
                    st.error("Username or email already exists.")

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

# ---------- ADD BANK ----------
st.subheader("🏦 Add Bank Account")
bank_name = st.text_input("Bank Name", key="bank_name")
account_name = st.text_input("Account Name", key="acct_name")
account_number = st.text_input("Account Number (last 4 digits)", key="acct_num")
opening_balance = st.number_input("Opening Balance (₦)", min_value=0, key="open_bal")
if st.button("Add Bank", key="add_bank_btn"):
    if bank_name and account_name and account_number:
        cursor.execute("""
        INSERT INTO banks (user_id, bank_name, account_name, account_number, balance)
        VALUES (?, ?, ?, ?, ?)
        """, (user_id, bank_name, account_name, account_number[-4:], opening_balance))
        conn.commit()
        st.success("Bank added")
    else:
        st.warning("Please fill all fields.")

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
        else:
            st.warning("Please enter a name and amount.")
else:
    st.info("Add a bank account first")

# ---------- EXPENSE SUMMARY ----------
st.subheader("📋 Expense Summary")
cursor.execute("""
    SELECT e.created_at, e.name, e.amount, b.bank_name, b.account_number
    FROM expenses e
    JOIN banks b ON e.bank_id = b.id
    WHERE e.user_id = ?
    ORDER BY e.created_at DESC
""", (user_id,))
expenses_data = cursor.fetchall()
if expenses_data:
    df_expenses = pd.DataFrame(expenses_data, columns=["Date", "Expense Name", "Amount (₦)", "Bank", "Account"])
    st.dataframe(df_expenses, use_container_width=True)
    st.caption("💰 Total per category:")
    expense_summary = df_expenses.groupby("Expense Name")["Amount (₦)"].sum().reset_index().sort_values("Amount (₦)", ascending=False)
    st.bar_chart(expense_summary.set_index("Expense Name"))
    st.caption("📅 Daily expenses:")
    df_expenses_daily = df_expenses.copy()
    df_expenses_daily["Date"] = pd.to_datetime(df_expenses_daily["Date"])
    daily_expenses = df_expenses_daily.groupby(df_expenses_daily["Date"].dt.date)["Amount (₦)"].sum()
    st.line_chart(daily_expenses)
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

# ---------- LOGOUT ----------
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.rerun()
