# analytics.py — analytics queries, admin email helpers
import streamlit as st
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta

from db import get_db


def get_analytics():
    try:
        with get_db() as (conn, cursor):
            today     = datetime.now().date()
            cutoff_30 = today - timedelta(days=30)
            cutoff_7  = today - timedelta(days=7)

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

# ---------------- FILTER / SORT HELPERS ----------------

