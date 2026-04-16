# app.py — Budget Right (single-file version)
# -*- coding: utf-8 -*-
import streamlit as st

# ── MUST be the very first Streamlit call ─────────────────────────────────────
st.set_page_config(
    page_title="Budget Right",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
div[data-testid="stSidebarNavItems"] { display: none !important; }
section[data-testid="stSidebar"] ul { display: none !important; }
</style>
""", unsafe_allow_html=True)

from streamlit_cookies_manager import EncryptedCookieManager

cookies = EncryptedCookieManager(
    prefix="budget_right_",
    password=st.secrets["COOKIE_PASSWORD"]
)
if not cookies.ready():
    st.stop()

# ── Imports ───────────────────────────────────────────────────────────────────
import re, io, csv, hashlib, calendar, random, secrets, smtplib
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date
from email.message import EmailMessage

from styles    import inject_styles
from models    import create_tables
from auth      import (
    validate_session_token, revoke_session_token,
    get_onboarding_status, mark_onboarding_complete,
    register_user, login_user, verify_email_code,
    resend_verification, request_password_reset, reset_password,
    change_password, create_session_token, track_login, track_signup,
    validate_password, is_valid_email,
)
from db        import get_db
from retention import (
    run_retention_engine, get_unread_count, get_streak,
    get_notifications, mark_notifications_read, mark_notification_read,
    clear_all_notifications,
)
from utils     import (
    save_expense, apply_income_filters, apply_expense_filters,
    render_filter_bar_income, render_filter_bar_expenses,
    get_category_budgets, compute_daily_safe_to_spend,
    upsert_category_budget, BUDGET_CATEGORIES,
)
from analytics import get_analytics, notify_admin_new_signup
from pdf_report import (
    fetch_monthly_data, fetch_goal_data, fetch_category_budget_data,
    fetch_bank_data, build_monthly_statement, build_goal_progress_report,
    build_category_budget_report, build_bank_report,
)
from csv_import import csv_import_page

inject_styles()

# ── create_tables once per process ───────────────────────────────────────────
if "tables_created" not in st.session_state:
    create_tables()
    st.session_state["tables_created"] = True

# ── Session state defaults ────────────────────────────────────────────────────
_DEFAULTS = {
    "user_id": None, "user_role": None, "session_token": None,
    "show_forgot_password": False, "show_reset_form": False, "reset_email": "",
    "edit_exp_id": None, "edit_bank_id": None, "edit_income_id": None,
    "selected_goal": None, "show_goal_contribution": False,
    "goal_preset": "", "goal_preset_name": "",
    "onboarding_step": 1, "quick_add_name": "", "quick_add_amt": 0,
    "confirm_delete": {},
    "income_search": "", "income_filter_bank": "All",
    "income_filter_date_from": None, "income_filter_date_to": None,
    "income_sort": "Newest First",
    "exp_search": "", "exp_filter_bank": "All", "exp_filter_category": "All",
    "exp_filter_date_from": None, "exp_filter_date_to": None,
    "exp_sort": "Newest First",
    "_streak_cache": None, "_unread_cache": None, "_retention_date": None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Restore session from cookie ───────────────────────────────────────────────
if st.session_state.user_id is None:
    _tok = cookies.get("session_token", "")
    if _tok:
        _uid, _role = validate_session_token(_tok, cookies)
        if _uid:
            st.session_state.user_id       = _uid
            st.session_state.user_role     = _role
            st.session_state.session_token = _tok
        else:
            cookies["session_token"] = ""
            cookies.save()


# ══════════════════════════════════════════════════════════════════════════════
# LANDING PAGE (not logged in)
# ══════════════════════════════════════════════════════════════════════════════

def render_landing():
    st.markdown("""
    <style>
    .landing-hero { background: linear-gradient(135deg,#1a3c5e 0%,#0e7c5b 100%);
        border-radius:16px; padding:36px 28px 28px 28px; text-align:center; margin-bottom:24px; }
    .landing-title   { font-size:2.1rem; font-weight:900; color:#ffffff; margin-bottom:6px; }
    .landing-tagline { font-size:1.05rem; color:#a8d8c8; margin-bottom:0; }
    .landing-desc    { font-size:0.95rem; color:#e0f0ec; margin-top:10px; }
    .feature-card    { background:#f0f7f4; border-left:4px solid #0e7c5b; border-radius:10px;
        padding:14px 16px; margin-bottom:10px; }
    .demo-card  { background:#ffffff; border:1px solid #d0e8df; border-radius:10px;
        padding:14px 16px; margin-bottom:8px; }
    .demo-row   { display:flex; justify-content:space-between; align-items:center;
        padding:4px 0; font-size:0.88rem; }
    </style>

    <div class="landing-hero">
      <div class="landing-title">💰 Budget Right</div>
      <div class="landing-tagline">Nigeria's Smart Personal Finance Tracker</div>
      <div class="landing-desc">Track income &amp; expenses · Set savings goals · Import bank statements · Stay in control</div>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔑 Login", "📝 Register"])

    # ── Login ─────────────────────────────────────────────────────────────────
    with tab_login:
        if st.session_state.show_reset_form:
            st.subheader("🔐 Reset Password")
            email_r = st.text_input("Email address", key="reset_email_inp")
            code_r  = st.text_input("6-digit code (check your email)", key="reset_code_inp")
            new_pw  = st.text_input("New password", type="password", key="reset_new_pw")
            if st.button("Reset Password", key="do_reset"):
                ok, msg = reset_password(email_r, code_r, new_pw)
                if ok:
                    st.success(msg + " You can now log in.")
                    st.session_state.show_reset_form = False
                    st.rerun()
                else:
                    st.error(msg)
            if st.button("Back to login", key="back_login"):
                st.session_state.show_reset_form = False
                st.rerun()

        elif st.session_state.show_forgot_password:
            st.subheader("📧 Forgot Password")
            email_fp = st.text_input("Your registered email", key="fp_email")
            if st.button("Send Reset Code", key="send_reset"):
                ok, msg = request_password_reset(email_fp)
                if ok:
                    st.success("Reset code sent! Check your inbox.")
                    st.session_state.reset_email     = email_fp
                    st.session_state.show_forgot_password = False
                    st.session_state.show_reset_form = True
                    st.rerun()
                else:
                    st.error(msg)
            if st.button("Back", key="back_fp"):
                st.session_state.show_forgot_password = False
                st.rerun()

        else:
            with st.form("login_form"):
                uname = st.text_input("Username")
                pw    = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login", use_container_width=True)
            if submitted:
                uid = login_user(uname, pw)
                if uid:
                    track_login(uid)
                    raw_tok = create_session_token(uid, cookies)
                    st.session_state.session_token = raw_tok
                    st.rerun()
            st.markdown("")
            if st.button("Forgot password?", key="forgot_btn"):
                st.session_state.show_forgot_password = True
                st.rerun()

            # Resend verification
            with st.expander("Didn't receive verification email?"):
                rv_email = st.text_input("Your email address", key="rv_email")
                if st.button("Resend code", key="rv_btn"):
                    ok, msg = resend_verification(rv_email)
                    st.success(msg) if ok else st.error(msg)
                rv_code = st.text_input("Enter verification code", key="rv_code")
                if st.button("Verify email", key="rv_verify"):
                    ok, msg = verify_email_code(rv_email, rv_code)
                    st.success(msg) if ok else st.error(msg)

    # ── Register ──────────────────────────────────────────────────────────────
    with tab_register:
        if "reg_verify_mode" not in st.session_state:
            st.session_state.reg_verify_mode = False
        if "reg_email_pending" not in st.session_state:
            st.session_state.reg_email_pending = ""

        if st.session_state.reg_verify_mode:
            st.info(f"A 6-digit code was sent to **{st.session_state.reg_email_pending}**. Enter it below.")
            v_code = st.text_input("Verification code", key="reg_v_code")
            if st.button("Verify & Activate", key="reg_verify_btn"):
                ok, msg = verify_email_code(st.session_state.reg_email_pending, v_code)
                if ok:
                    st.success("Account verified! You can now log in.")
                    st.session_state.reg_verify_mode = False
                else:
                    st.error(msg)
        else:
            with st.form("register_form"):
                r_surname = st.text_input("Surname")
                r_other   = st.text_input("Other names")
                r_email   = st.text_input("Email")
                r_uname   = st.text_input("Username")
                r_pw      = st.text_input("Password", type="password")
                r_pw2     = st.text_input("Confirm password", type="password")
                reg_sub   = st.form_submit_button("Create Account", use_container_width=True)
            if reg_sub:
                if not all([r_surname, r_other, r_email, r_uname, r_pw]):
                    st.warning("Please fill all fields.")
                elif r_pw != r_pw2:
                    st.error("Passwords do not match.")
                elif not is_valid_email(r_email):
                    st.error("Invalid email address.")
                else:
                    pw_ok, pw_msg = validate_password(r_pw)
                    if not pw_ok:
                        st.error(pw_msg)
                    else:
                        from email_service import send_verification_email
                        code, msg = register_user(r_surname, r_other, r_email, r_uname, r_pw)
                        if code:
                            ok_email, _ = send_verification_email(r_email, code)
                            track_signup_needed = True
                            # find new user id
                            with get_db() as (conn, cursor):
                                cursor.execute("SELECT id FROM users WHERE email=%s", (r_email,))
                                new_row = cursor.fetchone()
                            if new_row:
                                track_signup(new_row["id"])
                                notify_admin_new_signup(
                                    f"{r_surname} {r_other}", r_uname, r_email
                                )
                            st.session_state.reg_verify_mode    = True
                            st.session_state.reg_email_pending  = r_email
                            st.rerun()
                        else:
                            st.error(msg)

    # Features
    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="feature-card">🏦 <b>Multiple Banks</b><br>Track GTB, Access, Kuda, Opay and more in one place</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="feature-card">📊 <b>Smart Insights</b><br>Nigerian-style financial tips and budget alerts</div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="feature-card">📥 <b>CSV Import</b><br>Import bank statements from 12+ Nigerian banks</div>', unsafe_allow_html=True)


if st.session_state.user_id is None:
    render_landing()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# LOGGED IN
# ══════════════════════════════════════════════════════════════════════════════
user_id = st.session_state.user_id

with get_db() as (conn, cursor):
    cursor.execute("SELECT surname, other_names, role, monthly_spending_limit FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
st.session_state.user_role = user["role"]

# ── Retention engine — once per day ──────────────────────────────────────────
_today_str = datetime.now().date().isoformat()
if st.session_state._retention_date != _today_str:
    try:
        run_retention_engine(user_id)
    except Exception:
        pass
    st.session_state._streak_cache   = get_streak(user_id)
    st.session_state._unread_cache   = get_unread_count(user_id)
    st.session_state._retention_date = _today_str

_streak_data  = st.session_state._streak_cache or {"current": 0, "longest": 0}
_unread       = st.session_state._unread_cache or 0
_streak_curr  = _streak_data["current"]
_streak_emoji = (
    "👑" if _streak_curr >= 30 else
    "🌟" if _streak_curr >= 14 else
    "🏆" if _streak_curr >= 7  else
    "🔥" if _streak_curr >= 3  else
    "📊"
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### Hello, {user['surname']} {user['other_names']}")

    _unread_badge = (
        f' <span style="background:#e74c3c;color:#fff;border-radius:20px;'
        f'padding:1px 7px;font-size:0.72rem;font-weight:700;">{_unread}</span>'
        if _unread > 0 else ""
    )
    st.markdown(
        f'<div style="background:#1a3c5e;border-radius:10px;padding:10px 14px;'
        f'margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="color:#a8d8c8;font-size:0.8rem;font-weight:700;">'
        f'{_streak_emoji} {_streak_curr}-day streak</span>'
        f'<span style="color:#a8d8c8;font-size:0.8rem;">🔔{_unread_badge}</span>'
        f'</div>',
        unsafe_allow_html=True
    )
    st.divider()

    pages = [
        "Dashboard", "Income", "Expenses",
        "Banks", "Transfers", "Savings Goals",
        "Tracker", "Summaries",
        "Notifications", "Import CSV", "Settings",
    ]
    if st.session_state.user_role == "admin":
        pages = ["Admin Panel", "Analytics"] + pages

    selected_idx = st.radio(
        "Navigate",
        range(len(pages)),
        format_func=lambda i: pages[i],
        key="nav_radio"
    )
    current_page = pages[selected_idx]

    st.divider()
    st.markdown(
        "Report a bug / Suggest a feature: "
        "[Click here](https://docs.google.com/forms/d/e/1FAIpQLSccXTBLwx6GhwqpUCt6lrjQ4qzNzNgjs2APheQ-FOryC0wCJA/viewform?usp=dialog)"
    )
    st.divider()
    if st.button("Logout", key="logout_btn"):
        revoke_session_token(st.session_state.get("session_token"), cookies)
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Onboarding checklist ──────────────────────────────────────────────────────
_ob = get_onboarding_status(user_id)
if not _ob["already_done"]:
    if _ob["all_done"]:
        mark_onboarding_complete(user_id)
    else:
        steps_done = sum([_ob["has_bank"], _ob["has_income"], _ob["has_expense"], _ob["has_budget"]])
        st.markdown("""
        <style>
        .ob-step { display:flex; align-items:center; gap:10px; background:#f0f7f4;
            border-radius:8px; padding:10px 14px; margin-bottom:6px; font-size:0.92rem; }
        .ob-done { border-left:4px solid #0e7c5b; color:#2c7a5a; }
        .ob-todo { border-left:4px solid #d0d0d0; color:#555; }
        .ob-icon { font-size:1.2rem; }
        </style>""", unsafe_allow_html=True)

        with st.expander(f"🚀 Setup checklist — {steps_done}/4 done", expanded=(steps_done == 0)):
            st.progress(steps_done / 4, text=f"{steps_done * 25}% set up")

            done1 = _ob["has_bank"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done1 else "ob-todo"}">'
                f'<span class="ob-icon">{"✅" if done1 else "🏦"}</span>'
                f'<span><strong>Step 1: Add your first bank account</strong>'
                f'{"&nbsp;&mdash; done!" if done1 else ""}</span></div>',
                unsafe_allow_html=True
            )
            if not done1:
                with st.form("ob_bank_form"):
                    ob_bank_name   = st.text_input("Bank Name (e.g. GTB, Access, Opay)")
                    ob_acct_name   = st.text_input("Account Name")
                    ob_acct_num    = st.text_input("Account Number (last 4 digits)")
                    ob_opening_bal = st.number_input("Current Balance (NGN)", min_value=0, step=1000)
                    ob_bank_submit = st.form_submit_button("Add Bank and Continue")
                if ob_bank_submit:
                    if ob_bank_name and ob_acct_name and ob_acct_num:
                        with get_db() as (conn, cursor):
                            cursor.execute(
                                "INSERT INTO banks (user_id, bank_name, account_name, account_number, balance, min_balance_alert) "
                                "VALUES (%s,%s,%s,%s,%s,0)",
                                (user_id, ob_bank_name, ob_acct_name, ob_acct_num[-4:], int(ob_opening_bal))
                            )
                        st.success(f"Bank '{ob_bank_name}' added!")
                        st.rerun()
                    else:
                        st.warning("Please fill all bank fields.")

            done2 = _ob["has_income"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done2 else "ob-todo"}">'
                f'<span class="ob-icon">{"✅" if done2 else "💰"}</span>'
                f'<span><strong>Step 2: Record your first income</strong>'
                f'{"&nbsp;&mdash; done!" if done2 else ""}</span></div>',
                unsafe_allow_html=True
            )
            if done1 and not done2:
                with get_db() as (conn, cursor):
                    cursor.execute("SELECT id, bank_name, account_number FROM banks WHERE user_id=%s", (user_id,))
                    ob_banks = cursor.fetchall()
                ob_bank_map = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in ob_banks}
                with st.form("ob_income_form"):
                    ob_inc_source = st.text_input("Income Source (e.g. Salary, Freelance)")
                    ob_inc_amount = st.number_input("Amount (NGN)", min_value=1, step=1000)
                    ob_inc_bank   = st.selectbox("Which bank?", list(ob_bank_map.keys()))
                    ob_inc_submit = st.form_submit_button("Add Income and Continue")
                if ob_inc_submit:
                    if ob_inc_source and ob_inc_amount > 0:
                        bk_id = ob_bank_map[ob_inc_bank]
                        with get_db() as (conn, cursor):
                            cursor.execute("UPDATE banks SET balance=balance+%s WHERE id=%s", (int(ob_inc_amount), bk_id))
                            cursor.execute(
                                "INSERT INTO transactions (bank_id,type,amount,description,created_at) VALUES (%s,'credit',%s,%s,%s)",
                                (bk_id, int(ob_inc_amount), f"Income: {ob_inc_source}", datetime.now().date())
                            )
                        st.success("Income recorded!")
                        st.rerun()
                    else:
                        st.warning("Please enter a source and amount.")
            elif not done1:
                st.caption("Complete Step 1 first.")

            done3 = _ob["has_expense"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done3 else "ob-todo"}">'
                f'<span class="ob-icon">{"✅" if done3 else "🧾"}</span>'
                f'<span><strong>Step 3: Log your first expense</strong>'
                f'{"&nbsp;&mdash; done!" if done3 else ""}</span></div>',
                unsafe_allow_html=True
            )
            if done1 and not done3:
                with get_db() as (conn, cursor):
                    cursor.execute("SELECT id, bank_name, account_number FROM banks WHERE user_id=%s", (user_id,))
                    ob_banks2 = cursor.fetchall()
                ob_bank_map2 = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in ob_banks2}
                with st.form("ob_expense_form"):
                    ob_exp_name   = st.text_input("Expense Name (e.g. Transport, Food)")
                    ob_exp_amount = st.number_input("Amount (NGN)", min_value=1, step=100, key="ob_exp_amt")
                    ob_exp_bank   = st.selectbox("Pay From Bank", list(ob_bank_map2.keys()))
                    ob_exp_submit = st.form_submit_button("Add Expense and Continue")
                if ob_exp_submit:
                    if ob_exp_name and ob_exp_amount > 0:
                        bk_id = ob_bank_map2[ob_exp_bank]
                        ok, result = save_expense(user_id, bk_id, ob_exp_name, ob_exp_amount)
                        if ok:
                            st.success("Expense logged!")
                            st.rerun()
                        else:
                            st.error(result)
                    else:
                        st.warning("Please enter a name and amount.")
            elif not done1:
                st.caption("Complete Step 1 first.")

            done4 = _ob["has_budget"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done4 else "ob-todo"}">'
                f'<span class="ob-icon">{"✅" if done4 else "📊"}</span>'
                f'<span><strong>Step 4: Set your monthly spending budget</strong>'
                f'{"&nbsp;&mdash; done!" if done4 else ""}</span></div>',
                unsafe_allow_html=True
            )
            if not done4:
                with st.form("ob_budget_form"):
                    ob_budget        = st.number_input("Monthly Budget (NGN)", min_value=1000, step=5000, value=100000)
                    ob_budget_submit = st.form_submit_button("Set Budget and Finish")
                if ob_budget_submit:
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE users SET monthly_spending_limit=%s WHERE id=%s", (int(ob_budget), user_id))
                    st.success("Budget set! You're all set up.")
                    st.rerun()

            if st.button("Skip setup checklist", key="skip_onboarding"):
                mark_onboarding_complete(user_id)
                st.rerun()
        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# HELPER: QUICK-ADD CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════
QUICK_ADD_CATEGORIES = [
    ("🚗 Transport", "Transport"), ("🍽️ Food", "Food & Eating Out"),
    ("🛒 Foodstuff", "Foodstuff"), ("⚡ Electricity", "Electricity (NEPA)"),
    ("📱 Airtime/Data", "Airtime/Data"), ("🏠 Rent", "Rent"),
    ("⛽ Fuel", "Fuel"), ("💊 Hospital/Drugs", "Hospital/Drugs"),
    ("🌐 Internet", "Internet"), ("🏫 School Fees", "School Fees"),
    ("🤲 Family Support", "Family Support"), ("⛪ Church/Mosque", "Church/Mosque Giving"),
    ("📦 Business Stock", "Business Stock"), ("📺 Subscription", "Subscription"),
    ("💇 Hair/Beauty", "Hair/Beauty"), ("👗 Clothing", "Clothing"),
    ("🔌 Generator", "Generator/Fuel"), ("💧 Water", "Water"),
    ("💳 POS Charges", "POS Charges"), ("🏦 Transfer Fees", "Transfer Fees"),
    ("🎰 Betting", "Betting"), ("💰 Savings", "Savings Deposit"),
    ("🛠️ Maintenance", "Maintenance"), ("🎁 Gift", "Gift"),
    ("🛍️ Shopping", "Shopping"),
]


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
def render_dashboard():
    st.title("📊 Dashboard")

    today       = datetime.now().date()
    month_start = today.replace(day=1)

    with get_db() as (conn, cursor):
        # Banks
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

        # Monthly totals
        cursor.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
              COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at>=%s
        """, (user_id, month_start))
        totals = cursor.fetchone()
        income = int(totals["income"] or 0)
        spent  = int(totals["spent"] or 0)
        net    = income - spent

        # Spending limit
        cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
        limit = int(cursor.fetchone()["monthly_spending_limit"] or 0)

        # Weekly spend (last 7 days)
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount),0) AS n FROM transactions t
            JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.type='debit' AND t.created_at>=%s
        """, (user_id, today - timedelta(days=7)))
        weekly_spend = int(cursor.fetchone()["n"] or 0)

        # Top 5 expenses this month
        cursor.execute("""
            SELECT e.name, COALESCE(e.category, e.name) AS cat, e.amount, e.created_at, b.bank_name
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at>=%s
            ORDER BY e.created_at DESC LIMIT 5
        """, (user_id, month_start))
        recent_expenses = cursor.fetchall()

        # Category breakdown
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat, SUM(e.amount) AS total
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at>=%s
            GROUP BY cat ORDER BY total DESC LIMIT 8
        """, (user_id, month_start))
        cat_data = cursor.fetchall()

        # Active goals
        cursor.execute("""
            SELECT name, target_amount, current_amount FROM goals
            WHERE user_id=%s AND status='active' ORDER BY created_at DESC LIMIT 3
        """, (user_id,))
        goals = cursor.fetchall()

    total_balance = sum(b["balance"] for b in banks)
    savings_rate  = round((net / income * 100), 1) if income > 0 else 0

    # ── Key metrics ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Total Balance", f"₦{total_balance:,}")
    c2.metric("📈 Income (MTD)",  f"₦{income:,}")
    c3.metric("📉 Spent (MTD)",   f"₦{spent:,}")
    c4.metric("💚 Net Saved",     f"₦{net:,}", delta=f"{savings_rate}% savings rate")

    # ── Budget progress ───────────────────────────────────────────────────────
    if limit > 0:
        pct = min(spent / limit * 100, 100)
        bar_color = "🔴" if pct >= 100 else ("🟡" if pct >= 80 else "🟢")
        st.markdown(f"**{bar_color} Monthly Budget: ₦{spent:,} / ₦{limit:,} ({pct:.0f}%)**")
        st.progress(pct / 100)

    # ── Weekly summary card ───────────────────────────────────────────────────
    days_in_month  = calendar.monthrange(today.year, today.month)[1]
    days_remaining = days_in_month - today.day + 1
    daily_safe = max(limit - spent, 0) // max(days_remaining, 1) if limit else 0

    st.markdown(f"""
    <div class="week-card">
      <div class="week-title">📅 This Week at a Glance</div>
      <div class="week-grid">
        <div class="week-stat"><div class="week-stat-label">Weekly Spend</div><div class="week-stat-value">₦{weekly_spend:,}</div></div>
        <div class="week-stat"><div class="week-stat-label">Daily Safe-to-Spend</div><div class="week-stat-value">₦{daily_safe:,}</div></div>
        <div class="week-stat"><div class="week-stat-label">Days Left</div><div class="week-stat-value">{days_remaining}</div></div>
        <div class="week-stat"><div class="week-stat-label">Savings Rate</div><div class="week-stat-value">{savings_rate}%</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Bank accounts ─────────────────────────────────────────────────────────
    if banks:
        st.subheader("🏦 Your Banks")
        cols = st.columns(min(len(banks), 3))
        for i, b in enumerate(banks):
            with cols[i % 3]:
                st.metric(f"{b['bank_name']} (****{b['account_number']})", f"₦{b['balance']:,}")

    # ── Pie chart + recent expenses ───────────────────────────────────────────
    col_chart, col_recent = st.columns([1, 1])

    with col_chart:
        st.subheader("📊 Spending by Category")
        if cat_data:
            df_cat = pd.DataFrame(cat_data, columns=["Category", "Amount"])
            fig = px.pie(df_cat, names="Category", values="Amount",
                         color_discrete_sequence=px.colors.sequential.Teal)
            fig.update_layout(margin=dict(t=20, b=20, l=0, r=0), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No expenses this month yet.")

    with col_recent:
        st.subheader("🧾 Recent Expenses")
        if recent_expenses:
            for e in recent_expenses:
                st.markdown(
                    f'<div class="exp-card">'
                    f'<div class="exp-card-left">'
                    f'<div class="exp-card-name">{e["name"]}</div>'
                    f'<div class="exp-card-bank">{e["cat"]} · {e["bank_name"]}</div>'
                    f'<div class="exp-card-date">{e["created_at"]}</div>'
                    f'</div>'
                    f'<div class="exp-card-right">'
                    f'<div class="exp-card-amount">-₦{e["amount"]:,}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No expenses recorded this month.")

    # ── Savings goals ─────────────────────────────────────────────────────────
    if goals:
        st.subheader("🎯 Savings Goals Progress")
        for g in goals:
            pct = min(int(g["current_amount"]) / max(int(g["target_amount"]), 1) * 100, 100)
            st.markdown(f"**{g['name']}** — ₦{g['current_amount']:,} / ₦{g['target_amount']:,} ({pct:.0f}%)")
            st.progress(pct / 100)

    # ── Insight cards ─────────────────────────────────────────────────────────
    st.subheader("💡 Financial Insights")
    insights = []
    if income > 0 and savings_rate < 10:
        insights.append(("⚠️", "#fff3e0", "Low Savings Rate",
            f"You're saving {savings_rate}% of income. Aim for at least 20% — the 50/30/20 rule says: "
            "50% needs, 30% wants, 20% savings."))
    if limit > 0 and spent / limit >= 0.8:
        insights.append(("🚨", "#fdecea", "Budget Warning",
            f"You've used {spent/limit*100:.0f}% of your ₦{limit:,} budget. Slow down spending for the rest of the month."))
    if spent == 0 and income == 0:
        insights.append(("📌", "#e8f5f0", "Get Started",
            "You haven't recorded any transactions this month. Start by logging your income and expenses."))
    if daily_safe > 0:
        insights.append(("📅", "#e8f5f0", "Daily Budget",
            f"You can safely spend ₦{daily_safe:,}/day for the remaining {days_remaining} days of this month."))
    if not insights:
        insights.append(("✅", "#e8f5f0", "Looking Good!",
            "Your finances look healthy this month. Keep tracking consistently."))

    for icon, bg, title, text in insights:
        st.markdown(
            f'<div class="insight-card" style="background:{bg};">'
            f'<div class="insight-icon">{icon}</div>'
            f'<div class="insight-body"><div class="insight-title">{title}</div>'
            f'<div class="insight-text">{text}</div></div></div>',
            unsafe_allow_html=True
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: INCOME
# ══════════════════════════════════════════════════════════════════════════════
def render_income():
    st.title("📈 Income")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    if not banks:
        st.warning("Add a bank account first (go to Banks).")
        return

    bank_map = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in banks}

    # ── Add income form ───────────────────────────────────────────────────────
    with st.expander("➕ Add Income", expanded=False):
        with st.form("add_income_form"):
            inc_source = st.text_input("Income Source (e.g. Salary, Freelance, Business)")
            inc_amount = st.number_input("Amount (NGN)", min_value=1, step=500)
            inc_bank   = st.selectbox("Deposit to Bank", list(bank_map.keys()))
            inc_date   = st.date_input("Date", value=datetime.now().date())
            inc_submit = st.form_submit_button("Add Income", use_container_width=True)
        if inc_submit:
            if inc_source and inc_amount > 0:
                bk_id = bank_map[inc_bank]
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE banks SET balance=balance+%s WHERE id=%s", (int(inc_amount), bk_id))
                    cursor.execute(
                        "INSERT INTO transactions (bank_id,type,amount,description,created_at) VALUES (%s,'credit',%s,%s,%s)",
                        (bk_id, int(inc_amount), f"Income: {inc_source}", inc_date)
                    )
                st.success(f"₦{inc_amount:,} income recorded!")
                st.rerun()
            else:
                st.warning("Please fill all fields.")

    # ── Income history ────────────────────────────────────────────────────────
    st.subheader("📋 Income History")
    render_filter_bar_income(banks)

    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT t.id, t.description, t.amount, t.created_at, b.bank_name, b.id AS bank_id
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.type='credit'
            ORDER BY t.created_at DESC
        """, (user_id,))
        all_income = cursor.fetchall()

    filtered = apply_income_filters(all_income)

    if not filtered:
        st.info("No income records found. Add your first income above.")
        return

    total_shown = sum(r["amount"] for r in filtered)
    st.caption(f"{len(filtered)} records · Total: ₦{total_shown:,}")

    for r in filtered:
        source = str(r["description"] or "").replace("Income: ", "")
        edit_key = f"edit_inc_{r['id']}"

        col_info, col_amt, col_btns = st.columns([3, 1.5, 1])
        with col_info:
            st.markdown(f"**{source}**  \n{r['bank_name']} · {r['created_at']}")
        with col_amt:
            st.markdown(f"<span style='color:#0e7c5b;font-weight:700;font-size:1rem;'>+₦{r['amount']:,}</span>", unsafe_allow_html=True)
        with col_btns:
            cb1, cb2 = st.columns(2)
            with cb1:
                if st.button("✏️", key=f"ei_{r['id']}", help="Edit"):
                    st.session_state.edit_income_id = r["id"]
            with cb2:
                if st.button("🗑️", key=f"di_{r['id']}", help="Delete"):
                    st.session_state.confirm_delete[f"inc_{r['id']}"] = True

        # Edit inline
        if st.session_state.edit_income_id == r["id"]:
            with st.form(f"edit_inc_form_{r['id']}"):
                new_src = st.text_input("Source", value=str(r["description"] or "").replace("Income: ", ""))
                new_amt = st.number_input("Amount", value=int(r["amount"]), min_value=1)
                new_bk  = st.selectbox("Bank", list(bank_map.keys()),
                                        index=list(bank_map.values()).index(r["bank_id"]) if r["bank_id"] in bank_map.values() else 0)
                new_dt  = st.date_input("Date", value=r["created_at"])
                upd_sub = st.form_submit_button("Save Changes")
                can_sub = st.form_submit_button("Cancel")
            if upd_sub:
                diff = int(new_amt) - int(r["amount"])
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE transactions SET description=%s,amount=%s,created_at=%s,bank_id=%s WHERE id=%s",
                                   (f"Income: {new_src}", new_amt, new_dt, bank_map[new_bk], r["id"]))
                    cursor.execute("UPDATE banks SET balance=balance+%s WHERE id=%s", (diff, bank_map[new_bk]))
                st.session_state.edit_income_id = None
                st.rerun()
            if can_sub:
                st.session_state.edit_income_id = None
                st.rerun()

        # Confirm delete
        if st.session_state.confirm_delete.get(f"inc_{r['id']}"):
            st.warning(f"Delete ₦{r['amount']:,} income from {source}?")
            cd1, cd2 = st.columns(2)
            with cd1:
                if st.button("Yes, delete", key=f"cd_yes_inc_{r['id']}"):
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE banks SET balance=balance-%s WHERE id=%s", (r["amount"], r["bank_id"]))
                        cursor.execute("DELETE FROM transactions WHERE id=%s", (r["id"],))
                    st.session_state.confirm_delete.pop(f"inc_{r['id']}", None)
                    st.rerun()
            with cd2:
                if st.button("Cancel", key=f"cd_no_inc_{r['id']}"):
                    st.session_state.confirm_delete.pop(f"inc_{r['id']}", None)
                    st.rerun()
        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: EXPENSES
# ══════════════════════════════════════════════════════════════════════════════
def render_expenses():
    st.title("📉 Expenses")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    if not banks:
        st.warning("Add a bank account first (go to Banks).")
        return

    bank_map = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in banks}
    cat_options = [c for _, c in QUICK_ADD_CATEGORIES]

    # ── Quick-add buttons ─────────────────────────────────────────────────────
    st.subheader("⚡ Quick Add")
    qa_cols = st.columns(5)
    for i, (label, cat) in enumerate(QUICK_ADD_CATEGORIES[:15]):
        with qa_cols[i % 5]:
            if st.button(label, key=f"qa_{cat}", use_container_width=True):
                st.session_state.quick_add_name = cat

    # ── Add expense form ──────────────────────────────────────────────────────
    with st.expander("➕ Add Expense", expanded=True):
        with st.form("add_expense_form"):
            exp_name   = st.text_input("Expense Name", value=st.session_state.quick_add_name)
            exp_cat    = st.selectbox("Category", ["Other"] + cat_options,
                                      index=(["Other"] + cat_options).index(st.session_state.quick_add_name)
                                      if st.session_state.quick_add_name in cat_options else 0)
            exp_amount = st.number_input("Amount (NGN)", min_value=1, step=100)
            exp_bank   = st.selectbox("Pay From Bank", list(bank_map.keys()))
            exp_submit = st.form_submit_button("Log Expense", use_container_width=True)
        if exp_submit:
            if exp_name and exp_amount > 0:
                bk_id = bank_map[exp_bank]
                ok, result = save_expense(user_id, bk_id, exp_name, exp_amount, exp_cat)
                if ok:
                    st.success(f"Expense ''{exp_name}'' logged!")
                    st.session_state.quick_add_name = ""
                    st.rerun()
                else:
                    st.error(result)
            else:
                st.warning("Please enter a name and amount.")

    # ── Expense list ──────────────────────────────────────────────────────────
    st.subheader("📋 Expense History")

    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT e.id, e.name, e.category, e.amount, e.created_at,
                   b.bank_name, b.id AS bank_id
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s ORDER BY e.created_at DESC
        """, (user_id,))
        all_expenses = cursor.fetchall()

    all_cats = sorted(set((r["category"] or r["name"]) for r in all_expenses))
    render_filter_bar_expenses(banks, all_cats)
    filtered = apply_expense_filters(all_expenses)

    if not filtered:
        st.info("No expenses found. Log your first expense above.")
        return

    total_shown = sum(r["amount"] for r in filtered)
    st.caption(f"{len(filtered)} records · Total: ₦{total_shown:,}")

    for r in filtered:
        col_info, col_amt, col_btns = st.columns([3, 1.5, 1])
        with col_info:
            st.markdown(f"**{r['name']}** · {r['category'] or r['name']}  \n{r['bank_name']} · {r['created_at']}")
        with col_amt:
            st.markdown(f"<span style='color:#c0392b;font-weight:700;font-size:1rem;'>-₦{r['amount']:,}</span>", unsafe_allow_html=True)
        with col_btns:
            cb1, cb2 = st.columns(2)
            with cb1:
                if st.button("✏️", key=f"ee_{r['id']}", help="Edit"):
                    st.session_state.edit_exp_id = r["id"]
            with cb2:
                if st.button("🗑️", key=f"de_{r['id']}", help="Delete"):
                    st.session_state.confirm_delete[f"exp_{r['id']}"] = True

        # Edit inline
        if st.session_state.edit_exp_id == r["id"]:
            with st.form(f"edit_exp_{r['id']}"):
                new_name = st.text_input("Name", value=r["name"])
                new_cat  = st.selectbox("Category", ["Other"] + cat_options,
                                         index=(["Other"] + cat_options).index(r["category"]) if r["category"] in cat_options else 0)
                new_amt  = st.number_input("Amount", value=int(r["amount"]), min_value=1)
                new_bk   = st.selectbox("Bank", list(bank_map.keys()))
                new_dt   = st.date_input("Date", value=r["created_at"])
                e_save   = st.form_submit_button("Save")
                e_cancel = st.form_submit_button("Cancel")
            if e_save:
                diff = int(new_amt) - int(r["amount"])
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE expenses SET name=%s,category=%s,amount=%s,created_at=%s,bank_id=%s WHERE id=%s",
                                   (new_name, new_cat, new_amt, new_dt, bank_map[new_bk], r["id"]))
                    if diff != 0:
                        cursor.execute("UPDATE banks SET balance=balance+%s WHERE id=%s", (-diff, r["bank_id"]))
                st.session_state.edit_exp_id = None
                st.rerun()
            if e_cancel:
                st.session_state.edit_exp_id = None
                st.rerun()

        # Confirm delete
        if st.session_state.confirm_delete.get(f"exp_{r['id']}"):
            st.warning(f"Delete ₦{r['amount']:,} expense '{r['name']}'?")
            cd1, cd2 = st.columns(2)
            with cd1:
                if st.button("Yes, delete", key=f"cd_yes_exp_{r['id']}"):
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE banks SET balance=balance+%s WHERE id=%s", (r["amount"], r["bank_id"]))
                        cursor.execute("DELETE FROM expenses WHERE id=%s", (r["id"],))
                        cursor.execute("DELETE FROM transactions WHERE id=(SELECT tx_id FROM expenses WHERE id=%s)", (r["id"],))
                    st.session_state.confirm_delete.pop(f"exp_{r['id']}", None)
                    st.rerun()
            with cd2:
                if st.button("Cancel", key=f"cd_no_exp_{r['id']}"):
                    st.session_state.confirm_delete.pop(f"exp_{r['id']}", None)
                    st.rerun()
        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: BANKS
