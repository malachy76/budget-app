# landing.py — landing page, login, register, verify, forgot password
import streamlit as st
from datetime import datetime

from db import get_db
from auth import (
    is_valid_email, validate_password,
    register_user, login_user,
    request_password_reset, reset_password,
    resend_verification, verify_email_code,
    create_session_token, track_login, track_signup,
    CODE_EXPIRY_MINUTES,
)
from email_service import notify_admin_new_signup


def render_landing(cookies):
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
                        token = create_session_token(uid, cookies)
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
                    st.caption(f"A reset code will be sent to your email. It expires in {CODE_EXPIRY_MINUTES} minutes.")
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
                    st.caption(f"Enter the 6-digit code sent to your email. The code expires {CODE_EXPIRY_MINUTES} minutes after it was sent.")
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
            st.caption(f"Verification codes expire {CODE_EXPIRY_MINUTES} minutes after they are sent. Request a new code if yours has expired.")
            verify_email = st.text_input("Registered Email", key="verify_email")
            verify_code  = st.text_input("Verification Code", key="verify_code")
            col1, col2   = st.columns(2)
            with col1:
                if st.button("Verify Email", key="verify_btn"):
                    if verify_email and verify_code:
                        ok, msg = verify_email_code(verify_email, verify_code)
                        if ok:
                            st.success(f"{msg} You can now log in.")
                        else:
                            st.error(msg)
                    else:
                        st.warning("Enter your email and the verification code.")
            with col2:
                if st.button("Resend Code", key="resend_btn"):
                    if verify_email:
                        success, msg = resend_verification(verify_email)
                        st.success(msg) if success else st.error(msg)
                    else:
                        st.warning("Enter your email first.")

    st.stop()
