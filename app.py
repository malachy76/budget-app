# -*- coding: utf-8 -*-
import streamlit as st
st.set_page_config(page_title="Budgeting Smart", page_icon="\U0001f4b0", layout="wide")

# ============================================================
# COOKIE-BASED PERSISTENT LOGIN
# ============================================================
from streamlit_cookies_manager import EncryptedCookieManager

# Cookie encryption password now lives in st.secrets["COOKIE_PASSWORD"]
# Add this key to your Streamlit secrets: COOKIE_PASSWORD = "your-secret-here"
cookies = EncryptedCookieManager(
    prefix="budget_right_",
    password=st.secrets["COOKIE_PASSWORD"]
)

if not cookies.ready():
    st.stop()

# ---------------- MOBILE CSS ----------------
st.markdown("""
<style>
html, body { overflow-x: hidden !important; }
.main .block-container { max-width: 100% !important; }

@media screen and (max-width: 640px) {
    .main .block-container { padding: 0.6rem 0.7rem 1rem 0.7rem !important; }
    h1 { font-size: 1.4rem !important; line-height: 1.3 !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; }
    div[data-testid="stHorizontalBlock"] { flex-direction: column !important; gap: 0.4rem !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] {
        width: 100% !important; min-width: 100% !important; flex: 1 1 100% !important;
    }
    div[data-testid="stMetric"] {
        background: #1a3c5e !important; border: 1px solid #0e7c5b !important;
        border-radius: 10px !important; padding: 0.65rem 0.8rem !important; margin-bottom: 0.4rem !important;
    }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricLabel"],
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] p,
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] div {
        color: #a8d8c8 !important; font-size: 0.8rem !important; font-weight: 600 !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricValue"] div,
    div[data-testid="stMetric"] [data-testid="stMetricValue"] p {
        color: #ffffff !important; font-size: 1.25rem !important; font-weight: 800 !important;
    }
    .stButton > button {
        width: 100% !important; min-height: 2.8rem !important;
        font-size: 0.98rem !important; border-radius: 8px !important; margin-bottom: 0.3rem !important;
    }
    input, textarea,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    div[data-baseweb="select"] {
        font-size: 1rem !important; min-height: 2.6rem !important;
        width: 100% !important; box-sizing: border-box !important;
    }
    div[data-testid="stTabs"] > div:first-child {
        overflow-x: auto !important; -webkit-overflow-scrolling: touch !important;
        white-space: nowrap !important; scrollbar-width: none !important;
    }
    div[data-testid="stTabs"] > div:first-child::-webkit-scrollbar { display: none !important; }
    section[data-testid="stSidebar"] { min-width: 200px !important; max-width: 220px !important; }
    section[data-testid="stSidebar"] label { font-size: 0.92rem !important; }
    div[data-testid="stArrowVegaLiteChart"],
    div[data-testid="stVegaLiteChart"],
    .stPlotlyChart { overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; }
    div[data-testid="stDataFrame"],
    div[data-testid="stTable"] { overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; }
    details, div[data-testid="stExpander"] { width: 100% !important; }
    div[data-testid="stProgress"] { width: 100% !important; }
    .landing-hero { padding: 24px 14px 20px 14px !important; border-radius: 12px !important; }
    .landing-title   { font-size: 1.6rem !important; }
    .landing-tagline { font-size: 0.9rem !important; }
    .landing-desc    { font-size: 0.88rem !important; }
    .demo-card  { padding: 12px !important; }
    .demo-row   { font-size: 0.82rem !important; flex-wrap: wrap !important; }
    .feature-card { margin-bottom: 0.5rem !important; }
    hr { margin: 0.6rem 0 !important; }
    .stAlert { font-size: 0.9rem !important; }
}

.exp-card {
    background: #ffffff; border: 1px solid #d0e8df;
    border-left: 4px solid #0e7c5b; border-radius: 10px;
    padding: 12px 14px; margin-bottom: 8px;
    display: flex; justify-content: space-between;
    align-items: flex-start; flex-wrap: wrap; gap: 6px;
}
.exp-card-left { flex: 1 1 60%; min-width: 0; }
.exp-card-right { flex: 0 0 auto; text-align: right; }
.exp-card-name {
    font-weight: 700; color: #1a3c5e; font-size: 0.97rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.exp-card-bank  { font-size: 0.78rem; color: #7a9aaa; margin-top: 2px; }
.exp-card-date  { font-size: 0.75rem; color: #95a5a6; margin-top: 2px; }
.exp-card-amount { font-size: 1.05rem; font-weight: 800; color: #c0392b; }

@media screen and (max-width: 640px) {
    .exp-card { padding: 10px 11px !important; }
    .exp-card-name { font-size: 0.92rem !important; }
    .exp-card-amount { font-size: 1rem !important; }
}

@media screen and (min-width: 641px) and (max-width: 900px) {
    .main .block-container { padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100% !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] { min-width: 44% !important; flex-wrap: wrap !important; }
    .stButton > button { min-height: 2.5rem !important; font-size: 0.96rem !important; }
}
</style>
""", unsafe_allow_html=True)

import re
import psycopg2
import psycopg2.extras
import bcrypt
import random
import smtplib
import secrets
from contextlib import contextmanager
from email.message import EmailMessage
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

from csv_import import csv_import_page

# ---------------- VALIDATION HELPERS ----------------

def is_valid_email(email: str) -> bool:
    """Basic RFC-style email format check."""
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))

def validate_password(password: str):
    """
    Returns (True, "") if password is strong enough, else (False, reason).
    Rules: 8+ chars, at least one uppercase, one lowercase, one digit, one special char.
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r'[A-Z]', password):
        return False, "Password must include at least one uppercase letter."
    if not re.search(r'[a-z]', password):
        return False, "Password must include at least one lowercase letter."
    if not re.search(r'[0-9]', password):
        return False, "Password must include at least one digit."
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password):
        return False, "Password must include at least one special character (!@#$%^&* etc.)."
    return True, ""

# ---------------- DATABASE (PostgreSQL / Supabase) ----------------

def get_connection():
    return psycopg2.connect(
        st.secrets["SUPABASE_DB_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor
    )

@contextmanager
def get_db():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def create_tables():
    with get_db() as (conn, cursor):
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            surname TEXT NOT NULL,
            other_names TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password BYTEA NOT NULL,
            email_verified INTEGER DEFAULT 0,
            verification_code TEXT,
            role TEXT DEFAULT 'user',
            monthly_spending_limit INTEGER DEFAULT 0,
            created_at TEXT,
            last_login TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS banks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            bank_name TEXT NOT NULL,
            account_name TEXT NOT NULL,
            account_number TEXT NOT NULL,
            balance INTEGER DEFAULT 0,
            min_balance_alert INTEGER DEFAULT 0
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            bank_id INTEGER NOT NULL REFERENCES banks(id),
            type TEXT CHECK(type IN ('credit','debit')),
            amount INTEGER NOT NULL,
            description TEXT,
            created_at TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            bank_id INTEGER REFERENCES banks(id),
            name TEXT NOT NULL,
            amount INTEGER NOT NULL,
            created_at TEXT,
            tx_id INTEGER REFERENCES transactions(id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            target_amount INTEGER NOT NULL,
            current_amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_logins (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            login_date TEXT NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        # Safely add onboarding_complete to existing deployments
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS onboarding_complete INTEGER DEFAULT 0
        """)

create_tables()

# ---------------- SESSION STATE INIT ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "session_token" not in st.session_state:
    st.session_state.session_token = None
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
if "edit_income_id" not in st.session_state:
    st.session_state.edit_income_id = None
if "selected_goal" not in st.session_state:
    st.session_state.selected_goal = None
if "show_goal_contribution" not in st.session_state:
    st.session_state.show_goal_contribution = False
if "onboarding_step" not in st.session_state:
    st.session_state.onboarding_step = 1
if "quick_add_name" not in st.session_state:
    st.session_state.quick_add_name = ""
if "quick_add_amt" not in st.session_state:
    st.session_state.quick_add_amt = 0

# ---------------- AUTH FUNCTIONS ----------------
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    if isinstance(hashed, memoryview):
        hashed = bytes(hashed)
    return bcrypt.checkpw(password.encode(), hashed)