# ══════════════════════════════════════════════════════════════════════════════
def render_banks():
    st.title("🏦 Banks")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_name, account_number, balance, min_balance_alert FROM banks WHERE user_id=%s ORDER BY bank_name", (user_id,))
        banks = cursor.fetchall()

    # Add bank
    with st.expander("➕ Add Bank Account", expanded=not banks):
        with st.form("add_bank_form"):
            b_name   = st.text_input("Bank Name (e.g. GTB, Kuda, Opay)")
            b_acct   = st.text_input("Account Name")
            b_num    = st.text_input("Account Number / Last 4 digits")
            b_bal    = st.number_input("Opening Balance (NGN)", min_value=0, step=1000)
            b_alert  = st.number_input("Minimum Balance Alert (NGN)", min_value=0, step=1000)
            b_submit = st.form_submit_button("Add Bank", use_container_width=True)
        if b_submit:
            if b_name and b_acct and b_num:
                with get_db() as (conn, cursor):
                    cursor.execute(
                        "INSERT INTO banks (user_id, bank_name, account_name, account_number, balance, min_balance_alert) VALUES (%s,%s,%s,%s,%s,%s)",
                        (user_id, b_name, b_acct, b_num[-4:], int(b_bal), int(b_alert))
                    )
                st.success(f"Bank '{b_name}' added!")
                st.rerun()
            else:
                st.warning("Please fill all required fields.")

    if not banks:
        st.info("No bank accounts yet. Add your first bank above.")
        return

    total_balance = sum(b["balance"] for b in banks)
    st.metric("💰 Total Balance Across All Banks", f"₦{total_balance:,}")
    st.divider()

    for b in banks:
        col_info, col_bal, col_btns = st.columns([3, 1.5, 1])
        with col_info:
            st.markdown(f"**{b['bank_name']}** · {b['account_name']}  \nAcct: ****{b['account_number']}")
            if b["min_balance_alert"] and b["balance"] < b["min_balance_alert"]:
                st.warning(f"⚠️ Balance below alert threshold (₦{b['min_balance_alert']:,})")
        with col_bal:
            st.metric("Balance", f"₦{b['balance']:,}")
        with col_btns:
            cb1, cb2 = st.columns(2)
            with cb1:
                if st.button("✏️", key=f"eb_{b['id']}", help="Edit"):
                    st.session_state.edit_bank_id = b["id"]
            with cb2:
                if st.button("🗑️", key=f"db_{b['id']}", help="Delete"):
                    st.session_state.confirm_delete[f"bank_{b['id']}"] = True

        # Edit inline
        if st.session_state.edit_bank_id == b["id"]:
            with st.form(f"edit_bank_{b['id']}"):
                nb_name  = st.text_input("Bank Name", value=b["bank_name"])
                nb_acct  = st.text_input("Account Name", value=b["account_name"])
                nb_num   = st.text_input("Account Number", value=b["account_number"])
                nb_alert = st.number_input("Min Balance Alert", value=int(b["min_balance_alert"]), min_value=0)
                bs_save  = st.form_submit_button("Save")
                bs_cancel= st.form_submit_button("Cancel")
            if bs_save:
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE banks SET bank_name=%s,account_name=%s,account_number=%s,min_balance_alert=%s WHERE id=%s AND user_id=%s",
                                   (nb_name, nb_acct, nb_num[-4:], nb_alert, b["id"], user_id))
                st.session_state.edit_bank_id = None
                st.rerun()
            if bs_cancel:
                st.session_state.edit_bank_id = None
                st.rerun()

        # Confirm delete
        if st.session_state.confirm_delete.get(f"bank_{b['id']}"):
            st.warning(f"Delete '{b['bank_name']}'? This will also delete all its transactions!")
            cd1, cd2 = st.columns(2)
            with cd1:
                if st.button("Yes, delete", key=f"cd_yes_bank_{b['id']}"):
                    with get_db() as (conn, cursor):
                        cursor.execute("DELETE FROM banks WHERE id=%s AND user_id=%s", (b["id"], user_id))
                    st.session_state.confirm_delete.pop(f"bank_{b['id']}", None)
                    st.rerun()
            with cd2:
                if st.button("Cancel", key=f"cd_no_bank_{b['id']}"):
                    st.session_state.confirm_delete.pop(f"bank_{b['id']}", None)
                    st.rerun()
        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: TRANSFERS
