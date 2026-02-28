import streamlit as st
st.set_page_config(page_title="Budgeting Smart", page_icon="💰", layout="wide")

# ---------------- MOBILE CSS ----------------
st.markdown("""
<style>
/* ══════════════════════════════════════════
   BASE — prevent horizontal overflow on all screens
══════════════════════════════════════════ */
html, body {
    overflow-x: hidden !important;
}
.main .block-container {
    max-width: 100% !important;
}

/* ══════════════════════════════════════════
   MOBILE  ≤ 640 px
══════════════════════════════════════════ */
@media screen and (max-width: 640px) {

    /* Tighter content padding */
    .main .block-container {
        padding: 0.6rem 0.7rem 1rem 0.7rem !important;
    }

    /* Page title */
    h1 { font-size: 1.4rem !important; line-height: 1.3 !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; }

    /* ── Stack ALL st.columns rows vertically ── */
    div[data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 0.4rem !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] {
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }

    /* ── Metric cards ── */
    div[data-testid="stMetric"] {
        background: #f4fbf8 !important;
        border: 1px solid #c8e6da !important;
        border-radius: 10px !important;
        padding: 0.65rem 0.8rem !important;
        margin-bottom: 0.4rem !important;
    }

    /* ── Buttons: full-width, tall enough to tap ── */
    .stButton > button {
        width: 100% !important;
        min-height: 2.8rem !important;
        font-size: 0.98rem !important;
        border-radius: 8px !important;
        margin-bottom: 0.3rem !important;
    }

    /* ── Inputs & selects ── */
    input, textarea,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    div[data-baseweb="select"] {
        font-size: 1rem !important;
        min-height: 2.6rem !important;
        width: 100% !important;
        box-sizing: border-box !important;
    }

    /* ── Tabs: scroll horizontally so nothing is cut off ── */
    div[data-testid="stTabs"] > div:first-child {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        white-space: nowrap !important;
        scrollbar-width: none !important;
    }
    div[data-testid="stTabs"] > div:first-child::-webkit-scrollbar {
        display: none !important;
    }

    /* ── Sidebar: narrower so content area keeps space ── */
    section[data-testid="stSidebar"] {
        min-width: 200px !important;
        max-width: 220px !important;
    }
    section[data-testid="stSidebar"] label {
        font-size: 0.92rem !important;
    }

    /* ── Charts: scroll rather than overflow ── */
    div[data-testid="stArrowVegaLiteChart"],
    div[data-testid="stVegaLiteChart"],
    .stPlotlyChart {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
    }

    /* ── Dataframes / tables ── */
    div[data-testid="stDataFrame"],
    div[data-testid="stTable"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
    }

    /* ── Expanders ── */
    details, div[data-testid="stExpander"] {
        width: 100% !important;
    }

    /* ── Progress bars ── */
    div[data-testid="stProgress"] {
        width: 100% !important;
    }

    /* ── Landing page hero ── */
    .landing-hero {
        padding: 24px 14px 20px 14px !important;
        border-radius: 12px !important;
    }
    .landing-title   { font-size: 1.6rem !important; }
    .landing-tagline { font-size: 0.9rem !important; }
    .landing-desc    { font-size: 0.88rem !important; }

    /* ── Demo & feature cards ── */
    .demo-card  { padding: 12px !important; }
    .demo-row   { font-size: 0.82rem !important; flex-wrap: wrap !important; }
    .feature-card { margin-bottom: 0.5rem !important; }

    /* ── Reduce whitespace between elements ── */
    hr { margin: 0.6rem 0 !important; }
    .stAlert { font-size: 0.9rem !important; }
}

/* ══════════════════════════════════════════
   TABLET  641 px – 900 px
══════════════════════════════════════════ */
@media screen and (min-width: 641px) and (max-width: 900px) {
    .main .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
    /* Let columns stay side-by-side but prevent squeezing too small */
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] {
        min-width: 44% !important;
        flex-wrap: wrap !important;
    }
    .stButton > button {
        min-height: 2.5rem !important;
        font-size: 0.96rem !important;
    }
}
</style>
""", unsafe_allow_html=True)
import sqlite3
import bcrypt
import random
import smtplib
import uuid
import secrets
from contextlib import contextmanager
from email.message import EmailMessage
from datetime import datetime, timedelta
import pandas as pd

from csv_import import csv_import_page

# ---------------- DATABASE ----------------
DB_NAME = "budgeting_Smsrt.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_db():
    """Open a fresh connection, yield (conn, cursor), commit+close on exit."""
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surname TEXT NOT NULL,
            other_names TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password BLOB NOT NULL,
            email_verified INTEGER DEFAULT 0,
            verification_code TEXT,
            role TEXT DEFAULT 'user',
            monthly_spending_limit INTEGER DEFAULT 0,
            created_at TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS banks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bank_name TEXT NOT NULL,
            account_name TEXT NOT NULL,
            account_number TEXT NOT NULL,
            balance INTEGER DEFAULT 0,
            min_balance_alert INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_id INTEGER NOT NULL,
            type TEXT CHECK(type IN ('credit','debit')),
            amount INTEGER NOT NULL,
            description TEXT,
            created_at TEXT,
            FOREIGN KEY(bank_id) REFERENCES banks(id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bank_id INTEGER,
            name TEXT NOT NULL,
            amount INTEGER NOT NULL,
            created_at TEXT,
            tx_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(bank_id) REFERENCES banks(id),
            FOREIGN KEY(tx_id) REFERENCES transactions(id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            target_amount INTEGER NOT NULL,
            current_amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)
        # Analytics: one row per login event
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            login_date TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)
        # Persistent session tokens for cookie-based login
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)

create_tables()

