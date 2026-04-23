from styles import render_page_header
# banks.py — banks page
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db
from utils import save_expense, apply_income_filters, apply_expense_filters, \
    render_filter_bar_income, render_filter_bar_expenses, \
    get_category_budgets, compute_daily_safe_to_spend, BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password, get_onboarding_status, mark_onboarding_complete


def render_banks(user_id):
    render_page_header()
    st.title("🏦 Bank Accounts")

    with st.expander("➕ Add Bank Account", expanded=False):
        with st.form("add_bank_form_pg"):
            bank_name       = st.text_input("Bank Name (e.g. GTB, Kuda, Opay)")
            account_name    = st.text_input("Account Name")
            account_number  = st.text_input("Account Number (last 4 digits)")
            opening_balance = st.number_input("Opening Balance (NGN)", min_value=0)
            min_alert       = st.number_input("Alert if balance falls below (NGN)", min_value=0, value=0)
            add_submitted   = st.form_submit_button("Add Bank Account", use_container_width=True)
        if add_submitted:
            if bank_name and account_name and account_number:
                with get_db() as (conn, cursor):
                    cursor.execute("INSERT INTO banks (user_id, bank_name, account_name, account_number, balance, min_balance_alert) VALUES (%s, %s, %s, %s, %s, %s)",
                                   (user_id, bank_name, account_name, account_number[-4:], opening_balance, min_alert))
                st.success(f"Bank '{bank_name}' added!")
                st.rerun()
            else:
                st.warning("Please fill all fields.")

    st.subheader("Your Bank Accounts")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks_manage = cursor.fetchall()

    if banks_manage:
        for bank in banks_manage:
            st.markdown(
                f'<div style="background:#fff;border:1px solid #d8eae2;border-radius:12px;padding:12px 16px;'
                f'display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">'
                f'<div>'
                f'<div style="font-weight:800;font-size:0.97rem;color:#1a2e3b;">{bank["bank_name"]}</div>'
                f'<div style="font-size:0.8rem;color:#6b7f8e;margin-top:2px;">{bank["account_name"]} · ****{bank["account_number"]}</div>'
                f'</div>'
                f'<div style="font-size:1.25rem;font-weight:800;color:#0e7c5b;">₦{int(bank["balance"]):,}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                pass  # card rendered above
            with col2:
                if st.button("✏️", key=f"edit_bank_{bank['id']}", help="Edit bank"):
                    st.session_state.edit_bank_id = bank["id"]
            with col3:
                del_key = f"bank_{bank['id']}"
                if st.session_state.confirm_delete.get(del_key):
                    st.error(f"Delete {bank['bank_name']}? This will permanently erase all its transactions and expenses.")
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("Yes, delete all", key=f"confirm_yes_bank_{bank['id']}"):
                            with get_db() as (conn, cursor):
                                cursor.execute("UPDATE expenses SET tx_id=NULL WHERE bank_id=%s", (bank["id"],))
                                cursor.execute("DELETE FROM expenses WHERE bank_id=%s", (bank["id"],))
                                cursor.execute("DELETE FROM transactions WHERE bank_id=%s", (bank["id"],))
                                cursor.execute("DELETE FROM banks WHERE id=%s", (bank["id"],))
                            st.session_state.confirm_delete.pop(del_key, None)
                            st.success("Bank and all its data deleted.")
                            st.rerun()
                    with cc2:
                        if st.button("Cancel", key=f"confirm_no_bank_{bank['id']}"):
                            st.session_state.confirm_delete.pop(del_key, None)
                            st.rerun()
                else:
                    if st.button("🗑️", key=f"delete_bank_{bank['id']}", help="Delete bank"):
                        st.session_state.confirm_delete[del_key] = True
                        st.rerun()

        if st.session_state.get("edit_bank_id"):
            edit_id = st.session_state.edit_bank_id
            with get_db() as (conn, cursor):
                cursor.execute("SELECT bank_name, account_name, account_number FROM banks WHERE id=%s", (edit_id,))
                bank = cursor.fetchone()
            if bank:
                st.markdown("### Edit Bank")
                new_name     = st.text_input("Bank Name",      value=bank["bank_name"])
                new_acc_name = st.text_input("Account Name",   value=bank["account_name"])
                new_acc_num  = st.text_input("Account Number", value=bank["account_number"])
                if st.button("Update Bank"):
                    with get_db() as (conn, cursor):
                        cursor.execute("UPDATE banks SET bank_name=%s, account_name=%s, account_number=%s WHERE id=%s",
                                       (new_name, new_acc_name, new_acc_num, edit_id))
                    st.success("Bank updated.")
                    st.session_state.edit_bank_id = None
                    st.rerun()
    else:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:10px;padding:20px 22px;text-align:center;color:#6b7f8e;margin-top:12px;">
          <div style="font-size:2rem;">&#x1F3E6;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a2e3b;">No bank accounts yet</div>
          <div style="font-size:0.92rem;">Use the form above to add your GTB, Access, Opay, or any other account.<br>
          Your ATM card number is never needed — just your bank name and last 4 digits.</div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: TRANSFERS =================
