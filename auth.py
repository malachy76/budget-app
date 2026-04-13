# auth.py — validation helpers, registration, login, verification,
#            password reset, session tokens, onboarding tracking
import re
import random
import secrets
import hashlib
import psycopg2
import psycopg2.extras
import bcrypt
import streamlit as st
from datetime import datetime, timedelta

from db import get_db
from email_service import send_verification_email


CODE_EXPIRY_MINUTES = 12   # verification & reset codes expire after 12 minutes
SESSION_EXPIRY_DAYS = 30  # Sessions expire after 30 days


# ── Validation ────────────────────────────────────────────────────────────────

def is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def validate_password(password: str):
    """Returns (True, \'\') or (False, reason)."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r'[A-Z]', password):
        return False, "Password must include at least one uppercase letter."
    if not re.search(r'[a-z]', password):
        return False, "Password must include at least one lowercase letter."
    if not re.search(r'[0-9]', password):
        return False, "Password must include at least one digit."
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"|,.<>\/?]', password):
        return False, "Password must include at least one special character."
    return True, ""


# ── Security / Auth ───────────────────────────────────────────────────────────

def _hash_token(raw_token: str) -> str:
    """SHA-256 hash of a raw token — stored in DB, raw token given to user."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _check_rate_limit(identifier: str, action: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
    """
    Returns True if the action is ALLOWED (under the rate limit).
    Returns False if the limit has been exceeded.
    identifier: IP substitute — username or email string.
    """
    try:
        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT COUNT(*) AS n FROM rate_limit_log
                WHERE identifier = %s AND action = %s AND attempted_at >= %s
            """, (identifier, action, cutoff))
            count = cursor.fetchone()["n"] or 0
            if count >= max_attempts:
                return False
            cursor.execute(
                "INSERT INTO rate_limit_log (identifier, action, attempted_at) VALUES (%s, %s, %s)",
                (identifier, action, datetime.now())
            )
        return True
    except Exception:
        return True  # fail open — don't lock users out on DB error


def _rate_limit_remaining(identifier: str, action: str, max_attempts: int = 5, window_minutes: int = 15) -> int:
    """Returns how many attempts remain in the current window."""
    try:
        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT COUNT(*) AS n FROM rate_limit_log
                WHERE identifier = %s AND action = %s AND attempted_at >= %s
            """, (identifier, action, cutoff))
            count = cursor.fetchone()["n"] or 0
        return max(0, max_attempts - count)
    except Exception:
        return max_attempts

# ---------------- AUTH FUNCTIONS ----------------


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())


def check_password(password, hashed):
    if isinstance(hashed, memoryview):
        hashed = bytes(hashed)
    return bcrypt.checkpw(password.encode(), hashed)