def migrate_db():
    """Safe migrations for existing databases — only runs if column is missing."""
    with get_db() as (conn, cursor):
        cursor.execute("PRAGMA table_info(expenses)")
        columns = [row[1] for row in cursor.fetchall()]
        if "tx_id" not in columns:
            cursor.execute("ALTER TABLE expenses ADD COLUMN tx_id INTEGER REFERENCES transactions(id)")
        # Add last_login to users if missing
        cursor.execute("PRAGMA table_info(users)")
        user_cols = [row[1] for row in cursor.fetchall()]
        if "last_login" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN last_login TEXT")

migrate_db()

# ---------------- SESSION ----------------
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

# ---------------- AUTH FUNCTIONS ----------------
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

def register_user(surname, other, email, username, password):
    code = str(random.randint(100000, 999999))
    try:
        hashed_pw = hash_password(password)
        with get_db() as (conn, cursor):
            cursor.execute("""
                INSERT INTO users (surname, other_names, email, username, password, verification_code, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (surname, other, email, username, hashed_pw, code, datetime.now().strftime("%Y-%m-%d")))
        return code, "User created"
    except sqlite3.IntegrityError as e:
        return None, str(e)

def login_user(username, password):
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, password, role, email_verified FROM users WHERE username=?", (username,))
        user = cursor.fetchone()
    if user:
        user_id, pw_hash, role, verified = user
        if verified == 0:
            st.warning("Email not verified. Please verify before logging in.")
            return None
        if check_password(password, pw_hash):
            st.session_state.user_id = user_id
            st.session_state.user_role = role
            return user_id
    return None

def send_verification_email(email, code):
    try:
        msg = EmailMessage()
        msg["Subject"] = "Verify your Budget Smart account"
        msg["From"] = st.secrets["EMAIL_SENDER"]
        msg["To"] = email
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
            cursor.execute("UPDATE users SET verification_code=? WHERE email=?", (code, email))
            if cursor.rowcount == 0:
                return False, "Email not found"
        return send_verification_email(email, code)
    except Exception as e:
        return False, str(e)

def reset_password(email, code, new_password):
    try:
        with get_db() as (conn, cursor):
            cursor.execute("SELECT id FROM users WHERE email=? AND verification_code=?", (email, code))
            user = cursor.fetchone()
            if not user:
                return False, "Invalid reset code"
            hashed_pw = hash_password(new_password)
            cursor.execute("UPDATE users SET password=?, verification_code=NULL WHERE email=?", (hashed_pw, email))
        return True, "Password reset successful"
    except Exception as e:
        return False, str(e)

def resend_verification(email):
    try:
        code = str(random.randint(100000, 999999))
        with get_db() as (conn, cursor):
            cursor.execute("UPDATE users SET verification_code=? WHERE email=?", (code, email))
            if cursor.rowcount == 0:
                return False, "Email not found"
        return send_verification_email(email, code)
    except Exception as e:
        return False, str(e)

def change_password(user_id, current_pw, new_pw):
    with get_db() as (conn, cursor):
        cursor.execute("SELECT password FROM users WHERE id=?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, "User not found"
        if check_password(current_pw, row[0]):
            cursor.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_pw), user_id))
            return True, "Password updated"
        else:
            return False, "Current password incorrect"

# ---------------- PERSISTENT SESSION (query_params) ----------------
# Token stored in URL as ?t=<token>.
# Survives: refresh, tab close+reopen, browser restart, device reboot.
# Cleared only on: logout (removes param) or explicit URL edit.
PARAM_KEY = "t"

def _read_token_from_url() -> str | None:
    """Pull the session token out of the URL query string."""
    try:
        return st.query_params.get(PARAM_KEY)
    except Exception:
        return None

def _write_token_to_url(token: str):
    """Embed the session token into the URL query string."""
    try:
        st.query_params[PARAM_KEY] = token
    except Exception:
        pass

def _clear_token_from_url():
    """Remove the session token from the URL query string."""
    try:
        st.query_params.pop(PARAM_KEY, None)
    except Exception:
        pass

def create_session_token(user_id: int) -> str:
    """Generate a secure random token, persist in DB, write to URL."""
    token = secrets.token_urlsafe(48)
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO session_tokens (user_id, token, created_at) VALUES (?, ?, ?)",
            (user_id, token, now)
        )
    _write_token_to_url(token)
    return token

def validate_session_token(token: str):
    """Return (user_id, role) if token exists in DB, else (None, None)."""
    if not token:
        return None, None
    try:
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT u.id, u.role
                FROM session_tokens s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = ? AND u.email_verified = 1
            """, (token,))
            row = cursor.fetchone()
        if row:
            return row[0], row[1]
    except Exception:
        pass
    return None, None

def revoke_session_token(token: str):
    """Delete token from DB and remove from URL."""
    if not token:
        return
    try:
        with get_db() as (conn, cursor):
            cursor.execute("DELETE FROM session_tokens WHERE token = ?", (token,))
    except Exception:
        pass
    _clear_token_from_url()

# ---------------- ANALYTICS FUNCTIONS ----------------
def track_login(user_id):
    """Record a login event and update last_login timestamp."""
    try:
        now = datetime.now().strftime("%Y-%m-%d")
        with get_db() as (conn, cursor):
            cursor.execute(
                "INSERT INTO analytics_logins (user_id, login_date) VALUES (?, ?)",
                (user_id, now)
            )
            cursor.execute(
                "UPDATE users SET last_login=? WHERE id=?",
                (now, user_id)
            )
    except Exception:
        pass  # Never crash the app over analytics

def track_signup(user_id):
    """Record signup as a login event too — counts as day-1 activity."""
    try:
        now = datetime.now().strftime("%Y-%m-%d")
        with get_db() as (conn, cursor):
            cursor.execute(
                "INSERT INTO analytics_logins (user_id, login_date) VALUES (?, ?)",
                (user_id, now)
            )
    except Exception:
        pass

