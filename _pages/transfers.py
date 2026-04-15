# transfers.py — transfers page
import re
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db
from utils import save_expense, apply_income_filters, apply_expense_filters, \
    render_filter_bar_income, render_filter_bar_expenses, \
    get_category_budgets, compute_daily_safe_to_spend, BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password, get_onboarding_status, mark_onboarding_complete


def render_transfers(user_id):
    st.markdown("## Transfer Between Banks")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    if len(banks) >= 2:
        bank_map_transfer = {f"{b['bank_name']} (****{b['account_number']}) - NGN {b['balance']:,}": b for b in banks}
        from_bank       = st.selectbox("From Bank", list(bank_map_transfer.keys()), key="from_bank")
        to_bank         = st.selectbox("To Bank",   list(bank_map_transfer.keys()), key="to_bank")
        transfer_amount = st.number_input("Amount to Transfer (NGN)", min_value=1, key="transfer_amt")
        if st.button("Transfer", key="transfer_btn"):
            if from_bank == to_bank:
                st.warning("Cannot transfer to the same bank")
            else:
                from_b    = bank_map_transfer[from_bank]
                to_b      = bank_map_transfer[to_bank]
                from_id   = from_b["id"]
                to_id     = to_b["id"]
                from_name = from_b["bank_name"]
                to_name   = to_b["bank_name"]
                with get_db() as (conn, cursor):
                    cursor.execute("SELECT balance FROM banks WHERE id=%s", (from_id,))
                    from_balance = cursor.fetchone()["balance"]
                    if transfer_amount > from_balance:
                        st.error(f"Insufficient funds. {from_name} only has NGN {from_balance:,}.")
                    else:
                        today = datetime.now().date()
                        cursor.execute("UPDATE banks SET balance = balance - %s WHERE id=%s", (transfer_amount, from_id))
                        cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (transfer_amount, to_id))
                        cursor.execute(
                            "INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s, 'debit', %s, %s, %s)",
                            (from_id, transfer_amount, f"Transfer to {to_name}", today)
                        )
                        cursor.execute(
                            "INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s, 'credit', %s, %s, %s)",
                            (to_id, transfer_amount, f"Transfer from {from_name}", today)
                        )
                        st.success(f"Transferred NGN {transfer_amount:,} from {from_name} to {to_name} ✓")
                        st.rerun()

        # ── Transfer History ──────────────────────────────────────────────────
        st.divider()
        st.subheader("Transfer History")
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT t.id, t.created_at, t.description, t.amount, t.type,
                       b.bank_name, b.account_number
                FROM transactions t JOIN banks b ON t.bank_id = b.id
                WHERE b.user_id = %s
                  AND (t.description LIKE 'Transfer to %%' OR t.description LIKE 'Transfer from %%'
                       OR t.description LIKE 'Transfer to bank %%' OR t.description LIKE 'Transfer from bank %%')
                ORDER BY t.created_at DESC
                LIMIT 50
            """, (user_id,))
            transfer_history = cursor.fetchall()

        if transfer_history:
            for tx in transfer_history:
                color  = "#0e7c5b" if tx["type"] == "credit" else "#c0392b"
                prefix = "+" if tx["type"] == "credit" else "-"
                # Humanise legacy "Transfer to bank 12" descriptions
                desc = tx["description"]
                desc = re.sub(r"Transfer to bank \d+", "Transfer to another account", desc)
                desc = re.sub(r"Transfer from bank \d+", "Transfer from another account", desc)
                st.markdown(f"""
                <div class="exp-card" style="border-left-color:{color};">
                  <div class="exp-card-left">
                    <div class="exp-card-name">{desc}</div>
                    <div class="exp-card-bank">Account: {tx['bank_name']} (****{tx['account_number']})</div>
                    <div class="exp-card-date">Date: {tx['created_at']}</div>
                  </div>
                  <div class="exp-card-right">
                    <div class="exp-card-amount" style="color:{color};">{prefix}NGN {tx['amount']:,.0f}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No transfers recorded yet.")
    else:
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:10px;padding:20px 22px;text-align:center;color:#4a6070;">
          <div style="font-size:2rem;">&#x1F4B8;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a3c5e;">You need at least two bank accounts to transfer</div>
          <div style="font-size:0.92rem;">Add a second account on the <strong>Banks</strong> page, then come back here to move money between them.</div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: SAVINGS GOALS =================