def register_user(surname, other, email, username, password):
    code = str(random.randint(100000, 999999))
    try:
        hashed_pw = hash_password(password)
        with get_db() as (conn, cursor):
            cursor.execute("""
                INSERT INTO users (surname, other_names, email, username, password, verification_code, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (surname, other, email, username, psycopg2.Binary(hashed_pw), code, datetime.now().strftime("%Y-%m-%d")))
        return code, "User created"
    except psycopg2.errors.UniqueViolation:
        return None, "Username or email already exists"
    except Exception as e:
        return None, str(e)

def login_user(username, password):
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, password, role, email_verified FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()
    if user:
        if user["email_verified"] == 0:
            st.warning("Email not verified. Please verify before logging in.")
            return None
        if check_password(password, user["password"]):
            st.session_state.user_id   = user["id"]
            st.session_state.user_role = user["role"]
            return user["id"]
    return None

def send_verification_email(email, code):
    try:
        msg = EmailMessage()
        msg["Subject"] = "Verify your Budget Smart account"
        msg["From"]    = st.secrets["EMAIL_SENDER"]
        msg["To"]      = email
        msg.set_content(f"Your verification code is: {code}")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(st.secrets["EMAIL_SENDER"], st.secrets["EMAIL_APP_PASSWORD"])
            server.send_message(msg)
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

def request_password_reset(email):
    try:
        code = str(random.randint(100000, 999999))
        with get_db() as (conn, cursor):
            cursor.execute("UPDATE users SET verification_code=%s WHERE email=%s", (code, email))
            if cursor.rowcount == 0:
                return False, "Email not found"
        return send_verification_email(email, code)
    except Exception as e:
        return False, str(e)

def reset_password(email, code, new_password):
    try:
        with get_db() as (conn, cursor):
            cursor.execute("SELECT id FROM users WHERE email=%s AND verification_code=%s", (email, code))
            user = cursor.fetchone()
            if not user:
                return False, "Invalid reset code"
            hashed_pw = hash_password(new_password)
            cursor.execute(
                "UPDATE users SET password=%s, verification_code=NULL WHERE email=%s",
                (psycopg2.Binary(hashed_pw), email)
            )
        return True, "Password reset successful"
    except Exception as e:
        return False, str(e)

def resend_verification(email):
    try:
        code = str(random.randint(100000, 999999))
        with get_db() as (conn, cursor):
            cursor.execute("UPDATE users SET verification_code=%s WHERE email=%s", (code, email))
            if cursor.rowcount == 0:
                return False, "Email not found"
        return send_verification_email(email, code)
    except Exception as e:
        return False, str(e)

def change_password(user_id, current_pw, new_pw):
    with get_db() as (conn, cursor):
        cursor.execute("SELECT password FROM users WHERE id=%s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, "User not found"
        if check_password(current_pw, row["password"]):
            cursor.execute(
                "UPDATE users SET password=%s WHERE id=%s",
                (psycopg2.Binary(hash_password(new_pw)), user_id)
            )
            return True, "Password updated"
        return False, "Current password incorrect"

def save_expense(user_id, bank_id, name, amount):
    """Shared helper used by manual add and quick-add buttons."""
    now = datetime.now().strftime("%Y-%m-%d")
    amt = int(amount)
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO transactions (bank_id, type, amount, description, created_at) "
            "VALUES (%s, 'debit', %s, %s, %s) RETURNING id",
            (bank_id, amt, f"Expense: {name}", now)
        )
        tx_id = cursor.fetchone()["id"]
        cursor.execute(
            "INSERT INTO expenses (user_id, bank_id, name, amount, created_at, tx_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, bank_id, name, amt, now, tx_id)
        )
        cursor.execute(
            "UPDATE banks SET balance = balance - %s WHERE id=%s",
            (amt, bank_id)
        )

def get_onboarding_status(user_id):
    """Returns dict with booleans for each onboarding step."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT onboarding_complete FROM users WHERE id=%s", (user_id,))
        row = cursor.fetchone()
        already_done = bool(row["onboarding_complete"])

        cursor.execute("SELECT COUNT(*) AS n FROM banks WHERE user_id=%s", (user_id,))
        has_bank = cursor.fetchone()["n"] > 0

        cursor.execute(
            "SELECT COUNT(*) AS n FROM transactions t "
            "JOIN banks b ON t.bank_id=b.id "
            "WHERE b.user_id=%s AND t.type='credit'", (user_id,)
        )
        has_income = cursor.fetchone()["n"] > 0

        cursor.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id=%s", (user_id,)
        )
        has_expense = cursor.fetchone()["n"] > 0

        cursor.execute(
            "SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,)
        )
        limit_row = cursor.fetchone()
        has_budget = bool(limit_row["monthly_spending_limit"])

    return {
        "already_done": already_done,
        "has_bank":     has_bank,
        "has_income":   has_income,
        "has_expense":  has_expense,
        "has_budget":   has_budget,
        "all_done":     has_bank and has_income and has_expense and has_budget,
    }

def mark_onboarding_complete(user_id):
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE users SET onboarding_complete=1 WHERE id=%s", (user_id,)
        )

# ============================================================
# COOKIE SESSION HELPERS
# ============================================================

SESSION_EXPIRY_DAYS = 30  # Sessions expire after 30 days

def create_session_token(user_id):
    token = secrets.token_urlsafe(48)
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO session_tokens (user_id, token, created_at) VALUES (%s, %s, %s)",
            (user_id, token, now)
        )
    cookies["session_token"] = token
    cookies.save()
    return token