def get_analytics():
    """Return a dict of all key analytics figures."""
    try:
        with get_db() as (conn, cursor):
            today = datetime.now().strftime("%Y-%m-%d")
            cutoff_30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            cutoff_7  = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

            cursor.execute("SELECT COUNT(*) FROM users WHERE email_verified=1")
            total_verified = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM users")
            total_registered = cursor.fetchone()[0] or 0

            cursor.execute(
                "SELECT COUNT(DISTINCT user_id) FROM analytics_logins WHERE login_date=?",
                (today,)
            )
            dau = cursor.fetchone()[0] or 0  # Daily Active Users

            cursor.execute(
                "SELECT COUNT(DISTINCT user_id) FROM analytics_logins WHERE login_date >= ?",
                (cutoff_7,)
            )
            wau = cursor.fetchone()[0] or 0  # Weekly Active Users

            cursor.execute(
                "SELECT COUNT(DISTINCT user_id) FROM analytics_logins WHERE login_date >= ?",
                (cutoff_30,)
            )
            mau = cursor.fetchone()[0] or 0  # Monthly Active Users

            # New signups in last 30 days
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?",
                (cutoff_30,)
            )
            new_signups_30d = cursor.fetchone()[0] or 0

            # Signups today
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE created_at=?",
                (today,)
            )
            signups_today = cursor.fetchone()[0] or 0

            # Daily logins for last 14 days (for chart)
            cursor.execute("""
                SELECT login_date, COUNT(DISTINCT user_id)
                FROM analytics_logins
                WHERE login_date >= date('now', '-14 days')
                GROUP BY login_date ORDER BY login_date
            """)
            daily_rows = cursor.fetchall()

            # Inactive users: verified, never logged in OR last_login > 14 days ago
            cursor.execute("""
                SELECT id, surname, other_names, email, last_login
                FROM users
                WHERE email_verified=1
                AND (last_login IS NULL OR last_login < ?)
                ORDER BY last_login ASC
            """, (cutoff_7,))
            inactive_users = cursor.fetchall()

        return {
            "total_registered": total_registered,
            "total_verified": total_verified,
            "dau": dau,
            "wau": wau,
            "mau": mau,
            "new_signups_30d": new_signups_30d,
            "signups_today": signups_today,
            "daily_rows": daily_rows,
            "inactive_users": inactive_users,
        }
    except Exception as e:
        return {}

def notify_admin_new_signup(new_name, new_username, new_email):
    """Email the admin instantly when a new user signs up."""
    try:
        with get_db() as (conn, cursor):
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0] or 0

        msg = EmailMessage()
        msg["Subject"] = f"🆕 New signup on Budget Right — {new_name}"
        msg["From"] = st.secrets["EMAIL_SENDER"]
        msg["To"] = st.secrets["ADMIN_EMAIL"]
        msg.set_content(f"""New user just signed up on Budget Right!

Name:     {new_name}
Username: {new_username}
Email:    {new_email}
Time:     {datetime.now().strftime("%Y-%m-%d %H:%M")}

Total registered users: {total_users}

Log into the admin panel to view all users.
""")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(st.secrets["EMAIL_SENDER"], st.secrets["EMAIL_APP_PASSWORD"])
            server.send_message(msg)
    except Exception:
        pass  # Never crash the app if admin notification fails

def send_reengagement_email(email, name):
    """Send a re-engagement nudge email to an inactive user."""
    try:
        msg = EmailMessage()
        msg["Subject"] = "We miss you on Budget Right 💰"
        msg["From"] = st.secrets["EMAIL_SENDER"]
        msg["To"] = email
        msg.set_content(f"""Hi {name},

You haven't logged into Budget Right in a while — your finances miss you! 😊

Log back in to check your balance, track your spending, and stay on top of your savings goals.

👉 Visit the app and pick up where you left off.

Stay financially smart,
The Budget Right Team
""")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(st.secrets["EMAIL_SENDER"], st.secrets["EMAIL_APP_PASSWORD"])
            server.send_message(msg)
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

# ---------------- UI ----------------
# ── Restore session from URL token on every rerun ──
# Runs FIRST before anything renders so the logged-in state is set immediately.
if st.session_state.user_id is None:
    _raw = _read_token_from_url()
    if _raw:
        _uid, _role = validate_session_token(str(_raw))
        if _uid:
            st.session_state.user_id       = _uid
            st.session_state.user_role     = _role
            st.session_state.session_token = str(_raw)
        else:
            # Token in URL is invalid/expired — clean it up
            _clear_token_from_url()

st.title("Budget Right")

