# tracker.py — Tracker page
# Tabs: Recurring Income | Recurring Expenses | Bill Reminders | Debt/Loan | Emergency Fund | Savings Goals
import math
import streamlit as st
from datetime import datetime, timedelta, date

from db import get_db


FREQ_OPTIONS = ["monthly", "weekly", "daily", "yearly"]
FREQ_LABELS  = {"monthly": "Monthly", "weekly": "Weekly",
                "daily": "Daily",   "yearly": "Yearly"}
FREQ_MULT    = {"daily": 30, "weekly": 4.33, "monthly": 1, "yearly": 1/12}


def _next_due(freq):
    today = datetime.now().date()
    if freq == "daily":  return today + timedelta(days=1)
    if freq == "weekly": return today + timedelta(weeks=1)
    if freq == "yearly": return today.replace(year=today.year + 1)
    if today.month == 12:
        return today.replace(year=today.year + 1, month=1, day=1)
    return today.replace(month=today.month + 1, day=1)


def _advance_next_due(freq, current_due):
    """Return the next due date after current_due, advancing by one period."""
    if current_due is None:
        current_due = datetime.now().date()
    if isinstance(current_due, str):
        current_due = date.fromisoformat(current_due)
    if freq == "daily":
        return current_due + timedelta(days=1)
    if freq == "weekly":
        return current_due + timedelta(weeks=1)
    if freq == "yearly":
        return current_due.replace(year=current_due.year + 1)
    # monthly
    if current_due.month == 12:
        return current_due.replace(year=current_due.year + 1, month=1)
    return current_due.replace(month=current_due.month + 1)


def _due_badge(next_due, today):
    if next_due is None:
        return "No date", "#95a5a6"
    days = (next_due - today).days
    if days < 0:
        return f"Overdue {abs(days)}d", "#c0392b"
    if days == 0:
        return "Due today", "#e67e22"
    if days <= 3:
        return f"Due in {days}d", "#c0392b"
    if days <= 7:
        return f"Due in {days}d", "#f39c12"
    return f"Due in {days}d", "#1a3c5e"


# ---------------------------------------------------------------------------
# AUTO-POST ENGINE  — posts all auto_post=1 items whose next_due <= today
# Runs once per calendar day per user session to avoid duplicate posts.
# ---------------------------------------------------------------------------
def _run_auto_post(user_id):
    today = datetime.now().date()
    session_key = f"_auto_post_ran_{user_id}_{today.isoformat()}"
    if st.session_state.get(session_key):
        return
    st.session_state[session_key] = True

    try:
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.type, r.name, r.category, r.amount,
                       r.frequency, r.next_due, r.bank_id
                FROM recurring_items r
                WHERE r.user_id = %s
                  AND r.auto_post = 1
                  AND r.active = 1
                  AND r.next_due IS NOT NULL
                  AND r.next_due <= %s
            """, (user_id, today))
            due_items = cursor.fetchall()

        for item in due_items:
            item_id  = item["id"]
            bank_id  = item["bank_id"]
            amount   = int(item["amount"])
            freq     = item["frequency"]
            due_date = (item["next_due"] if isinstance(item["next_due"], date)
                        else date.fromisoformat(str(item["next_due"])))
            new_due  = _advance_next_due(freq, due_date)

            with get_db() as (conn, cursor):
                if bank_id:
                    tx_type = "credit" if item["type"] == "income" else "debit"
                    cursor.execute("""
                        INSERT INTO transactions
                            (bank_id, type, amount, description, created_at)
                        VALUES (%s, %s, %s, %s, %s) RETURNING id
                    """, (bank_id, tx_type, amount, item["name"], today))
                    tx_id = cursor.fetchone()["id"]

                    if item["type"] == "income":
                        cursor.execute(
                            "UPDATE banks SET balance = balance + %s WHERE id=%s",
                            (amount, bank_id))
                    else:
                        cursor.execute(
                            "UPDATE banks SET balance = balance - %s WHERE id=%s",
                            (amount, bank_id))

                    if item["type"] == "expense":
                        cursor.execute("""
                            INSERT INTO expenses
                                (user_id, bank_id, name, category, amount, created_at, tx_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (user_id, bank_id, item["name"],
                              item.get("category"), amount, today, tx_id))

                cursor.execute(
                    "UPDATE recurring_items SET next_due=%s WHERE id=%s AND user_id=%s",
                    (new_due, item_id, user_id)
                )
    except Exception:
        pass  # Never crash the page due to auto-post errors


# ---------------------------------------------------------------------------
# HELPER — manually post one recurring item and advance next_due
# ---------------------------------------------------------------------------
def _manual_post_item(item_id, user_id, item, today):
    bank_id = item.get("bank_id")
    amount  = int(item["amount"])
    freq    = item["frequency"]
    new_due = _advance_next_due(freq, item["next_due"])

    try:
        with get_db() as (conn, cursor):
            if bank_id:
                tx_type = "credit" if item["type"] == "income" else "debit"
                cursor.execute("""
                    INSERT INTO transactions
                        (bank_id, type, amount, description, created_at)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (bank_id, tx_type, amount, item["name"], today))
                tx_id = cursor.fetchone()["id"]

                if item["type"] == "income":
                    cursor.execute(
                        "UPDATE banks SET balance = balance + %s WHERE id=%s",
                        (amount, bank_id))
                else:
                    cursor.execute(
                        "UPDATE banks SET balance = balance - %s WHERE id=%s",
                        (amount, bank_id))

                if item["type"] == "expense":
                    cursor.execute("""
                        INSERT INTO expenses
                            (user_id, bank_id, name, category, amount, created_at, tx_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, bank_id, item["name"],
                          item.get("category"), amount, today, tx_id))

            cursor.execute(
                "UPDATE recurring_items SET next_due=%s WHERE id=%s AND user_id=%s",
                (new_due, item_id, user_id)
            )
        st.success(f"Posted '{item['name']}'. Next due: {new_due}")
    except Exception as e:
        st.error(f"Could not post item: {e}")


