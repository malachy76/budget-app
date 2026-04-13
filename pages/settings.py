# settings.py — settings page
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db
from utils import save_expense, apply_income_filters, apply_expense_filters, \
    render_filter_bar_income, render_filter_bar_expenses, \
    get_category_budgets, compute_daily_safe_to_spend, BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password, get_onboarding_status, mark_onboarding_complete


def render_settings(user_id):
    st.markdown("## Settings")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT monthly_spending_limit, allow_overdraft FROM users WHERE id=%s", (user_id,))
        settings_row  = cursor.fetchone()
        current_limit = settings_row["monthly_spending_limit"] or 0
        current_od    = bool(settings_row["allow_overdraft"])

    # ── Monthly spending budget ───────────────────────────────────────────────
    st.subheader("Monthly Spending Budget")
    st.caption(
        "Set a limit on how much you want to spend each month. "
        "Budget Right will alert you on the Dashboard at 50%, 80%, and 100% of your limit."
    )
    new_limit = st.number_input("Monthly Budget (NGN) — set to 0 to disable alerts", min_value=0, value=current_limit, step=5000, key="monthly_limit")
    if st.button("Update Budget", key="update_limit_btn"):
        with get_db() as (conn, cursor):
            cursor.execute("UPDATE users SET monthly_spending_limit=%s WHERE id=%s", (new_limit, user_id))
        st.success("Monthly budget updated. Alerts will show on your Dashboard.")
        st.rerun()

    st.divider()

    # ── Category Budgets ──────────────────────────────────────────────────────
    st.subheader("Category Budgets")
    st.caption(
        "Set a monthly spending limit for individual categories. "
        "Budget Right will track your spending against each limit and show "
        "your remaining amount and daily safe-to-spend on the Dashboard."
    )

    # Preset categories + any custom ones the user already has
    PRESET_CATEGORIES = [
        "Foodstuff", "Food & Eating Out", "Transport", "Airtime/Data", "Fuel",
        "Rent", "Electricity (NEPA)", "Internet", "Family Support", "School Fees",
        "Hospital/Drugs", "Church/Mosque Giving", "Business Stock", "POS Charges",
        "Transfer Fees", "Subscription", "Hair/Beauty", "Clothing",
        "Generator/Fuel", "Water", "Betting", "Savings Deposit", "Other",
    ]

    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT category, monthly_limit FROM category_budgets WHERE user_id=%s ORDER BY category",
            (user_id,)
        )
        existing_budgets = {r["category"]: int(r["monthly_limit"]) for r in cursor.fetchall()}

    # Merge preset + existing custom categories
    all_budget_cats = sorted(set(PRESET_CATEGORIES) | set(existing_budgets.keys()))

    st.markdown("Set limit to **0** to disable tracking for that category.")

    # Render in a form so all saves happen in one click
    with st.form("category_budget_form"):
        updated_budgets = {}
        cols_per_row = 2
        cat_rows = [all_budget_cats[i:i+cols_per_row] for i in range(0, len(all_budget_cats), cols_per_row)]
        for cat_row in cat_rows:
            form_cols = st.columns(cols_per_row)
            for ci, cat in enumerate(cat_row):
                with form_cols[ci]:
                    current_val = existing_budgets.get(cat, 0)
                    new_val = st.number_input(
                        cat,
                        min_value=0,
                        value=current_val,
                        step=5000,
                        key=f"catbudget_{cat}",
                        help=f"Monthly limit for {cat} (NGN). Set to 0 to disable."
                    )
                    updated_budgets[cat] = new_val

        save_cat_budgets = st.form_submit_button("Save Category Budgets", use_container_width=True)

    if save_cat_budgets:
        with get_db() as (conn, cursor):
            for cat, limit in updated_budgets.items():
                if limit > 0:
                    cursor.execute("""
                        INSERT INTO category_budgets (user_id, category, monthly_limit)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id, category)
                        DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit
                    """, (user_id, cat, int(limit)))
                else:
                    # Remove the row if limit set to 0 — no point tracking zeroes
                    cursor.execute(
                        "DELETE FROM category_budgets WHERE user_id=%s AND category=%s",
                        (user_id, cat)
                    )
        st.success("Category budgets saved! Check your Dashboard to see progress.")
        st.rerun()

    st.divider()

    # ── Overdraft setting ─────────────────────────────────────────────────────
    st.subheader("Bank Overdraft")
    st.caption(
        "By default, Budget Right will block any expense that would take your bank balance below zero. "
        "Enable overdraft below if you want to allow spending beyond your balance — for example if you use a credit facility."
    )
    new_od = st.toggle(
        "Allow overdraft (let balance go below zero)",
        value=current_od,
        key="overdraft_toggle"
    )
    if new_od != current_od:
        with get_db() as (conn, cursor):
            cursor.execute("UPDATE users SET allow_overdraft=%s WHERE id=%s", (1 if new_od else 0, user_id))
        if new_od:
            st.warning("Overdraft enabled. Expenses can now take your balance below zero.")
        else:
            st.success("Overdraft disabled. Expenses that exceed your balance will be blocked.")
        st.rerun()

    st.divider()

    # ── Category Budgets ──────────────────────────────────────────────────────
    st.subheader("Category Budgets")
    st.caption(
        "Set a monthly spending limit for each category. "
        "Budget Right will show your remaining amount and alert you on the Dashboard "
        "when you are close to or over the limit."
    )

    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT category, monthly_limit FROM category_budgets WHERE user_id = %s ORDER BY category",
            (user_id,)
        )
        existing_cat_budgets = {r["category"]: int(r["monthly_limit"]) for r in cursor.fetchall()}

    # Show all default categories plus any custom ones already set
    all_settable = sorted(set(BUDGET_CATEGORIES) | set(existing_cat_budgets.keys()))

    st.markdown("""
    <style>
    .cb-settings-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 10px; margin-bottom: 14px;
    }
    .cb-settings-row {
        background: #f8fbf9; border: 1px solid #d0e8df;
        border-radius: 10px; padding: 10px 14px;
        display: flex; justify-content: space-between;
        align-items: center; gap: 10px;
    }
    .cb-settings-label {
        font-size: 0.88rem; font-weight: 700; color: #1a3c5e;
        flex: 1; min-width: 0; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis;
    }
    @media(max-width:640px) {
        .cb-settings-grid { grid-template-columns: 1fr !important; }
    }
    </style>
    """, unsafe_allow_html=True)

    # Use a form so all saves happen together
    with st.form("category_budgets_form"):
        st.markdown("Enter **0** to remove a category budget.", help=None)
        new_cat_limits = {}
        # Render in a 2-column grid using st.columns
        cols_per_row = 2
        cat_rows = [all_settable[i:i+cols_per_row] for i in range(0, len(all_settable), cols_per_row)]
        for cat_row in cat_rows:
            grid_cols = st.columns(len(cat_row))
            for gc, cat in zip(grid_cols, cat_row):
                with gc:
                    current_val = existing_cat_budgets.get(cat, 0)
                    new_val = st.number_input(
                        cat,
                        min_value=0,
                        value=current_val,
                        step=1000,
                        key=f"cb_{cat}",
                        help=f"Monthly budget for {cat} (NGN). Set to 0 to remove."
                    )
                    new_cat_limits[cat] = new_val

        # Allow adding a custom category not in the default list
        st.markdown("---")
        custom_cat_col, custom_amt_col = st.columns([2, 1])
        with custom_cat_col:
            custom_cat = st.text_input(
                "Add custom category (optional)",
                placeholder="e.g. Wedding, Business Travel…",
                key="cb_custom_cat"
            )
        with custom_amt_col:
            custom_amt = st.number_input(
                "Budget (NGN)",
                min_value=0, step=1000, value=0,
                key="cb_custom_amt"
            )

        save_btn = st.form_submit_button("Save Category Budgets", use_container_width=True, type="primary")

    if save_btn:
        saved_count  = 0
        removed_count = 0
        for cat, limit in new_cat_limits.items():
            old_val = existing_cat_budgets.get(cat, 0)
            if limit != old_val:
                upsert_category_budget(user_id, cat, int(limit))
                saved_count  += 1 if limit > 0 else 0
                removed_count += 1 if limit == 0 and old_val > 0 else 0

        # Custom category
        if custom_cat.strip() and custom_amt > 0:
            upsert_category_budget(user_id, custom_cat.strip(), int(custom_amt))
            saved_count += 1

        if saved_count > 0 or removed_count > 0:
            parts = []
            if saved_count:
                parts.append(f"{saved_count} budget{'s' if saved_count != 1 else ''} saved")
            if removed_count:
                parts.append(f"{removed_count} removed")
            st.success(f"Category budgets updated — {', '.join(parts)}.")
            st.rerun()
        else:
            st.info("No changes to save.")

    # Show current summary if any budgets exist
    if existing_cat_budgets:
        with st.expander("Current category budgets", expanded=False):
            for cat, limit in sorted(existing_cat_budgets.items()):
                st.markdown(
                    f"**{cat}** — NGN {limit:,} / month"
                )

    st.divider()
    st.subheader("Change Password")
    current_pw     = st.text_input("Current Password",    type="password", key="current_pw")
    new_pw         = st.text_input("New Password",         type="password", key="new_pw")
    confirm_new_pw = st.text_input("Confirm New Password", type="password", key="confirm_new_pw")
    if st.button("Change Password", key="change_pw_btn"):
        if current_pw and new_pw and confirm_new_pw:
            if new_pw != confirm_new_pw:
                st.error("New passwords do not match.")
            else:
                pw_ok, pw_msg = validate_password(new_pw)
                if not pw_ok:
                    st.error(pw_msg)
                else:
                    success, msg = change_password(user_id, current_pw, new_pw)
                    st.success(msg) if success else st.error(msg)
        else:
            st.warning("All fields required.")