# ================= AUTH =================
if st.session_state.user_id is None:

    # -------- LANDING PAGE --------
    st.markdown("""
    <style>
    .landing-hero {
        background: linear-gradient(135deg, #1a3c5e 0%, #0e7c5b 100%);
        border-radius: 16px;
        padding: 48px 40px 40px 40px;
        text-align: center;
        margin-bottom: 8px;
    }
    .landing-logo {
        font-size: 56px;
        margin-bottom: 4px;
        display: block;
    }
    .landing-title {
        font-size: 2.6rem;
        font-weight: 800;
        color: #ffffff;
        margin: 0 0 6px 0;
        letter-spacing: -0.5px;
    }
    .landing-tagline {
        font-size: 1.1rem;
        color: #a8d8c8;
        margin: 0 0 28px 0;
        font-weight: 400;
    }
    .landing-desc {
        font-size: 1.05rem;
        color: #d4eee6;
        max-width: 560px;
        margin: 0 auto;
        line-height: 1.7;
    }
    .feature-card {
        background: #f0f7f4;
        border-left: 4px solid #0e7c5b;
        border-radius: 10px;
        padding: 18px 20px;
        height: 100%;
    }
    .feature-icon { font-size: 1.8rem; }
    .feature-title { font-weight: 700; color: #1a3c5e; font-size: 1rem; margin: 6px 0 4px 0; }
    .feature-text  { color: #4a6070; font-size: 0.92rem; line-height: 1.5; }
    .demo-card {
        background: #ffffff;
        border: 1px solid #d0e8df;
        border-radius: 14px;
        padding: 24px;
        margin-bottom: 4px;
    }
    .demo-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 0;
        border-bottom: 1px solid #eef5f2;
        font-size: 0.95rem;
    }
    .demo-row:last-child { border-bottom: none; }
    .demo-credit { color: #0e7c5b; font-weight: 600; }
    .demo-debit  { color: #c0392b; font-weight: 600; }
    .demo-label  { color: #2c3e50; }
    .demo-date   { color: #95a5a6; font-size: 0.82rem; }
    .badge {
        display: inline-block;
        background: #e8f5f0;
        color: #0e7c5b;
        border-radius: 20px;
        padding: 4px 14px;
        font-size: 0.82rem;
        font-weight: 600;
        margin: 4px 4px 0 0;
    }
    </style>
    """, unsafe_allow_html=True)

    # — Hero —
    st.markdown("""
    <div class="landing-hero">
      <span class="landing-logo">💰</span>
      <p class="landing-title">Budget Right</p>
      <p class="landing-tagline">🔒 Secure budget tracking — built for Nigerians</p>
      <p class="landing-desc">
        Track your income, expenses, and savings easily.<br>
        Know exactly where your money goes — in naira, every day.
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # — Feature cards —
    fc1, fc2, fc3, fc4 = st.columns(4)
    features = [
        ("💳", "Multiple Banks", "Link all your accounts — GTB, Access, Opay and more — in one place."),
        ("📊", "Live Dashboard", "See your total balance, monthly spend, and net savings at a glance."),
        ("🎯", "Savings Goals", "Set a target, contribute from any bank, and track your progress."),
        ("📥", "CSV Import", "Upload your bank statement and have it auto-parsed into your ledger."),
    ]
    for col, (icon, title, text) in zip([fc1, fc2, fc3, fc4], features):
        with col:
            st.markdown(f"""
            <div class="feature-card">
              <div class="feature-icon">{icon}</div>
              <div class="feature-title">{title}</div>
              <div class="feature-text">{text}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # — Demo screenshot —
    demo_col, auth_col = st.columns([1.1, 1], gap="large")

    with demo_col:
        st.markdown("#### 📱 See it in action")
        st.markdown("""
        <div class="demo-card">
          <div style="font-weight:700;color:#1a3c5e;margin-bottom:12px;font-size:1rem;">
            💳 My Dashboard &nbsp;·&nbsp;
            <span style="color:#0e7c5b;">₦ 842,500 total</span>
          </div>
          <div class="demo-row">
            <span class="demo-label">💼 Salary — GTB</span>
            <span><span class="demo-date">Jun 28 &nbsp;</span><span class="demo-credit">+₦450,000</span></span>
          </div>
          <div class="demo-row">
            <span class="demo-label">🛒 Shoprite groceries</span>
            <span><span class="demo-date">Jun 29 &nbsp;</span><span class="demo-debit">−₦18,400</span></span>
          </div>
          <div class="demo-row">
            <span class="demo-label">⚡ NEPA / electricity</span>
            <span><span class="demo-date">Jun 30 &nbsp;</span><span class="demo-debit">−₦12,000</span></span>
          </div>
          <div class="demo-row">
            <span class="demo-label">🚗 Transport (Bolt)</span>
            <span><span class="demo-date">Jul 01 &nbsp;</span><span class="demo-debit">−₦5,600</span></span>
          </div>
          <div class="demo-row">
            <span class="demo-label">🎯 Emergency Fund goal</span>
            <span><span class="demo-date">Jul 01 &nbsp;</span><span class="demo-debit">−₦30,000</span></span>
          </div>
          <div style="margin-top:16px;padding-top:12px;border-top:1px solid #eef5f2;">
            <span class="badge">🏦 3 banks linked</span>
            <span class="badge">📉 ₦66,000 spent</span>
            <span class="badge">🎯 2 active goals</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background:#fffbea;border-left:4px solid #f39c12;border-radius:8px;
                    padding:12px 16px;margin-top:12px;font-size:0.9rem;color:#7d5a00;">
          ⚠️ <strong>Spending alert:</strong> You've used 68% of your ₦97,000 monthly budget.
        </div>
        """, unsafe_allow_html=True)

    # — Auth tabs in right column —
    with auth_col:
        st.markdown("#### 🚀 Get started — it's free")
        tabs = st.tabs(["🔐 Login", "📝 Register", "📧 Verify Email"])

        with tabs[0]:
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Login", key="login_btn"):
                    uid = login_user(login_username, login_password)
                    if uid:
                        track_login(uid)
                        # Create persistent token → store in DB and URL
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
                        with get_db() as (conn, cursor):
                            cursor.execute("SELECT id FROM users WHERE username=?", (reg_username,))
                            new_row = cursor.fetchone()
                        if new_row:
                            track_signup(new_row[0])
                        notify_admin_new_signup(
                            f"{reg_surname} {reg_other}",
                            reg_username,
                            reg_email,
                        )
                        success, email_msg = send_verification_email(reg_email, code)
                        if success:
                            st.success("Account created. Check email to verify.")
                        else:
                            st.error(f"Account created but email failed: {email_msg}")
                    else:
                        st.error(msg)

        with tabs[2]:
            verify_email = st.text_input("Registered Email", key="verify_email")
            verify_code = st.text_input("Verification Code", key="verify_code")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Verify Email", key="verify_btn"):
                    with get_db() as (conn, cursor):
                        cursor.execute("SELECT id FROM users WHERE email=? AND verification_code=?", (verify_email, verify_code))
                        user = cursor.fetchone()
                        if user:
                            cursor.execute("UPDATE users SET email_verified=1, verification_code=NULL WHERE id=?", (user[0],))
                    if user:
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

    st.stop()

# ================= LOGGED IN — SIDEBAR NAV =================
user_id = st.session_state.user_id

with get_db() as (conn, cursor):
    cursor.execute("SELECT surname, other_names, role FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
st.session_state.user_role = user[2]

with st.sidebar:
    st.markdown(f"### 👋 {user[0]} {user[1]}")
    st.divider()

    pages = [
        "📊 Dashboard",
        "💰 Income",
        "➕ Expenses",
        "🏦 Banks",
        "💸 Transfers",
        "🎯 Savings Goals",
        "📥 Import CSV",
        "⚙️ Settings",
    ]
    if st.session_state.user_role == "admin":
        pages.insert(0, "🛠 Admin Panel")
        pages.insert(1, "📈 Analytics")

    selected = st.radio("Navigate", pages, key="nav_radio")
    current_page = selected.split(" ", 1)[-1]

    st.divider()
    st.markdown(
        "🐛 [Report a bug / Suggest a feature]"
        "(https://forms.gle/YOUR_GOOGLE_FORM_ID)",
        unsafe_allow_html=False,
    )
    st.divider()
    if st.button("🚪 Logout", key="logout_btn"):
        # Revoke DB token and clear from URL — can never be reused
        revoke_session_token(st.session_state.get("session_token"))
        st.session_state.user_id       = None
        st.session_state.user_role     = None
        st.session_state.session_token = None
        for key in ["login_username", "login_password"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

st.success(f"Welcome {user[0]} {user[1]} 👋")

# ================= PAGE: ADMIN PANEL =================
if current_page == "Admin Panel":
    st.subheader("🛠 Admin Panel")
    tabs_admin = st.tabs(["Users", "Banks", "Expenses & Income"])
    with tabs_admin[0]:
        st.write("All Users:")
        with get_db() as (conn, cursor):
            cursor.execute("SELECT id, surname, other_names, username, email, role FROM users")
            all_users = cursor.fetchall()
        for u in all_users:
            st.write(f"{u[1]} {u[2]} | {u[3]} | {u[4]} | Role: {u[5]}")
    with tabs_admin[1]:
        st.write("All Bank Accounts:")
        with get_db() as (conn, cursor):
            cursor.execute("SELECT b.id, u.username, bank_name, account_name, account_number, balance FROM banks b JOIN users u ON b.user_id = u.id")
            all_banks = cursor.fetchall()
        for b in all_banks:
            st.write(b)
    with tabs_admin[2]:
        st.info("You can paste your existing Expenses & Income code here for admin view.")

# ================= PAGE: ANALYTICS (admin only) =================
elif current_page == "Analytics":
    if st.session_state.user_role != "admin":
        st.error("Access denied.")
        st.stop()

    st.markdown("## 📈 Analytics Dashboard")
    data = get_analytics()

    if not data:
        st.warning("Could not load analytics data.")
    else:
        # — Summary metrics —
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("👥 Total Registered",   data["total_registered"])
        c2.metric("✅ Verified Users",      data["total_verified"])
        c3.metric("🟢 Active Today",        data["dau"])
        c4.metric("📅 Active This Week",    data["wau"])
        c5.metric("📆 Active This Month",   data["mau"])

        st.divider()

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("📝 Signups")
            s1, s2 = st.columns(2)
            s1.metric("Signups Today",      data["signups_today"])
            s2.metric("Signups (30 days)",  data["new_signups_30d"])

            st.subheader("📊 Daily Active Users — Last 14 Days")
            if data["daily_rows"]:
                df_dau = pd.DataFrame(data["daily_rows"], columns=["date", "active_users"])
                df_dau["date"] = pd.to_datetime(df_dau["date"])
                df_dau = df_dau.set_index("date")
                st.bar_chart(df_dau["active_users"])
            else:
                st.info("No login data yet.")

        with col_right:
            st.subheader(f"😴 Inactive Users ({len(data['inactive_users'])} total)")
            st.caption("Verified accounts with no login in the last 7 days.")

            inactive = data["inactive_users"]
            if inactive:
                df_inactive = pd.DataFrame(
                    inactive,
                    columns=["id", "Surname", "Other Names", "Email", "Last Login"]
                )
                df_inactive["Last Login"] = df_inactive["Last Login"].fillna("Never")
                st.dataframe(df_inactive[["Surname", "Other Names", "Email", "Last Login"]], use_container_width=True)

                st.divider()
                st.subheader("📧 Send Re-engagement Email")
                st.caption("Send a friendly nudge to bring inactive users back.")

                email_options = {
                    f"{row[1]} {row[2]} ({row[3]})": (row[3], row[1])
                    for row in inactive
                }
                selected_user = st.selectbox(
                    "Select user to email",
                    list(email_options.keys()),
                    key="reeng_select"
                )
                if st.button("📨 Send Re-engagement Email", key="reeng_send_btn"):
                    target_email, target_name = email_options[selected_user]
                    ok, msg = send_reengagement_email(target_email, target_name)
                    if ok:
                        st.success(f"Email sent to {target_email}")
                    else:
                        st.error(f"Failed: {msg}")

                st.divider()
                st.subheader("📨 Bulk Email All Inactive Users")
                st.caption(f"This will send to all {len(inactive)} inactive verified accounts.")
                if st.button("🚀 Send to All Inactive", key="reeng_bulk_btn"):
                    sent, failed = 0, 0
                    for row in inactive:
                        ok, _ = send_reengagement_email(row[3], row[1])
                        if ok:
                            sent += 1
                        else:
                            failed += 1
                    st.success(f"✅ Sent: {sent}  |  ❌ Failed: {failed}")
            else:
                st.success("No inactive users right now — everyone's engaged! 🎉")

# ================= PAGE: DASHBOARD =================
elif current_page == "Dashboard":
    st.markdown("## 💳 My Dashboard")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT SUM(balance) FROM banks WHERE user_id=?", (user_id,))
        total_balance = cursor.fetchone()[0] or 0

        current_month = datetime.now().strftime("%Y-%m")
        cursor.execute("""
            SELECT SUM(t.amount) FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = ? AND t.type = 'debit' AND strftime('%Y-%m', t.created_at) = ?
        """, (user_id, current_month))
        expenses_this_month = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM banks WHERE user_id=?", (user_id,))
        num_banks = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT SUM(CASE WHEN type='credit' THEN amount ELSE -amount END)
            FROM transactions t JOIN banks b ON t.bank_id = b.id
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

    st.subheader("📊 Income vs Expenses Over Time")
    period_map = {
        "Last 30 Days": timedelta(days=30),
        "Last 3 Months": timedelta(days=90),
        "Last 6 Months": timedelta(days=180),
        "Last Year": timedelta(days=365),
        "All Time": None,
    }
    selected_period = st.selectbox("Select Period", list(period_map.keys()), key="period_select")
    start_date = (datetime.now() - period_map[selected_period]).date() if period_map[selected_period] else datetime(2000, 1, 1).date()
    start_str = start_date.strftime("%Y-%m-%d")

    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT t.created_at, t.type, t.amount FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = ? AND t.created_at >= ? ORDER BY t.created_at
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

# ================= PAGE: INCOME =================
elif current_page == "Income":
    st.markdown("## 💰 Add Income")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
        banks = cursor.fetchall()

    income_source = st.text_input("Income Source", key="income_source")
    income_amount = st.number_input("Amount (₦)", min_value=1, key="income_amt")

    if banks:
        bank_map_income = {f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0] for b in banks}
        selected_bank_income = st.selectbox("Deposit To Bank", list(bank_map_income.keys()), key="bank_income_select")
        if st.button("Add Income", key="add_income_btn"):
            if income_source and income_amount > 0:
                bank_id = bank_map_income[selected_bank_income]
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (income_amount, bank_id))
                    cursor.execute("""
                        INSERT INTO transactions (bank_id, type, amount, description, created_at)
                        VALUES (?, 'credit', ?, ?, ?)
                    """, (bank_id, income_amount, f"Income: {income_source}", datetime.now().strftime("%Y-%m-%d")))
                st.success(f"Income of ₦{income_amount:,} added")
                st.rerun()
    else:
        st.info("You need at least one bank account to add income.")

# ================= PAGE: EXPENSES =================
elif current_page == "Expenses":
    st.markdown("## ➕ Expenses")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
        banks = cursor.fetchall()

    st.subheader("Add Expense")
    expense_name = st.text_input("Expense Name", key="exp_name")
    expense_amount = st.number_input("Amount (₦)", min_value=1, key="exp_amt")

    if banks:
        bank_map = {f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0] for b in banks}
        selected_bank = st.selectbox("Pay From Bank", list(bank_map.keys()), key="bank_select")
        if st.button("Add Expense", key="add_expense_btn"):
            if expense_name and expense_amount > 0:
                bank_id = bank_map[selected_bank]
                now = datetime.now().strftime("%Y-%m-%d")
                with get_db() as (conn, cursor):
                    # Insert transaction FIRST so we can capture its id
                    cursor.execute("""
                        INSERT INTO transactions (bank_id, type, amount, description, created_at)
                        VALUES (?, 'debit', ?, ?, ?)
                    """, (bank_id, expense_amount, f"Expense: {expense_name}", now))
                    tx_id = cursor.lastrowid
                    # Insert expense with the tx_id linked
                    cursor.execute("""
                        INSERT INTO expenses (user_id, bank_id, name, amount, created_at, tx_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (user_id, bank_id, expense_name, expense_amount, now, tx_id))
                    cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (expense_amount, bank_id))
                st.success("Expense added & bank debited")
                st.rerun()
            else:
                st.warning("Please enter a name and amount.")
    else:
        st.info("Add a bank account first.")

    st.divider()

    st.subheader("📋 Expense Summary")
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT e.id, e.created_at, e.name, e.amount, e.bank_id, b.bank_name, b.account_number, e.tx_id
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE e.user_id = ? ORDER BY e.created_at DESC
        """, (user_id,))
        expenses_data = cursor.fetchall()

    if expenses_data:
        for exp in expenses_data:
            exp_id, date, name, amount, bank_id, bank_name, acc_num, tx_id = exp
            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 1, 1])
            col1.write(date)
            col2.write(name)
            col3.write(f"₦{amount:,.0f}")
            col4.write(f"{bank_name} (****{acc_num})")
            if col5.button("✏️", key=f"edit_exp_{exp_id}"):
                st.session_state.edit_exp_id = exp_id
            if col6.button("🗑", key=f"delete_exp_{exp_id}"):
                with get_db() as (conn, cursor):
                    # Refund the bank balance
                    cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (amount, bank_id))
                    # Delete the linked transaction by its exact id (tx_id)
                    if tx_id:
                        cursor.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
                    # Delete the expense record
                    cursor.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
                st.success("Expense deleted & bank refunded")
                st.rerun()

        if st.session_state.get("edit_exp_id"):
            edit_id = st.session_state.edit_exp_id
            with get_db() as (conn, cursor):
                cursor.execute("SELECT name, amount, bank_id, tx_id FROM expenses WHERE id=?", (edit_id,))
                exp = cursor.fetchone()
            if exp:
                old_name, old_amount, old_bank_id, old_tx_id = exp
                st.markdown("### ✏️ Edit Expense")
                new_name = st.text_input("Expense Name", value=old_name)
                new_amount = st.number_input("Amount (₦)", min_value=1, value=old_amount)
                if st.button("Update Expense"):
                    diff = new_amount - old_amount
                    with get_db() as (conn, cursor):
                        # Adjust bank balance by the difference
                        cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (diff, old_bank_id))
                        # Update the linked transaction directly by its exact id
                        if old_tx_id:
                            cursor.execute("""
                                UPDATE transactions SET amount=?, description=? WHERE id=?
                            """, (new_amount, f"Expense: {new_name}", old_tx_id))
                        # Update the expense record
                        cursor.execute("UPDATE expenses SET name=?, amount=? WHERE id=?", (new_name, new_amount, edit_id))
                    st.success("Expense updated")
                    st.session_state.edit_exp_id = None
                    st.rerun()