def validate_session_token(token):
    """
    Returns (user_id, role) if the token is valid and the user has been active
    within the last SESSION_EXPIRY_DAYS days.

    'created_at' on the session_tokens table is used as 'last_active_at':
    it is refreshed to NOW on every successful validation, so the 30-day
    window slides forward with each visit. Only a genuine absence of 30 days
    will cause the session to expire.
    """
    if not token:
        return None, None
    try:
        now           = datetime.now()
        expiry_cutoff = (now - timedelta(days=SESSION_EXPIRY_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        now_str       = now.strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as (conn, cursor):
            # Check the token is valid and was last active within the window
            cursor.execute("""
                SELECT u.id, u.role FROM session_tokens s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = %s
                  AND u.email_verified = 1
                  AND s.created_at >= %s
            """, (token, expiry_cutoff))
            row = cursor.fetchone()
            if row:
                # Slide the inactivity window: update last-active timestamp
                cursor.execute(
                    "UPDATE session_tokens SET created_at = %s WHERE token = %s",
                    (now_str, token)
                )
                return row["id"], row["role"]
    except Exception:
        pass
    return None, None

def revoke_session_token(token):
    if not token:
        return
    try:
        with get_db() as (conn, cursor):
            cursor.execute("DELETE FROM session_tokens WHERE token=%s", (token,))
    except Exception:
        pass
    cookies["session_token"] = ""
    cookies.save()

# ============================================================
# RESTORE SESSION FROM COOKIE
# ============================================================
if st.session_state.user_id is None:
    _cookie_token = cookies.get("session_token", "")
    if _cookie_token:
        _uid, _role = validate_session_token(_cookie_token)
        if _uid:
            st.session_state.user_id       = _uid
            st.session_state.user_role     = _role
            st.session_state.session_token = _cookie_token
        else:
            cookies["session_token"] = ""
            cookies.save()

# ---------------- ANALYTICS FUNCTIONS ----------------
def track_login(user_id):
    try:
        now = datetime.now().strftime("%Y-%m-%d")
        with get_db() as (conn, cursor):
            cursor.execute("INSERT INTO analytics_logins (user_id, login_date) VALUES (%s, %s)", (user_id, now))
            cursor.execute("UPDATE users SET last_login=%s WHERE id=%s", (now, user_id))
    except Exception:
        pass

def track_signup(user_id):
    try:
        now = datetime.now().strftime("%Y-%m-%d")
        with get_db() as (conn, cursor):
            cursor.execute("INSERT INTO analytics_logins (user_id, login_date) VALUES (%s, %s)", (user_id, now))
    except Exception:
        pass

def get_analytics():
    try:
        with get_db() as (conn, cursor):
            today     = datetime.now().strftime("%Y-%m-%d")
            cutoff_30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            cutoff_7  = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

            cursor.execute("SELECT COUNT(*) AS n FROM users WHERE email_verified=1")
            total_verified = cursor.fetchone()["n"] or 0
            cursor.execute("SELECT COUNT(*) AS n FROM users")
            total_registered = cursor.fetchone()["n"] or 0
            cursor.execute("SELECT COUNT(DISTINCT user_id) AS n FROM analytics_logins WHERE login_date=%s", (today,))
            dau = cursor.fetchone()["n"] or 0
            cursor.execute("SELECT COUNT(DISTINCT user_id) AS n FROM analytics_logins WHERE login_date >= %s", (cutoff_7,))
            wau = cursor.fetchone()["n"] or 0
            cursor.execute("SELECT COUNT(DISTINCT user_id) AS n FROM analytics_logins WHERE login_date >= %s", (cutoff_30,))
            mau = cursor.fetchone()["n"] or 0
            cursor.execute("SELECT COUNT(*) AS n FROM users WHERE created_at >= %s", (cutoff_30,))
            new_signups_30d = cursor.fetchone()["n"] or 0
            cursor.execute("SELECT COUNT(*) AS n FROM users WHERE created_at=%s", (today,))
            signups_today = cursor.fetchone()["n"] or 0
            cursor.execute("""
                SELECT login_date, COUNT(DISTINCT user_id) AS active_users
                FROM analytics_logins
                WHERE login_date >= CURRENT_DATE - INTERVAL '14 days'
                GROUP BY login_date ORDER BY login_date
            """)
            daily_rows = [(r["login_date"], r["active_users"]) for r in cursor.fetchall()]
            cursor.execute("""
                SELECT id, surname, other_names, email, last_login FROM users
                WHERE email_verified=1 AND (last_login IS NULL OR last_login < %s)
                ORDER BY last_login ASC
            """, (cutoff_7,))
            inactive_users = [(r["id"], r["surname"], r["other_names"], r["email"], r["last_login"]) for r in cursor.fetchall()]
        return {
            "total_registered": total_registered, "total_verified": total_verified,
            "dau": dau, "wau": wau, "mau": mau,
            "new_signups_30d": new_signups_30d, "signups_today": signups_today,
            "daily_rows": daily_rows, "inactive_users": inactive_users,
        }
    except Exception:
        return {}

def notify_admin_new_signup(new_name, new_username, new_email):
    try:
        with get_db() as (conn, cursor):
            cursor.execute("SELECT COUNT(*) AS n FROM users")
            total_users = cursor.fetchone()["n"] or 0
        msg = EmailMessage()
        msg["Subject"] = f"New signup on Budget Right - {new_name}"
        msg["From"]    = st.secrets["EMAIL_SENDER"]
        msg["To"]      = st.secrets["ADMIN_EMAIL"]
        msg.set_content(
            f"New user signed up!\nName: {new_name}\nUsername: {new_username}\n"
            f"Email: {new_email}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Total users: {total_users}"
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(st.secrets["EMAIL_SENDER"], st.secrets["EMAIL_APP_PASSWORD"])
            server.send_message(msg)
    except Exception:
        pass

def send_reengagement_email(email, name):
    try:
        msg = EmailMessage()
        msg["Subject"] = "We miss you on Budget Right"
        msg["From"]    = st.secrets["EMAIL_SENDER"]
        msg["To"]      = email
        msg.set_content(
            f"Hi {name},\n\nYou haven't logged into Budget Right in a while "
            f"- your finances miss you!\n\nLog back in to check your balance, "
            f"track your spending, and stay on top of your savings goals.\n\n"
            f"Stay financially smart,\nThe Budget Right Team"
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(st.secrets["EMAIL_SENDER"], st.secrets["EMAIL_APP_PASSWORD"])
            server.send_message(msg)
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

# ---------------- UI ----------------
st.title("Budget Right")

# ================= AUTH =================
if st.session_state.user_id is None:
    st.markdown("""
    <style>
    .landing-hero {
        background: linear-gradient(135deg, #1a3c5e 0%, #0e7c5b 100%);
        border-radius: 16px; padding: 48px 40px 40px 40px; text-align: center; margin-bottom: 8px;
    }
    .landing-logo { font-size: 56px; margin-bottom: 4px; display: block; }
    .landing-title { font-size: 2.6rem; font-weight: 800; color: #ffffff; margin: 0 0 6px 0; letter-spacing: -0.5px; }
    .landing-tagline { font-size: 1.1rem; color: #a8d8c8; margin: 0 0 28px 0; font-weight: 400; }
    .landing-desc { font-size: 1.05rem; color: #d4eee6; max-width: 560px; margin: 0 auto; line-height: 1.7; }
    .feature-card { background: #f0f7f4; border-left: 4px solid #0e7c5b; border-radius: 10px; padding: 18px 20px; height: 100%; }
    .feature-icon { font-size: 1.8rem; }
    .feature-title { font-weight: 700; color: #1a3c5e; font-size: 1rem; margin: 6px 0 4px 0; }
    .feature-text  { color: #4a6070; font-size: 0.92rem; line-height: 1.5; }
    .demo-card { background: #ffffff; border: 1px solid #d0e8df; border-radius: 14px; padding: 24px; margin-bottom: 4px; }
    .demo-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #eef5f2; font-size: 0.95rem; }
    .demo-row:last-child { border-bottom: none; }
    .demo-credit { color: #0e7c5b; font-weight: 600; }
    .demo-debit  { color: #c0392b; font-weight: 600; }
    .demo-label  { color: #2c3e50; }
    .demo-date   { color: #95a5a6; font-size: 0.82rem; }
    .badge { display: inline-block; background: #e8f5f0; color: #0e7c5b; border-radius: 20px; padding: 4px 14px; font-size: 0.82rem; font-weight: 600; margin: 4px 4px 0 0; }
    .trust-bar {
        background: #f0f7f4; border: 1px solid #c2e0d4; border-radius: 12px;
        padding: 18px 24px; margin: 18px 0 4px 0;
        display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; align-items: center;
    }
    .trust-item {
        display: flex; align-items: center; gap: 8px;
        font-size: 0.92rem; color: #1a3c5e; font-weight: 600;
    }
    .trust-icon { font-size: 1.3rem; }
    .trust-divider { color: #b0cfc4; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="landing-hero">
      <span class="landing-logo">&#x1F4B0;</span>
      <p class="landing-title">Budget Right</p>
      <p class="landing-tagline">&#x1F512; Secure budget tracking &#x2014; built for Nigerians</p>
      <p class="landing-desc">Track your income, expenses, and savings easily.<br>Know exactly where your money goes &#x2014; in naira, every day.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    fc1, fc2, fc3, fc4 = st.columns(4)
    features = [
        ("&#x1F4B3;", "Multiple Banks", "Link all your accounts &mdash; GTB, Access, Opay and more &mdash; in one place."),
        ("&#x1F4CA;", "Live Dashboard", "See your total balance, monthly spend, and net savings at a glance."),
        ("&#x1F3AF;", "Savings Goals", "Set a target, contribute from any bank, and track your progress."),
        ("&#x1F4E5;", "CSV Import", "Upload your bank statement and have it auto-parsed into your ledger."),
    ]
    for col, (icon, title, text) in zip([fc1, fc2, fc3, fc4], features):
        with col:
            st.markdown(
                f'<div class="feature-card">'
                f'<div class="feature-icon">{icon}</div>'
                f'<div class="feature-title">{title}</div>'
                f'<div class="feature-text">{text}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

    # ── TRUST / PRIVACY SECTION ──
    st.markdown("""
    <div class="trust-bar">
      <div class="trust-item">
        <span class="trust-icon">&#x1F6AB;</span>
        <span>No ATM card needed</span>
      </div>
      <span class="trust-divider">|</span>
      <div class="trust-item">
        <span class="trust-icon">&#x1F512;</span>
        <span>We do not move your money</span>
      </div>
      <span class="trust-divider">|</span>
      <div class="trust-item">
        <span class="trust-icon">&#x1F1F3;&#x1F1EC;</span>
        <span>Built for Nigerians</span>
      </div>
      <span class="trust-divider">|</span>
      <div class="trust-item">
        <span class="trust-icon">&#x1F441;&#xFE0F;</span>
        <span>Only you see your data</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    demo_col, auth_col = st.columns([1.1, 1], gap="large")

    with demo_col:
        st.markdown("#### &#x1F4F1; See it in action")
        st.markdown("""
        <div class="demo-card">
          <div style="font-weight:700;color:#1a3c5e;margin-bottom:12px;font-size:1rem;">
            &#x1F4B3; My Dashboard &nbsp;&middot;&nbsp;
            <span style="color:#0e7c5b;">&#x20A6; 842,500 total</span>
          </div>
          <div class="demo-row">
            <span class="demo-label">&#x1F4BC; Salary &mdash; GTB</span>
            <span><span class="demo-date">Jun 28 &nbsp;</span><span class="demo-credit">+&#x20A6;450,000</span></span>
          </div>
          <div class="demo-row">
            <span class="demo-label">&#x1F6D2; Shoprite groceries</span>
            <span><span class="demo-date">Jun 29 &nbsp;</span><span class="demo-debit">&minus;&#x20A6;18,400</span></span>
          </div>
          <div class="demo-row">
            <span class="demo-label">&#x26A1; NEPA / electricity</span>
            <span><span class="demo-date">Jun 30 &nbsp;</span><span class="demo-debit">&minus;&#x20A6;12,000</span></span>
          </div>
          <div class="demo-row">
            <span class="demo-label">&#x1F697; Transport (Bolt)</span>
            <span><span class="demo-date">Jul 01 &nbsp;</span><span class="demo-debit">&minus;&#x20A6;5,600</span></span>
          </div>
          <div class="demo-row">
            <span class="demo-label">&#x1F3AF; Emergency Fund goal</span>
            <span><span class="demo-date">Jul 01 &nbsp;</span><span class="demo-debit">&minus;&#x20A6;30,000</span></span>
          </div>
          <div style="margin-top:16px;padding-top:12px;border-top:1px solid #eef5f2;">
            <span class="badge">&#x1F3E6; 3 banks linked</span>
            <span class="badge">&#x1F4C9; &#x20A6;66,000 spent</span>
            <span class="badge">&#x1F3AF; 2 active goals</span>
          </div>
        </div>
        <div style="background:#fffbea;border-left:4px solid #f39c12;border-radius:8px;padding:12px 16px;margin-top:12px;font-size:0.9rem;color:#7d5a00;">
          &#x26A0;&#xFE0F; <strong>Spending alert:</strong> You&#x2019;ve used 68% of your &#x20A6;97,000 monthly budget.
        </div>
        """, unsafe_allow_html=True)

    with auth_col:
        st.markdown("#### &#x1F680; Get started &mdash; it&#x2019;s free")
        tabs = st.tabs(["&#x1F510; Login", "&#x1F4DD; Register", "&#x1F4E7; Verify Email"])

        with tabs[0]:
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Login", key="login_btn"):
                    uid = login_user(login_username, login_password)
                    if uid:
                        track_login(uid)
                        token = create_session_token(uid)
                        st.session_state.session_token = token
                        st.success("Logged in!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials or email not verified")
            with col2:
                if st.button("Forgot Password?", key="forgot_btn"):
                    st.session_state.show_forgot_password = True

            if st.session_state.show_forgot_password:
                with st.expander("Reset Password", expanded=True):
                    email_input = st.text_input("Enter your email", key="reset_email_input")
                    if st.button("Send Reset Code", key="send_reset_btn"):
                        if email_input:
                            if not is_valid_email(email_input):
                                st.error("Please enter a valid email address.")
                            else:
                                success, msg = request_password_reset(email_input)
                                if success:
                                    st.success(msg)
                                    st.session_state.show_forgot_password = False
                                    st.session_state.show_reset_form = True
                                    st.session_state.reset_email = email_input
                                else:
                                    st.error(msg)
                        else:
                            st.warning("Enter your email.")
                    if st.button("Cancel", key="cancel_reset_btn"):
                        st.session_state.show_forgot_password = False
                        st.rerun()

            if st.session_state.show_reset_form:
                with st.expander("Enter Reset Code", expanded=True):
                    reset_code   = st.text_input("Reset code", key="reset_code")
                    new_pass     = st.text_input("New password", type="password", key="new_pass")
                    confirm_pass = st.text_input("Confirm new password", type="password", key="confirm_pass")
                    if st.button("Reset Password", key="do_reset_btn"):
                        if reset_code and new_pass and confirm_pass:
                            if new_pass == confirm_pass:
                                pw_ok, pw_msg = validate_password(new_pass)
                                if not pw_ok:
                                    st.error(pw_msg)
                                else:
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

        with tabs[1]:
            reg_surname  = st.text_input("Surname", key="reg_surname")
            reg_other    = st.text_input("Other Names", key="reg_other")
            reg_email    = st.text_input("Email", key="reg_email")
            reg_username = st.text_input("Username", key="reg_username")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            st.caption(
                "Password must be at least 8 characters and include: "
                "uppercase letter, lowercase letter, digit, and special character (!@#$%^&* etc.)"
            )
            if st.button("Register", key="register_btn"):
                errors = []
                if not all([reg_surname, reg_other, reg_email, reg_username, reg_password]):
                    errors.append("All fields are required.")
                if reg_email and not is_valid_email(reg_email):
                    errors.append("Please enter a valid email address.")
                if reg_password:
                    pw_ok, pw_msg = validate_password(reg_password)
                    if not pw_ok:
                        errors.append(pw_msg)
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    code, msg = register_user(reg_surname, reg_other, reg_email, reg_username, reg_password)
                    if code:
                        with get_db() as (conn, cursor):
                            cursor.execute("SELECT id FROM users WHERE username=%s", (reg_username,))
                            new_row = cursor.fetchone()
                        if new_row:
                            track_signup(new_row["id"])
                        notify_admin_new_signup(f"{reg_surname} {reg_other}", reg_username, reg_email)
                        success, email_msg = send_verification_email(reg_email, code)
                        if success:
                            st.success("Account created! Check your email to verify.")
                        else:
                            st.error(f"Account created but email failed: {email_msg}")
                    else:
                        st.error(msg)

        with tabs[2]:
            verify_email = st.text_input("Registered Email", key="verify_email")
            verify_code  = st.text_input("Verification Code", key="verify_code")
            col1, col2   = st.columns(2)
            with col1:
                if st.button("Verify Email", key="verify_btn"):
                    with get_db() as (conn, cursor):
                        cursor.execute("SELECT id FROM users WHERE email=%s AND verification_code=%s", (verify_email, verify_code))
                        user = cursor.fetchone()
                        if user:
                            cursor.execute("UPDATE users SET email_verified=1, verification_code=NULL WHERE id=%s", (user["id"],))
                    if user:
                        st.success("Email verified. You can now log in.")
                    else:
                        st.error("Invalid email or code.")
            with col2:
                if st.button("Resend Code", key="resend_btn"):
                    if verify_email:
                        success, msg = resend_verification(verify_email)
                        st.success(msg) if success else st.error(msg)
                    else:
                        st.warning("Enter your email first.")

    st.stop()

# ================= LOGGED IN — SIDEBAR NAV =================
user_id = st.session_state.user_id

with get_db() as (conn, cursor):
    cursor.execute("SELECT surname, other_names, role FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
st.session_state.user_role = user["role"]

with st.sidebar:
    st.markdown(f"### Hello, {user['surname']} {user['other_names']}")
    st.divider()
    pages = [
        "&#x1F4CA; Dashboard", "&#x1F4B0; Income", "&#x2795; Expenses",
        "&#x1F3E6; Banks", "&#x1F4B8; Transfers", "&#x1F3AF; Savings Goals",
        "&#x1F4E5; Import CSV", "&#x2699;&#xFE0F; Settings",
    ]
    pages_clean = [
        "Dashboard", "Income", "Expenses",
        "Banks", "Transfers", "Savings Goals",
        "Import CSV", "Settings",
    ]
    if st.session_state.user_role == "admin":
        pages.insert(0, "&#x1F6E0; Admin Panel")
        pages.insert(1, "&#x1F4C8; Analytics")
        pages_clean.insert(0, "Admin Panel")
        pages_clean.insert(1, "Analytics")

    selected_idx = st.radio(
        "Navigate",
        range(len(pages)),
        format_func=lambda i: pages_clean[i],
        key="nav_radio"
    )
    current_page = pages_clean[selected_idx]

    st.divider()
    st.markdown(
        "Report a bug / Suggest a feature: "
        "[Click here](https://docs.google.com/forms/d/e/1FAIpQLSccXTBLwx6GhwqpUCt6lrjQ4qzNzNgjs2APheQ-FOryC0wCJA/viewform?usp=dialog)",
        unsafe_allow_html=False,
    )
    st.divider()
    if st.button("Logout", key="logout_btn"):
        revoke_session_token(st.session_state.get("session_token"))
        st.session_state.user_id = st.session_state.user_role = st.session_state.session_token = None
        st.rerun()

st.success(f"Welcome {user['surname']} {user['other_names']}")

# ================= ONBOARDING FLOW =================
_ob = get_onboarding_status(user_id)

if not _ob["already_done"]:
    # Auto-mark complete once all steps done
    if _ob["all_done"]:
        mark_onboarding_complete(user_id)
    else:
        # Progress bar
        steps_done = sum([_ob["has_bank"], _ob["has_income"], _ob["has_expense"], _ob["has_budget"]])
        st.markdown("""
        <style>
        .ob-banner {
            background: linear-gradient(90deg, #1a3c5e 0%, #0e7c5b 100%);
            border-radius: 12px; padding: 18px 22px; margin-bottom: 16px;
        }
        .ob-title { color: #ffffff; font-size: 1.05rem; font-weight: 700; margin-bottom: 6px; }
        .ob-sub   { color: #a8d8c8; font-size: 0.88rem; }
        .ob-step  {
            display: flex; align-items: center; gap: 10px;
            background: #f0f7f4; border-radius: 8px;
            padding: 10px 14px; margin-bottom: 6px; font-size: 0.92rem;
        }
        .ob-done   { border-left: 4px solid #0e7c5b; color: #2c7a5a; }
        .ob-todo   { border-left: 4px solid #d0d0d0; color: #555; }
        .ob-icon   { font-size: 1.2rem; }
        .ob-skip   { font-size: 0.8rem; color: #95a5a6; text-align: right; margin-top: 4px; }
        </style>
        """, unsafe_allow_html=True)

        with st.expander(f"Setup checklist — {steps_done}/4 steps done", expanded=(steps_done == 0)):
            st.progress(steps_done / 4, text=f"You are {steps_done * 25}% set up")
            st.markdown("<br>", unsafe_allow_html=True)

            # Step 1 — Bank
            done1 = _ob["has_bank"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done1 else "ob-todo"}">'
                f'<span class="ob-icon">{"&#x2705;" if done1 else "&#x1F3E6;"}</span>'
                f'<span><strong>Step 1: Add your first bank account</strong>'
                f'{"&nbsp; — done!" if done1 else " — so Budget Right knows where your money lives."}</span>'
                f'</div>', unsafe_allow_html=True
            )
            if not done1:
                with st.form("ob_bank_form"):
                    ob_bank_name    = st.text_input("Bank Name (e.g. GTB, Access, Opay)")
                    ob_acct_name    = st.text_input("Account Name")
                    ob_acct_num     = st.text_input("Account Number (last 4 digits)")
                    ob_opening_bal  = st.number_input("Current Balance (NGN)", min_value=0, step=1000)
                    ob_bank_submit  = st.form_submit_button("Add Bank and Continue")
                if ob_bank_submit:
                    if ob_bank_name and ob_acct_name and ob_acct_num:
                        with get_db() as (conn, cursor):
                            cursor.execute(
                                "INSERT INTO banks (user_id, bank_name, account_name, account_number, balance, min_balance_alert) "
                                "VALUES (%s, %s, %s, %s, %s, 0)",
                                (user_id, ob_bank_name, ob_acct_name, ob_acct_num[-4:], int(ob_opening_bal))
                            )
                        st.success(f"Bank '{ob_bank_name}' added!")
                        st.rerun()
                    else:
                        st.warning("Please fill all bank fields.")

            st.markdown("<br>", unsafe_allow_html=True)

            # Step 2 — Income
            done2 = _ob["has_income"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done2 else "ob-todo"}">'
                f'<span class="ob-icon">{"&#x2705;" if done2 else "&#x1F4B0;"}</span>'
                f'<span><strong>Step 2: Record your first income</strong>'
                f'{"&nbsp; — done!" if done2 else " — add your salary or any other income source."}</span>'
                f'</div>', unsafe_allow_html=True
            )
            if done1 and not done2:
                with get_db() as (conn, cursor):
                    cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
                    ob_banks = cursor.fetchall()
                ob_bank_map = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in ob_banks}
                with st.form("ob_income_form"):
                    ob_inc_source  = st.text_input("Income Source (e.g. Salary, Freelance)")
                    ob_inc_amount  = st.number_input("Amount (NGN)", min_value=1, step=1000)
                    ob_inc_bank    = st.selectbox("Which bank?", list(ob_bank_map.keys()))
                    ob_inc_submit  = st.form_submit_button("Add Income and Continue")
                if ob_inc_submit:
                    if ob_inc_source and ob_inc_amount > 0:
                        bk_id = ob_bank_map[ob_inc_bank]
                        with get_db() as (conn, cursor):
                            cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (int(ob_inc_amount), bk_id))
                            cursor.execute(
                                "INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s,'credit',%s,%s,%s)",
                                (bk_id, int(ob_inc_amount), f"Income: {ob_inc_source}", datetime.now().strftime("%Y-%m-%d"))
                            )
                        st.success("Income recorded!")
                        st.rerun()
                    else:
                        st.warning("Please enter a source and amount.")
            elif not done1 and not done2:
                st.caption("Complete Step 1 first.")

            st.markdown("<br>", unsafe_allow_html=True)

            # Step 3 — Expense
            done3 = _ob["has_expense"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done3 else "ob-todo"}">'
                f'<span class="ob-icon">{"&#x2705;" if done3 else "&#x1F9FE;"}</span>'
                f'<span><strong>Step 3: Log your first expense</strong>'
                f'{"&nbsp; — done!" if done3 else " — what did you spend money on today?"}</span>'
                f'</div>', unsafe_allow_html=True
            )
            if done1 and not done3:
                with get_db() as (conn, cursor):
                    cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
                    ob_banks2 = cursor.fetchall()
                ob_bank_map2 = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in ob_banks2}
                with st.form("ob_expense_form"):
                    ob_exp_name   = st.text_input("Expense Name (e.g. Transport, Food)")
                    ob_exp_amount = st.number_input("Amount (NGN)", min_value=1, step=100)
                    ob_exp_bank   = st.selectbox("Pay From Bank", list(ob_bank_map2.keys()))
                    ob_exp_submit = st.form_submit_button("Add Expense and Continue")
                if ob_exp_submit:
                    if ob_exp_name and ob_exp_amount > 0:
                        bk_id = ob_bank_map2[ob_exp_bank]
                        save_expense(user_id, bk_id, ob_exp_name, ob_exp_amount)
                        st.success("Expense logged!")
                        st.rerun()
                    else:
                        st.warning("Please enter a name and amount.")
            elif not done1 and not done3:
                st.caption("Complete Step 1 first.")

            st.markdown("<br>", unsafe_allow_html=True)

            # Step 4 — Budget
            done4 = _ob["has_budget"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done4 else "ob-todo"}">'
                f'<span class="ob-icon">{"&#x2705;" if done4 else "&#x1F4CA;"}</span>'
                f'<span><strong>Step 4: Set your monthly spending budget</strong>'
                f'{"&nbsp; — done!" if done4 else " — get alerts before you overspend."}</span>'
                f'</div>', unsafe_allow_html=True
            )
            if not done4:
                with st.form("ob_budget_form"):
                    ob_budget = st.number_input("Monthly Budget (NGN)", min_value=1000, step=5000, value=100000)
                    ob_budget_submit = st.form_submit_button("Set Budget and Finish")
                if ob_budget_submit:
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE users SET monthly_spending_limit=%s WHERE id=%s", (int(ob_budget), user_id))
                    st.success("Budget set! You're all set up.")
                    st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                '<div class="ob-skip">Already set up? '
                '<a href="#" style="color:#95a5a6;">Skip this checklist</a> — '
                'it disappears automatically once all steps are done.</div>',
                unsafe_allow_html=True
            )
            # Let them skip manually
            if st.button("Skip setup checklist", key="skip_onboarding"):
                mark_onboarding_complete(user_id)
                st.rerun()

        st.divider()

