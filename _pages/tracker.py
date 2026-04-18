# tracker.py — Tracker page
# Tabs: Recurring Income | Recurring Expenses | Bill Reminders | Debt/Loan | Emergency Fund
import math
import streamlit as st
from datetime import datetime, timedelta

from db import get_db


FREQ_OPTIONS = ["monthly", "weekly", "daily", "yearly"]
FREQ_LABELS  = {"monthly": "Monthly", "weekly": "Weekly",
                "daily": "Daily",    "yearly": "Yearly"}
FREQ_MULT    = {"daily": 30, "weekly": 4.33, "monthly": 1, "yearly": 1/12}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _next_due(freq, from_date=None):
    """Calculate the next due date from a given date (default today)."""
    base = from_date or datetime.now().date()
    if freq == "daily":   return base + timedelta(days=1)
    if freq == "weekly":  return base + timedelta(weeks=1)
    if freq == "yearly":  return base.replace(year=base.year + 1)
    # monthly
    if base.month == 12:
        return base.replace(year=base.year + 1, month=1, day=1)
    return base.replace(month=base.month + 1, day=1)


def _due_badge(next_due, today):
    if next_due is None:
        return "No date", "#95a5a6"
    days = (next_due - today).days
    if days < 0:   return f"Overdue {abs(days)}d", "#c0392b"
    if days == 0:  return "Due today", "#e67e22"
    if days <= 3:  return f"Due in {days}d", "#c0392b"
    if days <= 7:  return f"Due in {days}d", "#f39c12"
    return f"Due in {days}d", "#1a3c5e"


def _run_auto_posting(user_id: int, today) -> list:
    """
    Check all recurring items with auto_post=1 that are due today or overdue.
    Post them (create transaction/expense record), advance next_due, update last_posted_at.
    Returns a list of result strings for display.

    Rules:
    - allow_overdraft=0 (default): only post if bank has sufficient balance
    - allow_overdraft=1: post even if balance goes negative
    - After posting, advance next_due to the next cycle
    - If bank_id is NULL, skip auto-posting (no bank selected)
    """
    results = []
    with get_db() as (conn, cursor):
        # Load all due auto-post items
        cursor.execute("""
            SELECT r.id, r.type, r.name, r.category, r.amount, r.frequency,
                   r.next_due, r.bank_id, r.allow_overdraft,
                   b.balance, b.bank_name
            FROM recurring_items r
            LEFT JOIN banks b ON r.bank_id = b.id
            WHERE r.user_id = %s
              AND r.auto_post = 1
              AND r.active = 1
              AND r.next_due IS NOT NULL
              AND r.next_due <= %s
        """, (user_id, today))
        due_items = cursor.fetchall()

        for item in due_items:
            # Must have a linked bank for auto-posting
            if not item["bank_id"]:
                continue

            bank_balance    = int(item["balance"] or 0)
            amount          = int(item["amount"])
            allow_overdraft = bool(item["allow_overdraft"])
            item_type       = item["type"]  # 'income' or 'expense'

            # Check funds (only relevant for expenses)
            if item_type == "expense":
                if bank_balance < amount and not allow_overdraft:
                    results.append(
                        f"⚠️ **{item['name']}** — Skipped (insufficient funds: "
                        f"NGN {bank_balance:,} available, NGN {amount:,} needed)"
                    )
                    continue

            # ── Post the transaction ──────────────────────────────────────────
            tx_type      = "credit" if item_type == "income" else "debit"
            description  = f"Auto-posted: {item['name']}"
            balance_delta = amount if item_type == "income" else -amount

            cursor.execute("""
                INSERT INTO transactions (bank_id, type, amount, description, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (item["bank_id"], tx_type, amount, description, today))

            # For expenses also create an expense record
            if item_type == "expense":
                cursor.execute("""
                    INSERT INTO expenses (user_id, bank_id, name, category, amount, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, item["bank_id"], item["name"],
                      item.get("category") or item["name"], amount, today))

            # Update bank balance
            cursor.execute(
                "UPDATE banks SET balance = balance + %s WHERE id = %s",
                (balance_delta, item["bank_id"])
            )

            # Advance next_due and record last_posted_at
            new_next_due = _next_due(item["frequency"], today)
            cursor.execute("""
                UPDATE recurring_items
                SET next_due = %s, last_posted_at = %s
                WHERE id = %s AND user_id = %s
            """, (new_next_due, today, item["id"], user_id))

            sign   = "+" if item_type == "income" else "-"
            results.append(
                f"✅ **{item['name']}** — {sign}NGN {amount:,} posted to "
                f"{item['bank_name']}. Next due: {new_next_due}"
            )

    return results


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDER
# ─────────────────────────────────────────────────────────────────────────────