# ================= PAGE: BANKS =================
elif current_page == "Banks":
    st.markdown("## 🏦 Bank Accounts")

    st.subheader("Add Bank Account")
    bank_name = st.text_input("Bank Name", key="bank_name")
    account_name = st.text_input("Account Name", key="acct_name")
    account_number = st.text_input("Account Number (last 4 digits)", key="acct_num")
    opening_balance = st.number_input("Opening Balance (₦)", min_value=0, key="open_bal")
    min_alert = st.number_input("Alert me if balance falls below (₦)", min_value=0, value=0, key="min_alert")
    if st.button("Add Bank", key="add_bank_btn"):
        if bank_name and account_name and account_number:
            with get_db() as (conn, cursor):
                cursor.execute("""
                INSERT INTO banks (user_id, bank_name, account_name, account_number, balance, min_balance_alert)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, bank_name, account_name, account_number[-4:], opening_balance, min_alert))
            st.success("Bank added")
            st.rerun()
        else:
            st.warning("Please fill all fields.")

    st.divider()

    st.subheader("Manage Bank Accounts")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
        banks_manage = cursor.fetchall()

    if banks_manage:
        for bank in banks_manage:
            bank_id, name, acc_name, acc_num, balance = bank
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(f"**{name}** (****{acc_num}) — ₦{balance:,.0f}")
            with col2:
                if st.button("✏️", key=f"edit_bank_{bank_id}"):
                    st.session_state.edit_bank_id = bank_id
            with col3:
                if st.button("🗑", key=f"delete_bank_{bank_id}"):
                    with get_db() as (conn, cursor):
                        # 1. Clear the tx_id link on expenses for this bank (so FK is not violated)
                        cursor.execute("UPDATE expenses SET tx_id=NULL WHERE bank_id=?", (bank_id,))
                        # 2. Delete all expenses linked to this bank
                        cursor.execute("DELETE FROM expenses WHERE bank_id=?", (bank_id,))
                        # 3. Delete all transactions linked to this bank
                        cursor.execute("DELETE FROM transactions WHERE bank_id=?", (bank_id,))
                        # 4. Now safely delete the bank
                        cursor.execute("DELETE FROM banks WHERE id=?", (bank_id,))
                    st.success("Bank and all its transactions deleted.")
                    st.rerun()

        if st.session_state.get("edit_bank_id"):
            edit_id = st.session_state.edit_bank_id
            with get_db() as (conn, cursor):
                cursor.execute("SELECT bank_name, account_name, account_number FROM banks WHERE id=?", (edit_id,))
                bank = cursor.fetchone()
            if bank:
                old_name, old_acc_name, old_acc_num = bank
                st.markdown("### ✏️ Edit Bank")
                new_name = st.text_input("Bank Name", value=old_name)
                new_acc_name = st.text_input("Account Name", value=old_acc_name)
                new_acc_num = st.text_input("Account Number", value=old_acc_num)
                if st.button("Update Bank"):
                    with get_db() as (conn, cursor):
                        cursor.execute("""
                            UPDATE banks SET bank_name=?, account_name=?, account_number=?
                            WHERE id=?
                        """, (new_name, new_acc_name, new_acc_num, edit_id))
                    st.success("Bank updated.")
                    st.session_state.edit_bank_id = None
                    st.rerun()
    else:
        st.info("No bank accounts yet.")

# ================= PAGE: TRANSFERS =================
elif current_page == "Transfers":
    st.markdown("## 💸 Transfer Between Banks")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=?", (user_id,))
        banks = cursor.fetchall()

    if len(banks) >= 2:
        bank_map_transfer = {f"{b[1]} (****{b[2]}) – ₦{b[3]:,}": b[0] for b in banks}
        from_bank = st.selectbox("From Bank", list(bank_map_transfer.keys()), key="from_bank")
        to_bank = st.selectbox("To Bank", list(bank_map_transfer.keys()), key="to_bank")
        transfer_amount = st.number_input("Amount to Transfer (₦)", min_value=1, key="transfer_amt")
        if st.button("Transfer", key="transfer_btn"):
            if from_bank == to_bank:
                st.warning("Cannot transfer to the same bank")
            else:
                from_id = bank_map_transfer[from_bank]
                to_id = bank_map_transfer[to_bank]
                with get_db() as (conn, cursor):
                    cursor.execute("SELECT balance FROM banks WHERE id=?", (from_id,))
                    from_balance = cursor.fetchone()[0]
                    if transfer_amount > from_balance:
                        st.error("Insufficient funds")
                    else:
                        now = datetime.now().strftime("%Y-%m-%d")
                        cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (transfer_amount, from_id))
                        cursor.execute("UPDATE banks SET balance = balance + ? WHERE id=?", (transfer_amount, to_id))
                        cursor.execute("""
                            INSERT INTO transactions (bank_id, type, amount, description, created_at)
                            VALUES (?, 'debit', ?, ?, ?)
                        """, (from_id, transfer_amount, f"Transfer to bank {to_id}", now))
                        cursor.execute("""
                            INSERT INTO transactions (bank_id, type, amount, description, created_at)
                            VALUES (?, 'credit', ?, ?, ?)
                        """, (to_id, transfer_amount, f"Transfer from bank {from_id}", now))
                        st.success("Transfer completed")
                        st.rerun()
    else:
        st.info("Add at least two bank accounts to enable transfers.")

# ================= PAGE: SAVINGS GOALS =================
elif current_page == "Savings Goals":
    st.markdown("## 🎯 Savings Goals")

    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT id, name, target_amount, current_amount, status
            FROM goals WHERE user_id=? ORDER BY status, created_at DESC
        """, (user_id,))
        goals = cursor.fetchall()

    if goals:
        for goal in goals:
            goal_id, name, target, current, status = goal
            progress = (current / target) * 100 if target > 0 else 0
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                st.markdown(f"**{name}**")
                st.progress(min(progress / 100, 1.0), text=f"₦{current:,.0f} / ₦{target:,.0f} ({progress:.1f}%)")
            with col2:
                st.markdown(f"Status: **{status}**")
            with col3:
                if status == "active":
                    if st.button("Add Money", key=f"add_goal_{goal_id}"):
                        st.session_state.selected_goal = goal_id
                        st.session_state.show_goal_contribution = True
            with col4:
                if st.button("🗑", key=f"delete_goal_{goal_id}"):
                    with get_db() as (conn, cursor):
                        cursor.execute("DELETE FROM goals WHERE id=?", (goal_id,))
                    st.success("Goal deleted.")
                    st.rerun()
            st.divider()
    else:
        st.info("No savings goals yet. Create one below.")

    with st.expander("➕ Create New Goal"):
        goal_name = st.text_input("Goal Name", key="goal_name")
        goal_target = st.number_input("Target Amount (₦)", min_value=1, key="goal_target")
        if st.button("Create Goal", key="create_goal_btn"):
            if goal_name and goal_target > 0:
                with get_db() as (conn, cursor):
                    cursor.execute("""
                        INSERT INTO goals (user_id, name, target_amount, created_at, current_amount, status)
                        VALUES (?, ?, ?, ?, 0, 'active')
                    """, (user_id, goal_name, goal_target, datetime.now().strftime("%Y-%m-%d")))
                st.success("Goal created!")
                st.rerun()
            else:
                st.warning("Please enter a name and target.")

    if st.session_state.get("show_goal_contribution") and st.session_state.get("selected_goal"):
        goal_id = st.session_state.selected_goal
        with get_db() as (conn, cursor):
            cursor.execute("SELECT name, target_amount, current_amount FROM goals WHERE id=?", (goal_id,))
            g = cursor.fetchone()
        if g:
            g_name, g_target, g_current = g
            st.write(f"**Add money to '{g_name}'**")
            with get_db() as (conn, cursor):
                cursor.execute("SELECT id, bank_name, balance FROM banks WHERE user_id=?", (user_id,))
                bank_list = cursor.fetchall()
            if bank_list:
                bank_options = {f"{b[1]} (₦{b[2]:,})": b[0] for b in bank_list}
                selected_bank = st.selectbox("From Bank", list(bank_options.keys()), key="goal_bank")
                contrib_amount = st.number_input("Amount to add (₦)", min_value=1, key="goal_amount")
                if st.button("Confirm Contribution", key="confirm_goal_contrib"):
                    bank_id = bank_options[selected_bank]
                    with get_db() as (conn, cursor):
                        cursor.execute("SELECT balance FROM banks WHERE id=?", (bank_id,))
                        bank_balance = cursor.fetchone()[0]
                        if contrib_amount > bank_balance:
                            st.error("Insufficient funds in selected bank.")
                        else:
                            now = datetime.now().strftime("%Y-%m-%d")
                            cursor.execute("UPDATE banks SET balance = balance - ? WHERE id=?", (contrib_amount, bank_id))
                            new_current = g_current + contrib_amount
                            new_status = "completed" if new_current >= g_target else "active"
                            cursor.execute("UPDATE goals SET current_amount = ?, status = ? WHERE id = ?", (new_current, new_status, goal_id))
                            cursor.execute("""
                                INSERT INTO transactions (bank_id, type, amount, description, created_at)
                                VALUES (?, 'debit', ?, ?, ?)
                            """, (bank_id, contrib_amount, f"Savings goal: {g_name}", now))
                            st.success(f"Added ₦{contrib_amount:,.0f} to goal.")
                            st.session_state.show_goal_contribution = False
                            st.rerun()
            else:
                st.warning("You need a bank account to transfer from.")
        else:
            st.session_state.show_goal_contribution = False

