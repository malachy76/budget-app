# _pages/tracker.py
# Tabs: Recurring Items | Bill Reminders | Debt / Loan Tracker | Emergency Fund
import streamlit as st
from datetime import datetime, date, timedelta
from db import get_db

# ── helpers ───────────────────────────────────────────────────────────────────

FREQ_LABELS   = ["daily", "weekly", "monthly", "yearly"]
FREQ_DELTAS   = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}

def _advance_due(current_due: date, frequency: str) -> date:
    """Return the next due date after current_due based on frequency."""
    today = date.today()
    d = current_due or today
    if frequency == "daily":
        d += timedelta(days=1)
    elif frequency == "weekly":
        d += timedelta(weeks=1)
    elif frequency == "yearly":
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:
            d = d + timedelta(days=365)
    else:  # monthly
        month = d.month + 1
        year  = d.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        d = d.replace(year=year, month=month, day=min(d.day, last_day))
    return d


def _auto_post_due_items(user_id: int):
    """Post any auto_post=1 recurring items that are due today or overdue."""
    today = date.today()
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT * FROM recurring_items
            WHERE user_id=%s AND active=1 AND auto_post=1
              AND next_due IS NOT NULL AND next_due <= %s
        """, (user_id, today))
        due_items = cursor.fetchall()

        for item in due_items:
            bank_id = item["bank_id"]
            if not bank_id:
                continue
            amt  = int(item["amount"])
            name = item["name"]
            itype = item["type"]
            cat  = item["category"] or name

            if itype == "expense":
                cursor.execute("SELECT balance FROM banks WHERE id=%s AND user_id=%s", (bank_id, user_id))
                bank = cursor.fetchone()
                if not bank or bank["balance"] - amt < 0:
                    continue  # skip — not enough balance, let user handle manually
                cursor.execute(
                    "INSERT INTO transactions (bank_id,type,amount,description,created_at) VALUES (%s,'debit',%s,%s,%s) RETURNING id",
                    (bank_id, amt, f"Recurring: {name}", today)
                )
                tx_id = cursor.fetchone()["id"]
                cursor.execute(
                    "INSERT INTO expenses (user_id,bank_id,name,category,amount,created_at,tx_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (user_id, bank_id, name, cat, amt, today, tx_id)
                )
                cursor.execute("UPDATE banks SET balance=balance-%s WHERE id=%s", (amt, bank_id))
            else:  # income
                cursor.execute(
                    "INSERT INTO transactions (bank_id,type,amount,description,created_at) VALUES (%s,'credit',%s,%s,%s)",
                    (bank_id, amt, f"Recurring income: {name}", today)
                )
                cursor.execute("UPDATE banks SET balance=balance+%s WHERE id=%s", (amt, bank_id))

            # advance next_due
            new_due = _advance_due(item["next_due"], item["frequency"])
            cursor.execute("UPDATE recurring_items SET next_due=%s WHERE id=%s", (new_due, item["id"]))


# ── main render ───────────────────────────────────────────────────────────────

def render_tracker(user_id: int):
    st.title("📋 Tracker")

    # Auto-post anything due
    try:
        _auto_post_due_items(user_id)
    except Exception:
        pass

    tab1, tab2, tab3, tab4 = st.tabs([
        "🔁 Recurring Items",
        "🔔 Bill Reminders",
        "💳 Debts & Loans",
        "🛡️ Emergency Fund",
    ])

    with tab1:
        _render_recurring(user_id)
    with tab2:
        _render_bill_reminders(user_id)
    with tab3:
        _render_debts(user_id)
    with tab4:
        _render_emergency_fund(user_id)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — RECURRING ITEMS
# ─────────────────────────────────────────────────────────────────────────────

def _render_recurring(user_id: int):
    st.subheader("Recurring Income & Expenses")
    st.caption("Add bills, subscriptions, salary, or any amount that repeats on a schedule.")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number FROM banks WHERE user_id=%s ORDER BY bank_name", (user_id,))
        banks = cursor.fetchall()
        cursor.execute("""
            SELECT r.*, b.bank_name FROM recurring_items r
            LEFT JOIN banks b ON r.bank_id = b.id
            WHERE r.user_id=%s ORDER BY r.next_due ASC NULLS LAST, r.name
        """, (user_id,))
        items = cursor.fetchall()

    bank_map = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in banks}
    bank_options = ["(none / manual)"] + list(bank_map.keys())

    # ── Add new form ──────────────────────────────────────────────────────────
    with st.expander("➕ Add Recurring Item", expanded=not items):
        with st.form("add_recurring_form"):
            c1, c2 = st.columns(2)
            with c1:
                r_name  = st.text_input("Name *", placeholder="e.g. DSTV, Rent, Salary")
                r_type  = st.selectbox("Type *", ["expense", "income"])
                r_amt   = st.number_input("Amount (NGN) *", min_value=1, step=500)
            with c2:
                r_freq  = st.selectbox("Frequency *", FREQ_LABELS, index=2)
                r_due   = st.date_input("Next Due Date *", value=date.today())
                r_cat   = st.text_input("Category", placeholder="e.g. Subscription, Salary")
            r_bank  = st.selectbox("Bank account (optional)", bank_options)
            r_auto  = st.checkbox("Auto-post when due (deduct/credit automatically)", value=False)
            submitted = st.form_submit_button("Add Recurring Item", use_container_width=True)

        if submitted:
            if not r_name or r_amt < 1:
                st.warning("Name and amount are required.")
            else:
                bid = bank_map.get(r_bank) if r_bank != "(none / manual)" else None
                with get_db() as (conn, cursor):
                    cursor.execute("""
                        INSERT INTO recurring_items
                            (user_id, type, name, category, amount, frequency, next_due, bank_id, auto_post, active)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
                    """, (user_id, r_type, r_name, r_cat or r_name, r_amt, r_freq,
                          r_due, bid, 1 if r_auto else 0))
                st.success(f"'{r_name}' added as a recurring {r_type}.")
                st.rerun()

    if not items:
        st.info("No recurring items yet. Add one above to get started.")
        return

    # ── List ──────────────────────────────────────────────────────────────────
    today = date.today()
    income_items  = [i for i in items if i["type"] == "income"]
    expense_items = [i for i in items if i["type"] == "expense"]

    for section_label, section_items, icon in [
        ("💰 Recurring Income", income_items, "income"),
        ("💸 Recurring Expenses", expense_items, "expense"),
    ]:
        if not section_items:
            continue
        st.markdown(f"**{section_label}**")
        for item in section_items:
            next_due = item["next_due"]
            days_away = (next_due - today).days if next_due else None
            active = bool(item["active"])

            if days_away is not None:
                if days_away < 0:
                    due_label = f"🔴 Overdue by {abs(days_away)}d"
                elif days_away == 0:
                    due_label = "🟠 Due today"
                elif days_away <= 3:
                    due_label = f"🟡 Due in {days_away}d"
                else:
                    due_label = f"🟢 Due {next_due}"
            else:
                due_label = "No date set"

            with st.container():
                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                with col1:
                    auto_badge = " ⚡auto" if item["auto_post"] else ""
                    inactive_badge = " (paused)" if not active else ""
                    st.markdown(
                        f"**{item['name']}**{auto_badge}{inactive_badge}  \n"
                        f"<small style='color:#666'>{item['frequency'].capitalize()} · "
                        f"{item['category'] or ''} · "
                        f"{item['bank_name'] or 'manual'}</small>",
                        unsafe_allow_html=True
                    )
                with col2:
                    color = "#0e7c5b" if item["type"] == "income" else "#c0392b"
                    st.markdown(
                        f"<span style='font-weight:700;font-size:1rem;color:{color}'>"
                        f"NGN {int(item['amount']):,}</span>  \n"
                        f"<small>{due_label}</small>",
                        unsafe_allow_html=True
                    )
                with col3:
                    toggle_label = "Pause" if active else "Resume"
                    if st.button(toggle_label, key=f"rec_toggle_{item['id']}"):
                        with get_db() as (conn, cursor):
                            cursor.execute(
                                "UPDATE recurring_items SET active=%s WHERE id=%s AND user_id=%s",
                                (0 if active else 1, item["id"], user_id)
                            )
                        st.rerun()
                with col4:
                    if st.button("Delete", key=f"rec_del_{item['id']}"):
                        with get_db() as (conn, cursor):
                            cursor.execute(
                                "DELETE FROM recurring_items WHERE id=%s AND user_id=%s",
                                (item["id"], user_id)
                            )
                        st.rerun()
            st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — BILL REMINDERS (upcoming in next 30 days)
# ─────────────────────────────────────────────────────────────────────────────

def _render_bill_reminders(user_id: int):
    st.subheader("Upcoming Bills (Next 30 Days)")
    st.caption("All recurring expenses with a due date in the next 30 days, sorted by urgency.")

    today  = date.today()
    cutoff = today + timedelta(days=30)

    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT r.*, b.bank_name, b.balance AS bank_balance
            FROM recurring_items r
            LEFT JOIN banks b ON r.bank_id = b.id
            WHERE r.user_id=%s AND r.active=1 AND r.type='expense'
              AND r.next_due IS NOT NULL AND r.next_due <= %s
            ORDER BY r.next_due ASC
        """, (user_id, cutoff))
        bills = cursor.fetchall()

        # Also include income so the user can see expected inflows
        cursor.execute("""
            SELECT r.*, b.bank_name, b.balance AS bank_balance
            FROM recurring_items r
            LEFT JOIN banks b ON r.bank_id = b.id
            WHERE r.user_id=%s AND r.active=1 AND r.type='income'
              AND r.next_due IS NOT NULL AND r.next_due <= %s
            ORDER BY r.next_due ASC
        """, (user_id, cutoff))
        income_due = cursor.fetchall()

    all_due = sorted(list(bills) + list(income_due), key=lambda r: r["next_due"])

    if not all_due:
        st.success("No upcoming bills or income in the next 30 days.")
        st.info("Add recurring items on the **Recurring Items** tab to see them here.")
        return

    total_bills   = sum(int(r["amount"]) for r in bills)
    total_income  = sum(int(r["amount"]) for r in income_due)

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Bills Due (30d)", f"NGN {total_bills:,}")
    mc2.metric("Income Expected (30d)", f"NGN {total_income:,}")
    mc3.metric("Net", f"NGN {total_income - total_bills:,}")
    st.divider()

    for r in all_due:
        days_away = (r["next_due"] - today).days
        is_income = r["type"] == "income"

        if days_away < 0:
            status_color = "#c0392b"
            status_icon  = "🔴"
            status_text  = f"Overdue by {abs(days_away)} day(s)"
        elif days_away == 0:
            status_color = "#e67e22"
            status_icon  = "🟠"
            status_text  = "Due TODAY"
        elif days_away <= 3:
            status_color = "#f39c12"
            status_icon  = "🟡"
            status_text  = f"Due in {days_away} day(s)"
        elif days_away <= 7:
            status_color = "#2980b9"
            status_icon  = "🔵"
            status_text  = f"Due in {days_away} day(s)"
        else:
            status_color = "#27ae60"
            status_icon  = "🟢"
            status_text  = f"Due {r['next_due']}"

        amount_color = "#0e7c5b" if is_income else "#c0392b"
        amount_sign  = "+" if is_income else "-"
        bank_info    = f" · {r['bank_name']}" if r["bank_name"] else ""

        # Warn if bank balance might be too low
        balance_warn = ""
        if not is_income and r["bank_balance"] is not None:
            if int(r["bank_balance"]) < int(r["amount"]):
                shortfall = int(r["amount"]) - int(r["bank_balance"])
                balance_warn = f" ⚠️ Balance short by NGN {shortfall:,}"

        st.markdown(
            f"""<div style='background:#f8f9fa;border-left:4px solid {status_color};
            border-radius:8px;padding:12px 16px;margin-bottom:8px;'>
            <div style='display:flex;justify-content:space-between;align-items:center;'>
            <div>
              <span style='font-weight:700;font-size:0.97rem'>{status_icon} {r['name']}</span>
              <span style='font-size:0.8rem;color:#666;margin-left:8px'>{r['frequency'].capitalize()}{bank_info}</span>
              {f"<span style='font-size:0.78rem;color:#c0392b'>{balance_warn}</span>" if balance_warn else ""}
            </div>
            <div style='text-align:right'>
              <span style='font-weight:800;font-size:1.05rem;color:{amount_color}'>{amount_sign}NGN {int(r['amount']):,}</span><br>
              <span style='font-size:0.78rem;color:{status_color};font-weight:600'>{status_text}</span>
            </div>
            </div></div>""",
            unsafe_allow_html=True
        )

    st.divider()
    st.caption("💡 Bills auto-post to your expense log when they are due if **auto-post** is enabled on that recurring item.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — DEBTS & LOANS
# ─────────────────────────────────────────────────────────────────────────────

def _render_debts(user_id: int):
    st.subheader("Debt & Loan Tracker")
    st.caption("Track money you borrowed or lent, record repayments, and see your payoff timeline.")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s ORDER BY bank_name", (user_id,))
        banks = cursor.fetchall()
        cursor.execute("""
            SELECT d.*,
              (SELECT COALESCE(SUM(amount),0) FROM debt_payments WHERE debt_id=d.id) AS total_paid
            FROM debts d WHERE d.user_id=%s ORDER BY d.status, d.due_date ASC NULLS LAST
        """, (user_id,))
        debts = cursor.fetchall()

    bank_map = {f"{b['bank_name']} (****{b['account_number']})": b for b in banks}

    # ── Summary metrics ───────────────────────────────────────────────────────
    active_debts = [d for d in debts if d["status"] == "active"]
    if active_debts:
        total_owed  = sum(int(d["balance_remaining"]) for d in active_debts if d["type"] == "borrowed")
        total_lent  = sum(int(d["balance_remaining"]) for d in active_debts if d["type"] == "lent")
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Total You Owe", f"NGN {total_owed:,}")
        mc2.metric("Total Owed to You", f"NGN {total_lent:,}")
        mc3.metric("Active Debts/Loans", str(len(active_debts)))
        st.divider()

    # ── Add new debt ──────────────────────────────────────────────────────────
    with st.expander("➕ Add Debt / Loan", expanded=not debts):
        with st.form("add_debt_form"):
            c1, c2 = st.columns(2)
            with c1:
                d_name    = st.text_input("Label *", placeholder="e.g. GTB Loan, Lent to Kemi")
                d_type    = st.selectbox("Type *", ["borrowed", "lent"],
                                         help="'borrowed' = you owe someone; 'lent' = they owe you")
                d_principal = st.number_input("Principal Amount (NGN) *", min_value=1, step=1000)
                d_balance   = st.number_input("Current Balance Remaining (NGN) *", min_value=0, step=1000)
            with c2:
                d_rate     = st.number_input("Interest Rate (% per annum, 0 if none)", min_value=0.0, step=0.5, format="%.2f")
                d_monthly  = st.number_input("Monthly Payment (NGN, 0 if flexible)", min_value=0, step=500)
                d_due      = st.date_input("Due / End Date (optional)", value=None)
                d_counter  = st.text_input("Counterparty (person/bank name)", placeholder="e.g. GTB, Mama, John")
            d_notes = st.text_area("Notes (optional)", height=60)
            submitted = st.form_submit_button("Add Debt/Loan", use_container_width=True)

        if submitted:
            if not d_name or d_principal < 1:
                st.warning("Label and principal amount are required.")
            else:
                with get_db() as (conn, cursor):
                    cursor.execute("""
                        INSERT INTO debts
                            (user_id, name, type, principal, balance_remaining,
                             interest_rate, monthly_payment, due_date, counterparty, notes)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (user_id, d_name, d_type, int(d_principal), int(d_balance),
                          d_rate, int(d_monthly), d_due, d_counter or None, d_notes or None))
                st.success(f"'{d_name}' added to your debt tracker.")
                st.rerun()

    if not debts:
        st.info("No debts or loans tracked yet.")
        return

    # ── Debt list ─────────────────────────────────────────────────────────────
    today = date.today()
    for section, section_debts, section_icon in [
        ("Active", [d for d in debts if d["status"] == "active"], "🔴"),
        ("Paid Off", [d for d in debts if d["status"] == "paid"], "✅"),
    ]:
        if not section_debts:
            continue
        st.markdown(f"**{section_icon} {section} Debts & Loans**")

        for d in section_debts:
            principal  = int(d["principal"])
            balance    = int(d["balance_remaining"])
            total_paid = int(d["total_paid"] or 0)
            pct_paid   = round((principal - balance) / principal * 100, 1) if principal else 0
            due_date   = d["due_date"]
            is_overdue = due_date and due_date < today and d["status"] == "active"
            label_color = "#c0392b" if d["type"] == "borrowed" else "#0e7c5b"

            with st.expander(
                f"{'🔴' if is_overdue else ('💸' if d['type']=='borrowed' else '💰')} "
                f"**{d['name']}** — NGN {balance:,} remaining"
                f"{' ⚠️ OVERDUE' if is_overdue else ''}",
                expanded=False
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Type:** {'You borrowed' if d['type']=='borrowed' else 'You lent'}")
                    st.markdown(f"**Principal:** NGN {principal:,}")
                    st.markdown(f"**Remaining:** NGN {balance:,}")
                    if d["interest_rate"]:
                        st.markdown(f"**Interest rate:** {float(d['interest_rate']):.2f}% p.a.")
                    if d["monthly_payment"]:
                        st.markdown(f"**Monthly payment:** NGN {int(d['monthly_payment']):,}")
                with col2:
                    st.markdown(f"**Counterparty:** {d['counterparty'] or '—'}")
                    st.markdown(f"**Due date:** {due_date or '—'}")
                    st.markdown(f"**Total paid so far:** NGN {total_paid:,}")
                    if d["notes"]:
                        st.markdown(f"**Notes:** {d['notes']}")

                # Progress bar
                bar_color = "#0e7c5b" if pct_paid >= 75 else ("#f39c12" if pct_paid >= 40 else "#c0392b")
                filled = int(pct_paid / 5)
                st.markdown(
                    f"<div style='margin:8px 0 4px'>"
                    f"<span style='font-size:0.8rem;color:#666'>Paid off: {pct_paid}%</span><br>"
                    f"<span style='color:{bar_color};font-size:1.1rem'>{'█'*filled}"
                    f"<span style='color:#ddd'>{'░'*(20-filled)}</span></span></div>",
                    unsafe_allow_html=True
                )

                # Payoff estimate
                if d["status"] == "active" and d["monthly_payment"] and balance > 0:
                    months_left = -(-balance // int(d["monthly_payment"]))  # ceiling div
                    st.caption(f"⏱️ At NGN {int(d['monthly_payment']):,}/month, payoff in ~{months_left} month(s).")

                st.markdown("---")

                # Record payment
                if d["status"] == "active":
                    with st.form(f"debt_payment_{d['id']}"):
                        pc1, pc2 = st.columns(2)
                        with pc1:
                            pay_amt  = st.number_input("Payment amount (NGN)", min_value=1, step=500, key=f"pamt_{d['id']}")
                        with pc2:
                            pay_bank = st.selectbox("Pay from bank (optional)", ["(none)"] + list(bank_map.keys()), key=f"pbnk_{d['id']}")
                        pay_note = st.text_input("Note (optional)", key=f"pnote_{d['id']}")
                        pay_date = st.date_input("Payment date", value=today, key=f"pdate_{d['id']}")
                        pay_submitted = st.form_submit_button("Record Payment")

                    if pay_submitted and pay_amt > 0:
                        bid = bank_map[pay_bank]["id"] if pay_bank != "(none)" else None
                        new_balance = max(balance - pay_amt, 0)
                        new_status  = "paid" if new_balance == 0 else "active"
                        with get_db() as (conn, cursor):
                            cursor.execute("""
                                INSERT INTO debt_payments (debt_id, user_id, bank_id, amount, note, paid_at)
                                VALUES (%s,%s,%s,%s,%s,%s)
                            """, (d["id"], user_id, bid, pay_amt, pay_note or None, pay_date))
                            cursor.execute("""
                                UPDATE debts SET balance_remaining=%s, status=%s WHERE id=%s AND user_id=%s
                            """, (new_balance, new_status, d["id"], user_id))
                            if bid:
                                cursor.execute(
                                    "INSERT INTO transactions (bank_id,type,amount,description,created_at) VALUES (%s,'debit',%s,%s,%s)",
                                    (bid, pay_amt, f"Debt payment: {d['name']}", pay_date)
                                )
                                cursor.execute("UPDATE banks SET balance=balance-%s WHERE id=%s", (pay_amt, bid))
                        msg = "🎉 Debt fully paid off!" if new_status == "paid" else f"Payment recorded. NGN {new_balance:,} remaining."
                        st.success(msg)
                        st.rerun()

                # Mark as paid / delete
                cc1, cc2 = st.columns(2)
                with cc1:
                    if d["status"] == "active":
                        if st.button("✅ Mark as Paid Off", key=f"debt_paid_{d['id']}"):
                            with get_db() as (conn, cursor):
                                cursor.execute(
                                    "UPDATE debts SET status='paid', balance_remaining=0 WHERE id=%s AND user_id=%s",
                                    (d["id"], user_id)
                                )
                            st.success("Marked as paid!")
                            st.rerun()
                with cc2:
                    if st.button("🗑️ Delete", key=f"debt_del_{d['id']}"):
                        with get_db() as (conn, cursor):
                            cursor.execute("DELETE FROM debts WHERE id=%s AND user_id=%s", (d["id"], user_id))
                        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — EMERGENCY FUND PLANNER
# ─────────────────────────────────────────────────────────────────────────────

def _render_emergency_fund(user_id: int):
    st.subheader("Emergency Fund Planner")
    st.caption(
        "An emergency fund should cover 3–6 months of essential expenses. "
        "Set your target, link it to a savings goal, and track your progress here."
    )

    today = date.today()

    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM emergency_fund_plan WHERE user_id=%s", (user_id,))
        plan = cursor.fetchone()

        # Auto-compute monthly expenses from last 3 months
        cursor.execute("""
            SELECT COALESCE(AVG(monthly_total),0) AS avg_monthly
            FROM (
                SELECT DATE_TRUNC('month', e.created_at) AS mo, SUM(e.amount) AS monthly_total
                FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s
                  AND e.created_at >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY mo
            ) sub
        """, (user_id,))
        avg_monthly = int(cursor.fetchone()["avg_monthly"] or 0)

        cursor.execute("SELECT id, name, current_amount, status FROM goals WHERE user_id=%s AND status='active' ORDER BY name", (user_id,))
        goals = cursor.fetchall()

    goal_map = {"(none / manual tracking)": None}
    goal_map.update({f"{g['name']} — NGN {int(g['current_amount']):,} saved": g["id"] for g in goals})

    # ── Setup / edit plan ─────────────────────────────────────────────────────
    with st.expander("⚙️ Configure Emergency Fund Plan", expanded=plan is None):
        with st.form("ef_plan_form"):
            default_months  = int(plan["target_months"])     if plan else 6
            default_exp     = int(plan["monthly_expenses_estimate"]) if plan and plan["monthly_expenses_estimate"] else avg_monthly
            default_saved   = int(plan["current_saved"])     if plan else 0

            ef_months   = st.slider("Target months of expenses to cover", 1, 12, default_months)
            ef_expenses = st.number_input(
                "Monthly expenses estimate (NGN)",
                min_value=0, step=5000, value=default_exp,
                help=f"Your 3-month average is NGN {avg_monthly:,}. You can override this."
            )
            ef_saved    = st.number_input("Currently saved in emergency fund (NGN)", min_value=0, step=5000, value=default_saved)

            # Goal linkage
            current_goal_key = "(none / manual tracking)"
            if plan and plan["goal_id"]:
                for k, v in goal_map.items():
                    if v == plan["goal_id"]:
                        current_goal_key = k
                        break
            ef_goal = st.selectbox("Link to a Savings Goal (optional)", list(goal_map.keys()),
                                   index=list(goal_map.keys()).index(current_goal_key))

            submitted = st.form_submit_button("Save Plan", use_container_width=True)

        if submitted:
            linked_goal_id = goal_map.get(ef_goal)
            with get_db() as (conn, cursor):
                cursor.execute("""
                    INSERT INTO emergency_fund_plan
                        (user_id, target_months, monthly_expenses_estimate, current_saved, goal_id, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        target_months=%s, monthly_expenses_estimate=%s,
                        current_saved=%s, goal_id=%s, updated_at=%s
                """, (user_id, ef_months, ef_expenses, ef_saved, linked_goal_id, today,
                      ef_months, ef_expenses, ef_saved, linked_goal_id, today))
            st.success("Emergency fund plan saved!")
            st.rerun()

    if not plan:
        st.info("Set up your emergency fund plan above to get started.")
        return

    # ── Display plan ──────────────────────────────────────────────────────────
    target_months = int(plan["target_months"])
    monthly_exp   = int(plan["monthly_expenses_estimate"] or avg_monthly or 0)
    fund_target   = target_months * monthly_exp

    # If linked to a goal, use goal's current_amount
    current_saved = int(plan["current_saved"])
    if plan["goal_id"]:
        with get_db() as (conn, cursor):
            cursor.execute("SELECT current_amount, name FROM goals WHERE id=%s", (plan["goal_id"],))
            grow = cursor.fetchone()
            if grow:
                current_saved = int(grow["current_amount"])
                goal_name = grow["name"]
            else:
                goal_name = None
    else:
        goal_name = None

    shortfall   = max(fund_target - current_saved, 0)
    pct_done    = min(current_saved / fund_target * 100, 100) if fund_target else 0
    months_done = current_saved / monthly_exp if monthly_exp else 0

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Target", f"NGN {fund_target:,}", help=f"{target_months} months × NGN {monthly_exp:,}/month")
    mc2.metric("Saved", f"NGN {current_saved:,}", delta=f"{pct_done:.0f}% funded")
    mc3.metric("Shortfall", f"NGN {shortfall:,}")
    mc4.metric("Months Covered", f"{months_done:.1f} / {target_months}")

    bar_color = "#0e7c5b" if pct_done >= 100 else ("#f39c12" if pct_done >= 50 else "#c0392b")
    filled = int(pct_done / 5)
    st.markdown(
        f"<div style='margin:12px 0 8px'>"
        f"<span style='font-size:0.85rem;color:#444;font-weight:600'>Progress: {pct_done:.1f}%</span><br>"
        f"<span style='color:{bar_color};font-size:1.25rem;letter-spacing:1px'>{'█'*filled}"
        f"<span style='color:#ddd'>{'░'*(20-filled)}</span></span></div>",
        unsafe_allow_html=True
    )

    if goal_name:
        st.info(f"📎 Linked to savings goal: **{goal_name}** — contributions there count toward your emergency fund.")

    if pct_done >= 100:
        st.success("🎉 You have fully funded your emergency fund! Maintain it and avoid dipping into it except for genuine emergencies.")
    else:
        # Monthly saving suggestions
        st.markdown("**💡 How to reach your goal:**")
        suggestions = [(3, 36), (6, 18), (12, 9), (24, 5)]
        cols = st.columns(4)
        for (monthly_save, months_needed), col in zip(suggestions, cols):
            contribution = shortfall // months_needed
            col.metric(f"In ~{months_needed} mo.", f"NGN {contribution:,}/mo",
                       help=f"Save NGN {contribution:,} every month for {months_needed} months")

    # Contextual tips
    st.divider()
    st.markdown("**📚 Emergency Fund Tips**")
    tips = [
        "Keep your emergency fund in a **separate account** so you are not tempted to spend it.",
        "Aim for **6 months** if you are self-employed or your income is irregular.",
        "**3 months** is sufficient if you have a stable salary and low fixed costs.",
        "Do not invest your emergency fund — keep it in a **savings or fixed-deposit** account.",
        "Review and increase it **annually** as your expenses grow.",
    ]
    for tip in tips:
        st.markdown(f"• {tip}")