# ================= PAGE: ADMIN PANEL =================
if current_page == "Admin Panel":
    st.subheader("Admin Panel")
    tabs_admin = st.tabs(["Users", "Banks", "Expenses & Income"])
    with tabs_admin[0]:
        st.write("All Users:")
        with get_db() as (conn, cursor):
            cursor.execute("SELECT id, surname, other_names, username, email, role FROM users")
            all_users = cursor.fetchall()
        for u in all_users:
            st.write(f"{u['surname']} {u['other_names']} | {u['username']} | {u['email']} | Role: {u['role']}")
    with tabs_admin[1]:
        st.write("All Bank Accounts:")
        with get_db() as (conn, cursor):
            cursor.execute("SELECT b.id, u.username, b.bank_name, b.account_name, b.account_number, b.balance FROM banks b JOIN users u ON b.user_id = u.id")
            all_banks = cursor.fetchall()
        for b in all_banks:
            st.write(dict(b))
    with tabs_admin[2]:
        st.info("You can paste your existing Expenses & Income code here for admin view.")

# ================= PAGE: ANALYTICS =================
elif current_page == "Analytics":
    if st.session_state.user_role != "admin":
        st.error("Access denied.")
        st.stop()
    st.markdown("## Analytics Dashboard")
    data = get_analytics()
    if not data:
        st.warning("Could not load analytics data.")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Registered", data["total_registered"])
        c2.metric("Verified Users",    data["total_verified"])
        c3.metric("Active Today",      data["dau"])
        c4.metric("Active This Week",  data["wau"])
        c5.metric("Active This Month", data["mau"])
        st.divider()
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("Signups")
            s1, s2 = st.columns(2)
            s1.metric("Signups Today",     data["signups_today"])
            s2.metric("Signups (30 days)", data["new_signups_30d"])
            st.subheader("Daily Active Users — Last 14 Days")
            if data["daily_rows"]:
                df_dau = pd.DataFrame(data["daily_rows"], columns=["date", "active_users"])
                df_dau["date"] = pd.to_datetime(df_dau["date"])
                st.bar_chart(df_dau.set_index("date")["active_users"])
            else:
                st.info("No login data yet.")
        with col_right:
            st.subheader(f"Inactive Users ({len(data['inactive_users'])} total)")
            st.caption("Verified accounts with no login in the last 7 days.")
            inactive = data["inactive_users"]
            if inactive:
                df_inactive = pd.DataFrame(inactive, columns=["id","Surname","Other Names","Email","Last Login"])
                df_inactive["Last Login"] = df_inactive["Last Login"].fillna("Never")
                st.dataframe(df_inactive[["Surname","Other Names","Email","Last Login"]], use_container_width=True)
                st.divider()
                st.subheader("Send Re-engagement Email")
                email_options = {f"{r[1]} {r[2]} ({r[3]})": (r[3], r[1]) for r in inactive}
                selected_user = st.selectbox("Select user to email", list(email_options.keys()), key="reeng_select")
                if st.button("Send Re-engagement Email", key="reeng_send_btn"):
                    target_email, target_name = email_options[selected_user]
                    ok, msg = send_reengagement_email(target_email, target_name)
                    st.success(f"Email sent to {target_email}") if ok else st.error(f"Failed: {msg}")
                st.divider()
                st.subheader("Bulk Email All Inactive Users")
                st.caption(f"This will send to all {len(inactive)} inactive verified accounts.")
                if st.button("Send to All Inactive", key="reeng_bulk_btn"):
                    sent, failed = 0, 0
                    for row in inactive:
                        ok, _ = send_reengagement_email(row[3], row[1])
                        if ok: sent += 1
                        else:  failed += 1
                    st.success(f"Sent: {sent}  |  Failed: {failed}")
            else:
                st.success("No inactive users right now - everyone's engaged!")

