from styles import render_page_header
# settings.py — Settings page
import streamlit as st
from db import get_db
from utils import BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password


def render_settings(user_id):
    render_page_header()
    st.title("⚙️ Settings")

    # ── Single preflight query — load everything the page needs at once ───────
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT monthly_spending_limit, allow_overdraft FROM users WHERE id=%s",
            (user_id,)
        )
        row           = cursor.fetchone()
        current_limit = int(row["monthly_spending_limit"] or 0)
        current_od    = bool(row["allow_overdraft"])

        cursor.execute(
            "SELECT category, monthly_limit FROM category_budgets "
            "WHERE user_id=%s ORDER BY category",
            (user_id,)
        )
        existing_budgets = {r["category"]: int(r["monthly_limit"]) for r in cursor.fetchall()}

    tab_budget, tab_cats, tab_security = st.tabs(["💰 Budget", "📊 Category Budgets", "🔒 Security"])

    with tab_budget:
        # ── Monthly Spending Budget ───────────────────────────────────────────
        st.subheader("Monthly Spending Budget")
        st.caption(
            "Set a limit on how much you want to spend each month. "
            "Budget Right will alert you at 50%, 80%, and 100% of your limit on the Dashboard."
        )
        new_limit = st.number_input(
            "Monthly Budget (NGN) — set to 0 to disable alerts",
            min_value=0, value=current_limit, step=5000, key="monthly_limit"
        )
        if st.button("Update Budget", key="update_limit_btn", use_container_width=True):
            with get_db() as (conn, cursor):
                cursor.execute(
                    "UPDATE users SET monthly_spending_limit=%s WHERE id=%s",
                    (new_limit, user_id)
                )
            st.success("Monthly budget updated.")
            st.rerun()

        st.divider()

        # ── Bank Overdraft ────────────────────────────────────────────────────
        st.subheader("Bank Overdraft")
        st.caption(
            "By default Budget Right blocks any expense that would take your bank balance below zero. "
            "Enable this if you use a credit facility or want to allow overdraft spending."
        )
        new_od = st.toggle(
            "Allow overdraft (let balance go below zero)",
            value=current_od, key="overdraft_toggle"
        )
        if new_od != current_od:
            with get_db() as (conn, cursor):
                cursor.execute(
                    "UPDATE users SET allow_overdraft=%s WHERE id=%s",
                    (1 if new_od else 0, user_id)
                )
            if new_od:
                st.warning("Overdraft enabled. Expenses can now take your balance below zero.")
            else:
                st.success("Overdraft disabled. Expenses that exceed your balance will be blocked.")
            st.rerun()

    with tab_cats:
        # ── Category Budgets ──────────────────────────────────────────────────
        st.subheader("Category Budgets")
    st.caption(
        "Set a monthly spending limit for each category. "
        "Budget Right shows your remaining amount and progress on the Dashboard."
    )

    all_cats = sorted(set(BUDGET_CATEGORIES) | set(existing_budgets.keys()))

    st.markdown("""
    <style>
    .cb-settings-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
                        gap:10px; margin-bottom:14px; }
    @media(max-width:640px) { .cb-settings-grid { grid-template-columns:1fr !important; } }
    </style>
    """, unsafe_allow_html=True)

    with st.form("category_budgets_form"):
        st.markdown("Set to **0** to remove a category budget.")
        new_limits = {}
        cols_per_row = 2
        for i in range(0, len(all_cats), cols_per_row):
            chunk = all_cats[i:i + cols_per_row]
            grid  = st.columns(len(chunk))
            for col, cat in zip(grid, chunk):
                with col:
                    new_limits[cat] = st.number_input(
                        cat, min_value=0,
                        value=existing_budgets.get(cat, 0),
                        step=1000, key=f"cb_{cat}"
                    )

        st.markdown("---")
        cc1, cc2 = st.columns([2, 1])
        with cc1:
            custom_cat = st.text_input("Add custom category (optional)",
                                       placeholder="e.g. Wedding, Business Travel…")
        with cc2:
            custom_amt = st.number_input("Budget (NGN)", min_value=0, step=1000, value=0,
                                         key="cb_custom_amt")
        save_btn = st.form_submit_button("Save Category Budgets",
                                         use_container_width=True, type="primary")

    if save_btn:
        saved = removed = 0
        for cat, limit in new_limits.items():
            if limit != existing_budgets.get(cat, 0):
                upsert_category_budget(user_id, cat, int(limit))
                saved   += (1 if limit > 0 else 0)
                removed += (1 if limit == 0 and existing_budgets.get(cat, 0) > 0 else 0)
        if custom_cat.strip() and custom_amt > 0:
            upsert_category_budget(user_id, custom_cat.strip(), int(custom_amt))
            saved += 1
        if saved or removed:
            parts = []
            if saved:   parts.append(f"{saved} saved")
            if removed: parts.append(f"{removed} removed")
            st.success(f"Category budgets updated — {', '.join(parts)}.")
            st.rerun()
        else:
            st.info("No changes to save.")

    if existing_budgets:
        with st.expander("Current category budgets", expanded=False):
            for cat, limit in sorted(existing_budgets.items()):
                st.markdown(f"**{cat}** — ₦{limit:,} / month")

    with tab_security:
        # ── Change Password ───────────────────────────────────────────────────
        st.subheader("Change Password")
        with st.form("change_pw_form_pg"):
            current_pw     = st.text_input("Current Password",    type="password")
            new_pw         = st.text_input("New Password",         type="password")
            confirm_new_pw = st.text_input("Confirm New Password", type="password")
            pw_submitted   = st.form_submit_button("Change Password", use_container_width=True)
        if pw_submitted:
            if not (current_pw and new_pw and confirm_new_pw):
                st.warning("All fields required.")
            elif new_pw != confirm_new_pw:
                st.error("New passwords do not match.")
            else:
                pw_ok, pw_msg = validate_password(new_pw)
                if not pw_ok:
                    st.error(pw_msg)
                else:
                    success, msg = change_password(user_id, current_pw, new_pw)
                    st.success(msg) if success else st.error(msg)