# ================= PAGE: IMPORT CSV =================
elif current_page == "Import CSV":
    st.markdown("## 📥 Import Bank Statement (CSV)")
    # csv_import_page receives a fresh connection it manages itself
    conn = get_connection()
    try:
        csv_import_page(conn, user_id)
    finally:
        conn.close()

# ================= PAGE: SETTINGS =================
elif current_page == "Settings":
    st.markdown("## ⚙️ Settings")

    st.subheader("🔔 Alert Settings")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=?", (user_id,))
        current_limit = cursor.fetchone()[0] or 0
    new_limit = st.number_input("Monthly Spending Limit (₦) – 0 = no limit", min_value=0, value=current_limit, key="monthly_limit")
    if st.button("Update Spending Limit", key="update_limit_btn"):
        with get_db() as (conn, cursor):
            cursor.execute("UPDATE users SET monthly_spending_limit = ? WHERE id=?", (new_limit, user_id))
        st.success("Monthly limit updated.")
        st.rerun()

    st.divider()

    st.subheader("🔑 Change Password")
    current_pw = st.text_input("Current Password", type="password", key="current_pw")
    new_pw = st.text_input("New Password", type="password", key="new_pw")
    confirm_new_pw = st.text_input("Confirm New Password", type="password", key="confirm_new_pw")
    if st.button("Change Password", key="change_pw_btn"):
        if current_pw and new_pw and confirm_new_pw:
            if new_pw != confirm_new_pw:
                st.error("New passwords do not match.")
            else:
                success, msg = change_password(user_id, current_pw, new_pw)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        else:
            st.warning("All fields required.")