# ══════════════════════════════════════════════════════════════════════════════
def render_transfers():
    st.title("🔄 Transfers")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    if len(banks) < 2:
        st.warning("You need at least 2 bank accounts to make a transfer.")
        return

    bank_map = {f"{b['bank_name']} (****{b['account_number']}) — ₦{b['balance']:,}": b["id"] for b in banks}
    bank_list = list(bank_map.keys())

    with st.form("transfer_form"):
        from_bank = st.selectbox("From Bank", bank_list, key="tr_from")
        to_bank   = st.selectbox("To Bank",   bank_list, key="tr_to")
        tr_amt    = st.number_input("Amount (NGN)", min_value=1, step=500)
        tr_desc   = st.text_input("Note (optional)", placeholder="e.g. Move for savings")
        tr_submit = st.form_submit_button("Transfer", use_container_width=True)

    if tr_submit:
        if from_bank == to_bank:
            st.error("Cannot transfer to the same bank.")
        elif tr_amt <= 0:
            st.error("Amount must be positive.")
        else:
            from_id = bank_map[from_bank]
            to_id   = bank_map[to_bank]
            with get_db() as (conn, cursor):
                cursor.execute("SELECT balance, allow_overdraft FROM banks b JOIN users u ON b.user_id=u.id WHERE b.id=%s", (from_id,))
                brow = cursor.fetchone()
                if brow["balance"] < tr_amt:
                    cursor.execute("SELECT allow_overdraft FROM users WHERE id=%s", (user_id,))
                    urow = cursor.fetchone()
                    if not urow["allow_overdraft"]:
                        st.error(f"Insufficient funds. Balance: ₦{brow['balance']:,}")
                        st.stop()
                note = tr_desc or "Transfer"
                today = datetime.now().date()
                cursor.execute("UPDATE banks SET balance=balance-%s WHERE id=%s", (tr_amt, from_id))
                cursor.execute("UPDATE banks SET balance=balance+%s WHERE id=%s", (tr_amt, to_id))
                cursor.execute("INSERT INTO transactions (bank_id,type,amount,description,created_at) VALUES (%s,'debit',%s,%s,%s)",
                               (from_id, tr_amt, f"Transfer out: {note}", today))
                cursor.execute("INSERT INTO transactions (bank_id,type,amount,description,created_at) VALUES (%s,'credit',%s,%s,%s)",
                               (to_id, tr_amt, f"Transfer in: {note}", today))
            st.success(f"₦{tr_amt:,} transferred successfully!")
            st.rerun()

    # Recent transfers
    st.subheader("📋 Recent Transfers")
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT t.description, t.amount, t.created_at, b.bank_name
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.description LIKE 'Transfer%%'
            ORDER BY t.created_at DESC LIMIT 20
        """, (user_id,))
        transfers = cursor.fetchall()

    if not transfers:
        st.info("No transfers yet.")
    else:
        for t in transfers:
            color = "#c0392b" if "out" in (t["description"] or "").lower() else "#0e7c5b"
            prefix = "-" if "out" in (t["description"] or "").lower() else "+"
            st.markdown(
                f"**{t['description']}** · {t['bank_name']} · {t['created_at']}  "
                f"<span style='color:{color};font-weight:700;'>{prefix}₦{t['amount']:,}</span>",
                unsafe_allow_html=True
            )
            st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SAVINGS GOALS
# ══════════════════════════════════════════════════════════════════════════════
GOAL_PRESETS = [
    "Emergency Fund", "Rent", "School Fees", "Bride Price",
    "New Phone", "Laptop", "Car", "Travel",
    "Business Capital", "House Deposit", "Wedding",
    "Medical Fund", "Holiday", "Investment",
]

def render_goals():
    st.title("🎯 Savings Goals")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()
        cursor.execute("SELECT id, name, target_amount, current_amount, status, created_at FROM goals WHERE user_id=%s ORDER BY status, created_at DESC", (user_id,))
        goals = cursor.fetchall()

    bank_map = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in banks}

    # ── Add goal ──────────────────────────────────────────────────────────────
    with st.expander("➕ Create New Goal", expanded=not goals):
        st.markdown("**Quick select:**")
        chip_cols = st.columns(4)
        for i, preset in enumerate(GOAL_PRESETS):
            with chip_cols[i % 4]:
                if st.button(preset, key=f"preset_{preset}"):
                    st.session_state.goal_preset_name = preset
        with st.form("add_goal_form"):
            g_name   = st.text_input("Goal Name", value=st.session_state.goal_preset_name)
            g_target = st.number_input("Target Amount (NGN)", min_value=100, step=1000)
            g_submit = st.form_submit_button("Create Goal", use_container_width=True)
        if g_submit:
            if g_name and g_target > 0:
                with get_db() as (conn, cursor):
                    cursor.execute(
                        "INSERT INTO goals (user_id, name, target_amount, current_amount, status, created_at) VALUES (%s,%s,%s,0,'active',%s)",
                        (user_id, g_name, int(g_target), datetime.now().date())
                    )
                st.success(f"Goal '{g_name}' created!")
                st.session_state.goal_preset_name = ""
                st.rerun()
            else:
                st.warning("Please enter a name and target amount.")

    if not goals:
        st.info("No goals yet. Create your first savings goal above!")
        return

    # ── Goal cards ────────────────────────────────────────────────────────────
    active_goals    = [g for g in goals if g["status"] == "active"]
    completed_goals = [g for g in goals if g["status"] != "active"]

    for section_label, goal_list in [("🎯 Active Goals", active_goals), ("✅ Completed Goals", completed_goals)]:
        if not goal_list:
            continue
        st.subheader(section_label)
        for g in goal_list:
            target  = int(g["target_amount"])
            saved   = int(g["current_amount"])
            pct     = min(saved / target * 100, 100) if target > 0 else 0
            remain  = max(target - saved, 0)

            with st.container():
                st.markdown(f"**{g['name']}** — ₦{saved:,} / ₦{target:,}")
                st.progress(pct / 100, text=f"{pct:.0f}% — ₦{remain:,} to go")

                if g["status"] == "active":
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        if st.button("💰 Add Money", key=f"gc_{g['id']}"):
                            st.session_state.selected_goal = g["id"]
                    with col_b:
                        if st.button("✅ Mark Complete", key=f"gm_{g['id']}"):
                            with get_db() as (conn, cursor):
                                cursor.execute("UPDATE goals SET status='completed' WHERE id=%s AND user_id=%s", (g["id"], user_id))
                            st.rerun()
                    with col_c:
                        if st.button("🗑️ Delete", key=f"gd_{g['id']}"):
                            st.session_state.confirm_delete[f"goal_{g['id']}"] = True

                    # Contribution form
                    if st.session_state.selected_goal == g["id"] and banks:
                        with st.form(f"contribute_{g['id']}"):
                            c_amt  = st.number_input("Amount to add (NGN)", min_value=1, step=500)
                            c_bank = st.selectbox("From Bank", list(bank_map.keys()))
                            c_sub  = st.form_submit_button("Add to Goal")
                        if c_sub:
                            bk_id = bank_map[c_bank]
                            with get_db() as (conn, cursor):
                                cursor.execute("SELECT balance FROM banks WHERE id=%s", (bk_id,))
                                bbal = cursor.fetchone()["balance"]
                                if bbal < int(c_amt):
                                    st.error(f"Insufficient funds. Bank balance: ₦{bbal:,}")
                                else:
                                    cursor.execute("UPDATE goals SET current_amount=current_amount+%s WHERE id=%s", (int(c_amt), g["id"]))
                                    cursor.execute("UPDATE banks SET balance=balance-%s WHERE id=%s", (int(c_amt), bk_id))
                                    cursor.execute("INSERT INTO goal_contributions (goal_id,user_id,bank_id,amount,contributed_at) VALUES (%s,%s,%s,%s,%s)",
                                                   (g["id"], user_id, bk_id, int(c_amt), datetime.now().date()))
                                    cursor.execute("INSERT INTO transactions (bank_id,type,amount,description,created_at) VALUES (%s,'debit',%s,%s,%s)",
                                                   (bk_id, int(c_amt), f"Savings: {g['name']}", datetime.now().date()))
                            st.success(f"₦{c_amt:,} added to '{g['name']}'!")
                            st.session_state.selected_goal = None
                            st.rerun()

                # Confirm delete goal
                if st.session_state.confirm_delete.get(f"goal_{g['id']}"):
                    st.warning(f"Delete goal '{g['name']}'?")
                    gd1, gd2 = st.columns(2)
                    with gd1:
                        if st.button("Yes, delete", key=f"cd_yes_goal_{g['id']}"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM goals WHERE id=%s AND user_id=%s", (g["id"], user_id))
                            st.session_state.confirm_delete.pop(f"goal_{g['id']}", None)
                            st.rerun()
                    with gd2:
                        if st.button("Cancel", key=f"cd_no_goal_{g['id']}"):
                            st.session_state.confirm_delete.pop(f"goal_{g['id']}", None)
                            st.rerun()
            st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: TRACKER (Recurring items)
# ══════════════════════════════════════════════════════════════════════════════
def render_tracker():
    st.title("🔁 Recurring Tracker")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()
        cursor.execute("""
            SELECT r.id, r.type, r.name, r.category, r.amount, r.frequency, r.next_due,
                   r.auto_post, r.active, b.bank_name
            FROM recurring_items r LEFT JOIN banks b ON r.bank_id=b.id
            WHERE r.user_id=%s ORDER BY r.next_due ASC NULLS LAST
        """, (user_id,))
        items = cursor.fetchall()

    bank_map = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in banks}
    cat_options = [c for _, c in QUICK_ADD_CATEGORIES]

    with st.expander("➕ Add Recurring Item"):
        with st.form("add_recurring"):
            ri_type  = st.selectbox("Type", ["expense", "income"])
            ri_name  = st.text_input("Name (e.g. DSTV, Rent, Salary)")
            ri_cat   = st.selectbox("Category", ["Other"] + cat_options)
            ri_amt   = st.number_input("Amount (NGN)", min_value=1, step=500)
            ri_freq  = st.selectbox("Frequency", ["monthly", "weekly", "daily", "yearly"])
            ri_due   = st.date_input("Next Due Date", value=datetime.now().date())
            ri_bank  = st.selectbox("Bank", ["(none)"] + list(bank_map.keys()))
            ri_auto  = st.checkbox("Auto-post when due")
            ri_sub   = st.form_submit_button("Add Item")
        if ri_sub:
            bk_id = bank_map.get(ri_bank) if ri_bank != "(none)" else None
            with get_db() as (conn, cursor):
                cursor.execute("""
                    INSERT INTO recurring_items (user_id,type,name,category,amount,frequency,next_due,bank_id,auto_post,active,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)
                """, (user_id, ri_type, ri_name, ri_cat, int(ri_amt), ri_freq, ri_due, bk_id, 1 if ri_auto else 0, datetime.now().date()))
            st.success(f"'{ri_name}' added!")
            st.rerun()

    if not items:
        st.info("No recurring items yet.")
        return

    today = datetime.now().date()
    for it in items:
        due   = it["next_due"]
        overdue = due and due < today
        due_label = f"Due: {due}" if due else "No due date"
        color = "#c0392b" if overdue else ("#f39c12" if due and (due - today).days <= 3 else "#0e7c5b")

        col_info, col_amt, col_btn = st.columns([3, 1.5, 1])
        with col_info:
            badge = "📥 INCOME" if it["type"] == "income" else "📤 EXPENSE"
            st.markdown(f"**{it['name']}** {badge}  \n{it['frequency'].title()} · {it['bank_name'] or '—'}  \n<span style='color:{color};font-size:0.82rem;font-weight:700;'>{'⚠️ OVERDUE — ' if overdue else ''}{due_label}</span>", unsafe_allow_html=True)
        with col_amt:
            st.metric("Amount", f"₦{it['amount']:,}")
        with col_btn:
            if st.button("🗑️", key=f"dr_{it['id']}", help="Delete"):
                with get_db() as (conn, cursor):
                    cursor.execute("DELETE FROM recurring_items WHERE id=%s AND user_id=%s", (it["id"], user_id))
                st.rerun()
        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SUMMARIES
# ══════════════════════════════════════════════════════════════════════════════
def render_summaries():
    st.title("📄 Summaries & Reports")

    today = datetime.now().date()

    tab_csv, tab_pdf = st.tabs(["📥 CSV Export", "📄 PDF Reports"])

    with tab_csv:
        st.subheader("📊 Monthly CSV Report")
        sel_year  = st.selectbox("Year",  list(range(today.year, today.year - 3, -1)), key="csv_yr")
        sel_month = st.selectbox("Month", list(range(1, 13)), index=today.month - 1,
                                  format_func=lambda m: datetime(2000, m, 1).strftime("%B"), key="csv_mo")
        if st.button("Generate CSV", key="gen_csv"):
            m_start = date(sel_year, sel_month, 1)
            m_end   = date(sel_year, sel_month, calendar.monthrange(sel_year, sel_month)[1])
            with get_db() as (conn, cursor):
                cursor.execute("""
                    SELECT e.created_at, e.name, COALESCE(e.category,e.name) AS category,
                           e.amount, b.bank_name
                    FROM expenses e JOIN banks b ON e.bank_id=b.id
                    WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
                    ORDER BY e.created_at
                """, (user_id, m_start, m_end))
                rows = cursor.fetchall()
            if rows:
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["Date", "Name", "Category", "Amount (NGN)", "Bank"])
                for r in rows:
                    writer.writerow([r["created_at"], r["name"], r["category"], r["amount"], r["bank_name"]])
                month_name = datetime(sel_year, sel_month, 1).strftime("%B_%Y")
                st.download_button("⬇️ Download CSV", buf.getvalue(),
                                   file_name=f"Budget_Right_{month_name}.csv", mime="text/csv")
            else:
                st.info("No expenses found for that month.")

    with tab_pdf:
        st.subheader("📄 PDF Reports")
        sel_year_p  = st.selectbox("Year",  list(range(today.year, today.year - 3, -1)), key="pdf_yr")
        sel_month_p = st.selectbox("Month", list(range(1, 13)), index=today.month - 1,
                                    format_func=lambda m: datetime(2000, m, 1).strftime("%B"), key="pdf_mo")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📊 Monthly Statement", use_container_width=True):
                with st.spinner("Generating..."):
                    data = fetch_monthly_data(user_id, sel_year_p, sel_month_p)
                    pdf  = build_monthly_statement(data)
                    fname = datetime(sel_year_p, sel_month_p, 1).strftime("%B_%Y")
                st.download_button("⬇️ Download", pdf, file_name=f"BudgetRight_Statement_{fname}.pdf", mime="application/pdf")

        with col2:
            if st.button("🎯 Goal Progress Report", use_container_width=True):
                with st.spinner("Generating..."):
                    data = fetch_goal_data(user_id)
                    pdf  = build_goal_progress_report(data)
                st.download_button("⬇️ Download", pdf, file_name="BudgetRight_Goals.pdf", mime="application/pdf")

        col3, col4 = st.columns(2)
        with col3:
            if st.button("📋 Category Budget Report", use_container_width=True):
                with st.spinner("Generating..."):
                    data = fetch_category_budget_data(user_id, sel_year_p, sel_month_p)
                    pdf  = build_category_budget_report(data)
                    fname = datetime(sel_year_p, sel_month_p, 1).strftime("%B_%Y")
                st.download_button("⬇️ Download", pdf, file_name=f"BudgetRight_CategoryBudget_{fname}.pdf", mime="application/pdf")

        with col4:
            if st.button("🏦 Bank Report", use_container_width=True):
                with st.spinner("Generating..."):
                    data = fetch_bank_data(user_id, sel_year_p, sel_month_p)
                    pdf  = build_bank_report(data)
                    fname = datetime(sel_year_p, sel_month_p, 1).strftime("%B_%Y")
                st.download_button("⬇️ Download", pdf, file_name=f"BudgetRight_Banks_{fname}.pdf", mime="application/pdf")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════
def render_notifications():
    st.title("🔔 Notifications")

    notifications = get_notifications(user_id, unread_only=False, limit=50)
    unread_count  = sum(1 for n in notifications if not n["read"])

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption(f"{len(notifications)} notifications · {unread_count} unread")
    with col_b:
        if st.button("Mark all read", key="mark_all_read"):
            mark_notifications_read(user_id)
            st.session_state._unread_cache = 0
            st.rerun()

    if st.button("🗑️ Clear all", key="clear_notifs"):
        clear_all_notifications(user_id)
        st.rerun()

    if not notifications:
        st.info("No notifications yet. Keep using Budget Right to earn streaks and tips!")
        return

    TYPE_COLORS = {
        "reminder": "#e8f5f0", "tip": "#e3f2fd",
        "milestone": "#fff8e1", "alert": "#fdecea", "nudge": "#f3e5f5",
    }
    TYPE_ICONS = {
        "reminder": "🔔", "tip": "💡", "milestone": "🏆", "alert": "⚠️", "nudge": "👋",
    }

    for n in notifications:
        bg    = TYPE_COLORS.get(n["type"], "#f5f5f5")
        icon  = n["icon"] or TYPE_ICONS.get(n["type"], "🔔")
        read_style = "" if not n["read"] else "opacity:0.65;"
        unread_dot = '<span style="background:#e74c3c;border-radius:50%;width:8px;height:8px;display:inline-block;margin-left:6px;"></span>' if not n["read"] else ""

        st.markdown(
            f'<div style="background:{bg};border-radius:10px;padding:12px 14px;'
            f'margin-bottom:8px;{read_style}">'
            f'<div style="font-weight:700;margin-bottom:4px;">{n["title"]} {unread_dot}</div>'
            f'<div style="font-size:0.88rem;">{n["body"]}</div>'
            f'<div style="font-size:0.75rem;color:#888;margin-top:6px;">{str(n["created_at"])[:16]}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        if not n["read"]:
            if st.button("Mark read", key=f"nr_{n['id']}"):
                mark_notification_read(n["id"])
                st.session_state._unread_cache = max(0, (st.session_state._unread_cache or 1) - 1)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: IMPORT CSV
# ══════════════════════════════════════════════════════════════════════════════
def render_import_csv():
    st.title("📥 Import CSV")
    with get_db() as (conn, cursor):
        csv_import_page(conn, user_id)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
def render_settings():
    st.title("⚙️ Settings")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT surname, other_names, email, username, monthly_spending_limit, allow_overdraft FROM users WHERE id=%s", (user_id,))
        u = cursor.fetchone()

    tab_profile, tab_budget, tab_security = st.tabs(["👤 Profile", "💰 Budgets", "🔒 Security"])

    with tab_profile:
        st.subheader("Profile Details")
        st.markdown(f"**Name:** {u['surname']} {u['other_names']}")
        st.markdown(f"**Email:** {u['email']}")
        st.markdown(f"**Username:** {u['username']}")

        st.subheader("Monthly Spending Limit")
        with st.form("update_limit_form"):
            new_limit = st.number_input("Monthly Budget (NGN)", min_value=0, step=5000,
                                         value=int(u["monthly_spending_limit"] or 0))
            new_overdraft = st.checkbox("Allow overdraft (let balance go negative)", value=bool(u["allow_overdraft"]))
            lim_sub = st.form_submit_button("Save Settings")
        if lim_sub:
            with get_db() as (conn, cursor):
                cursor.execute("UPDATE users SET monthly_spending_limit=%s, allow_overdraft=%s WHERE id=%s",
                               (new_limit, 1 if new_overdraft else 0, user_id))
            st.success("Settings saved!")
            st.rerun()

    with tab_budget:
        st.subheader("📊 Category Budgets")
        st.caption("Set monthly limits per category. Budget Right alerts you when you're close.")

        cat_budgets = get_category_budgets(user_id)
        budget_map  = {cb["category"]: cb for cb in cat_budgets}

        for cat in BUDGET_CATEGORIES:
            cb     = budget_map.get(cat, {})
            cur_lim = int(cb.get("monthly_limit", 0))
            spent   = int(cb.get("spent", 0))
            col_c, col_inp, col_prog = st.columns([2, 1.5, 2])
            with col_c:
                st.caption(cat)
            with col_inp:
                new_lim = st.number_input("", min_value=0, step=1000, value=cur_lim,
                                           key=f"catbdg_{cat}", label_visibility="collapsed")
                if new_lim != cur_lim:
                    upsert_category_budget(user_id, cat, new_lim)
            with col_prog:
                if cur_lim > 0:
                    pct = min(spent / cur_lim * 100, 100)
                    color = "#c0392b" if pct >= 100 else ("#f39c12" if pct >= 80 else "#0e7c5b")
                    st.markdown(
                        f'<div style="background:#f0f0f0;border-radius:6px;height:8px;margin-top:10px;">'
                        f'<div style="background:{color};width:{pct:.0f}%;height:100%;border-radius:6px;"></div></div>'
                        f'<div style="font-size:0.72rem;color:#666;">₦{spent:,} / ₦{cur_lim:,}</div>',
                        unsafe_allow_html=True
                    )

    with tab_security:
        st.subheader("Change Password")
        with st.form("change_pw_form"):
            cur_pw  = st.text_input("Current Password", type="password")
            new_pw  = st.text_input("New Password", type="password")
            new_pw2 = st.text_input("Confirm New Password", type="password")
            pw_sub  = st.form_submit_button("Change Password")
        if pw_sub:
            if new_pw != new_pw2:
                st.error("New passwords do not match.")
            else:
                pw_ok, pw_msg = validate_password(new_pw)
                if not pw_ok:
                    st.error(pw_msg)
                else:
                    ok, msg = change_password(user_id, cur_pw, new_pw)
                    st.success(msg) if ok else st.error(msg)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════
def render_admin():
    if st.session_state.user_role != "admin":
        st.error("Access denied.")
        return
    st.title("🛡️ Admin Panel")

    from analytics import send_reengagement_email
    data = get_analytics()
    if not data:
        st.error("Could not load analytics.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Registered", data.get("total_registered", 0))
    c2.metric("Verified",   data.get("total_verified", 0))
    c3.metric("DAU",        data.get("dau", 0))
    c4.metric("WAU",        data.get("wau", 0))
    c5.metric("MAU",        data.get("mau", 0))

    st.subheader("Inactive Users (7+ days)")
    inactive = data.get("inactive_users", [])
    if inactive:
        for uid_i, surname, other, email, last_login in inactive:
            col_u, col_btn = st.columns([4, 1])
            with col_u:
                st.markdown(f"**{surname} {other}** · {email} · last login: {last_login}")
            with col_btn:
                if st.button("Re-engage", key=f"reeng_{uid_i}"):
                    ok, msg = send_reengagement_email(email, f"{surname} {other}")
                    st.success(msg) if ok else st.error(msg)
    else:
        st.info("No inactive users.")


def render_analytics():
    if st.session_state.user_role != "admin":
        st.error("Access denied.")
        return
    st.title("📊 Analytics")
    data = get_analytics()
    if not data:
        st.error("Could not load analytics.")
        return

    st.subheader("Daily Active Users (last 14 days)")
    daily_rows = data.get("daily_rows", [])
    if daily_rows:
        df = pd.DataFrame(daily_rows, columns=["Date", "Active Users"])
        fig = px.line(df, x="Date", y="Active Users", markers=True)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No login data yet.")

    c1, c2, c3 = st.columns(3)
    c1.metric("New signups (30d)", data.get("new_signups_30d", 0))
    c2.metric("Signups today",     data.get("signups_today", 0))
    c3.metric("MAU",               data.get("mau", 0))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTING
# ══════════════════════════════════════════════════════════════════════════════
if current_page == "Admin Panel":
    render_admin()
elif current_page == "Analytics":
    render_analytics()
elif current_page == "Dashboard":
    render_dashboard()
elif current_page == "Income":
    render_income()
elif current_page == "Expenses":
    render_expenses()
elif current_page == "Banks":
    render_banks()
elif current_page == "Transfers":
    render_transfers()
elif current_page == "Savings Goals":
    render_goals()
elif current_page == "Tracker":
    render_tracker()
elif current_page == "Summaries":
    render_summaries()
elif current_page == "Notifications":
    render_notifications()
elif current_page == "Import CSV":
    render_import_csv()
elif current_page == "Settings":
    render_settings()
