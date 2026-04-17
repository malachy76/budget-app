# tracker.py — Tracker page
# Tabs: Recurring Income | Recurring Expenses | Bill Reminders | Debt/Loan | Emergency Fund
import streamlit as st
from datetime import datetime, timedelta

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
    # monthly
    if today.month == 12:
        return today.replace(year=today.year + 1, month=1, day=1)
    return today.replace(month=today.month + 1, day=1)


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


def render_tracker(user_id):
    st.markdown("## Tracker")
    st.caption("Recurring income & expenses, bill reminders, debts, and your emergency fund.")

    today = datetime.now().date()

    # Load banks once for all tabs
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, bank_name, account_number FROM banks WHERE user_id=%s ORDER BY bank_name",
            (user_id,)
        )
        banks = cursor.fetchall()

    bank_map  = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in banks}
    bank_opts = list(bank_map.keys())

    tab_ri, tab_re, tab_bill, tab_debt, tab_ef = st.tabs([
        "&#x1F4B0; Recurring Income",
        "&#x1F4B8; Recurring Expenses",
        "&#x1F514; Bill Reminders",
        "&#x1F4B3; Debt / Loan",
        "&#x1F6E1; Emergency Fund",
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

        # Load + display
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.amount, r.frequency, r.next_due,
                       r.auto_post, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id=%s AND r.type='income'
                ORDER BY r.next_due NULLS LAST
            """, (user_id,))
            rec_incomes = cursor.fetchall()

        if not rec_incomes:
            st.info("No recurring income yet. Use the form above to add salary, freelance, or rental income.")
        else:
            # Summary metric
            total_monthly_income = sum(
                r["amount"] * FREQ_MULT.get(r["frequency"], 1) for r in rec_incomes
            )
            st.caption(f"Estimated monthly recurring income: **NGN {int(total_monthly_income):,}**")

            for ri in rec_incomes:
                due_label, due_color = _due_badge(ri["next_due"], today)
                col_card, col_del = st.columns([6, 0.5])
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
                SELECT r.id, r.name, r.category, r.amount, r.frequency, r.next_due, b.bank_name
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
                col_card, col_del = st.columns([6, 0.5])
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
            st.info("No items due in the next 30 days. Add recurring income or expenses on the other tabs.")
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

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 4 — DEBT / LOAN TRACKER
    # ─────────────────────────────────────────────────────────────────────────
    with tab_debt:
        st.subheader("Debt & Loan Tracker")
        st.caption("Track money you owe (borrowed) and money owed to you (lent) — personal or business.")

        DEBT_CATEGORIES = [
            "Personal", "Business", "Bank Loan", "Credit Card",
            "Family / Friend", "BNPL / Hire Purchase", "Mortgage", "Other",
        ]

        # ── Add form ─────────────────────────────────────────────────────────
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
                    d_remaining = st.number_input("Balance still owed (NGN)", min_value=0, step=1000,
                                                  help="How much is left to pay/receive right now")
                    d_monthly   = st.number_input("Monthly payment (NGN, 0 if none)", min_value=0, step=500,
                                                  help="Regular monthly repayment amount")
                with c2:
                    d_rate  = st.number_input("Interest rate (% p.a., 0 if none)", min_value=0.0, step=0.5)
                    d_due   = st.date_input("Due / repayment date")
                    d_party = st.text_input("Counterparty (person or bank name)")
                d_notes = st.text_area("Notes (optional)", height=60,
                                       placeholder="e.g. Collateral, loan purpose, agreement terms")
                if st.form_submit_button("Add Debt / Loan", type="primary"):
                    if d_name and d_principal > 0:
                        with get_db() as (conn, cursor):
                            # Add category to notes since debts table has no category column
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

        # ── Load all debts ────────────────────────────────────────────────────
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
            # ── Summary metrics ───────────────────────────────────────────────
            active_debts  = [d for d in debts if d["status"] == "active"]
            total_owe     = sum(d["balance_remaining"] for d in active_debts if d["type"] == "borrowed")
            total_owed    = sum(d["balance_remaining"] for d in active_debts if d["type"] == "lent")
            total_monthly = sum(d["monthly_payment"] for d in active_debts if d["type"] == "borrowed")
            c1, c2, c3 = st.columns(3)
            c1.metric("You owe (total)",      f"NGN {total_owe:,}")
            c2.metric("Owed to you (total)",  f"NGN {total_owed:,}")
            c3.metric("Monthly repayments",   f"NGN {total_monthly:,}",
                      help="Sum of all your active monthly debt payments")
            st.divider()

            for d in debts:
                is_lent   = d["type"] == "lent"
                principal = int(d["principal"])
                balance   = int(d["balance_remaining"])
                paid      = principal - balance
                pct_paid  = round(paid / principal * 100, 1) if principal > 0 else 0
                color     = "#0e7c5b" if is_lent else "#c0392b"
                direction = "📤 Lent" if is_lent else "📥 Borrowed"

                # Extract category from notes prefix [Category]
                import re as _re
                notes_raw = d["notes"] or ""
                cat_match = _re.match(r'^\[([^\]]+)\]', notes_raw)
                debt_cat  = cat_match.group(1) if cat_match else ""
                clean_notes = notes_raw[len(f"[{debt_cat}]"):].strip() if debt_cat else notes_raw

                # Payoff timeline
                monthly_pmt = int(d["monthly_payment"] or 0)
                if monthly_pmt > 0 and balance > 0 and d["status"] == "active":
                    months_left = -(-balance // monthly_pmt)  # ceiling division
                    payoff_str  = f"{months_left} month{'s' if months_left != 1 else ''} at NGN {monthly_pmt:,}/mo"
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
                # Progress bar HTML
                bar_pct  = min(pct_paid, 100)
                bar_color = "#0e7c5b" if pct_paid >= 100 else ("#f39c12" if pct_paid >= 50 else color)
                progress_html = (
                    f'<div style="background:#eef5f2;border-radius:6px;height:7px;margin-top:6px;overflow:hidden;">'
                    f'<div style="background:{bar_color};width:{bar_pct:.1f}%;height:7px;border-radius:6px;"></div>'
                    f'</div>'
                    f'<div style="font-size:0.72rem;color:#95a5a6;margin-top:3px;">'
                    f'NGN {paid:,} paid of NGN {principal:,} ({pct_paid:.0f}%)'
                    f'</div>'
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
                        if st.button("✅ Paid", key=f"dp_{d['id']}", use_container_width=True,
                                     help="Mark as fully paid"):
                            with get_db() as (conn, cursor):
                                cursor.execute(
                                    "UPDATE debts SET status='paid', balance_remaining=0 "
                                    "WHERE id=%s AND user_id=%s", (d["id"], user_id)
                                )
                            st.rerun()

                        # Record a partial payment
                        pay_key = f"show_pay_{d['id']}"
                        if st.button("💳 Pay", key=f"pp_{d['id']}", use_container_width=True,
                                     help="Record a partial payment"):
                            st.session_state[pay_key] = not st.session_state.get(pay_key, False)
                            st.rerun()

                        if st.session_state.get(pay_key, False):
                            with st.form(f"partial_pay_{d['id']}"):
                                amt_paid = st.number_input(
                                    "Payment amount (NGN)",
                                    min_value=1,
                                    max_value=balance,
                                    step=500,
                                    key=f"pay_amt_{d['id']}"
                                )
                                if st.form_submit_button("Record payment"):
                                    new_balance = max(balance - int(amt_paid), 0)
                                    new_status  = "paid" if new_balance == 0 else "active"
                                    with get_db() as (conn, cursor):
                                        cursor.execute(
                                            "UPDATE debts SET balance_remaining=%s, status=%s "
                                            "WHERE id=%s AND user_id=%s",
                                            (new_balance, new_status, d["id"], user_id)
                                        )
                                    st.session_state.pop(pay_key, None)
                                    st.success(f"NGN {int(amt_paid):,} recorded. "
                                               f"{'Debt fully cleared!' if new_balance == 0 else f'NGN {new_balance:,} remaining.'}")
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

        # ── Pull actual avg monthly spending from last 3 months ──────────────
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
            three_mo_total = int(cursor.fetchone()["total"] or 0)
            actual_avg_monthly = three_mo_total // 3 if three_mo_total > 0 else 0

            cursor.execute("""
                SELECT COALESCE(SUM(t.amount), 0) AS total
                FROM transactions t JOIN banks b ON t.bank_id = b.id
                WHERE b.user_id = %s AND t.type = 'credit'
                  AND t.created_at >= %s
            """, (user_id, today.replace(day=1)))
            income_this_month = int(cursor.fetchone()["total"] or 0)

        # ── Auto-populate hint ────────────────────────────────────────────────
        if actual_avg_monthly > 0:
            st.info(
                f"📊 Based on your last 3 months of spending, your average monthly expenses are "
                f"**NGN {actual_avg_monthly:,}**. We've used this as the default below — adjust if needed."
            )

        # ── Input form ────────────────────────────────────────────────────────
        with st.form("ef_form"):
            st.markdown("#### Step 1 — Set your target")
            c1, c2 = st.columns(2)
            with c1:
                ef_months = st.slider(
                    "How many months of expenses to save?",
                    min_value=1, max_value=12,
                    value=int(ef["target_months"]) if ef else 3,
                    help="3 months is the minimum recommended; 6 months is ideal"
                )
            with c2:
                default_monthly = (
                    int(ef["monthly_expenses_estimate"]) if ef and ef["monthly_expenses_estimate"]
                    else actual_avg_monthly
                )
                ef_monthly = st.number_input(
                    "Your monthly expenses (NGN)",
                    min_value=0, step=1000,
                    value=default_monthly,
                    help="Your average monthly spend on essentials — rent, food, transport, bills"
                )

            st.markdown("#### Step 2 — Where are you now?")
            ef_saved = st.number_input(
                "Amount already saved towards emergency fund (NGN)",
                min_value=0, step=1000,
                value=int(ef["current_saved"]) if ef else 0
            )

            st.markdown("#### Step 3 — How much can you save monthly?")
            suggested = max(-(-max(ef_months * (ef_monthly or 0) - (ef_saved or 0), 0) // 6), 1000)
            ef_contribution = st.number_input(
                "Monthly contribution towards emergency fund (NGN)",
                min_value=0, step=500,
                value=suggested,
                help="How much you plan to set aside each month specifically for this fund"
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

        # ── Resolve working values ────────────────────────────────────────────
        _months       = ef_months       if ef_saved_btn else (int(ef["target_months"])             if ef else 3)
        _monthly      = ef_monthly      if ef_saved_btn else (int(ef["monthly_expenses_estimate"]) if ef and ef["monthly_expenses_estimate"] else actual_avg_monthly)
        _saved        = ef_saved        if ef_saved_btn else (int(ef["current_saved"])             if ef else 0)
        _contribution = ef_contribution if ef_saved_btn else suggested

        if _monthly > 0:
            import math as _math
            from datetime import date as _date

            target    = _months * _monthly
            shortfall = max(target - _saved, 0)
            pct       = min(round(_saved / target * 100, 1), 100) if target > 0 else 0

            # ── Key metrics ───────────────────────────────────────────────────
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                f"Target ({_months}-month fund)",
                f"NGN {target:,}",
                help=f"{_months} months × NGN {_monthly:,}/mo"
            )
            c2.metric("Saved so far",   f"NGN {_saved:,}")
            c3.metric("Still needed",   f"NGN {shortfall:,}")
            if income_this_month > 0 and _monthly > 0:
                savings_pct = round(_contribution / income_this_month * 100, 1)
                c4.metric("% of income",  f"{savings_pct:.1f}%",
                          help="Monthly contribution as % of this month's income")
            else:
                c4.metric("Monthly contribution", f"NGN {_contribution:,}")

            # ── Progress bar ──────────────────────────────────────────────────
            st.progress(
                pct / 100,
                text=f"{pct:.0f}% complete — NGN {_saved:,} of NGN {target:,}"
            )

            if shortfall > 0 and _contribution > 0:
                # ── Completion date calculator ────────────────────────────────
                months_needed = _math.ceil(shortfall / _contribution)
                completion    = today.replace(day=1)
                for _ in range(months_needed):
                    if completion.month == 12:
                        completion = completion.replace(year=completion.year + 1, month=1)
                    else:
                        completion = completion.replace(month=completion.month + 1)

                st.markdown(
                    f'<div style="background:linear-gradient(90deg,#1a3c5e,#0e7c5b);'
                    f'border-radius:12px;padding:16px 20px;margin:12px 0;color:#fff;">'
                    f'<div style="font-size:0.8rem;color:#a8d8c8;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.05em;">Completion estimate</div>'
                    f'<div style="font-size:1.5rem;font-weight:800;margin:4px 0;">'
                    f'{completion.strftime("%B %Y")}</div>'
                    f'<div style="font-size:0.88rem;color:#d4eee6;">'
                    f'Save NGN {_contribution:,}/month &rarr; fund complete in '
                    f'<strong>{months_needed} month{"s" if months_needed != 1 else ""}</strong>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # ── Three standard scenarios ──────────────────────────────────
                st.markdown("**Compare saving scenarios:**")
                cols = st.columns(3)
                for col, n_months in zip(cols, [3, 6, 12]):
                    mo_needed  = -(-shortfall // n_months)
                    comp_date  = today.replace(day=1)
                    for _ in range(n_months):
                        if comp_date.month == 12:
                            comp_date = comp_date.replace(year=comp_date.year + 1, month=1)
                        else:
                            comp_date = comp_date.replace(month=comp_date.month + 1)
                    col.markdown(
                        f'<div style="background:#f0f7f4;border-radius:10px;'
                        f'padding:14px;text-align:center;">'
                        f'<div style="font-size:0.75rem;color:#4a6070;font-weight:600;">'
                        f'Done in {n_months} months</div>'
                        f'<div style="font-size:1.15rem;font-weight:800;color:#1a3c5e;">'
                        f'NGN {mo_needed:,}/mo</div>'
                        f'<div style="font-size:0.72rem;color:#95a5a6;">'
                        f'by {comp_date.strftime("%b %Y")}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                st.markdown("<br>", unsafe_allow_html=True)
                st.info(
                    f"💡 Tip: Open a separate **Savings Goal** called 'Emergency Fund' and "
                    f"auto-transfer NGN {_contribution:,} into it every month. "
                    f"At that rate you'll be fully funded by **{completion.strftime('%B %Y')}**."
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
