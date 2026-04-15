# email_service.py — all outbound email functions
import smtplib
import streamlit as st
from email.message import EmailMessage
from datetime import datetime

from db import get_db

CODE_EXPIRY_MINUTES = 12   # imported by auth.py — keep in sync


def send_verification_email(email: str, code: str):
    """Send a 6-digit verification code to the user's email."""
    try:
        msg = EmailMessage()
        msg["Subject"] = "Verify your Budget Right account"
        msg["From"]    = st.secrets["EMAIL_SENDER"]
        msg["To"]      = email
        msg.set_content(
            f"Your Budget Right verification code is: {code}\n\n"
            f"This code expires in {CODE_EXPIRY_MINUTES} minutes.\n"
            f"If you did not request this, please ignore this email."
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(st.secrets["EMAIL_SENDER"], st.secrets["EMAIL_APP_PASSWORD"])
            server.send_message(msg)
        return True, "Email sent"
    except Exception as e:
        return False, str(e)


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