# ================= PAGE: DASHBOARD =================
elif current_page == "Dashboard":
    st.markdown("## My Dashboard")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT COALESCE(SUM(balance),0) AS n FROM banks WHERE user_id=%s", (user_id,))
        total_balance = cursor.fetchone()["n"]
        current_month = datetime.now().strftime("%Y-%m")
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount),0) AS n FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id=%s AND t.type='debit'
              AND TO_CHAR(TO_DATE(t.created_at,'YYYY-MM-DD'),'YYYY-MM') = %s
        """, (user_id, current_month))
        expenses_this_month = cursor.fetchone()["n"]
        cursor.execute("SELECT COUNT(*) AS n FROM banks WHERE user_id=%s", (user_id,))
        num_banks = cursor.fetchone()["n"]
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN type='credit' THEN amount ELSE -amount END),0) AS n
            FROM transactions t JOIN banks b ON t.bank_id = b.id WHERE b.user_id=%s
        """, (user_id,))
        net_savings = cursor.fetchone()["n"]
        cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
        spending_limit = cursor.fetchone()["monthly_spending_limit"] or 0

    # ── Empty state: no banks at all ──
    if num_banks == 0:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:12px;padding:28px 24px;text-align:center;margin:16px 0;">
          <div style="font-size:2.5rem;">&#x1F3E6;</div>
          <div style="font-size:1.1rem;font-weight:700;color:#1a3c5e;margin:8px 0 4px;">Welcome! Let's get you set up.</div>
          <div style="color:#4a6070;font-size:0.93rem;">
            Your dashboard will show your balances, charts, and insights once you add a bank account.<br>
            Start by adding your first bank on the <strong>Banks</strong> page.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Add my first bank account", key="dash_goto_banks"):
            st.session_state.nav_radio = pages_clean.index("Banks")
            st.rerun()
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Total Balance (NGN)",       f"{total_balance:,.0f}")
    with col2: st.metric("Expenses This Month (NGN)", f"{expenses_this_month:,.0f}")
    with col3: st.metric("Bank Accounts",              num_banks)
    with col4: st.metric("Net Savings (NGN)",          f"{net_savings:,.0f}")

    # ── Spending budget alert ──
    if spending_limit > 0 and expenses_this_month > 0:
        pct = (expenses_this_month / spending_limit) * 100
        if pct >= 100:
            st.error(
                f"Budget exceeded! You have spent NGN {expenses_this_month:,.0f} — "
                f"NGN {expenses_this_month - spending_limit:,.0f} over your NGN {spending_limit:,.0f} monthly limit."
            )
        elif pct >= 80:
            st.warning(
                f"Spending alert: You have used {pct:.0f}% of your NGN {spending_limit:,.0f} monthly budget "
                f"(NGN {expenses_this_month:,.0f} spent). Only NGN {spending_limit - expenses_this_month:,.0f} left."
            )
        elif pct >= 50:
            st.info(
                f"You are halfway through your monthly budget — {pct:.0f}% used "
                f"(NGN {expenses_this_month:,.0f} of NGN {spending_limit:,.0f})."
            )
    elif spending_limit == 0:
        st.caption("Tip: Set a monthly spending limit in Settings to get budget alerts here.")

    st.divider()
    st.subheader("Income vs Expenses Over Time")
    period_map = {
        "Last 30 Days": timedelta(days=30), "Last 3 Months": timedelta(days=90),
        "Last 6 Months": timedelta(days=180), "Last Year": timedelta(days=365), "All Time": None,
    }
    selected_period = st.selectbox("Select Period", list(period_map.keys()), key="period_select")
    start_date = (datetime.now() - period_map[selected_period]).date() if period_map[selected_period] else datetime(2000,1,1).date()
    start_str  = start_date.strftime("%Y-%m-%d")
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT t.created_at, t.type, t.amount FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id=%s AND t.created_at >= %s ORDER BY t.created_at
        """, (user_id, start_str))
        rows = cursor.fetchall()
    if rows:
        df = pd.DataFrame([(r["created_at"], r["type"], r["amount"]) for r in rows], columns=["date","type","amount"])
        df["date"] = pd.to_datetime(df["date"])
        df_pivot = df.pivot_table(index="date", columns="type", values="amount", aggfunc="sum", fill_value=0)
        for col in ["credit","debit"]:
            if col not in df_pivot.columns: df_pivot[col] = 0
        df_pivot = df_pivot.rename(columns={"credit":"Income","debit":"Expenses"}).sort_index()
        st.line_chart(df_pivot[["Income","Expenses"]])
        st.bar_chart(df_pivot[["Income","Expenses"]])
    else:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:10px;padding:20px 22px;text-align:center;color:#4a6070;">
          <div style="font-size:2rem;">&#x1F4C8;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">No transactions yet</div>
          <div style="font-size:0.92rem;">Add income on the <strong>Income</strong> page or log an expense on the <strong>Expenses</strong> page to see your chart here.</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    st.subheader("Expense Breakdown by Category")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT name, SUM(amount) AS total FROM expenses WHERE user_id=%s GROUP BY name ORDER BY total DESC", (user_id,))
        pie_rows = cursor.fetchall()
    if pie_rows:
        df_pie = pd.DataFrame([(r["name"], r["total"]) for r in pie_rows], columns=["Expense","Amount"])
        threshold    = df_pie["Amount"].sum() * 0.02
        df_pie_main  = df_pie[df_pie["Amount"] >= threshold]
        df_pie_other = df_pie[df_pie["Amount"] < threshold]
        if not df_pie_other.empty:
            df_pie_main = pd.concat([df_pie_main, pd.DataFrame([{"Expense":"Others","Amount":df_pie_other["Amount"].sum()}])], ignore_index=True)
        fig = px.pie(df_pie_main, names="Expense", values="Amount", title="All-time Expense Breakdown (NGN)",
                     color_discrete_sequence=px.colors.qualitative.Set3, hole=0.35)
        fig.update_traces(textposition="inside", textinfo="percent+label",
                          hovertemplate="<b>%{label}</b><br>NGN %{value:,.0f}<br>%{percent}<extra></extra>")
        fig.update_layout(margin=dict(t=40,b=10,l=10,r=10), legend=dict(orientation="v",x=1.02,y=0.5))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:10px;padding:20px 22px;text-align:center;color:#4a6070;">
          <div style="font-size:2rem;">&#x1F967;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">Expense breakdown will appear here</div>
          <div style="font-size:0.92rem;">
            Log your first expense on the <strong>Expenses</strong> page —
            or use the Quick Add buttons for Transport, Food, Airtime and more.
          </div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: INCOME =================
elif current_page == "Income":
    st.markdown("## Income")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    if not banks:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:12px;padding:24px;text-align:center;color:#4a6070;margin:12px 0;">
          <div style="font-size:2rem;">&#x1F4B0;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">Add a bank account first</div>
          <div style="font-size:0.92rem;">
            Before you can record income, Budget Right needs to know which account to credit.<br>
            Go to <strong>Banks</strong> and add your first account — it only takes 30 seconds.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Banks page", key="income_goto_banks"):
            st.session_state.nav_radio = pages_clean.index("Banks")
            st.rerun()
        st.stop()

    # -- EDIT FORM at top --
    if st.session_state.get("edit_income_id"):
        edit_id = st.session_state.edit_income_id
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT t.id, t.description, t.amount, t.bank_id FROM transactions t
                JOIN banks b ON t.bank_id = b.id
                WHERE t.id=%s AND b.user_id=%s AND t.type='credit'
            """, (edit_id, user_id))
            inc_row = cursor.fetchone()
        if inc_row:
            display_source = inc_row["description"].replace("Income: ", "", 1)
            st.info(f"Editing: {display_source} — NGN {inc_row['amount']:,.0f}")
            with st.form("edit_income_form"):
                new_source = st.text_input("Income Source", value=display_source)
                new_amount = st.number_input("Amount (NGN)", min_value=1, value=int(inc_row["amount"]))
                save_col, cancel_col = st.columns(2)
                save_clicked   = save_col.form_submit_button("Save Changes")
                cancel_clicked = cancel_col.form_submit_button("Cancel")
            if save_clicked:
                diff = new_amount - inc_row["amount"]
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (diff, inc_row["bank_id"]))
                    cursor.execute("UPDATE transactions SET amount=%s, description=%s WHERE id=%s",
                                   (new_amount, f"Income: {new_source}", inc_row["id"]))
                st.success("Income updated!")
                st.session_state.edit_income_id = None
                st.rerun()
            if cancel_clicked:
                st.session_state.edit_income_id = None
                st.rerun()
        else:
            st.warning("Income entry not found.")
            st.session_state.edit_income_id = None
        st.divider()

    st.subheader("Add Income")
    income_source = st.text_input("Income Source", key="income_source")
    income_amount = st.number_input("Amount (NGN)", min_value=1, key="income_amt")
    if banks:
        bank_map_income = {f"{b['bank_name']} (****{b['account_number']}) - NGN {b['balance']:,}": b["id"] for b in banks}
        selected_bank_income = st.selectbox("Deposit To Bank", list(bank_map_income.keys()), key="bank_income_select")
        if st.button("Add Income", key="add_income_btn"):
            if income_source and income_amount > 0:
                bank_id = bank_map_income[selected_bank_income]
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (income_amount, bank_id))
                    cursor.execute("INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s, 'credit', %s, %s, %s)",
                                   (bank_id, income_amount, f"Income: {income_source}", datetime.now().strftime("%Y-%m-%d")))
                st.success(f"Income of NGN {income_amount:,} added")
                st.rerun()
    else:
        st.info("You need at least one bank account to add income.")

    st.divider()
    st.subheader("Income History")
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT t.id, t.created_at, t.description, t.amount, t.bank_id, b.bank_name, b.account_number
            FROM transactions t JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id=%s AND t.type='credit' AND t.description LIKE 'Income:%%'
            ORDER BY t.created_at DESC
        """, (user_id,))
        income_data = cursor.fetchall()

    if income_data:
        for inc in income_data:
            source = inc["description"].replace("Income: ", "", 1)
            card_col, edit_col, del_col = st.columns([5, 0.5, 0.5])
            with card_col:
                st.markdown(f"""
                <div class="exp-card" style="border-left-color:#0e7c5b;">
                  <div class="exp-card-left">
                    <div class="exp-card-name">{source}</div>
                    <div class="exp-card-bank">Bank: {inc['bank_name']} (****{inc['account_number']})</div>
                    <div class="exp-card-date">Date: {inc['created_at']}</div>
                  </div>
                  <div class="exp-card-right">
                    <div class="exp-card-amount" style="color:#0e7c5b;">+NGN {inc['amount']:,.0f}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            with edit_col:
                if st.button("Edit", key=f"edit_inc_{inc['id']}", help="Edit"):
                    st.session_state.edit_income_id = inc["id"]
                    st.rerun()
            with del_col:
                if st.button("Del", key=f"delete_inc_{inc['id']}", help="Delete"):
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE banks SET balance = balance - %s WHERE id=%s", (inc["amount"], inc["bank_id"]))
                        cursor.execute("DELETE FROM transactions WHERE id=%s", (inc["id"],))
                    st.success(f"'{source}' deleted & NGN {inc['amount']:,.0f} reversed.")
                    st.rerun()
    else:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:10px;padding:20px 22px;text-align:center;color:#4a6070;">
          <div style="font-size:2rem;">&#x1F4B0;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">No income recorded yet</div>
          <div style="font-size:0.92rem;">Add your salary, freelance pay, or any money that came in using the form above.</div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: EXPENSES =================
