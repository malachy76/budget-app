# income.py — income page
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db
from utils import save_expense, apply_income_filters, apply_expense_filters, \
    render_filter_bar_income, render_filter_bar_expenses, \
    get_category_budgets, compute_daily_safe_to_spend, BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password, get_onboarding_status, mark_onboarding_complete


def render_income(user_id):
    st.title("📈 Income")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    if not banks:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:12px;padding:24px;text-align:center;color:#6b7f8e;margin:12px 0;">
          <div style="font-size:2rem;">&#x1F4B0;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a2e3b;">Add a bank account first</div>
          <div style="font-size:0.92rem;">
            Before you can record income, Budget Right needs to know which account to credit.<br>
            Go to <strong>Banks</strong> and add your first account — it only takes 30 seconds.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Banks page", key="income_goto_banks"):
            st.session_state.nav_radio = pages.index("Banks")
            st.rerun()
        st.stop()

    # -- EDIT FORM at top --
    if st.session_state.get("edit_income_id"):
        edit_id = st.session_state.edit_income_id
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT t.id, t.description, t.amount, t.bank_id FROM transactions t
                JOIN banks b ON t.bank_id = b.id
                WHERE t.id=%s AND b.user_id=%s AND t.type='credit'
            """, (edit_id, user_id))
            inc_row = cursor.fetchone()
        if inc_row:
            display_source = inc_row["description"].replace("Income: ", "", 1)
            st.info(f"Editing: {display_source} — ₦{inc_row['amount']:,}")
            with st.form("edit_income_form"):
                new_source = st.text_input("Income Source", value=display_source)
                new_amount = st.number_input("Amount (NGN)", min_value=1, value=int(inc_row["amount"]))
                save_col, cancel_col = st.columns(2)
                save_clicked   = save_col.form_submit_button("Save Changes")
                cancel_clicked = cancel_col.form_submit_button("Cancel")
            if save_clicked:
                diff = new_amount - inc_row["amount"]
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (diff, inc_row["bank_id"]))
                    cursor.execute("UPDATE transactions SET amount=%s, description=%s WHERE id=%s",
                                   (new_amount, f"Income: {new_source}", inc_row["id"]))
                st.success("Income updated!")
                st.session_state.edit_income_id = None
                st.rerun()
            if cancel_clicked:
                st.session_state.edit_income_id = None
                st.rerun()
        else:
            st.warning("Income entry not found.")
            st.session_state.edit_income_id = None
        st.divider()

    with st.expander("➕ Add Income", expanded=False):
        if banks:
            bank_map_income = {f"{b['bank_name']} (****{b['account_number']}) — ₦{b['balance']:,}": b["id"] for b in banks}
            with st.form("add_income_form_pg"):
                income_source        = st.text_input("Income Source (e.g. Salary, Freelance, Business)")
                income_amount        = st.number_input("Amount (NGN)", min_value=1, step=500)
                selected_bank_income = st.selectbox("Deposit to Bank", list(bank_map_income.keys()))
                inc_date             = st.date_input("Date", value=datetime.now().date())
                inc_submitted        = st.form_submit_button("Add Income", use_container_width=True)
            if inc_submitted:
                if income_source and income_amount > 0:
                    bank_id = bank_map_income[selected_bank_income]
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (income_amount, bank_id))
                        cursor.execute("INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s, 'credit', %s, %s, %s)",
                                       (bank_id, income_amount, f"Income: {income_source}", inc_date))
                    st.success(f"₦{income_amount:,} income recorded!")
                    st.rerun()
                else:
                    st.warning("Please enter a source and amount.")
        else:
            st.info("You need at least one bank account to add income.")

    st.divider()
    st.subheader("Income History")
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT t.id, t.created_at, t.description, t.amount, t.bank_id, b.bank_name, b.account_number
            FROM transactions t JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id=%s AND t.type='credit' AND t.description LIKE 'Income:%%'
            ORDER BY t.created_at DESC
        """, (user_id,))
        income_data = cursor.fetchall()

    if income_data:
        render_filter_bar_income(banks)
        filtered_income = apply_income_filters(income_data)

        total_shown = sum(r["amount"] for r in filtered_income)
        if len(filtered_income) != len(income_data):
            st.caption(f"Showing {len(filtered_income)} of {len(income_data)} entries — ₦{total_shown:,} total")
        else:
            st.caption(f"{len(income_data)} entries — ₦{total_shown:,} total")

        if not filtered_income:
            st.markdown(
                '<div style="background:#f4f7f6;border-radius:10px;padding:18px;text-align:center;color:#6b7f8e;">' +
                '<div style="font-weight:700;color:#1a2e3b;">No entries match your filters</div>' +
                '<div style="font-size:0.88rem;margin-top:4px;">Try clearing the search or adjusting the date range.</div></div>',
                unsafe_allow_html=True
            )
        else:
            for inc in filtered_income:
                source = inc["description"].replace("Income: ", "", 1)
                card_col, edit_col, del_col = st.columns([5, 0.5, 0.5])
                with card_col:
                    st.markdown(f"""
                    <div class="exp-card" style="border-left-color:#0e7c5b;">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{source}</div>
                        <div class="exp-card-bank">Bank: {inc['bank_name']} (****{inc['account_number']})</div>
                        <div class="exp-card-date">Date: {inc['created_at']}</div>
                      </div>
                      <div class="exp-card-right">
                        <div class="exp-card-amount" style="color:#0e7c5b;">+₦{inc['amount']:,}</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with edit_col:
                    if st.button("✏️", key=f"edit_inc_{inc['id']}", help="Edit income"):
                        st.session_state.edit_income_id = inc["id"]
                        st.rerun()
                with del_col:
                    del_key = f"inc_{inc['id']}"
                    if st.session_state.confirm_delete.get(del_key):
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✓", key=f"confirm_yes_inc_{inc['id']}", help="Confirm delete", type="primary"):
                                with get_db() as (conn, cursor):
                                    cursor.execute("UPDATE banks SET balance = balance - %s WHERE id=%s", (inc["amount"], inc["bank_id"]))
                                    cursor.execute("DELETE FROM transactions WHERE id=%s", (inc["id"],))
                                st.session_state.confirm_delete.pop(del_key, None)
                                st.toast(f"Deleted — ₦{inc['amount']:,} reversed from {inc['bank_name']}", icon="🗑️")
                                st.rerun()
                        with c2:
                            if st.button("✗", key=f"confirm_no_inc_{inc['id']}", help="Cancel"):
                                st.session_state.confirm_delete.pop(del_key, None)
                                st.rerun()
                    else:
                        if st.button("🗑️", key=f"delete_inc_{inc['id']}", help=f"Delete '{source}'"):
                            st.session_state.confirm_delete[del_key] = True
                            st.rerun()
    else:
        st.markdown(
            '<div style="background:#f4f7f6;border-radius:12px;padding:28px;text-align:center;color:#6b7f8e;">' +
            '<div style="font-size:2.5rem;">💰</div>' +
            '<div style="font-weight:700;color:#1a2e3b;font-size:1rem;margin:8px 0 4px;">No income recorded yet</div>' +
            '<div style="font-size:0.9rem;">Add your salary, freelance pay, or any money that came in using the form above.</div></div>',
            unsafe_allow_html=True
        )

# ================= PAGE: EXPENSES =================