def register_user(surname, other, email, username, password):
    code    = str(random.randint(100000, 999999))
    expires = datetime.now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
    try:
        hashed_pw = hash_password(password)
        with get_db() as (conn, cursor):
            cursor.execute("""
                INSERT INTO users (surname, other_names, email, username, password,
                                   verification_code, verification_code_expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (surname, other, email, username, psycopg2.Binary(hashed_pw),
                  code, expires, datetime.now().date()))
        return code, "User created"
    except psycopg2.errors.UniqueViolation:
        return None, "Username or email already exists"
    except Exception as e:
        return None, str(e)


def login_user(username, password):
    # Rate limit: 5 attempts per 15 minutes per username
    if not _check_rate_limit(username.lower(), "login", max_attempts=5, window_minutes=15):
        st.error("Too many login attempts. Please wait 15 minutes before trying again.")
        return None
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


def request_password_reset(email):
    # Rate limit: 3 reset requests per 15 minutes per email
    if not _check_rate_limit(email.lower(), "password_reset", max_attempts=3, window_minutes=15):
        return False, "Too many reset requests. Please wait 15 minutes before trying again."
    try:
        code    = str(random.randint(100000, 999999))
        expires = datetime.now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
        with get_db() as (conn, cursor):
            cursor.execute(
                "UPDATE users SET verification_code=%s, verification_code_expires_at=%s WHERE email=%s",
                (code, expires, email)
            )
            if cursor.rowcount == 0:
                return False, "Email not found"
        return send_verification_email(email, code)
    except Exception as e:
        return False, str(e)


def reset_password(email, code, new_password):
    try:
        now = datetime.now()
        with get_db() as (conn, cursor):
            cursor.execute(
                "SELECT id, verification_code_expires_at FROM users "
                "WHERE email=%s AND verification_code=%s",
                (email, code)
            )
            user = cursor.fetchone()
            if not user:
                return False, "Invalid reset code. Please request a new one."
            if user["verification_code_expires_at"] and now > user["verification_code_expires_at"]:
                return False, f"This reset code has expired. Codes are only valid for {CODE_EXPIRY_MINUTES} minutes. Please request a new one."
            hashed_pw = hash_password(new_password)
            cursor.execute(
                "UPDATE users SET password=%s, verification_code=NULL, verification_code_expires_at=NULL WHERE email=%s",
                (psycopg2.Binary(hashed_pw), email)
            )
        return True, "Password reset successful"
    except Exception as e:
        return False, str(e)


def resend_verification(email):
    # Rate limit: 3 resends per 15 minutes per email
    if not _check_rate_limit(email.lower(), "resend_verification", max_attempts=3, window_minutes=15):
        return False, "Too many resend requests. Please wait 15 minutes."
    try:
        code    = str(random.randint(100000, 999999))
        expires = datetime.now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
        with get_db() as (conn, cursor):
            cursor.execute(
                "UPDATE users SET verification_code=%s, verification_code_expires_at=%s WHERE email=%s",
                (code, expires, email)
            )
            if cursor.rowcount == 0:
                return False, "Email not found"
        return send_verification_email(email, code)
    except Exception as e:
        return False, str(e)


def verify_email_code(email, code):
    """Check code validity including expiry, then mark verified."""
    now = datetime.now()
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, verification_code_expires_at FROM users "
            "WHERE email=%s AND verification_code=%s",
            (email, code)
        )
        user = cursor.fetchone()
        if not user:
            return False, "Invalid email or code."
        if user["verification_code_expires_at"] and now > user["verification_code_expires_at"]:
            return False, f"This code has expired. Codes are only valid for {CODE_EXPIRY_MINUTES} minutes. Please request a new code."
        cursor.execute(
            "UPDATE users SET email_verified=1, verification_code=NULL, "
            "verification_code_expires_at=NULL WHERE id=%s",
            (user["id"],)
        )
    return True, "Email verified successfully."


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



# ── Session tokens ────────────────────────────────────────────────────────────

def create_session_token(user_id, cookies):
    """Generate a raw token, store only its SHA-256 hash in the DB, put raw in cookie."""
    raw_token  = secrets.token_urlsafe(48)
    hashed_tok = _hash_token(raw_token)
    now        = datetime.now()
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO session_tokens (user_id, token, created_at) VALUES (%s, %s, %s)",
            (user_id, hashed_tok, now)
        )
    cookies["session_token"] = raw_token
    cookies.save()
    return raw_token


def validate_session_token(token, cookies):
    """
    Hash the incoming raw token, look up its hash in the DB.
    Returns (user_id, role) if valid and within SESSION_EXPIRY_DAYS of last activity.
    Refreshes the sliding-window timestamp on every successful call.
    """
    if not token:
        return None, None
    try:
        hashed_tok    = _hash_token(token)
        now           = datetime.now()
        expiry_cutoff = now - timedelta(days=SESSION_EXPIRY_DAYS)
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT u.id, u.role FROM session_tokens s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = %s
                  AND u.email_verified = 1
                  AND s.created_at >= %s
            """, (hashed_tok, expiry_cutoff))
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE session_tokens SET created_at = %s WHERE token = %s",
                    (now, hashed_tok)
                )
                return row["id"], row["role"]
    except Exception:
        pass
    return None, None


def revoke_session_token(token, cookies):
    if not token:
        return
    try:
        hashed_tok = _hash_token(token)
        with get_db() as (conn, cursor):
            cursor.execute("DELETE FROM session_tokens WHERE token=%s", (hashed_tok,))
    except Exception:
        pass
    cookies["session_token"] = ""
    cookies.save()


# ── Analytics tracking & onboarding ──────────────────────────────────────────

def track_login(user_id):
    try:
        today = datetime.now().date()
        with get_db() as (conn, cursor):
            cursor.execute("INSERT INTO analytics_logins (user_id, login_date) VALUES (%s, %s)", (user_id, today))
            cursor.execute("UPDATE users SET last_login=%s WHERE id=%s", (today, user_id))
    except Exception:
        pass


def track_signup(user_id):
    try:
        today = datetime.now().date()
        with get_db() as (conn, cursor):
            cursor.execute("INSERT INTO analytics_logins (user_id, login_date) VALUES (%s, %s)", (user_id, today))
    except Exception:
        pass





