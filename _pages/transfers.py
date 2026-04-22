# transfers.py — transfers page
import re
import streamlit as st
from datetime import datetime

from db import get_db


def render_transfers(user_id):
    st.title("🔄 Transfers")

    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s ORDER BY bank_name",
            (user_id,)
        )
        banks = cursor.fetchall()

    if len(banks) >= 2:
        bank_map = {
            f"{b['bank_name']} (****{b['account_number']}) — ₦{b['balance']:,}": b
            for b in banks
        }
        opts = list(bank_map.keys())

        with st.form("transfer_form_pg"):
            from_key        = st.selectbox("From Bank", opts, key="from_bank_f")
            to_key          = st.selectbox("To Bank",   opts, key="to_bank_f")
            transfer_amount = st.number_input("Amount (NGN)", min_value=1, step=500)
            st.text_input("Note (optional)", placeholder="e.g. Move for savings")
            submitted = st.form_submit_button("Transfer Now", use_container_width=True, type="primary")

        if submitted:
            if from_key == to_key:
                st.warning("Please select two different banks.")
            else:
                from_b    = bank_map[from_key]
                to_b      = bank_map[to_key]
                from_id   = from_b["id"]
                to_id     = to_b["id"]
                from_name = from_b["bank_name"]
                to_name   = to_b["bank_name"]
                today     = datetime.now().date()

                # ── Execute transfer, capture result BEFORE st calls ──────────
                transfer_ok    = False
                error_msg      = None
                current_bal    = None

                try:
                    conn = None
                    from db import get_connection, _return_connection
                    conn   = get_connection()
                    cursor = conn.cursor()

                    # Atomic debit with built-in balance guard
                    cursor.execute("""
                        UPDATE banks
                           SET balance = balance - %s
                         WHERE id = %s AND user_id = %s AND balance >= %s
                     RETURNING balance
                    """, (transfer_amount, from_id, user_id, transfer_amount))
                    row = cursor.fetchone()

                    if row is None:
                        # Insufficient funds — read current balance for message
                        cursor.execute(
                            "SELECT balance FROM banks WHERE id=%s AND user_id=%s",
                            (from_id, user_id)
                        )
                        bal_row     = cursor.fetchone()
                        current_bal = int(bal_row["balance"]) if bal_row else 0
                        conn.rollback()
                    else:
                        # Credit destination
                        cursor.execute(
                            "UPDATE banks SET balance = balance + %s WHERE id=%s AND user_id=%s",
                            (transfer_amount, to_id, user_id)
                        )
                        # Log debit side
                        cursor.execute(
                            "INSERT INTO transactions (bank_id, type, amount, description, created_at) "
                            "VALUES (%s,'debit',%s,%s,%s)",
                            (from_id, transfer_amount, f"Transfer to {to_name}", today)
                        )
                        # Log credit side
                        cursor.execute(
                            "INSERT INTO transactions (bank_id, type, amount, description, created_at) "
                            "VALUES (%s,'credit',%s,%s,%s)",
                            (to_id, transfer_amount, f"Transfer from {from_name}", today)
                        )
                        conn.commit()
                        transfer_ok = True

                    cursor.close()
                    _return_connection(conn, error=False)

                except Exception as e:
                    if conn:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        try:
                            _return_connection(conn, error=True)
                        except Exception:
                            pass
                    err = str(e)
                    if "QueryCanceled" in err or "timeout" in err.lower():
                        error_msg = "Connection timed out — please try again."
                    elif "could not serialize" in err.lower():
                        error_msg = "Transfer conflict — please try again."
                    else:
                        error_msg = f"Transfer failed: {err[:150]}"

                # ── Show result AFTER db work is fully done ───────────────────
                if transfer_ok:
                    st.success(f"✅ ₦{transfer_amount:,} transferred from {from_name} to {to_name}.")
                    st.rerun()
                elif current_bal is not None:
                    st.error(
                        f"Insufficient funds. {from_name} has ₦{current_bal:,} "
                        f"but you tried to transfer ₦{transfer_amount:,}."
                    )
                elif error_msg:
                    st.error(error_msg)

        # ── Transfer History ──────────────────────────────────────────────────
        st.divider()
        st.subheader("Transfer History")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT t.created_at, t.description, t.amount, t.type,
                       b.bank_name, b.account_number
                FROM transactions t
                JOIN banks b ON t.bank_id = b.id
                WHERE b.user_id = %s
                  AND (   t.description LIKE 'Transfer to %%'
                       OR t.description LIKE 'Transfer from %%'
                       OR t.description LIKE 'Transfer to bank %%'
                       OR t.description LIKE 'Transfer from bank %%')
                ORDER BY t.created_at DESC
                LIMIT 50
            """, (user_id,))
            history = cursor.fetchall()

        if history:
            for tx in history:
                color      = "#0e7c5b" if tx["type"] == "credit" else "#c0392b"
                prefix     = "+" if tx["type"] == "credit" else "-"
                desc       = re.sub(r"Transfer to bank \d+",   "Transfer to another account",   tx["description"])
                desc       = re.sub(r"Transfer from bank \d+", "Transfer from another account", desc)
                amount_fmt = "{:,}".format(tx["amount"])
                st.markdown(
                    '<div class="exp-card" style="border-left-color:' + color + ';">'
                    '<div class="exp-card-left">'
                    '<div class="exp-card-name">' + desc + '</div>'
                    '<div class="exp-card-bank">' + str(tx["bank_name"]) + ' (****' + str(tx["account_number"]) + ')</div>'
                    '<div class="exp-card-date">' + str(tx["created_at"]) + '</div>'
                    '</div>'
                    '<div class="exp-card-right">'
                    '<div class="exp-card-amount" style="color:' + color + ';">' + prefix + '₦' + amount_fmt + '</div>'
                    '</div></div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No transfers recorded yet.")

    else:
        st.markdown(
            '<div style="background:#f4f7f6;border-radius:10px;padding:20px 22px;text-align:center;color:#6b7f8e;">'
            '<div style="font-size:2rem;">&#x1F4B8;</div>'
            '<div style="font-weight:700;margin:6px 0 4px;color:#1a2e3b;">You need at least two bank accounts to transfer</div>'
            '<div style="font-size:0.92rem;">Add a second account on the <strong>Banks</strong> page, then come back here.</div>'
            '</div>',
            unsafe_allow_html=True
        )

# ================= PAGE: SAVINGS GOALS =================