elif current_page == "Expenses":
    st.markdown("## Expenses")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    # -- EDIT FORM at top --
    if st.session_state.get("edit_exp_id"):
        edit_id = st.session_state.edit_exp_id
        with get_db() as (conn, cursor):
            cursor.execute("SELECT name, amount, bank_id, tx_id FROM expenses WHERE id=%s AND user_id=%s", (edit_id, user_id))
            exp_row = cursor.fetchone()
        if exp_row:
            st.info(f"Editing: {exp_row['name']} — NGN {exp_row['amount']:,.0f}")
            with st.form("edit_expense_form"):
                new_name   = st.text_input("Expense Name", value=exp_row["name"])
                new_amount = st.number_input("Amount (NGN)", min_value=1, value=int(exp_row["amount"]))
                save_col, cancel_col = st.columns(2)
                save_clicked   = save_col.form_submit_button("Save Changes")
                cancel_clicked = cancel_col.form_submit_button("Cancel")
            if save_clicked:
                diff = new_amount - exp_row["amount"]
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE banks SET balance = balance - %s WHERE id=%s", (diff, exp_row["bank_id"]))
                    if exp_row["tx_id"]:
                        cursor.execute("UPDATE transactions SET amount=%s, description=%s WHERE id=%s",
                                       (new_amount, f"Expense: {new_name}", exp_row["tx_id"]))
                    cursor.execute("UPDATE expenses SET name=%s, amount=%s WHERE id=%s AND user_id=%s",
                                   (new_name, new_amount, edit_id, user_id))
                st.success("Expense updated!")
                st.session_state.edit_exp_id = None
                st.rerun()
            if cancel_clicked:
                st.session_state.edit_exp_id = None
                st.rerun()
        else:
            st.warning("Expense not found.")
            st.session_state.edit_exp_id = None
        st.divider()

    if not banks:
        # Empty state — no banks
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:12px;padding:28px 24px;text-align:center;margin:16px 0;">
          <div style="font-size:2.5rem;">&#x1F3E6;</div>
          <div style="font-size:1.1rem;font-weight:700;color:#1a3c5e;margin:8px 0 4px;">No bank account yet</div>
          <div style="color:#4a6070;font-size:0.93rem;">
            You need to add a bank account before you can log expenses.<br>
            Head over to the <strong>Banks</strong> page to get started.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Banks page", key="goto_banks_from_exp"):
            st.session_state.nav_radio = 3  # Banks index
            st.rerun()
        st.stop()

    bank_map = {f"{b['bank_name']} (****{b['account_number']}) - NGN {b['balance']:,}": b["id"] for b in banks}

    # ── QUICK ADD BUTTONS ──────────────────────────────────────────────────
    st.markdown("""
    <style>
    .qa-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }
    .qa-label {
        font-size: 0.82rem; font-weight: 700; color: #1a3c5e;
        text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.subheader("Quick Add Expense")
    st.caption("Tap a category to pre-fill the form below — just enter the amount and submit.")

    # Nigerian daily expense categories
    QUICK_CATEGORIES = [
        ("Transport", "&#x1F695;"),
        ("Airtime/Data", "&#x1F4F1;"),
        ("Food", "&#x1F37D;"),
        ("Fuel", "&#x26FD;"),
        ("Transfer Charges", "&#x1F4B8;"),
        ("Electricity (NEPA)", "&#x26A1;"),
        ("Internet", "&#x1F4F6;"),
        ("Groceries", "&#x1F6D2;"),
        ("Rent", "&#x1F3E0;"),
        ("School Fees", "&#x1F393;"),
        ("Hospital/Drugs", "&#x1F48A;"),
        ("Church/Tithe", "&#x26EA;"),
        ("Water", "&#x1F4A7;"),
        ("Generator Repair", "&#x1F527;"),
        ("Laundry", "&#x1F9FA;"),
        ("Betting", "&#x1F3B2;"),
        ("Subscription", "&#x1F4FA;"),
        ("Hair/Beauty", "&#x1F488;"),
        ("Clothing", "&#x1F455;"),
        ("Savings Deposit", "&#x1F4B0;"),
        ("Other", "&#x1F4DD;"),
    ]

    # Render in rows of 4
    cols_per_row = 4
    rows = [QUICK_CATEGORIES[i:i+cols_per_row] for i in range(0, len(QUICK_CATEGORIES), cols_per_row)]
    for row in rows:
        cols = st.columns(len(row))
        for col, (cat_name, cat_icon) in zip(cols, row):
            with col:
                btn_label = f"{cat_icon} {cat_name}"
                if st.button(btn_label, key=f"qa_{cat_name}", use_container_width=True):
                    st.session_state.quick_add_name = cat_name
                    st.session_state.quick_add_amt  = 0

    st.divider()

    # ── MANUAL / PRE-FILLED ADD FORM ─────────────────────────────────────
    st.subheader("Add Expense")

    # Pre-fill from quick-add if set
    prefill_name = st.session_state.get("quick_add_name", "")
    prefill_amt  = int(st.session_state.get("quick_add_amt", 0))

    with st.form("add_expense_form"):
        expense_name   = st.text_input("Expense Name", value=prefill_name, key="exp_name")
        expense_amount = st.number_input("Amount (NGN)", min_value=1, value=max(prefill_amt, 1), step=100, key="exp_amt")
        selected_bank  = st.selectbox("Pay From Bank", list(bank_map.keys()), key="bank_select")
        submitted_exp  = st.form_submit_button("Add Expense", use_container_width=True)

    if submitted_exp:
        if expense_name and expense_amount > 0:
            bank_id = bank_map[selected_bank]
            save_expense(user_id, bank_id, expense_name, expense_amount)
            st.success(f"Expense '{expense_name}' — NGN {expense_amount:,} added.")
            # Clear quick-add prefill
            st.session_state.quick_add_name = ""
            st.session_state.quick_add_amt  = 0
            st.rerun()
        else:
            st.warning("Please enter a name and amount.")

    st.divider()
    st.subheader("Expense Summary")
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT e.id, e.created_at, e.name, e.amount, e.bank_id, b.bank_name, b.account_number, e.tx_id
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE e.user_id=%s ORDER BY e.created_at DESC
        """, (user_id,))
        expenses_data = cursor.fetchall()

    if expenses_data:
        for exp in expenses_data:
            card_col, edit_col, del_col = st.columns([5, 0.5, 0.5])
            with card_col:
                st.markdown(f"""
                <div class="exp-card">
                  <div class="exp-card-left">
                    <div class="exp-card-name">{exp['name']}</div>
                    <div class="exp-card-bank">Bank: {exp['bank_name']} (****{exp['account_number']})</div>
                    <div class="exp-card-date">Date: {exp['created_at']}</div>
                  </div>
                  <div class="exp-card-right">
                    <div class="exp-card-amount">-NGN {exp['amount']:,.0f}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            with edit_col:
                if st.button("Edit", key=f"edit_exp_{exp['id']}", help="Edit"):
                    st.session_state.edit_exp_id = exp["id"]
                    st.rerun()
            with del_col:
                if st.button("Del", key=f"delete_exp_{exp['id']}", help="Delete"):
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (exp["amount"], exp["bank_id"]))
                        if exp["tx_id"]:
                            cursor.execute("DELETE FROM transactions WHERE id=%s", (exp["tx_id"],))
                        cursor.execute("DELETE FROM expenses WHERE id=%s AND user_id=%s", (exp["id"], user_id))
                    st.success(f"'{exp['name']}' deleted & NGN {exp['amount']:,.0f} refunded.")
                    st.rerun()

        st.divider()
        st.subheader("Your Expense Breakdown")
        df_exp_pie = pd.DataFrame([(e["name"], e["amount"]) for e in expenses_data], columns=["Expense","Amount"])
        df_grouped = df_exp_pie.groupby("Expense", as_index=False)["Amount"].sum().sort_values("Amount", ascending=False)
        threshold = df_grouped["Amount"].sum() * 0.02
        df_main  = df_grouped[df_grouped["Amount"] >= threshold]
        df_other = df_grouped[df_grouped["Amount"] < threshold]
        if not df_other.empty:
            df_main = pd.concat([df_main, pd.DataFrame([{"Expense":"Others","Amount":df_other["Amount"].sum()}])], ignore_index=True)
        fig = px.pie(df_main, names="Expense", values="Amount", title="Expenses by Name (NGN)",
                     color_discrete_sequence=px.colors.qualitative.Pastel, hole=0.35)
        fig.update_traces(textposition="inside", textinfo="percent+label",
                          hovertemplate="<b>%{label}</b><br>NGN %{value:,.0f}<br>%{percent}<extra></extra>")
        fig.update_layout(margin=dict(t=40,b=10,l=10,r=10), legend=dict(orientation="v",x=1.02,y=0.5))
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Empty state — no expenses yet
        st.markdown("""
        <div style="background:#fff8f0;border-left:4px solid #f39c12;border-radius:10px;padding:20px 22px;margin:8px 0;">
          <div style="font-size:1.8rem;">&#x1F9FE;</div>
          <div style="font-weight:700;color:#7d5a00;margin:6px 0 4px;">No expenses recorded yet</div>
          <div style="color:#8a6320;font-size:0.92rem;">
            Use the Quick Add buttons above to log your first expense in seconds,
            or type a custom name in the form.
          </div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: BANKS =================
elif current_page == "Banks":
    st.markdown("## Bank Accounts")
    st.subheader("Add Bank Account")
    bank_name       = st.text_input("Bank Name", key="bank_name")
    account_name    = st.text_input("Account Name", key="acct_name")
    account_number  = st.text_input("Account Number (last 4 digits)", key="acct_num")
    opening_balance = st.number_input("Opening Balance (NGN)", min_value=0, key="open_bal")
    min_alert       = st.number_input("Alert me if balance falls below (NGN)", min_value=0, value=0, key="min_alert")
    if st.button("Add Bank", key="add_bank_btn"):
        if bank_name and account_name and account_number:
            with get_db() as (conn, cursor):
                cursor.execute("INSERT INTO banks (user_id, bank_name, account_name, account_number, balance, min_balance_alert) VALUES (%s, %s, %s, %s, %s, %s)",
                               (user_id, bank_name, account_name, account_number[-4:], opening_balance, min_alert))
            st.success("Bank added")
            st.rerun()
        else:
            st.warning("Please fill all fields.")

    st.divider()
    st.subheader("Manage Bank Accounts")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks_manage = cursor.fetchall()

    if banks_manage:
        for bank in banks_manage:
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(f"**{bank['bank_name']}** (****{bank['account_number']}) — NGN {bank['balance']:,.0f}")
            with col2:
                if st.button("Edit", key=f"edit_bank_{bank['id']}"):
                    st.session_state.edit_bank_id = bank["id"]
            with col3:
                if st.button("Delete", key=f"delete_bank_{bank['id']}"):
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE expenses SET tx_id=NULL WHERE bank_id=%s", (bank["id"],))
                        cursor.execute("DELETE FROM expenses WHERE bank_id=%s", (bank["id"],))
                        cursor.execute("DELETE FROM transactions WHERE bank_id=%s", (bank["id"],))
                        cursor.execute("DELETE FROM banks WHERE id=%s", (bank["id"],))
                    st.success("Bank and all its transactions deleted.")
                    st.rerun()

        if st.session_state.get("edit_bank_id"):
            edit_id = st.session_state.edit_bank_id
            with get_db() as (conn, cursor):
                cursor.execute("SELECT bank_name, account_name, account_number FROM banks WHERE id=%s", (edit_id,))
                bank = cursor.fetchone()
            if bank:
                st.markdown("### Edit Bank")
                new_name     = st.text_input("Bank Name",      value=bank["bank_name"])
                new_acc_name = st.text_input("Account Name",   value=bank["account_name"])
                new_acc_num  = st.text_input("Account Number", value=bank["account_number"])
                if st.button("Update Bank"):
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE banks SET bank_name=%s, account_name=%s, account_number=%s WHERE id=%s",
                                       (new_name, new_acc_name, new_acc_num, edit_id))
                    st.success("Bank updated.")
                    st.session_state.edit_bank_id = None
                    st.rerun()
    else:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:10px;padding:20px 22px;text-align:center;color:#4a6070;margin-top:12px;">
          <div style="font-size:2rem;">&#x1F3E6;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">No bank accounts yet</div>
          <div style="font-size:0.92rem;">Use the form above to add your GTB, Access, Opay, or any other account.<br>
          Your ATM card number is never needed — just your bank name and last 4 digits.</div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: TRANSFERS =================