def render_tracker(user_id):
    st.markdown("## Tracker")
    st.caption("Recurring income & expenses, bill reminders, debts, and your emergency fund.")

    today = datetime.now().date()

    # ── Auto-posting engine (runs once per calendar day) ──────────────────────
    _ap_key = f"_autopost_{today.isoformat()}"
    if _ap_key not in st.session_state:
        posted = _run_auto_posting(user_id, today)
        st.session_state[_ap_key] = posted

    if st.session_state.get(_ap_key):
        with st.expander("⚙️ Auto-posting results (today)", expanded=True):
            for msg in st.session_state[_ap_key]:
                st.markdown(msg)

    # ── Load banks once for all tabs ──────────────────────────────────────────
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, bank_name, account_number, balance FROM banks "
            "WHERE user_id=%s ORDER BY bank_name",
            (user_id,)
        )
        banks = cursor.fetchall()

    bank_map  = {f"{b['bank_name']} (****{b['account_number']}) — NGN {b['balance']:,}": b["id"] for b in banks}
    bank_opts = list(bank_map.keys())

    tab_ri, tab_re, tab_bill, tab_debt, tab_ef = st.tabs([
        "💰 Recurring Income",
        "💸 Recurring Expenses",
        "🔔 Bill Reminders",
        "💳 Debt / Loan",
        "🛡️ Emergency Fund",
    ])

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1 — RECURRING INCOME
    # ─────────────────────────────────────────────────────────────────────────
    with tab_ri:
        st.subheader("Recurring Income")
        st.caption("Salary, freelance, rent — any money that arrives on a schedule.")

        with st.expander("➕ Add recurring income", expanded=False):
            with st.form("add_rec_income"):
                c1, c2 = st.columns(2)
                with c1:
                    ri_name = st.text_input("Income source", placeholder="e.g. Salary, Freelance")
                    ri_freq = st.selectbox("Frequency", FREQ_OPTIONS,
                                           format_func=lambda x: FREQ_LABELS[x], key="ri_freq")
                with c2:
                    ri_amt = st.number_input("Expected amount (NGN)", min_value=1, step=1000)
                    ri_due = st.date_input("Next expected date", value=_next_due("monthly"))
                ri_bank = st.selectbox("Deposit to bank (optional)", ["— none —"] + bank_opts)
                ri_auto = st.checkbox("Auto-post when due",
                                      help="When due date arrives, credit is posted automatically")
                if st.form_submit_button("Add Recurring Income", type="primary"):
                    if ri_name and ri_amt > 0:
                        bk_id = bank_map.get(ri_bank) if ri_bank != "— none —" else None
                        with get_db() as (conn, cursor):
                            cursor.execute("""
                                INSERT INTO recurring_items
                                    (user_id, type, name, amount, frequency,
                                     next_due, bank_id, auto_post)
                                VALUES (%s,'income',%s,%s,%s,%s,%s,%s)
                            """, (user_id, ri_name, int(ri_amt), ri_freq, ri_due,
                                  bk_id, 1 if ri_auto else 0))
                        st.success(f"'{ri_name}' added.")
                        st.session_state.pop(_ap_key, None)  # reset so it re-checks
                        st.rerun()
                    else:
                        st.warning("Please enter a name and amount.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.amount, r.frequency, r.next_due,
                       r.auto_post, r.last_posted_at, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id=%s AND r.type='income'
                ORDER BY r.next_due NULLS LAST
            """, (user_id,))
            rec_incomes = cursor.fetchall()

        if not rec_incomes:
            st.info("No recurring income yet.")
        else:
            total_monthly_income = sum(
                r["amount"] * FREQ_MULT.get(r["frequency"], 1) for r in rec_incomes
            )
            st.caption(f"Estimated monthly recurring income: **NGN {int(total_monthly_income):,}**")

            for ri in rec_incomes:
                due_label, due_color = _due_badge(ri["next_due"], today)
                col_card, col_del = st.columns([6, 0.5])
                with col_card:
                    last_posted = f" &middot; Last posted: {ri['last_posted_at']}" if ri.get("last_posted_at") else ""
                    st.markdown(f"""
                    <div class="exp-card" style="border-left-color:#0e7c5b;">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{ri['name']}</div>
                        <div class="exp-card-bank">
                          {FREQ_LABELS.get(ri['frequency'], 'Monthly')}
                          {f" &rarr; {ri['bank_name']}" if ri.get('bank_name') else ""}
                          {"&nbsp;<em style='font-size:0.75rem;'>auto-post</em>" if ri['auto_post'] else ""}
                          {last_posted}
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
                with col_del:
                    dk = f"ri_{ri['id']}"
                    if st.session_state.confirm_delete.get(dk):
                        if st.button("✓", key=f"ri_y_{ri['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM recurring_items WHERE id=%s AND user_id=%s",
                                               (ri["id"], user_id))
                            st.session_state.confirm_delete.pop(dk, None)
                            st.rerun()
                        if st.button("✗", key=f"ri_n_{ri['id']}"):
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"ri_d_{ri['id']}", help="Delete"):
                            st.session_state.confirm_delete[dk] = True; st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2 — RECURRING EXPENSES
    # ─────────────────────────────────────────────────────────────────────────
    with tab_re:
        st.subheader("Recurring Expenses")
        st.caption("Rent, DSTV, school fees — any expense that repeats on a schedule.")

        EXPENSE_CATS = [
            "— select —", "Rent", "Electricity (NEPA)", "School Fees", "Internet",
            "Subscription", "Transport", "Fuel", "Generator/Fuel", "Water",
            "Airtime/Data", "Hospital/Drugs", "Family Support", "Church/Mosque Giving",
            "Business Stock", "Savings Deposit", "Other",
        ]

        with st.expander("➕ Add recurring expense", expanded=False):
            with st.form("add_rec_expense"):
                c1, c2 = st.columns(2)
                with c1:
                    re_name = st.text_input("Expense name", placeholder="e.g. House rent, DSTV")
                    re_freq = st.selectbox("Frequency", FREQ_OPTIONS,
                                           format_func=lambda x: FREQ_LABELS[x], key="re_freq")
                with c2:
                    re_amt = st.number_input("Expected amount (NGN)", min_value=1, step=500, key="re_amt")
                    re_due = st.date_input("Next due date", key="re_due")
                re_cat  = st.selectbox("Category", EXPENSE_CATS)
                re_bank = st.selectbox("Pay from bank (optional)", ["— none —"] + bank_opts, key="re_bank")

                c_auto, c_od = st.columns(2)
                with c_auto:
                    re_auto = st.checkbox("Auto-post when due",
                                          help="Automatically deduct from bank when due")
                with c_od:
                    re_od = st.checkbox("Allow overdraft",
                                        help="Post even if bank balance is insufficient (balance goes negative)")

                if st.form_submit_button("Add Recurring Expense", type="primary"):
                    if re_name and re_amt > 0:
                        bk_id = bank_map.get(re_bank) if re_bank != "— none —" else None
                        cat   = None if re_cat == "— select —" else re_cat
                        with get_db() as (conn, cursor):
                            cursor.execute("""
                                INSERT INTO recurring_items
                                    (user_id, type, name, category, amount, frequency,
                                     next_due, bank_id, auto_post, allow_overdraft)
                                VALUES (%s,'expense',%s,%s,%s,%s,%s,%s,%s,%s)
                            """, (user_id, re_name, cat, int(re_amt), re_freq, re_due,
                                  bk_id, 1 if re_auto else 0, 1 if re_od else 0))
                        st.success(f"'{re_name}' added.")
                        st.session_state.pop(_ap_key, None)
                        st.rerun()
                    else:
                        st.warning("Please enter a name and amount.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.category, r.amount, r.frequency, r.next_due,
                       r.auto_post, r.allow_overdraft, r.last_posted_at, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id=%s AND r.type='expense'
                ORDER BY r.next_due NULLS LAST
            """, (user_id,))
            rec_expenses = cursor.fetchall()

        if not rec_expenses:
            st.info("No recurring expenses yet.")
        else:
            total_monthly = sum(r["amount"] * FREQ_MULT.get(r["frequency"], 1) for r in rec_expenses)
            st.caption(f"Estimated monthly recurring cost: **NGN {int(total_monthly):,}**")

            for re in rec_expenses:
                due_label, due_color = _due_badge(re["next_due"], today)
                col_card, col_del = st.columns([6, 0.5])
                with col_card:
                    cat_badge = (
                        f'<span style="background:#e8f5f0;color:#0e7c5b;border-radius:10px;'
                        f'padding:1px 8px;font-size:0.75rem;font-weight:600;margin-left:6px;">'
                        f'{re["category"]}</span>'
                        if re.get("category") else ""
                    )
                    flags = []
                    if re["auto_post"]:    flags.append("<em>auto-post</em>")
                    if re["allow_overdraft"]: flags.append("<em>overdraft ✓</em>")
                    flags_str = " &middot; ".join(flags)
                    last_posted = f" &middot; Last posted: {re['last_posted_at']}" if re.get("last_posted_at") else ""
                    st.markdown(f"""
                    <div class="exp-card">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{re['name']}{cat_badge}</div>
                        <div class="exp-card-bank">
                          {FREQ_LABELS.get(re['frequency'], 'Monthly')}
                          {f" &rarr; {re['bank_name']}" if re.get('bank_name') else ""}
                          {(" &middot; " + flags_str) if flags_str else ""}
                          {last_posted}
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
                with col_del:
                    dk = f"re_{re['id']}"
                    if st.session_state.confirm_delete.get(dk):
                        if st.button("✓", key=f"re_y_{re['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM recurring_items WHERE id=%s AND user_id=%s",
                                               (re["id"], user_id))
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                        if st.button("✗", key=f"re_n_{re['id']}"):
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"re_d_{re['id']}", help="Delete"):
                            st.session_state.confirm_delete[dk] = True; st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3 — BILL REMINDERS
    # ─────────────────────────────────────────────────────────────────────────
    with tab_bill:
        st.subheader("Bill Reminders")
        st.caption("All recurring items due within the next 30 days.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.type, r.category, r.amount, r.frequency,
                       r.next_due, r.auto_post, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id = %s AND r.active = 1
                  AND r.next_due IS NOT NULL
                ORDER BY r.next_due
            """, (user_id,))
            all_items = cursor.fetchall()

        upcoming = [r for r in all_items if (r["next_due"] - today).days <= 30]
        overdue  = [r for r in upcoming   if (r["next_due"] - today).days <  0]
        due_7    = [r for r in upcoming   if 0 <= (r["next_due"] - today).days <= 7]
        due_30   = [r for r in upcoming   if 7 <  (r["next_due"] - today).days <= 30]

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
                auto_tag = " <em style='font-size:0.72rem;color:#888;'>auto</em>" if r.get("auto_post") else ""
                st.markdown(f"""
                <div class="exp-card" style="border-left-color:{color};">
                  <div class="exp-card-left">
                    <div class="exp-card-name">{icon} {r['name']}{auto_tag}</div>
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
            c1.metric("Bills to pay (30 days)",    f"NGN {exp_total:,}")
            c2.metric("Income expected (30 days)", f"NGN {inc_total:,}")

            # ── Manual "Post now" button for overdue items ────────────────────
            if overdue:
                st.divider()
                st.markdown("**Manually post overdue items:**")
                for r in overdue:
                    if r.get("auto_post"):
                        continue  # auto-posted items handled by engine
                    if st.button(f"Post '{r['name']}' now",
                                 key=f"manual_post_{r['id']}"):
                        # Re-run posting for this specific item
                        result = _run_auto_posting(user_id, today)
                        st.session_state.pop(_ap_key, None)
                        st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 4 — DEBT / LOAN TRACKER
    # ─────────────────────────────────────────────────────────────────────────
    with tab_debt:
        st.subheader("Debt & Loan Tracker")
        st.caption("Track borrowed and lent money — personal or business — with full payment history.")

        DEBT_CATEGORIES = [
            "Personal", "Business", "Bank Loan", "Credit Card",
            "Family / Friend", "BNPL / Hire Purchase", "Mortgage", "Other",
        ]

        # ── Add new debt form ─────────────────────────────────────────────────
        with st.expander("➕ Add debt or loan", expanded=False):
            with st.form("add_debt"):
                c_top1, c_top2 = st.columns(2)
                with c_top1:
                    d_name = st.text_input("Name / Description",
                                           placeholder="e.g. GTB loan, Owe Chike ₦50k")
                    d_cat  = st.selectbox("Category", DEBT_CATEGORIES)
                with c_top2:
                    d_type = st.radio(
                        "Type", ["borrowed", "lent"],
                        format_func=lambda x: "📥 I borrowed this" if x == "borrowed" else "📤 I lent this"
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
                        full_notes = f"[{d_cat}] {d_notes.strip()}".strip()
                        with get_db() as (conn, cursor):
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

        # ── Load debts + payment history ──────────────────────────────────────
        import re as _re
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT id, name, type, principal, balance_remaining, interest_rate,
                       monthly_payment, due_date, counterparty, notes, status
                FROM debts WHERE user_id=%s ORDER BY status, due_date NULLS LAST
            """, (user_id,))
            debts = cursor.fetchall()

            # Load all payment history in one query
            if debts:
                debt_ids  = tuple(d["id"] for d in debts)
                ph_clause = "IN %s" if len(debt_ids) > 1 else "= %s"
                ph_param  = (debt_ids,) if len(debt_ids) > 1 else (debt_ids[0],)
                cursor.execute(f"""
                    SELECT debt_id, amount, payment_date, note
                    FROM debt_payments
                    WHERE debt_id {ph_clause}
                    ORDER BY payment_date DESC, created_at DESC
                """, ph_param)
                all_payments = cursor.fetchall()
            else:
                all_payments = []

        # Group payments by debt_id
        payments_by_debt: dict = {}
        for p in all_payments:
            payments_by_debt.setdefault(p["debt_id"], []).append(p)

        if not debts:
            st.info("No debts or loans tracked yet. Use the form above to add one.")
        else:
            active_debts  = [d for d in debts if d["status"] == "active"]
            total_owe     = sum(d["balance_remaining"] for d in active_debts if d["type"] == "borrowed")
            total_owed    = sum(d["balance_remaining"] for d in active_debts if d["type"] == "lent")
            total_monthly = sum(d["monthly_payment"]   for d in active_debts if d["type"] == "borrowed")
            total_repaid  = sum(sum(p["amount"] for p in payments_by_debt.get(d["id"], []))
                                for d in debts)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("You owe (active)",       f"NGN {total_owe:,}")
            c2.metric("Owed to you (active)",   f"NGN {total_owed:,}")
            c3.metric("Monthly repayments",     f"NGN {total_monthly:,}")
            c4.metric("Total repaid (all time)", f"NGN {total_repaid:,}")
            st.divider()

            for d in debts:
                is_lent   = d["type"] == "lent"
                principal = int(d["principal"])
                balance   = int(d["balance_remaining"])
                paid      = principal - balance
                pct_paid  = round(paid / principal * 100, 1) if principal > 0 else 0
                color     = "#0e7c5b" if is_lent else "#c0392b"
                direction = "📤 Lent" if is_lent else "📥 Borrowed"

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
                    'padding:1px 8px;font-size:0.72rem;font-weight:600;">Paid ✓</span>'
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

                    # ── Payment history inline ────────────────────────────────
                    debt_pmts = payments_by_debt.get(d["id"], [])
                    if debt_pmts:
                        hist_key = f"show_hist_{d['id']}"
                        if st.button(
                            f"📋 History ({len(debt_pmts)} payment{'s' if len(debt_pmts) != 1 else ''})",
                            key=f"hist_btn_{d['id']}"
                        ):
                            st.session_state[hist_key] = not st.session_state.get(hist_key, False)

                        if st.session_state.get(hist_key, False):
                            total_via_payments = sum(p["amount"] for p in debt_pmts)
                            st.markdown(
                                f'<div style="background:#f8fbf9;border-radius:8px;'
                                f'padding:10px 14px;margin:4px 0 8px;">'
                                f'<strong>Repayment History</strong> &mdash; '
                                f'Total paid: NGN {total_via_payments:,}</div>',
                                unsafe_allow_html=True
                            )
                            for p in debt_pmts:
                                note_str = f" — {p['note']}" if p.get("note") else ""
                                st.markdown(
                                    f'<div style="display:flex;justify-content:space-between;'
                                    f'padding:5px 14px;border-bottom:1px solid #e8f0ea;'
                                    f'font-size:0.88rem;">'
                                    f'<span style="color:#4a6070;">{p["payment_date"]}{note_str}</span>'
                                    f'<span style="color:#0e7c5b;font-weight:700;">'
                                    f'NGN {int(p["amount"]):,}</span>'
                                    f'</div>',
                                    unsafe_allow_html=True
                                )

                with col_act:
                    if d["status"] == "active":
                        # Mark fully paid
                        if st.button("✅ Paid", key=f"dp_{d['id']}", use_container_width=True,
                                     help="Mark as fully paid"):
                            with get_db() as (conn, cursor):
                                # Record final payment as payment history
                                if balance > 0:
                                    cursor.execute("""
                                        INSERT INTO debt_payments
                                            (debt_id, user_id, amount, payment_date, note)
                                        VALUES (%s,%s,%s,%s,'Marked as fully paid')
                                    """, (d["id"], user_id, balance, today))
                                cursor.execute(
                                    "UPDATE debts SET status='paid', balance_remaining=0 "
                                    "WHERE id=%s AND user_id=%s", (d["id"], user_id)
                                )
                            st.rerun()

                        # Record partial payment
                        pay_key = f"show_pay_{d['id']}"
                        if st.button("💳 Pay", key=f"pp_{d['id']}", use_container_width=True,
                                     help="Record a partial payment"):
                            st.session_state[pay_key] = not st.session_state.get(pay_key, False)
                            st.rerun()

                        if st.session_state.get(pay_key, False):
                            with st.form(f"partial_pay_{d['id']}"):
                                amt_paid = st.number_input(
                                    "Payment amount (NGN)",
                                    min_value=1, max_value=balance, step=500,
                                    key=f"pay_amt_{d['id']}"
                                )
                                pay_note = st.text_input("Note (optional)", key=f"pay_note_{d['id']}")
                                if st.form_submit_button("Record payment", type="primary"):
                                    new_balance = max(balance - int(amt_paid), 0)
                                    new_status  = "paid" if new_balance == 0 else "active"
                                    with get_db() as (conn, cursor):
                                        # Record in payment history
                                        cursor.execute("""
                                            INSERT INTO debt_payments
                                                (debt_id, user_id, amount, payment_date, note)
                                            VALUES (%s,%s,%s,%s,%s)
                                        """, (d["id"], user_id, int(amt_paid), today,
                                              pay_note.strip() or None))
                                        # Update debt balance
                                        cursor.execute(
                                            "UPDATE debts SET balance_remaining=%s, status=%s "
                                            "WHERE id=%s AND user_id=%s",
                                            (new_balance, new_status, d["id"], user_id)
                                        )
                                    st.session_state.pop(pay_key, None)
                                    msg = (f"NGN {int(amt_paid):,} recorded. "
                                           + ("Debt fully cleared! 🎉" if new_balance == 0
                                              else f"NGN {new_balance:,} remaining."))
                                    st.success(msg)
                                    st.rerun()

                    dk = f"debt_{d['id']}"
                    if st.session_state.confirm_delete.get(dk):
                        if st.button("✓", key=f"dy_{d['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM debts WHERE id=%s AND user_id=%s",
                                               (d["id"], user_id))
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                        if st.button("✗", key=f"dn_{d['id']}"):
                            st.session_state.confirm_delete.pop(dk, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"dd_{d['id']}", help="Delete"):
                            st.session_state.confirm_delete[dk] = True; st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 5 — EMERGENCY FUND PLANNER
    # ─────────────────────────────────────────────────────────────────────────
    with tab_ef:
        st.subheader("Emergency Fund Planner")
        st.caption(
            "An emergency fund covers 3–6 months of living expenses. "
            "It protects you from job loss, medical bills, or unexpected crises."
        )

        with get_db() as (conn, cursor):
            cursor.execute("SELECT * FROM emergency_fund_plan WHERE user_id=%s", (user_id,))
            ef = cursor.fetchone()

            # Auto-estimate from last 3 months of actual spending
            three_months_ago = today.replace(day=1)
            for _ in range(2):
                three_months_ago = (three_months_ago - timedelta(days=1)).replace(day=1)
            cursor.execute("""
                SELECT COALESCE(SUM(t.amount), 0) AS total
                FROM transactions t JOIN banks b ON t.bank_id = b.id
                WHERE b.user_id = %s AND t.type = 'debit'
                  AND t.created_at >= %s AND t.created_at < %s
            """, (user_id, three_months_ago, today.replace(day=1)))
            three_mo_total = int(cursor.fetchone()["total"] or 0)
            actual_avg_monthly = three_mo_total // 3 if three_mo_total > 0 else 0

            cursor.execute("""
                SELECT COALESCE(SUM(t.amount), 0) AS total
                FROM transactions t JOIN banks b ON t.bank_id = b.id
                WHERE b.user_id = %s AND t.type = 'credit' AND t.created_at >= %s
            """, (user_id, today.replace(day=1)))
            income_this_month = int(cursor.fetchone()["total"] or 0)

            # Check for a linked savings goal
            linked_goal = None
            if ef and ef.get("goal_id"):
                cursor.execute(
                    "SELECT id, name, target_amount, current_amount, status "
                    "FROM goals WHERE id=%s AND user_id=%s",
                    (ef["goal_id"], user_id)
                )
                linked_goal = cursor.fetchone()

            # Look for an existing "Emergency Fund" goal to auto-link
            if not linked_goal:
                cursor.execute("""
                    SELECT id, name, target_amount, current_amount, status
                    FROM goals
                    WHERE user_id=%s AND status='active'
                      AND LOWER(name) LIKE '%emergency%'
                    ORDER BY created_at LIMIT 1
                """, (user_id,))
                linked_goal = cursor.fetchone()
                # Auto-link it
                if linked_goal and ef:
                    cursor.execute(
                        "UPDATE emergency_fund_plan SET goal_id=%s WHERE user_id=%s",
                        (linked_goal["id"], user_id)
                    )

        if actual_avg_monthly > 0:
            st.info(
                f"📊 Your average monthly expenses over the last 3 months: "
                f"**NGN {actual_avg_monthly:,}**. Used as the default below — adjust if needed."
            )

        # ── Linked savings goal banner ────────────────────────────────────────
        if linked_goal:
            g_pct = round(
                int(linked_goal["current_amount"]) / int(linked_goal["target_amount"]) * 100, 1
            ) if linked_goal["target_amount"] > 0 else 0
            st.markdown(
                f'<div style="background:#e8f5f0;border-radius:10px;padding:12px 16px;'
                f'margin-bottom:12px;border-left:4px solid #0e7c5b;">'
                f'<strong>🔗 Linked Savings Goal:</strong> {linked_goal["name"]} &mdash; '
                f'NGN {int(linked_goal["current_amount"]):,} saved of '
                f'NGN {int(linked_goal["target_amount"]):,} ({g_pct:.0f}%)'
                f'</div>',
                unsafe_allow_html=True
            )

        # ── Input form ────────────────────────────────────────────────────────
        with st.form("ef_form"):
            st.markdown("#### Step 1 — Set your target")
            c1, c2 = st.columns(2)
            with c1:
                ef_months = st.slider(
                    "How many months of expenses to save?",
                    min_value=1, max_value=12,
                    value=int(ef["target_months"]) if ef else 3
                )
            with c2:
                default_monthly = (
                    int(ef["monthly_expenses_estimate"])
                    if ef and ef["monthly_expenses_estimate"]
                    else actual_avg_monthly
                )
                ef_monthly = st.number_input(
                    "Your monthly expenses (NGN)",
                    min_value=0, step=1000, value=default_monthly
                )

            st.markdown("#### Step 2 — Where are you now?")
            # Use linked goal's current_amount if available
            default_saved = (
                int(linked_goal["current_amount"])
                if linked_goal
                else (int(ef["current_saved"]) if ef else 0)
            )
            ef_saved = st.number_input(
                "Amount already saved (NGN)",
                min_value=0, step=1000, value=default_saved,
                help="Pre-filled from your linked Emergency Fund goal if one exists"
            )

            st.markdown("#### Step 3 — How much can you contribute monthly?")
            suggested = max(-(-max((ef_months * (ef_monthly or 0)) - (ef_saved or 0), 0) // 6), 1000)
            ef_contribution = st.number_input(
                "Monthly contribution (NGN)",
                min_value=0, step=500, value=suggested
            )

            ef_saved_btn = st.form_submit_button("Calculate & Save Plan", type="primary")

        if ef_saved_btn:
            with get_db() as (conn, cursor):
                cursor.execute("""
                    INSERT INTO emergency_fund_plan
                        (user_id, target_months, monthly_expenses_estimate, current_saved, updated_at)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        target_months             = EXCLUDED.target_months,
                        monthly_expenses_estimate = EXCLUDED.monthly_expenses_estimate,
                        current_saved             = EXCLUDED.current_saved,
                        updated_at                = EXCLUDED.updated_at
                """, (user_id, ef_months, int(ef_monthly), int(ef_saved), today))
            st.success("Plan saved.")
            st.rerun()

        # ── Resolve working values ────────────────────────────────────────────
        _months       = ef_months       if ef_saved_btn else (int(ef["target_months"])             if ef else 3)
        _monthly      = ef_monthly      if ef_saved_btn else (int(ef["monthly_expenses_estimate"]) if ef and ef["monthly_expenses_estimate"] else actual_avg_monthly)
        _saved        = ef_saved        if ef_saved_btn else default_saved
        _contribution = ef_contribution if ef_saved_btn else suggested

        if _monthly > 0:
            target    = _months * _monthly
            shortfall = max(target - _saved, 0)
            pct       = min(round(_saved / target * 100, 1), 100) if target > 0 else 0

            # ── Metrics ───────────────────────────────────────────────────────
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"Target ({_months}-month)",  f"NGN {target:,}",
                      help=f"{_months} months × NGN {_monthly:,}")
            c2.metric("Saved so far",  f"NGN {_saved:,}")
            c3.metric("Still needed",  f"NGN {shortfall:,}")
            if income_this_month > 0:
                savings_pct = round(_contribution / income_this_month * 100, 1)
                c4.metric("% of income", f"{savings_pct:.1f}%",
                          help="Monthly contribution as % of this month's income")
            else:
                c4.metric("Monthly contribution", f"NGN {_contribution:,}")

            st.progress(pct / 100,
                        text=f"{pct:.0f}% complete — NGN {_saved:,} of NGN {target:,}")

            if shortfall > 0 and _contribution > 0:
                months_needed = math.ceil(shortfall / _contribution)

                # Weekly savings equivalent
                weekly_needed = math.ceil(shortfall / (months_needed * 4.33))

                # Completion date
                completion = today.replace(day=1)
                for _ in range(months_needed):
                    if completion.month == 12:
                        completion = completion.replace(year=completion.year + 1, month=1)
                    else:
                        completion = completion.replace(month=completion.month + 1)

                # ── Completion banner ─────────────────────────────────────────
                st.markdown(
                    f'<div style="background:linear-gradient(90deg,#1a3c5e,#0e7c5b);'
                    f'border-radius:12px;padding:16px 20px;margin:12px 0;color:#fff;">'
                    f'<div style="font-size:0.8rem;color:#a8d8c8;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.05em;">Completion estimate</div>'
                    f'<div style="font-size:1.5rem;font-weight:800;margin:4px 0;">'
                    f'{completion.strftime("%B %Y")}</div>'
                    f'<div style="font-size:0.88rem;color:#d4eee6;">'
                    f'Save <strong>NGN {_contribution:,}/month</strong> '
                    f'(or <strong>NGN {weekly_needed:,}/week</strong>) &rarr; '
                    f'fund complete in <strong>{months_needed} month'
                    f'{"s" if months_needed != 1 else ""}</strong>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

                # ── Three standard scenarios ──────────────────────────────────
                st.markdown("**Compare saving scenarios:**")
                cols = st.columns(3)
                for col, n_months in zip(cols, [3, 6, 12]):
                    mo_needed    = -(-shortfall // n_months)
                    wk_needed    = math.ceil(mo_needed / 4.33)
                    comp_date    = today.replace(day=1)
                    for _ in range(n_months):
                        if comp_date.month == 12:
                            comp_date = comp_date.replace(year=comp_date.year + 1, month=1)
                        else:
                            comp_date = comp_date.replace(month=comp_date.month + 1)
                    col.markdown(
                        f'<div style="background:#f0f7f4;border-radius:10px;padding:14px;text-align:center;">'
                        f'<div style="font-size:0.75rem;color:#4a6070;font-weight:600;">'
                        f'Done in {n_months} months</div>'
                        f'<div style="font-size:1.1rem;font-weight:800;color:#1a3c5e;">'
                        f'NGN {mo_needed:,}/mo</div>'
                        f'<div style="font-size:0.78rem;color:#0e7c5b;">'
                        f'≈ NGN {wk_needed:,}/week</div>'
                        f'<div style="font-size:0.72rem;color:#95a5a6;">by {comp_date.strftime("%b %Y")}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                st.markdown("<br>", unsafe_allow_html=True)
                st.info(
                    f"💡 Tip: {'Link this plan to your Emergency Fund savings goal above, or create' if not linked_goal else 'Your linked savings goal is active. Also consider creating'} "
                    f"a recurring deposit of NGN {_contribution:,}/month. "
                    f"You'll be fully funded by **{completion.strftime('%B %Y')}**."
                )

            elif shortfall > 0 and _contribution == 0:
                st.warning("Set a monthly contribution above to see your completion date.")
            else:
                st.success(
                    f"✅ Emergency fund target of NGN {target:,} fully covered! "
                    f"Excellent financial discipline."
                )

            if ef and ef.get("updated_at"):
                st.caption(f"Last updated: {ef['updated_at']}")
        else:
            st.info("Enter your monthly expenses above to start the calculator.")
