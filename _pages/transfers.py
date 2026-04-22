# transfers.py
import re
import streamlit as st
from datetime import datetime
import psycopg2.extras

from db import _get_pool


def _do_transfer(user_id, from_id, to_id, from_name, to_name, amount):
    """
    Execute the transfer entirely in raw psycopg2 — no context managers,
    no Streamlit calls inside. Returns (True, None) on success or
    (False, error_message) on failure. Commit happens here before returning.
    """
    conn = None
    try:
        conn = _get_pool().getconn()
        conn.autocommit = False
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        today = datetime.now().date()

        # Check balance
        cur.execute(
            "SELECT balance FROM banks WHERE id = %s AND user_id = %s",
            (from_id, user_id)
        )
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return False, "Source bank not found."
        balance = int(row["balance"])
        if amount > balance:
            conn.rollback()
            return False, f"Insufficient funds. {from_name} has ₦{balance:,} but you tried to transfer ₦{amount:,}."

        # Debit source
        cur.execute(
            "UPDATE banks SET balance = balance - %s WHERE id = %s AND user_id = %s",
            (amount, from_id, user_id)
        )
        # Credit destination
        cur.execute(
            "UPDATE banks SET balance = balance + %s WHERE id = %s AND user_id = %s",
            (amount, to_id, user_id)
        )
        # Log debit
        cur.execute(
            "INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s,'debit',%s,%s,%s)",
            (from_id, amount, f"Transfer to {to_name}", today)
        )
        # Log credit
        cur.execute(
            "INSERT INTO transactions (bank_id, type, amount, description, created_at) VALUES (%s,'credit',%s,%s,%s)",
            (to_id, amount, f"Transfer from {from_name}", today)
        )

        conn.commit()   # ← committed here, nothing can undo it after this line
        cur.close()
        return True, None

    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return False, str(e)[:200]

    finally:
        if conn:
            try:
                conn.autocommit = True
                _get_pool().putconn(conn, close=False)
            except Exception:
                pass


def render_transfers(user_id):
    st.title("🔄 Transfers")

    from db import get_db
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

        # Show result from previous submission if any
        if st.session_state.get("_transfer_success"):
            st.success(st.session_state.pop("_transfer_success"))
        if st.session_state.get("_transfer_error"):
            st.error(st.session_state.pop("_transfer_error"))

        with st.form("transfer_form"):
            from_key = st.selectbox("From Bank", opts, key="from_bank_sel")
            to_key   = st.selectbox("To Bank",   opts, key="to_bank_sel")
            amount   = st.number_input("Amount (NGN)", min_value=1, step=500)
            st.text_input("Note (optional)", placeholder="e.g. Move for savings")
            submitted = st.form_submit_button("Transfer Now", use_container_width=True, type="primary")

        if submitted:
            if from_key == to_key:
                st.warning("Please select two different banks.")
            else:
                from_b = bank_map[from_key]
                to_b   = bank_map[to_key]

                ok, err = _do_transfer(
                    user_id,
                    from_b["id"], to_b["id"],
                    from_b["bank_name"], to_b["bank_name"],
                    int(amount)
                )

                if ok:
                    # Store success message in session_state then rerun —
                    # rerun fires AFTER this block, session_state survives it
                    st.session_state["_transfer_success"] = (
                        f"✅ ₦{int(amount):,} transferred from "
                        f"{from_b['bank_name']} to {to_b['bank_name']}."
                    )
                    st.rerun()
                else:
                    st.error(err)

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
