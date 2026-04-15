# app.py — entry point: config, cookies, session restore, routing
# -*- coding: utf-8 -*-
import streamlit as st

# ── MUST be the very first Streamlit call ─────────────────────────────────────
st.set_page_config(
    page_title="Budget Right",
    page_icon="\U0001f4b0",
    layout="wide",
    # Disable Streamlit's built-in multipage navigation entirely
    initial_sidebar_state="expanded",
)

# ── Hide Streamlit's auto-generated multipage nav (belt + suspenders) ─────────
st.markdown("""
<style>
/* Hide any auto-generated multipage nav Streamlit adds above the sidebar */
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
from styles    import inject_styles
from models    import create_tables
from auth      import (
    validate_session_token, revoke_session_token,
    get_onboarding_status, mark_onboarding_complete,
)
from db        import get_db
from retention import run_retention_engine, get_unread_count, get_streak
from utils     import save_expense
from datetime  import datetime

inject_styles()

# ── create_tables only once per process, not on every page load ───────────────
# Streamlit re-runs app.py on every interaction, so we gate this with
# session_state to avoid 30 SQL statements per click.
if "tables_created" not in st.session_state:
    create_tables()
    st.session_state["tables_created"] = True

# ── Session state defaults ────────────────────────────────────────────────────
_DEFAULTS = {
    "user_id":                   None,
    "user_role":                 None,
    "session_token":             None,
    "show_forgot_password":      False,
    "show_reset_form":           False,
    "reset_email":               "",
    "edit_exp_id":               None,
    "edit_bank_id":              None,
    "edit_income_id":            None,
    "selected_goal":             None,
    "show_goal_contribution":    False,
    "goal_preset":               "",
    "goal_preset_name":          "",
    "onboarding_step":           1,
    "quick_add_name":            "",
    "quick_add_amt":             0,
    "confirm_delete":            {},
    "income_search":             "",
    "income_filter_bank":        "All",
    "income_filter_date_from":   None,
    "income_filter_date_to":     None,
    "income_sort":               "Newest First",
    "exp_search":                "",
    "exp_filter_bank":           "All",
    "exp_filter_category":       "All",
    "exp_filter_date_from":      None,
    "exp_filter_date_to":        None,
    "exp_sort":                  "Newest First",
    # Retention cache — refreshed once per calendar day
    "_streak_cache":             None,
    "_unread_cache":             None,
    "_retention_date":           None,
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
    from _pages.landing import render_landing
    render_landing(cookies)
    st.stop()

# ── Logged in ─────────────────────────────────────────────────────────────────
user_id = st.session_state.user_id

with get_db() as (conn, cursor):
    cursor.execute("SELECT surname, other_names, role FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
st.session_state.user_role = user["role"]

# ── Retention engine + sidebar data — ONE DB round-trip, cached per day ───────
_today_str = datetime.now().date().isoformat()
if st.session_state._retention_date != _today_str:
    # Run the engine (idempotent within the day) and refresh cached values
    try:
        run_retention_engine(user_id)
    except Exception:
        pass
    st.session_state._streak_cache    = get_streak(user_id)
    st.session_state._unread_cache    = get_unread_count(user_id)
    st.session_state._retention_date  = _today_str

_streak_data  = st.session_state._streak_cache  or {"current": 0, "longest": 0}
_unread       = st.session_state._unread_cache  or 0
_streak_curr  = _streak_data["current"]
_streak_emoji = (
    "\U0001f451" if _streak_curr >= 30 else
    "\U0001f31f" if _streak_curr >= 14 else
    "\U0001f3c6" if _streak_curr >= 7  else
    "\U0001f525" if _streak_curr >= 3  else
    "\U0001f4ca"
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### Hello, {user['surname']} {user['other_names']}")

    # Streak + unread badge
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
        f'<span style="color:#a8d8c8;font-size:0.8rem;">&#x1F514;{_unread_badge}</span>'
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

# ── Onboarding checklist (shown on all pages until complete) ──────────────────
_ob = get_onboarding_status(user_id)
if not _ob["already_done"]:
    if _ob["all_done"]:
        mark_onboarding_complete(user_id)
    else:
        steps_done = sum([_ob["has_bank"], _ob["has_income"],
                          _ob["has_expense"], _ob["has_budget"]])
        st.markdown("""
        <style>
        .ob-step { display:flex; align-items:center; gap:10px; background:#f0f7f4;
            border-radius:8px; padding:10px 14px; margin-bottom:6px; font-size:0.92rem; }
        .ob-done { border-left:4px solid #0e7c5b; color:#2c7a5a; }
        .ob-todo { border-left:4px solid #d0d0d0; color:#555; }
        .ob-icon { font-size:1.2rem; }
        </style>""", unsafe_allow_html=True)

        with st.expander(f"&#x1F680; Setup checklist — {steps_done}/4 done", expanded=(steps_done == 0)):
            st.progress(steps_done / 4, text=f"{steps_done * 25}% set up")

            done1 = _ob["has_bank"]
            st.markdown(
                f'<div class="ob-step {"ob-done" if done1 else "ob-todo"}">'
                f'<span class="ob-icon">{"&#x2705;" if done1 else "&#x1F3E6;"}</span>'
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
                f'<span class="ob-icon">{"&#x2705;" if done2 else "&#x1F4B0;"}</span>'
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
                f'<span class="ob-icon">{"&#x2705;" if done3 else "&#x1F9FE;"}</span>'
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
                f'<span class="ob-icon">{"&#x2705;" if done4 else "&#x1F4CA;"}</span>'
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

# ── Page routing ──────────────────────────────────────────────────────────────
if current_page == "Admin Panel":
    from _pages.admin import render_admin
    render_admin(user_id)

elif current_page == "Analytics":
    from _pages.admin import render_analytics
    render_analytics(user_id)

elif current_page == "Dashboard":
    from _pages.dashboard import render_dashboard
    render_dashboard(user_id, pages)

elif current_page == "Income":
    from _pages.income import render_income
    render_income(user_id)

elif current_page == "Expenses":
    from _pages.expenses import render_expenses
    render_expenses(user_id, pages)

elif current_page == "Banks":
    from _pages.banks import render_banks
    render_banks(user_id)

elif current_page == "Transfers":
    from _pages.transfers import render_transfers
    render_transfers(user_id)

elif current_page == "Savings Goals":
    from _pages.goals import render_goals
    render_goals(user_id, pages)

elif current_page == "Tracker":
    from _pages.tracker import render_tracker
    render_tracker(user_id)

elif current_page == "Summaries":
    from _pages.summaries import render_summaries
    render_summaries(user_id)

elif current_page == "Notifications":
    from _pages.notifications import render_notifications
    render_notifications(user_id)

elif current_page == "Import CSV":
    from _pages.import_csv import render_import_csv
    render_import_csv(user_id, pages)

elif current_page == "Settings":
    from _pages.settings import render_settings
    render_settings(user_id)
