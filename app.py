import streamlit as st
import bcrypt
import random
from datetime import datetime
from database import get_connection, create_tables

st.set_page_config("Simple Budget App", "💰", layout="centered")

create_tables()
conn = get_connection()
cursor = conn.cursor()

st.title("💰 Simple Budget App")

# ---------------- SESSION ----------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- HELPERS ----------------
def generate_code():
    return str(random.randint(100000, 999999))

def register_user(surname, other_names, email, username, password):
    code = generate_code()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    try:
        cursor.execute("""
            INSERT INTO users 
            (surname, other_names, email, username, password, verification_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            surname, other_names, email, username,
            hashed, code, datetime.now().strftime("%Y-%m-%d")
        ))
        conn.commit()
        return code
    except:
        return None

def login_user(username, password):
    cursor.execute("""
        SELECT id, password, email_verified
        FROM users WHERE username=?
    """, (username,))
    user = cursor.fetchone()

    if user and bcrypt.checkpw(password.encode(), user[1]):
        if user[2] == 0:
            st.warning("Please verify your email first")
            return None
        return user[0]
    return None

# ---------------- AUTH ----------------
if st.session_state.user_id is None:
    tabs = st.tabs(["🔐 Login", "📝 Register", "📧 Verify Email"])

    # LOGIN
    with tabs[0]:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            user_id = login_user(u, p)
            if user_id:
                st.session_state.user_id = user_id
                st.rerun()
            else:
                st.error("Login failed")

    # REGISTER
    with tabs[1]:
        st.subheader("Create Account")
        surname = st.text_input("Surname")
        other = st.text_input("Other names")
        email = st.text_input("Email")
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")

        if st.button("Register"):
            if len(pwd) < 6:
                st.error("Password too short")
            else:
                code = register_user(surname, other, email, user, pwd)
                if code:
                    st.success("Account created")
                    st.info(f"Verification code (demo): {code}")
                else:
                    st.error("User already exists")

    # VERIFY EMAIL
    with tabs[2]:
        email = st.text_input("Email used to register")
        code = st.text_input("Verification code")

        if st.button("Verify"):
            cursor.execute("""
                SELECT id FROM users
                WHERE email=? AND verification_code=?
            """, (email, code))
            user = cursor.fetchone()

            if user:
                cursor.execute("""
                    UPDATE users
                    SET email_verified=1, verification_code=NULL
                    WHERE id=?
                """, (user[0],))
                conn.commit()
                st.success("Email verified successfully")
            else:
                st.error("Invalid code")

    st.stop()

# ---------------- DASHBOARD ----------------
user_id = st.session_state.user_id

cursor.execute("""
SELECT surname, other_names FROM users WHERE id=?
""", (user_id,))
name = cursor.fetchone()

st.success(f"Welcome {name[0]} {name[1]}")

# ---------------- KYC SECTION ----------------
st.subheader("🆔 KYC Verification")

cursor.execute("SELECT * FROM kyc WHERE user_id=?", (user_id,))
kyc = cursor.fetchone()

if not kyc:
    bvn = st.text_input("BVN (11 digits)")
    nin = st.text_input("NIN")

    if st.button("Submit KYC"):
        cursor.execute("""
            INSERT INTO kyc (user_id, bvn, nin)
            VALUES (?, ?, ?)
        """, (user_id, bvn, nin))
        conn.commit()
        st.success("KYC submitted (pending verification)")
else:
    st.info(f"KYC Status: {kyc[3]}")

# ---------------- LOGOUT ----------------
if st.button("Logout", key="logout_btn"):
    st.session_state.user_id = None
    st.rerun()
