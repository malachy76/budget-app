# app.py — entry point: page config, cookies, session restore, routing (~120 lines)
# -*- coding: utf-8 -*-
import streamlit as st
st.set_page_config(page_title="Budget Right", page_icon="\U0001f4b0", layout="wide")

from streamlit_cookies_manager import EncryptedCookieManager

cookies = EncryptedCookieManager(
    prefix="budget_right_",
    password=st.secrets["COOKIE_PASSWORD"]
)
if not cookies.ready():
    st.stop()

# ── One-time startup ──────────────────────────────────────────────────────────
from styles import inject_styles
from models import create_tables
from auth   import (
    validate_session_token, revoke_session_token,
    get_onboarding_status, mark_onboarding_complete,
)
from db import get_db

inject_styles()
create_tables()

# ── Session state defaults ────────────────────────────────────────────────────
_DEFAULTS = {
    "user_id": None, "user_role": None, "session_token": None,
    "show_forgot_password": False, "show_reset_form": False, "reset_email": "",
    "edit_exp_id": None, "edit_bank_id": None, "edit_income_id": None,
    "selected_goal": None, "show_goal_contribution": False,
    "goal_preset": "", "goal_preset_name": "", "onboarding_step": 1,
    "quick_add_name": "", "quick_add_amt": 0,
    "confirm_delete": {},
    "income_search": "", "income_filter_bank": "All",
    "income_filter_date_from": None, "income_filter_date_to": None,
    "income_sort": "Newest First",
    "exp_search": "", "exp_filter_bank": "All", "exp_filter_category": "All",
    "exp_filter_date_from": None, "exp_filter_date_to": None,
    "exp_sort": "Newest First",
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

# ── Not logged in → landing page ──────────────────────────────────────────────
if st.session_state.user_id is None:
    from pages.landing import render_landing
    render_landing(cookies)
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
        "&#x1F501; Tracker", "&#x1F4CB; Summaries",
        "&#x1F4E5; Import CSV", "&#x2699;&#xFE0F; Settings",
    ]
    pages_clean = [
        "Dashboard", "Income", "Expenses",
        "Banks", "Transfers", "Savings Goals",
        "Tracker", "Summaries",
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
                                (bk_id, int(ob_inc_amount), f"Income: {ob_inc_source}", datetime.now().date())
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
                        ok, result = save_expense(user_id, bk_id, ob_exp_name, ob_exp_amount)
                        if ok:
                            st.success("Expense logged!")
                            st.rerun()
                        else:
                            st.error(result)
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

# ── Page routing ──────────────────────────────────────────────────────────────
if current_page == "Admin Panel":
    from pages.admin import render_admin
    render_admin(user_id)

elif current_page == "Analytics":
    from pages.admin import render_analytics
    render_analytics(user_id)

elif current_page == "Dashboard":
    from pages.dashboard import render_dashboard
    render_dashboard(user_id, pages_clean)

elif current_page == "Income":
    from pages.income import render_income
    render_income(user_id)

elif current_page == "Expenses":
    from pages.expenses import render_expenses
    render_expenses(user_id, pages_clean)

elif current_page == "Banks":
    from pages.banks import render_banks
    render_banks(user_id)

elif current_page == "Transfers":
    from pages.transfers import render_transfers
    render_transfers(user_id)

elif current_page == "Savings Goals":
    from pages.goals import render_goals
    render_goals(user_id, pages_clean)

elif current_page == "Tracker":
    from pages.tracker import render_tracker
    render_tracker(user_id)

elif current_page == "Summaries":
    from pages.summaries import render_summaries
    render_summaries(user_id)

elif current_page == "Import CSV":
    from pages.import_csv import render_import_csv
    render_import_csv(user_id, pages_clean)

elif current_page == "Settings":
    from pages.settings import render_settings
    render_settings(user_id)
