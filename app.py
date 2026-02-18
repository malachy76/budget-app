import streamlit as st
import bcrypt
import random
from database import create_tables, get_conn

st.set_page_config("💰 Budget App")
create_tables()

conn = get_conn()
c = conn.cursor()

# ---------- SESSION ----------
if "page" not in st.session_state:
    st.session_state.page = "login"

if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------- HELPERS ----------
def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt())
def check_pw(p, h): return bcrypt.checkpw(p.encode(), h)

def send_email_stub(email, code):
    st.info(f"📧 Verification code sent to {email}: {code}")

# ---------- LOGIN ----------
if st.session_state.page == "login":
    st.title("🔐 Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        c.execute("SELECT id, password, verified FROM users WHERE username=?", (username,))
        user = c.fetchone()

        if user and check_pw(password, user[1]):
            if user[2] == 0:
                st.error("Account not verified")
            else:
                st.session_state.user_id = user[0]
                st.success("Login successful")
        else:
            st.error("Invalid login details")

    st.markdown(
        "<small><a href='#' onclick=\"window.location.reload()\">Forgot password?</a></small>",
        unsafe_allow_html=True
    )

    if st.button("Create account"):
        st.session_state.page = "register"
        st.rerun()

# ---------- REGISTER ----------
elif st.session_state.page == "register":
    st.title("📝 Register")

    surname = st.text_input("Surname")
    other = st.text_input("Other Names")
    email = st.text_input("Email")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Create Account"):
        try:
            hashed = hash_pw(password)
            c.execute("""
            INSERT INTO users (surname, other_names, email, username, password)
            VALUES (?, ?, ?, ?, ?)
            """, (surname, other, email, username, hashed))
            conn.commit()

            code = str(random.randint(100000, 999999))
            c.execute("INSERT INTO verification VALUES (?, ?)", (c.lastrowid, code))
            conn.commit()

            send_email_stub(email, code)
            st.success("Account created. Enter verification code below.")

            st.session_state.verify_user = c.lastrowid

        except:
            st.error("User already exists")

    # ---------- VERIFY ----------
    if "verify_user" in st.session_state:
        st.subheader("📩 Verify Email")

        code_input = st.text_input("Enter verification code")

        if st.button("Verify"):
            c.execute("""
            SELECT code FROM verification WHERE user_id=?
            """, (st.session_state.verify_user,))
            real_code = c.fetchone()

            if real_code and code_input == real_code[0]:
                c.execute("UPDATE users SET verified=1 WHERE id=?", (st.session_state.verify_user,))
                c.execute("DELETE FROM verification WHERE user_id=?", (st.session_state.verify_user,))
                conn.commit()

                st.success("Email verified. You can now login.")
                del st.session_state.verify_user
                st.session_state.page = "login"
                st.rerun()
            else:
                st.error("Invalid verification code")

        st.caption("Didn’t get a code?")
        if st.button("Resend verification code"):
            new_code = str(random.randint(100000, 999999))
            c.execute("UPDATE verification SET code=? WHERE user_id=?",
                      (new_code, st.session_state.verify_user))
            conn.commit()
            send_email_stub(email, new_code)

# ---------- RESET PASSWORD ----------
elif st.session_state.page == "reset":
    st.title("🔑 Reset Password")
    st.info("Password reset coming next (email-based)")