# ===========================================================================
# MAIN RENDER
# ===========================================================================
def render_tracker(user_id):
    st.markdown("## Tracker")
    st.caption("Recurring income & expenses, bill reminders, debts, emergency fund, and savings goals.")

    today = datetime.now().date()

    # Run auto-post engine first (idempotent within a day)
    _run_auto_post(user_id)

    # Load banks once for all tabs
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, bank_name, account_number FROM banks WHERE user_id=%s ORDER BY bank_name",
            (user_id,)
        )
        banks = cursor.fetchall()

    bank_map  = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in banks}
    bank_opts = list(bank_map.keys())

    tab_ri, tab_re, tab_bill, tab_debt, tab_ef, tab_goals = st.tabs([
        "&#x1F4B0; Recurring Income",
        "&#x1F4B8; Recurring Expenses",
        "&#x1F514; Bill Reminders",
        "&#x1F4B3; Debt / Loan",
        "&#x1F6E1; Emergency Fund",
        "&#x1F3AF; Savings Goals",
    ])

    # =========================================================================
    # TAB 1 — RECURRING INCOME
    # =========================================================================
    with tab_ri:
        st.subheader("Recurring Income")
        st.caption("Salary, freelance, rent — any money that arrives on a schedule.")

        with st.expander("Add recurring income", expanded=False):
            with st.form("add_rec_income"):
                c1, c2 = st.columns(2)
                with c1:
                    ri_name = st.text_input("Income source", placeholder="e.g. Salary, Freelance")
                    ri_freq = st.selectbox("Frequency", FREQ_OPTIONS,
                                           format_func=lambda x: FREQ_LABELS[x], key="ri_freq")
                with c2:
                    ri_amt  = st.number_input("Expected amount (NGN)", min_value=1, step=1000)
                    ri_due  = st.date_input("Next expected date", value=_next_due("monthly"))
                ri_bank = st.selectbox("Deposit to bank (optional)", ["— none —"] + bank_opts)
                ri_auto = st.checkbox("Auto-post when due")
                if st.form_submit_button("Add Recurring Income", type="primary"):
                    if ri_name and ri_amt > 0:
                        bk_id = bank_map.get(ri_bank) if ri_bank != "— none —" else None
                        with get_db() as (conn, cursor):
                            cursor.execute("""
                                INSERT INTO recurring_items
                                    (user_id, type, name, amount, frequency, next_due, bank_id, auto_post)
                                VALUES (%s,'income',%s,%s,%s,%s,%s,%s)
                            """, (user_id, ri_name, int(ri_amt), ri_freq, ri_due,
                                  bk_id, 1 if ri_auto else 0))
                        st.success(f"'{ri_name}' added.")
                        st.rerun()
                    else:
                        st.warning("Please enter a name and amount.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.amount, r.frequency, r.next_due,
                       r.auto_post, r.bank_id, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id=%s AND r.type='income'
                ORDER BY r.next_due NULLS LAST
            """, (user_id,))
            rec_incomes = cursor.fetchall()

        if not rec_incomes:
            st.info("No recurring income yet. Use the form above to add salary, freelance, or rental income.")
        else:
            total_monthly_income = sum(
                r["amount"] * FREQ_MULT.get(r["frequency"], 1) for r in rec_incomes
            )
            st.caption(f"Estimated monthly recurring income: **NGN {int(total_monthly_income):,}**")

            for ri in rec_incomes:
                due_label, due_color = _due_badge(ri["next_due"], today)
                is_due = ri["next_due"] and ri["next_due"] <= today
                col_card, col_post, col_del = st.columns([5, 1, 0.5])
                with col_card:
                    st.markdown(f"""
                    <div class="exp-card" style="border-left-color:#0e7c5b;">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{ri['name']}</div>
                        <div class="exp-card-bank">
                          {FREQ_LABELS.get(ri['frequency'], 'Monthly')}
                          {f" &rarr; {ri['bank_name']}" if ri.get('bank_name') else ""}
                          {"&nbsp;&nbsp;<em style='font-size:0.75rem;'>auto-post</em>" if ri['auto_post'] else ""}
                        </div>
                        <div class="exp-card-date" style="color:{due_color};">
                          {due_label} &mdash; {ri['next_due'] or 'No date'}
                        </div>
                      </div>
                      <div class="exp-card-right">
                        <div class="exp-card-amount" style="color:#0e7c5b;">+NGN {ri['amount']:,}</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_post:
                    if is_due:
                        if st.button("Post", key=f"ri_post_{ri['id']}", help="Post now",
                                     use_container_width=True, type="primary"):
                            _manual_post_item(ri["id"], user_id, ri, today)
                            st.rerun()
                with col_del:
                    dk = f"ri_{ri['id']}"
                    if st.session_state.confirm_delete.get(dk):
                        if st.button("Y", key=f"ri_y_{ri['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute(
                                    "DELETE FROM recurring_items WHERE id=%s AND user_id=%s",
                                    (ri["id"], user_id))
                            st.session_state.confirm_delete.pop(dk, None)
                            st.rerun()
                        if st.button("N", key=f"ri_n_{ri['id']}"):
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"ri_d_{ri['id']}", help="Delete"):
                            st.session_state.confirm_delete[dk] = True; st.rerun()

    # =========================================================================
    # TAB 2 — RECURRING EXPENSES
    # =========================================================================
    with tab_re:
        st.subheader("Recurring Expenses")
        st.caption("Rent, DSTV, school fees — any expense that repeats on a schedule.")

        EXPENSE_CATS = [
            "— select —", "Rent", "Electricity (NEPA)", "School Fees", "Internet",
            "Subscription", "Transport", "Fuel", "Generator/Fuel", "Water",
            "Airtime/Data", "Hospital/Drugs", "Family Support", "Church/Mosque Giving",
            "Business Stock", "Savings Deposit", "Other",
        ]

        with st.expander("Add recurring expense", expanded=False):
            with st.form("add_rec_expense"):
                c1, c2 = st.columns(2)
                with c1:
                    re_name = st.text_input("Expense name", placeholder="e.g. House rent, DSTV")
                    re_freq = st.selectbox("Frequency", FREQ_OPTIONS,
                                           format_func=lambda x: FREQ_LABELS[x], key="re_freq")
                with c2:
                    re_amt  = st.number_input("Expected amount (NGN)", min_value=1, step=500, key="re_amt")
                    re_due  = st.date_input("Next due date", key="re_due")
                re_cat  = st.selectbox("Category", EXPENSE_CATS)
                re_bank = st.selectbox("Pay from bank (optional)", ["— none —"] + bank_opts, key="re_bank")
                if st.form_submit_button("Add Recurring Expense", type="primary"):
                    if re_name and re_amt > 0:
                        bk_id = bank_map.get(re_bank) if re_bank != "— none —" else None
                        cat   = None if re_cat == "— select —" else re_cat
                        with get_db() as (conn, cursor):
                            cursor.execute("""
                                INSERT INTO recurring_items
                                    (user_id, type, name, category, amount, frequency, next_due, bank_id)
                                VALUES (%s,'expense',%s,%s,%s,%s,%s,%s)
                            """, (user_id, re_name, cat, int(re_amt), re_freq, re_due, bk_id))
                        st.success(f"'{re_name}' added.")
                        st.rerun()
                    else:
                        st.warning("Please enter a name and amount.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.category, r.amount, r.frequency,
                       r.next_due, r.bank_id, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id=%s AND r.type='expense'
                ORDER BY r.next_due NULLS LAST
            """, (user_id,))
            rec_expenses = cursor.fetchall()

        if not rec_expenses:
            st.info("No recurring expenses yet. Add rent, subscriptions, or regular bills above.")
        else:
            total_monthly = sum(r["amount"] * FREQ_MULT.get(r["frequency"], 1) for r in rec_expenses)
            st.caption(f"Estimated monthly recurring cost: **NGN {int(total_monthly):,}**")

            for re in rec_expenses:
                due_label, due_color = _due_badge(re["next_due"], today)
                is_due = re["next_due"] and re["next_due"] <= today
                col_card, col_post, col_del = st.columns([5, 1, 0.5])
                with col_card:
                    cat_badge = (
                        f'<span style="background:#e8f5f0;color:#0e7c5b;border-radius:10px;'
                        f'padding:1px 8px;font-size:0.75rem;font-weight:600;margin-left:6px;">'
                        f'{re["category"]}</span>'
                        if re.get("category") else ""
                    )
                    st.markdown(f"""
                    <div class="exp-card">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{re['name']}{cat_badge}</div>
                        <div class="exp-card-bank">
                          {FREQ_LABELS.get(re['frequency'], 'Monthly')}
                          {f" &rarr; {re['bank_name']}" if re.get('bank_name') else ""}
                        </div>
                        <div class="exp-card-date" style="color:{due_color};">
                          {due_label} &mdash; {re['next_due'] or 'No date'}
                        </div>
                      </div>
                      <div class="exp-card-right">
                        <div class="exp-card-amount">-NGN {re['amount']:,}</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_post:
                    if is_due:
                        if st.button("Post", key=f"re_post_{re['id']}", help="Post now",
                                     use_container_width=True, type="primary"):
                            _manual_post_item(re["id"], user_id, re, today)
                            st.rerun()
                with col_del:
                    dk = f"re_{re['id']}"
                    if st.session_state.confirm_delete.get(dk):
                        if st.button("Y", key=f"re_y_{re['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute(
                                    "DELETE FROM recurring_items WHERE id=%s AND user_id=%s",
                                    (re["id"], user_id))
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                        if st.button("N", key=f"re_n_{re['id']}"):
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"re_d_{re['id']}", help="Delete"):
                            st.session_state.confirm_delete[dk] = True; st.rerun()

    # =========================================================================
    # TAB 3 — BILL REMINDERS
    # =========================================================================
    with tab_bill:
        st.subheader("Bill Reminders")
        st.caption("All recurring items due within the next 30 days.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.type, r.category, r.amount, r.frequency,
                       r.next_due, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id = %s AND r.active = 1
                  AND r.next_due IS NOT NULL
                ORDER BY r.next_due
            """, (user_id,))
            all_items = cursor.fetchall()

        upcoming  = [r for r in all_items if (r["next_due"] - today).days <= 30]
        overdue   = [r for r in upcoming   if (r["next_due"] - today).days <  0]
        due_7     = [r for r in upcoming   if 0 <= (r["next_due"] - today).days <= 7]
        due_30    = [r for r in upcoming   if 7 <  (r["next_due"] - today).days <= 30]

        if not upcoming:
            st.info("No items due in the next 30 days.")
        else:
            def _bill_card(r):
                days   = (r["next_due"] - today).days
                income = r["type"] == "income"
                color  = "#0e7c5b" if income else "#c0392b"
                sign   = "+" if income else "-"
                icon   = "🔴" if days < 0 else ("🟠" if days <= 3 else "🟢")
                label  = (f"Overdue {abs(days)}d" if days < 0
                          else "Due today" if days == 0 else f"Due in {days}d")
                st.markdown(f"""
                <div class="exp-card" style="border-left-color:{color};">
                  <div class="exp-card-left">
                    <div class="exp-card-name">{icon} {r['name']}</div>
                    <div class="exp-card-bank">
                      {FREQ_LABELS.get(r['frequency'],'')}
                      {f" &rarr; {r['bank_name']}" if r.get('bank_name') else ""}
                    </div>
                    <div class="exp-card-date">{label} &mdash; {r['next_due']}</div>
                  </div>
                  <div class="exp-card-right">
                    <div class="exp-card-amount" style="color:{color};">
                      {sign}NGN {r['amount']:,}
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            if overdue:
                st.markdown("#### 🔴 Overdue")
                for r in overdue: _bill_card(r)
            if due_7:
                st.markdown("#### 🟠 Due within 7 days")
                for r in due_7: _bill_card(r)
            if due_30:
                st.markdown("#### 🟢 Due in 8–30 days")
                for r in due_30: _bill_card(r)

            st.divider()
            exp_total = sum(r["amount"] for r in upcoming if r["type"] == "expense")
            inc_total = sum(r["amount"] for r in upcoming if r["type"] == "income")
            c1, c2 = st.columns(2)
            c1.metric("Bills to pay (30 days)", f"NGN {exp_total:,}")
            c2.metric("Income expected (30 days)", f"NGN {inc_total:,}")

    # =========================================================================
    # TAB 4 — DEBT / LOAN TRACKER  (upgraded: payment history + bank linkage)
    # =========================================================================
    with tab_debt:
        st.subheader("Debt & Loan Tracker")
        st.caption("Track money you owe (borrowed) and money owed to you (lent).")

        DEBT_CATEGORIES = [
            "Personal", "Business", "Bank Loan", "Credit Card",
            "Family / Friend", "BNPL / Hire Purchase", "Mortgage", "Other",
        ]

        with st.expander("Add debt or loan", expanded=False):
            with st.form("add_debt"):
                c_top1, c_top2 = st.columns(2)
                with c_top1:
                    d_name = st.text_input("Name / Description",
                                           placeholder="e.g. GTB loan, Owe Chike")
                    d_cat  = st.selectbox("Category", DEBT_CATEGORIES)
                with c_top2:
                    d_type = st.radio(
                        "Type", ["borrowed", "lent"],
                        format_func=lambda x: "I borrowed this" if x == "borrowed" else "I lent this"
                    )
                c1, c2 = st.columns(2)
                with c1:
                    d_principal = st.number_input("Original amount (NGN)", min_value=1, step=1000)
                    d_remaining = st.number_input("Balance still owed (NGN)", min_value=0, step=1000)
                    d_monthly   = st.number_input("Monthly payment (NGN, 0 if none)", min_value=0, step=500)
                with c2:
                    d_rate  = st.number_input("Interest rate (% p.a., 0 if none)", min_value=0.0, step=0.5)
                    d_due   = st.date_input("Due / repayment date")
                    d_party = st.text_input("Counterparty (person or bank name)")
                d_notes = st.text_area("Notes (optional)", height=60)
                if st.form_submit_button("Add Debt / Loan", type="primary"):
                    if d_name and d_principal > 0:
                        with get_db() as (conn, cursor):
                            full_notes = f"[{d_cat}] {d_notes.strip()}".strip()
                            cursor.execute("""
                                INSERT INTO debts
                                    (user_id, name, type, principal, balance_remaining,
                                     interest_rate, monthly_payment, due_date, counterparty, notes)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """, (user_id, d_name, d_type, int(d_principal), int(d_remaining),
                                  d_rate, int(d_monthly), d_due,
                                  d_party.strip() or None, full_notes or None))
                        st.success(f"'{d_name}' added.")
                        st.rerun()
                    else:
                        st.warning("Please enter a name and amount.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT id, name, type, principal, balance_remaining, interest_rate,
                       monthly_payment, due_date, counterparty, notes, status
                FROM debts WHERE user_id=%s ORDER BY status, due_date NULLS LAST
            """, (user_id,))
            debts = cursor.fetchall()

        if not debts:
            st.info("No debts or loans tracked yet. Use the form above to add one.")
        else:
            active_debts  = [d for d in debts if d["status"] == "active"]
            total_owe     = sum(d["balance_remaining"] for d in active_debts if d["type"] == "borrowed")
            total_owed    = sum(d["balance_remaining"] for d in active_debts if d["type"] == "lent")
            total_monthly = sum(d["monthly_payment"] for d in active_debts if d["type"] == "borrowed")
            c1, c2, c3 = st.columns(3)
            c1.metric("You owe (total)",      f"NGN {total_owe:,}")
            c2.metric("Owed to you (total)",  f"NGN {total_owed:,}")
            c3.metric("Monthly repayments",   f"NGN {total_monthly:,}")
            st.divider()

            for d in debts:
                import re as _re
                is_lent   = d["type"] == "lent"
                principal = int(d["principal"])
                balance   = int(d["balance_remaining"])
                paid      = principal - balance
                pct_paid  = round(paid / principal * 100, 1) if principal > 0 else 0
                color     = "#0e7c5b" if is_lent else "#c0392b"
                direction = "Lent" if is_lent else "Borrowed"

                notes_raw = d["notes"] or ""
                cat_match = _re.match(r'^\[([^\]]+)\]', notes_raw)
                debt_cat  = cat_match.group(1) if cat_match else ""
                clean_notes = notes_raw[len(f"[{debt_cat}]"):].strip() if debt_cat else notes_raw

                monthly_pmt = int(d["monthly_payment"] or 0)
                if monthly_pmt > 0 and balance > 0 and d["status"] == "active":
                    months_left = -(-balance // monthly_pmt)
                    payoff_str  = f"{months_left}mo at NGN {monthly_pmt:,}/mo"
                else:
                    payoff_str  = None

                status_badge = (
                    '<span style="background:#e8f5f0;color:#0e7c5b;border-radius:10px;'
                    'padding:1px 8px;font-size:0.72rem;font-weight:600;">Paid</span>'
                    if d["status"] == "paid" else ""
                )
                cat_badge = (
                    f'<span style="background:#e8f0f7;color:#6a1b9a;border-radius:10px;'
                    f'padding:1px 8px;font-size:0.72rem;font-weight:600;">{debt_cat}</span>'
                    if debt_cat else ""
                )
                bar_pct   = min(pct_paid, 100)
                bar_color = "#0e7c5b" if pct_paid >= 100 else ("#f39c12" if pct_paid >= 50 else color)
                progress_html = (
                    f'<div style="background:#eef5f2;border-radius:6px;height:7px;'
                    f'margin-top:6px;overflow:hidden;">'
                    f'<div style="background:{bar_color};width:{bar_pct:.1f}%;'
                    f'height:7px;border-radius:6px;"></div></div>'
                    f'<div style="font-size:0.72rem;color:#95a5a6;margin-top:3px;">'
                    f'NGN {paid:,} paid of NGN {principal:,} ({pct_paid:.0f}%)</div>'
                )

                col_card, col_act = st.columns([5, 1])
                with col_card:
                    st.markdown(f"""
                    <div class="exp-card" style="border-left-color:{color};">
                      <div class="exp-card-left" style="width:100%;">
                        <div class="exp-card-name">
                          {direction}: {d['name']} {status_badge} {cat_badge}
                        </div>
                        <div class="exp-card-bank">
                          {f"{d['counterparty']} &middot; " if d.get('counterparty') else ""}
                          {f"{d['interest_rate']:.1f}% p.a." if d['interest_rate'] else "0% interest"}
                          {f" &middot; {payoff_str}" if payoff_str else ""}
                        </div>
                        <div class="exp-card-date">
                          Due: {d['due_date'] or 'Not set'}
                          {f" &middot; {clean_notes}" if clean_notes else ""}
                        </div>
                        {progress_html}
                      </div>
                      <div class="exp-card-right">
                        <div class="exp-card-amount" style="color:{color};">
                          NGN {balance:,}
                        </div>
                        <div style="font-size:0.72rem;color:#95a5a6;">remaining</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                with col_act:
                    if d["status"] == "active":
                        # Mark fully paid
                        if st.button("Paid", key=f"dp_{d['id']}", use_container_width=True,
                                     help="Mark as fully paid", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute(
                                    "UPDATE debts SET status='paid', balance_remaining=0 "
                                    "WHERE id=%s AND user_id=%s", (d["id"], user_id))
                                if balance > 0:
                                    cursor.execute("""
                                        INSERT INTO debt_payments
                                            (debt_id, user_id, amount, note, paid_at)
                                        VALUES (%s, %s, %s, %s, %s)
                                    """, (d["id"], user_id, balance, "Marked fully paid", today))
                            st.rerun()

                        # Partial payment toggle
                        pay_key = f"show_pay_{d['id']}"
                        if st.button("Pay", key=f"pp_{d['id']}", use_container_width=True,
                                     help="Record a partial payment"):
                            st.session_state[pay_key] = not st.session_state.get(pay_key, False)
                            st.rerun()

                        if st.session_state.get(pay_key, False):
                            with st.form(f"partial_pay_{d['id']}"):
                                pay_bank = st.selectbox(
                                    "Pay from bank (optional)",
                                    ["— none —"] + bank_opts,
                                    key=f"pay_bank_{d['id']}"
                                )
                                amt_paid = st.number_input(
                                    "Payment amount (NGN)",
                                    min_value=1, max_value=balance, step=500,
                                    key=f"pay_amt_{d['id']}"
                                )
                                pay_note = st.text_input("Note (optional)", key=f"pay_note_{d['id']}")
                                if st.form_submit_button("Record payment"):
                                    new_balance  = max(balance - int(amt_paid), 0)
                                    new_status   = "paid" if new_balance == 0 else "active"
                                    pay_bank_id  = bank_map.get(pay_bank) if pay_bank != "— none —" else None
                                    with get_db() as (conn, cursor):
                                        cursor.execute(
                                            "UPDATE debts SET balance_remaining=%s, status=%s "
                                            "WHERE id=%s AND user_id=%s",
                                            (new_balance, new_status, d["id"], user_id))
                                        cursor.execute("""
                                            INSERT INTO debt_payments
                                                (debt_id, user_id, bank_id, amount, note, paid_at)
                                            VALUES (%s, %s, %s, %s, %s, %s)
                                        """, (d["id"], user_id, pay_bank_id,
                                              int(amt_paid), pay_note.strip() or None, today))
                                        if pay_bank_id:
                                            cursor.execute(
                                                "UPDATE banks SET balance = balance - %s WHERE id=%s",
                                                (int(amt_paid), pay_bank_id))
                                            cursor.execute("""
                                                INSERT INTO transactions
                                                    (bank_id, type, amount, description, created_at)
                                                VALUES (%s,'debit',%s,%s,%s)
                                            """, (pay_bank_id, int(amt_paid),
                                                  f"Debt payment: {d['name']}", today))
                                    st.session_state.pop(pay_key, None)
                                    st.success(
                                        f"NGN {int(amt_paid):,} recorded. "
                                        f"{'Debt fully cleared!' if new_balance == 0 else f'NGN {new_balance:,} remaining.'}"
                                    )
                                    st.rerun()

                    dk = f"debt_{d['id']}"
                    if st.session_state.confirm_delete.get(dk):
                        if st.button("Y", key=f"dy_{d['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM debts WHERE id=%s AND user_id=%s",
                                               (d["id"], user_id))
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                        if st.button("N", key=f"dn_{d['id']}"):
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"dd_{d['id']}", help="Delete"):
                            st.session_state.confirm_delete[dk] = True; st.rerun()

                # ── Repayment History ─────────────────────────────────────────
                with get_db() as (conn, cursor):
                    cursor.execute("""
                        SELECT dp.paid_at, dp.amount, dp.note, b.bank_name
                        FROM debt_payments dp
                        LEFT JOIN banks b ON dp.bank_id = b.id
                        WHERE dp.debt_id = %s AND dp.user_id = %s
                        ORDER BY dp.paid_at DESC
                        LIMIT 30
                    """, (d["id"], user_id))
                    payment_history = cursor.fetchall()

                if payment_history:
                    total_repaid = sum(int(p["amount"]) for p in payment_history)
                    with st.expander(
                        f"Payment history — {len(payment_history)} payment(s) | "
                        f"Total repaid: NGN {total_repaid:,}",
                        expanded=False
                    ):
                        st.caption(
                            f"Total borrowed: **NGN {principal:,}** | "
                            f"Total repaid: **NGN {total_repaid:,}** | "
                            f"Remaining: **NGN {balance:,}**"
                        )
                        for p in payment_history:
                            bank_label = f"via {p['bank_name']}" if p.get("bank_name") else ""
                            note_label = f" — {p['note']}" if p.get("note") else ""
                            st.markdown(
                                f'<div class="exp-card" style="border-left-color:#0e7c5b;padding:8px 14px;">'
                                f'<div class="exp-card-left">'
                                f'<div class="exp-card-name" style="font-size:0.88rem;">'
                                f'{p["paid_at"]} {bank_label}{note_label}</div>'
                                f'</div>'
                                f'<div class="exp-card-right">'
                                f'<div class="exp-card-amount" style="color:#0e7c5b;font-size:0.95rem;">'
                                f'NGN {int(p["amount"]):,}</div>'
                                f'</div></div>',
                                unsafe_allow_html=True
                            )

                st.divider()

    # =========================================================================
    # TAB 5 — EMERGENCY FUND PLANNER  (upgraded)
    # =========================================================================
    with tab_ef:
        st.subheader("Emergency Fund Planner")
        st.caption(
            "An emergency fund covers 3–6 months of living expenses. "
            "It protects you from job loss, medical bills, or unexpected crises."
        )

        with get_db() as (conn, cursor):
            cursor.execute("SELECT * FROM emergency_fund_plan WHERE user_id=%s", (user_id,))
            ef = cursor.fetchone()

            three_months_ago = today.replace(day=1)
            for _ in range(2):
                three_months_ago = (three_months_ago - timedelta(days=1)).replace(day=1)

            cursor.execute("""
                SELECT COALESCE(SUM(t.amount), 0) AS total
                FROM transactions t JOIN banks b ON t.bank_id = b.id
                WHERE b.user_id = %s AND t.type = 'debit'
                  AND t.created_at >= %s AND t.created_at < %s
            """, (user_id, three_months_ago, today.replace(day=1)))
            three_mo_total     = int(cursor.fetchone()["total"] or 0)
            actual_avg_monthly = three_mo_total // 3 if three_mo_total > 0 else 0

            cursor.execute("""
                SELECT COALESCE(SUM(t.amount), 0) AS total
                FROM transactions t JOIN banks b ON t.bank_id = b.id
                WHERE b.user_id = %s AND t.type = 'credit'
                  AND t.created_at >= %s
            """, (user_id, today.replace(day=1)))
            income_this_month = int(cursor.fetchone()["total"] or 0)

            # Find linked Emergency Fund goal (name contains "emergency")
            cursor.execute("""
                SELECT id, name, target_amount, current_amount, status
                FROM goals
                WHERE user_id=%s
                  AND (LOWER(name) LIKE '%%emergency%%fund%%' OR LOWER(name) LIKE '%%emergency%%')
                ORDER BY
                    CASE WHEN LOWER(name) LIKE '%%emergency%%fund%%' THEN 0 ELSE 1 END,
                    created_at DESC
                LIMIT 1
            """, (user_id,))
            ef_goal = cursor.fetchone()

        if actual_avg_monthly > 0:
            st.info(
                f"Based on your last 3 months of spending, your average monthly expenses are "
                f"**NGN {actual_avg_monthly:,}**. This is used as the default below."
            )

        # Linked goal banner
        if ef_goal:
            g_pct    = min(round(ef_goal["current_amount"] / ef_goal["target_amount"] * 100, 1), 100) \
                       if ef_goal["target_amount"] > 0 else 0
            g_status = "Completed!" if ef_goal["status"] == "completed" else f"{g_pct:.0f}% saved"
            st.markdown(
                f'<div style="background:#e8f5f0;border-radius:10px;padding:12px 16px;margin-bottom:12px;">'
                f'<b>Linked Savings Goal:</b> {ef_goal["name"]} &mdash; '
                f'NGN {ef_goal["current_amount"]:,} / NGN {ef_goal["target_amount"]:,} ({g_status})'
                f'</div>',
                unsafe_allow_html=True
            )

        # Month target quick-view
        st.markdown("#### Target by months")
        cols_mo = st.columns(3)
        for i, mo in enumerate([1, 3, 6]):
            proj = actual_avg_monthly * mo if actual_avg_monthly > 0 else 0
            cols_mo[i].markdown(
                f'<div style="background:#f0f7f4;border-radius:10px;padding:12px;text-align:center;">'
                f'<div style="font-size:0.78rem;color:#4a6070;font-weight:600;">{mo}-Month</div>'
                f'<div style="font-size:1.1rem;font-weight:800;color:#1a3c5e;">NGN {proj:,}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown("<br>", unsafe_allow_html=True)

        with st.form("ef_form"):
            st.markdown("#### Step 1 — Set your target")
            c1, c2 = st.columns(2)
            with c1:
                ef_months = st.slider(
                    "Months of expenses to save",
                    min_value=1, max_value=12,
                    value=int(ef["target_months"]) if ef else 3,
                )
            with c2:
                default_monthly = (
                    int(ef["monthly_expenses_estimate"]) if ef and ef["monthly_expenses_estimate"]
                    else actual_avg_monthly
                )
                ef_monthly = st.number_input(
                    "Your monthly expenses (NGN)",
                    min_value=0, step=1000, value=default_monthly,
                )

            st.markdown("#### Step 2 — Where are you now?")
            default_saved = int(ef["current_saved"]) if ef else 0
            if ef_goal and int(ef_goal["current_amount"]) > default_saved:
                default_saved = int(ef_goal["current_amount"])
            ef_saved = st.number_input(
                "Amount already saved (NGN)",
                min_value=0, step=1000, value=default_saved,
            )

            st.markdown("#### Step 3 — Monthly contribution")
            suggested = max(-(-max(ef_months * (ef_monthly or 0) - (ef_saved or 0), 0) // 6), 1000)
            ef_contribution = st.number_input(
                "Monthly contribution (NGN)",
                min_value=0, step=500, value=suggested,
            )

            ef_saved_btn = st.form_submit_button("Calculate & Save Plan", type="primary")

        if ef_saved_btn:
            with get_db() as (conn, cursor):
                cursor.execute("""
                    INSERT INTO emergency_fund_plan
                        (user_id, target_months, monthly_expenses_estimate, current_saved, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        target_months             = EXCLUDED.target_months,
                        monthly_expenses_estimate = EXCLUDED.monthly_expenses_estimate,
                        current_saved             = EXCLUDED.current_saved,
                        updated_at                = EXCLUDED.updated_at
                """, (user_id, ef_months, int(ef_monthly), int(ef_saved), today))
            st.success("Plan saved.")
            st.rerun()

        _months       = ef_months       if ef_saved_btn else (int(ef["target_months"])             if ef else 3)
        _monthly      = ef_monthly      if ef_saved_btn else (int(ef["monthly_expenses_estimate"]) if ef and ef["monthly_expenses_estimate"] else actual_avg_monthly)
        _saved        = ef_saved        if ef_saved_btn else default_saved
        _contribution = ef_contribution if ef_saved_btn else suggested

        if _monthly > 0:
            target        = _months * _monthly
            shortfall     = max(target - _saved, 0)
            pct           = min(round(_saved / target * 100, 1), 100) if target > 0 else 0
            weekly_savings = round(_contribution / 4.33, 0) if _contribution > 0 else 0

            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"Target ({_months}-mo fund)", f"NGN {target:,}")
            c2.metric("Saved so far",    f"NGN {_saved:,}")
            c3.metric("Still needed",    f"NGN {shortfall:,}")
            c4.metric("Weekly savings",  f"NGN {int(weekly_savings):,}",
                      help="Monthly contribution ÷ 4.33 weeks")

            st.progress(pct / 100, text=f"{pct:.0f}% — NGN {_saved:,} of NGN {target:,}")

            if shortfall > 0 and _contribution > 0:
                months_needed = math.ceil(shortfall / _contribution)
                completion    = today.replace(day=1)
                for _ in range(months_needed):
                    if completion.month == 12:
                        completion = completion.replace(year=completion.year + 1, month=1)
                    else:
                        completion = completion.replace(month=completion.month + 1)

                st.markdown(
                    f'<div style="background:linear-gradient(90deg,#1a3c5e,#0e7c5b);'
                    f'border-radius:12px;padding:16px 20px;margin:12px 0;color:#fff;">'
                    f'<div style="font-size:0.8rem;color:#a8d8c8;font-weight:600;">Completion estimate</div>'
                    f'<div style="font-size:1.5rem;font-weight:800;margin:4px 0;">'
                    f'{completion.strftime("%B %Y")}</div>'
                    f'<div style="font-size:0.88rem;color:#d4eee6;">'
                    f'Save NGN {_contribution:,}/month &nbsp;|&nbsp; '
                    f'NGN {int(weekly_savings):,}/week &rarr; '
                    f'<strong>{months_needed} month{"s" if months_needed != 1 else ""}</strong>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

                st.markdown("**Compare saving scenarios:**")
                cols = st.columns(3)
                for col, n_months in zip(cols, [3, 6, 12]):
                    mo_needed  = -(-shortfall // n_months)
                    wk_needed  = round(mo_needed / 4.33, 0)
                    comp_date  = today.replace(day=1)
                    for _ in range(n_months):
                        if comp_date.month == 12:
                            comp_date = comp_date.replace(year=comp_date.year + 1, month=1)
                        else:
                            comp_date = comp_date.replace(month=comp_date.month + 1)
                    col.markdown(
                        f'<div style="background:#f0f7f4;border-radius:10px;padding:14px;text-align:center;">'
                        f'<div style="font-size:0.75rem;color:#4a6070;font-weight:600;">Done in {n_months} months</div>'
                        f'<div style="font-size:1.15rem;font-weight:800;color:#1a3c5e;">NGN {mo_needed:,}/mo</div>'
                        f'<div style="font-size:0.78rem;color:#0e7c5b;font-weight:600;">NGN {int(wk_needed):,}/week</div>'
                        f'<div style="font-size:0.72rem;color:#95a5a6;">by {comp_date.strftime("%b %Y")}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                st.markdown("<br>", unsafe_allow_html=True)
                if ef_goal:
                    st.info(
                        f"Linked to your **{ef_goal['name']}** savings goal. "
                        f"Keep contributing NGN {_contribution:,}/month "
                        f"(NGN {int(weekly_savings):,}/week) to be funded by "
                        f"**{completion.strftime('%B %Y')}**."
                    )
                else:
                    st.info(
                        f"Create a Savings Goal called 'Emergency Fund' on the Goals page and "
                        f"contribute NGN {_contribution:,}/month (NGN {int(weekly_savings):,}/week). "
                        f"You'll be funded by **{completion.strftime('%B %Y')}**."
                    )

            elif shortfall > 0 and _contribution == 0:
                st.warning("Set a monthly contribution above to see your completion date.")
            else:
                st.success(f"Emergency fund target of NGN {target:,} fully covered!")

            if ef and ef.get("updated_at"):
                st.caption(f"Last updated: {ef['updated_at']}")
        else:
            st.info("Enter your monthly expenses above to start the calculator.")

    # =========================================================================
    # TAB 6 — SAVINGS GOALS TRACKER  (new)
    # =========================================================================
    with tab_goals:
        st.subheader("Savings Goals Tracker")
        st.caption("Track all your savings goals and spot which ones need attention.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT g.id, g.name, g.target_amount, g.current_amount, g.status, g.created_at,
                       COALESCE(
                           (SELECT MAX(gc.contributed_at)
                            FROM goal_contributions gc WHERE gc.goal_id = g.id),
                           g.created_at
                       ) AS last_contributed
                FROM goals g
                WHERE g.user_id = %s
                ORDER BY
                    CASE WHEN g.status = 'active' THEN 0 ELSE 1 END,
                    g.created_at DESC
            """, (user_id,))
            tracker_goals = cursor.fetchall()

        if not tracker_goals:
            st.info("No savings goals yet. Create one on the **Goals** page.")
        else:
            active_goals    = [g for g in tracker_goals if g["status"] == "active"]
            completed_goals = [g for g in tracker_goals if g["status"] == "completed"]

            total_target = sum(int(g["target_amount"])  for g in active_goals)
            total_saved  = sum(int(g["current_amount"]) for g in active_goals)
            total_short  = max(total_target - total_saved, 0)

            c1, c2, c3 = st.columns(3)
            c1.metric("Active goals",    len(active_goals))
            c2.metric("Total saved",     f"NGN {total_saved:,}")
            c3.metric("Total remaining", f"NGN {total_short:,}")
            st.divider()

            def _goal_tracker_card(g):
                pct     = min(round(g["current_amount"] / g["target_amount"] * 100, 1), 100) \
                          if g["target_amount"] > 0 else 0
                gap     = int(g["target_amount"]) - int(g["current_amount"])
                is_done = g["status"] == "completed"
                bar_col = "#0e7c5b" if is_done else ("#f39c12" if pct >= 50 else "#c0392b")

                last_c = g["last_contributed"]
                if last_c:
                    if isinstance(last_c, str):
                        last_c = date.fromisoformat(str(last_c)[:10])
                    days_since = (today - last_c).days
                    if is_done:
                        r_label, r_color = "Completed", "#0e7c5b"
                    elif days_since > 60:
                        r_label, r_color = f"No contribution in {days_since}d", "#c0392b"
                    elif days_since > 30:
                        r_label, r_color = f"Last contributed {days_since}d ago", "#f39c12"
                    else:
                        r_label, r_color = f"Last contributed {days_since}d ago", "#0e7c5b"
                else:
                    r_label, r_color = "No contributions yet", "#95a5a6"

                progress_bar = (
                    f'<div style="background:#eef5f2;border-radius:6px;height:8px;'
                    f'margin-top:6px;overflow:hidden;">'
                    f'<div style="background:{bar_col};width:{pct:.1f}%;'
                    f'height:8px;border-radius:6px;"></div></div>'
                )
                st.markdown(f"""
                <div class="exp-card" style="border-left-color:{bar_col};">
                  <div class="exp-card-left" style="width:100%;">
                    <div class="exp-card-name">{g['name']}</div>
                    <div class="exp-card-bank" style="color:{r_color};">{r_label}</div>
                    <div class="exp-card-date">
                      NGN {int(g['current_amount']):,} of NGN {int(g['target_amount']):,}
                      {f" &mdash; NGN {gap:,} to go" if not is_done else " &mdash; Goal reached!"}
                    </div>
                    {progress_bar}
                    <div style="font-size:0.72rem;color:#95a5a6;margin-top:3px;">{pct:.0f}% complete</div>
                  </div>
                  <div class="exp-card-right">
                    <div class="exp-card-amount" style="color:{bar_col};">{pct:.0f}%</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            if active_goals:
                st.markdown(f"#### Active Goals ({len(active_goals)})")
                for g in active_goals:
                    _goal_tracker_card(g)

            if completed_goals:
                st.markdown(f"#### Completed Goals ({len(completed_goals)})")
                for g in completed_goals:
                    _goal_tracker_card(g)
