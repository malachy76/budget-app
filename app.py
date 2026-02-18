import streamlit as st
import bcrypt
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from database import get_connection, create_tables

st.set_page_config(page_title="Simple Budget App", page_icon="💰", layout="centered")

create_tables()
conn = get_connection()
cursor = conn.cursor()

st.title("💰 Simple Budget App")

# ---------------- SESSION ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- AUTH FUNCTIONS ----------------
def login(username, password):
    cursor.execute(
        "SELECT id, password FROM users WHERE username=?",
        (username,)
    )
    user = cursor.fetchone()
    if user and bcrypt.checkpw(password.encode(), user[1]):
        st.session_state.user_id = user[0]
        return True
    return False


def register(surname, other_names, email, username, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    try:
        cursor.execute("""
            INSERT INTO users 
            (surname, other_names, email, username, password, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            surname,
            other_names,
            email,
            username,
            hashed,
            datetime.now().strftime("%Y-%m-%d")
        ))
        conn.commit()
        return True
    except Exception as e:
        return False

# ---------------- LOGIN / REGISTER ----------------
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])

    # -------- LOGIN --------
    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login", key="login_btn"):
            if login(username, password):
                st.success("Login successful")
                st.rerun()
            else:
                st.error("Invalid username or password")

    # -------- REGISTER --------
    with tab2:
        st.subheader("Create a secure account")

        surname = st.text_input("Surname")
        other_names = st.text_input("Other names")
        email = st.text_input("Email address")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")

        if st.button("Create Account", key="register_btn"):
            if not all([surname, other_names, email, username, password]):
                st.error("All fields are required")
            elif password != confirm:
                st.error("Passwords do not match")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters")
            else:
                if register(surname, other_names, email, username, password):
                    st.success("Account created. Please login.")
                else:
                    st.error("Username or email already exists")

    st.stop()

user_id = st.session_state.user_id

# ---------------- FETCH USER PROFILE ----------------
cursor.execute("""
SELECT surname, other_names, email 
FROM users WHERE id=?
""", (user_id,))
profile = cursor.fetchone()

st.success(f"Welcome {profile[0]} {profile[1]}")
st.caption(f"📧 {profile[2]}")

# ---------------- LOGOUT ----------------
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.rerun()

# ---------------- CONTINUE APP ----------------
st.info("Your budget features continue below 👇")