elif current_page == "Transfers":
    st.markdown("## Transfer Between Banks")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    if len(banks) >= 2:
        bank_map_transfer = {f"{b['bank_name']} (****{b['account_number']}) - NGN {b['balance']:,}": b["id"] for b in banks}
        from_bank       = st.selectbox("From Bank", list(bank_map_transfer.keys()), key="from_bank")
        to_bank         = st.selectbox("To Bank",   list(bank_map_transfer.keys()), key="to_bank")
        transfer_amount = st.number_input("Amount to Transfer (NGN)", min_value=1, key="transfer_amt")
        if st.button("Transfer", key="transfer_btn"):
            if from_bank == to_bank:
                st.warning("Cannot transfer to the same bank")
            else:
                from_id = bank_map_transfer[from_bank]
                to_id   = bank_map_transfer[to_bank]
                with get_db() as (conn, cursor):
                    cursor.execute("SELECT balance FROM banks WHERE id=%s", (from_id,))
                    from_balance = cursor.fetchone()["balance"]
                    if transfer_amount > from_balance:
                        st.error("Insufficient funds")
                    else:
                        now = datetime.now().strftime("%Y-%m-%d")
                        cursor.execute("UPDATE banks SET balance = balance - %s WHERE id=%s", (transfer_amount, from_id))
                        cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (transfer_amount, to_id))
                        cursor.execute("INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s, 'debit', %s, %s, %s)",
                                       (from_id, transfer_amount, f"Transfer to bank {to_id}", now))
                        cursor.execute("INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s, 'credit', %s, %s, %s)",
                                       (to_id, transfer_amount, f"Transfer from bank {from_id}", now))
                        st.success("Transfer completed")
                        st.rerun()
    else:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:10px;padding:20px 22px;text-align:center;color:#4a6070;">
          <div style="font-size:2rem;">&#x1F4B8;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">You need at least two bank accounts to transfer</div>
          <div style="font-size:0.92rem;">Add a second account on the <strong>Banks</strong> page, then come back here to move money between them.</div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: SAVINGS GOALS =================
elif current_page == "Savings Goals":
    st.markdown("## Savings Goals")

    # Check for banks first
    with get_db() as (conn, cursor):
        cursor.execute("SELECT COUNT(*) AS n FROM banks WHERE user_id=%s", (user_id,))
        goals_bank_count = cursor.fetchone()["n"]

    if goals_bank_count == 0:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:12px;padding:24px;text-align:center;color:#4a6070;margin:12px 0;">
          <div style="font-size:2rem;">&#x1F3AF;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">Add a bank account first</div>
          <div style="font-size:0.92rem;">
            Savings goal contributions are deducted from a bank account.<br>
            Add your bank on the <strong>Banks</strong> page, then set up your goals here.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Banks page", key="goals_goto_banks"):
            st.session_state.nav_radio = pages_clean.index("Banks")
            st.rerun()
        st.stop()

    # ── Create New Goal form (always at top so it's always visible) ──
    with st.expander("Create New Goal", expanded=False):
        with st.form("create_goal_form"):
            goal_name   = st.text_input("Goal Name", key="goal_name")
            goal_target = st.number_input("Target Amount (NGN)", min_value=1, key="goal_target")
            submitted   = st.form_submit_button("Create Goal")
        if submitted:
            if goal_name and goal_target > 0:
                with get_db() as (conn, cursor):
                    cursor.execute(
                        "INSERT INTO goals (user_id, name, target_amount, created_at, current_amount, status) "
                        "VALUES (%s, %s, %s, %s, 0, 'active')",
                        (user_id, goal_name, int(goal_target), datetime.now().strftime("%Y-%m-%d"))
                    )
                st.success(f"Goal '{goal_name}' created!")
                st.rerun()
            else:
                st.warning("Please enter a name and a target amount greater than 0.")

    st.divider()

    # ── Contribution form (shown above goal list when "Add Money" is clicked) ──
    if st.session_state.show_goal_contribution and st.session_state.selected_goal:
        goal_id = st.session_state.selected_goal
        with get_db() as (conn, cursor):
            cursor.execute(
                "SELECT name, target_amount, current_amount FROM goals WHERE id=%s AND user_id=%s",
                (goal_id, user_id)
            )
            g = cursor.fetchone()
        if g:
            remaining = g["target_amount"] - g["current_amount"]
            st.info(f"Adding money to: **{g['name']}** — NGN {g['current_amount']:,.0f} saved, NGN {remaining:,.0f} remaining")
            with get_db() as (conn, cursor):
                cursor.execute("SELECT id, bank_name, balance FROM banks WHERE user_id=%s", (user_id,))
                bank_list = cursor.fetchall()
            if bank_list:
                bank_options = {f"{b['bank_name']} (NGN {b['balance']:,})": b["id"] for b in bank_list}
                bank_labels  = list(bank_options.keys())

                with st.form("goal_contribution_form"):
                    selected_bank  = st.selectbox("From Bank", bank_labels)
                    contrib_amount = st.number_input("Amount to add (NGN)", min_value=1, step=1, value=1)
                    confirm_col, cancel_col = st.columns(2)
                    confirm = confirm_col.form_submit_button("Confirm Contribution")
                    cancel  = cancel_col.form_submit_button("Cancel")

                    if confirm:
                        # Cast everything to int — number_input returns float
                        amt     = int(contrib_amount)
                        bank_id = bank_options[selected_bank]
                        try:
                            with get_db() as (conn, cursor):
                                cursor.execute("SELECT balance FROM banks WHERE id=%s", (bank_id,))
                                bank_balance = int(cursor.fetchone()["balance"])
                                if amt > bank_balance:
                                    st.error(f"Insufficient funds. Bank balance is NGN {bank_balance:,}.")
                                else:
                                    now         = datetime.now().strftime("%Y-%m-%d")
                                    new_current = int(g["current_amount"]) + amt
                                    new_status  = "completed" if new_current >= int(g["target_amount"]) else "active"
                                    cursor.execute(
                                        "UPDATE goals SET current_amount=%s, status=%s WHERE id=%s AND user_id=%s",
                                        (new_current, new_status, goal_id, user_id)
                                    )
                                    cursor.execute(
                                        "UPDATE banks SET balance = balance - %s WHERE id=%s",
                                        (amt, bank_id)
                                    )
                                    cursor.execute(
                                        "INSERT INTO transactions (bank_id, type, amount, description, created_at) "
                                        "VALUES (%s, 'debit', %s, %s, %s)",
                                        (bank_id, amt, f"Savings goal: {g['name']}", now)
                                    )
                            st.success(f"Added NGN {amt:,} to '{g['name']}'.")
                            st.session_state.show_goal_contribution = False
                            st.session_state.selected_goal = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"Something went wrong: {e}")

                    if cancel:
                        st.session_state.show_goal_contribution = False
                        st.session_state.selected_goal = None
                        st.rerun()
            else:
                st.warning("You need a bank account to transfer from.")
                if st.button("Cancel", key="cancel_contrib_no_bank"):
                    st.session_state.show_goal_contribution = False
                    st.session_state.selected_goal = None
                    st.rerun()
        else:
            st.session_state.show_goal_contribution = False
            st.session_state.selected_goal = None

    # ── Goals list — active first, then completed ──
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT id, name, target_amount, current_amount, status
            FROM goals
            WHERE user_id = %s
            ORDER BY
                CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                created_at DESC
        """, (user_id,))
        goals = cursor.fetchall()

    if not goals:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:12px;padding:24px;text-align:center;color:#4a6070;margin-top:8px;">
          <div style="font-size:2.2rem;">&#x1F3AF;</div>
          <div style="font-weight:700;margin:8px 0 4px;color:#1a3c5e;">No savings goals yet</div>
          <div style="font-size:0.93rem;">
            Use the <strong>Create New Goal</strong> form above to set a target — emergency fund,
            new phone, school fees, rent, or anything you're saving towards.
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        active_goals    = [g for g in goals if g["status"] == "active"]
        completed_goals = [g for g in goals if g["status"] == "completed"]

        def render_goal(goal):
            progress = (goal["current_amount"] / goal["target_amount"] * 100) if goal["target_amount"] > 0 else 0
            col1, col2, col3 = st.columns([5, 1, 1])
            with col1:
                st.markdown(f"**{goal['name']}**")
                st.progress(
                    min(progress / 100, 1.0),
                    text=f"NGN {goal['current_amount']:,.0f} / NGN {goal['target_amount']:,.0f} ({progress:.1f}%)"
                )
            with col2:
                if goal["status"] == "active":
                    if st.button("Add Money", key=f"add_goal_{goal['id']}"):
                        st.session_state.selected_goal          = goal["id"]
                        st.session_state.show_goal_contribution = True
                        st.rerun()
                else:
                    st.markdown("Completed")
            with col3:
                if st.button("Delete", key=f"delete_goal_{goal['id']}"):
                    with get_db() as (conn, cursor):
                        cursor.execute("DELETE FROM goals WHERE id=%s AND user_id=%s", (goal["id"], user_id))
                    st.success(f"'{goal['name']}' deleted.")
                    st.rerun()

        if active_goals:
            st.subheader(f"Active Goals ({len(active_goals)})")
            for goal in active_goals:
                render_goal(goal)
                st.divider()

        if completed_goals:
            st.subheader(f"Completed Goals ({len(completed_goals)})")
            for goal in completed_goals:
                render_goal(goal)
                st.divider()

# ================= PAGE: IMPORT CSV =================
elif current_page == "Import CSV":
    st.markdown("## Import Bank Statement (CSV)")

    # Check if user has banks first
    with get_db() as (conn, cursor):
        cursor.execute("SELECT COUNT(*) AS n FROM banks WHERE user_id=%s", (user_id,))
        csv_bank_count = cursor.fetchone()["n"]

    if csv_bank_count == 0:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:12px;padding:24px;text-align:center;color:#4a6070;margin:12px 0;">
          <div style="font-size:2rem;">&#x1F4E5;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">Add a bank account before importing</div>
          <div style="font-size:0.92rem;">
            Your CSV transactions need to be linked to a bank account.<br>
            Add your bank on the <strong>Banks</strong> page first, then come back to import.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Banks page", key="csv_goto_banks"):
            st.session_state.nav_radio = pages_clean.index("Banks")
            st.rerun()
    else:
        with st.expander("How does CSV import work?", expanded=False):
            st.markdown("""
            1. **Download your bank statement** as a CSV from your bank's app or internet banking portal.
            2. **Upload it here** using the file uploader below.
            3. **Map the columns** — tell Budget Right which column is the amount, date, and description.
            4. **Preview and import** — every row becomes an expense and debits your bank balance.

            **Supported banks:** GTB, Access, Zenith, UBA, First Bank, Opay, Kuda, and any bank that exports CSV.
            """)
        conn_csv = get_connection()
        try:
            csv_import_page(conn_csv, user_id)
        finally:
            conn_csv.close()

# ================= PAGE: SETTINGS =================
elif current_page == "Settings":
    st.markdown("## Settings")
    st.subheader("Monthly Spending Budget")
    st.caption(
        "Set a limit on how much you want to spend each month. "
        "Budget Right will alert you on the Dashboard at 50%, 80%, and 100% of your limit."
    )
    with get_db() as (conn, cursor):
        cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
        current_limit = cursor.fetchone()["monthly_spending_limit"] or 0
    new_limit = st.number_input("Monthly Budget (NGN) — set to 0 to disable alerts", min_value=0, value=current_limit, step=5000, key="monthly_limit")
    if st.button("Update Budget", key="update_limit_btn"):
        with get_db() as (conn, cursor):
            cursor.execute("UPDATE users SET monthly_spending_limit=%s WHERE id=%s", (new_limit, user_id))
        st.success("Monthly budget updated. Alerts will show on your Dashboard.")
        st.rerun()

    st.divider()
    st.subheader("Change Password")
    current_pw     = st.text_input("Current Password",    type="password", key="current_pw")
    new_pw         = st.text_input("New Password",         type="password", key="new_pw")
    confirm_new_pw = st.text_input("Confirm New Password", type="password", key="confirm_new_pw")
    if st.button("Change Password", key="change_pw_btn"):
        if current_pw and new_pw and confirm_new_pw:
            if new_pw != confirm_new_pw:
                st.error("New passwords do not match.")
            else:
                pw_ok, pw_msg = validate_password(new_pw)
                if not pw_ok:
                    st.error(pw_msg)
                else:
                    success, msg = change_password(user_id, current_pw, new_pw)
                    st.success(msg) if success else st.error(msg)
        else:
            st.warning("All fields required.")
