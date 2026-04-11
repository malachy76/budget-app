# tracker.py — tracker page
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db
from utils import save_expense, apply_income_filters, apply_expense_filters, \
    render_filter_bar_income, render_filter_bar_expenses, \
    get_category_budgets, compute_daily_safe_to_spend, BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password, get_onboarding_status, mark_onboarding_complete


def render_tracker(user_id):
    st.markdown("## Tracker")
    st.caption("Manage recurring income and expenses, bill reminders, debts, and your emergency fund plan.")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        tracker_banks = cursor.fetchall()

    tracker_bank_map = {f"{b['bank_name']} (****{b['account_number']})": b["id"] for b in tracker_banks}
    tracker_bank_opts = list(tracker_bank_map.keys())

    FREQ_OPTIONS = ["monthly", "weekly", "daily", "yearly"]
    FREQ_LABELS  = {"monthly": "Monthly", "weekly": "Weekly", "daily": "Daily", "yearly": "Yearly"}

    def next_due_from_freq(freq):
        from datetime import date as _d
        today = _d.today()
        if freq == "daily":   return today + timedelta(days=1)
        if freq == "weekly":  return today + timedelta(weeks=1)
        if freq == "yearly":  return today.replace(year=today.year + 1)
        return today.replace(day=1).replace(month=today.month % 12 + 1) if today.month < 12 \
               else today.replace(year=today.year + 1, month=1, day=1)

    tab_ri, tab_re, tab_bill, tab_debt, tab_ef = st.tabs([
        "&#x1F4B0; Recurring Income",
        "&#x1F4B8; Recurring Expenses",
        "&#x1F514; Bill Reminders",
        "&#x1F4B3; Debt / Loan",
        "&#x1F6E1; Emergency Fund",
    ])

    # ── TAB 1: Recurring Income ───────────────────────────────────────────────
    with tab_ri:
        st.subheader("Recurring Income")
        st.caption("Track salary, freelance, rent income, or any money that arrives on a schedule.")

        with st.expander("Add recurring income", expanded=False):
            with st.form("add_rec_income"):
                ri_name  = st.text_input("Income source (e.g. Salary, Rental income)")
                ri_amt   = st.number_input("Expected amount (NGN)", min_value=1, step=1000)
                ri_freq  = st.selectbox("Frequency", FREQ_OPTIONS, format_func=lambda x: FREQ_LABELS[x])
                ri_due   = st.date_input("Next expected date")
                ri_bank  = st.selectbox("Deposit to bank (optional)", ["— none —"] + tracker_bank_opts, key="ri_bank")
                ri_auto  = st.checkbox("Auto-post when due (adds income automatically on due date)")
                ri_sub   = st.form_submit_button("Add Recurring Income")
            if ri_sub:
                if ri_name and ri_amt > 0:
                    bk_id = tracker_bank_map.get(ri_bank) if ri_bank != "— none —" else None
                    with get_db() as (conn, cursor):
                        cursor.execute("""
                            INSERT INTO recurring_items
                                (user_id, type, name, amount, frequency, next_due, bank_id, auto_post)
                            VALUES (%s,'income',%s,%s,%s,%s,%s,%s)
                        """, (user_id, ri_name, int(ri_amt), ri_freq, ri_due, bk_id, 1 if ri_auto else 0))
                    st.success(f"Recurring income '{ri_name}' added.")
                    st.rerun()
                else:
                    st.warning("Please enter a name and amount.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.amount, r.frequency, r.next_due,
                       r.auto_post, r.active, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id=%s AND r.type='income'
                ORDER BY r.next_due
            """, (user_id,))
            rec_incomes = cursor.fetchall()

        today = datetime.now().date()
        if rec_incomes:
            for ri in rec_incomes:
                days_to = (ri["next_due"] - today).days if ri["next_due"] else None
                due_color = "#c0392b" if days_to is not None and days_to <= 3 else (
                            "#f39c12" if days_to is not None and days_to <= 7 else "#1a3c5e")
                due_label = (f"Due in {days_to}d" if days_to is not None and days_to >= 0
                             else f"Overdue {abs(days_to)}d" if days_to is not None else "No date")
                col_card, col_del = st.columns([6, 0.5])
                with col_card:
                    st.markdown(f"""
                    <div class="exp-card" style="border-left-color:#0e7c5b;">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{ri['name']}</div>
                        <div class="exp-card-bank">
                          {FREQ_LABELS.get(ri['frequency'],'Monthly')}
                          {f" &nbsp;&#x2192;&nbsp; {ri['bank_name']}" if ri.get('bank_name') else ""}
                          {"&nbsp; <em>auto-post</em>" if ri['auto_post'] else ""}
                        </div>
                        <div class="exp-card-date" style="color:{due_color};">{due_label} ({ri['next_due']})</div>
                      </div>
                      <div class="exp-card-right">
                        <div class="exp-card-amount" style="color:#0e7c5b;">+NGN {ri['amount']:,}</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_del:
                    del_key = f"ri_{ri['id']}"
                    if st.session_state.confirm_delete.get(del_key):
                        if st.button("✓", key=f"ri_yes_{ri['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM recurring_items WHERE id=%s AND user_id=%s", (ri["id"], user_id))
                            st.session_state.confirm_delete.pop(del_key, None)
                            st.rerun()
                        if st.button("✗", key=f"ri_no_{ri['id']}"):
                            st.session_state.confirm_delete.pop(del_key, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"ri_del_{ri['id']}", help="Delete"):
                            st.session_state.confirm_delete[del_key] = True; st.rerun()
        else:
            st.info("No recurring income yet. Use the form above to add salary, freelance, or rental income.")

    # ── TAB 2: Recurring Expenses ─────────────────────────────────────────────
    with tab_re:
        st.subheader("Recurring Expenses")
        st.caption("Track rent, subscriptions, school fees, or any expense that repeats on a schedule.")

        from csv_import import CATEGORY_KEYWORDS as _CK
        RE_CATEGORIES = ["— select category —"] + sorted(_CK.keys()) + ["Other"]

        with st.expander("Add recurring expense", expanded=False):
            with st.form("add_rec_expense"):
                re_name  = st.text_input("Expense name (e.g. House rent, DSTV, School fees)")
                re_amt   = st.number_input("Expected amount (NGN)", min_value=1, step=500)
                re_cat   = st.selectbox("Category", RE_CATEGORIES, key="re_cat_sel")
                re_freq  = st.selectbox("Frequency", FREQ_OPTIONS, format_func=lambda x: FREQ_LABELS[x], key="re_freq")
                re_due   = st.date_input("Next due date", key="re_due")
                re_bank  = st.selectbox("Pay from bank (optional)", ["— none —"] + tracker_bank_opts, key="re_bank")
                re_sub   = st.form_submit_button("Add Recurring Expense")
            if re_sub:
                if re_name and re_amt > 0:
                    bk_id = tracker_bank_map.get(re_bank) if re_bank != "— none —" else None
                    cat   = None if re_cat == "— select category —" else re_cat
                    with get_db() as (conn, cursor):
                        cursor.execute("""
                            INSERT INTO recurring_items
                                (user_id, type, name, category, amount, frequency, next_due, bank_id)
                            VALUES (%s,'expense',%s,%s,%s,%s,%s,%s)
                        """, (user_id, re_name, cat, int(re_amt), re_freq, re_due, bk_id))
                    st.success(f"Recurring expense '{re_name}' added.")
                    st.rerun()
                else:
                    st.warning("Please enter a name and amount.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.category, r.amount, r.frequency, r.next_due, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id=%s AND r.type='expense'
                ORDER BY r.next_due
            """, (user_id,))
            rec_expenses = cursor.fetchall()

        if rec_expenses:
            total_monthly = 0
            for re in rec_expenses:
                mult = {"daily": 30, "weekly": 4.33, "monthly": 1, "yearly": 1/12}
                total_monthly += re["amount"] * mult.get(re["frequency"], 1)

            st.caption(f"Estimated monthly recurring expense: NGN {int(total_monthly):,}")

            for re in rec_expenses:
                days_to = (re["next_due"] - today).days if re["next_due"] else None
                due_color = "#c0392b" if days_to is not None and days_to <= 3 else (
                            "#f39c12" if days_to is not None and days_to <= 7 else "#1a3c5e")
                due_label = (f"Due in {days_to}d" if days_to is not None and days_to >= 0
                             else f"Overdue {abs(days_to)}d" if days_to is not None else "No date")
                col_card, col_del = st.columns([6, 0.5])
                with col_card:
                    st.markdown(f"""
                    <div class="exp-card">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{re['name']}
                          {f'<span style="background:#e8f5f0;color:#0e7c5b;border-radius:10px;padding:1px 8px;font-size:0.75rem;font-weight:600;margin-left:6px;">{re["category"]}</span>' if re.get("category") else ''}
                        </div>
                        <div class="exp-card-bank">
                          {FREQ_LABELS.get(re['frequency'],'Monthly')}
                          {f" &nbsp;&#x2192;&nbsp; {re['bank_name']}" if re.get('bank_name') else ""}
                        </div>
                        <div class="exp-card-date" style="color:{due_color};">{due_label} ({re['next_due']})</div>
                      </div>
                      <div class="exp-card-right">
                        <div class="exp-card-amount">-NGN {re['amount']:,}</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_del:
                    del_key = f"re_{re['id']}"
                    if st.session_state.confirm_delete.get(del_key):
                        if st.button("✓", key=f"re_yes_{re['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM recurring_items WHERE id=%s AND user_id=%s", (re["id"], user_id))
                            st.session_state.confirm_delete.pop(del_key, None); st.rerun()
                        if st.button("✗", key=f"re_no_{re['id']}"):
                            st.session_state.confirm_delete.pop(del_key, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"re_del_{re['id']}", help="Delete"):
                            st.session_state.confirm_delete[del_key] = True; st.rerun()
        else:
            st.info("No recurring expenses yet. Add rent, subscriptions, or regular bills above.")

    # ── TAB 3: Bill Reminders ─────────────────────────────────────────────────
    with tab_bill:
        st.subheader("Bill Reminders")
        st.caption("See every bill due within the next 30 days, pulled from your recurring items.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT r.id, r.name, r.type, r.category, r.amount, r.frequency,
                       r.next_due, b.bank_name
                FROM recurring_items r
                LEFT JOIN banks b ON r.bank_id = b.id
                WHERE r.user_id = %s AND r.active = 1
                ORDER BY r.next_due
            """, (user_id,))
            all_recurring = cursor.fetchall()

        upcoming = [r for r in all_recurring
                    if r["next_due"] and (r["next_due"] - today).days <= 30]
        overdue  = [r for r in upcoming if (r["next_due"] - today).days < 0]
        due_soon = [r for r in upcoming if 0 <= (r["next_due"] - today).days <= 7]
        due_later= [r for r in upcoming if 7 < (r["next_due"] - today).days <= 30]

        if not upcoming:
            st.info("No bills due in the next 30 days. Add recurring items on the other tabs.")
        else:
            def _bill_card(r):
                days_to   = (r["next_due"] - today).days
                is_income = r["type"] == "income"
                color     = "#0e7c5b" if is_income else "#c0392b"
                sign      = "+" if is_income else "-"
                urgency   = "&#x1F534;" if days_to < 0 else ("&#x1F7E0;" if days_to <= 3 else "&#x1F7E2;")
                label     = f"Overdue {abs(days_to)}d" if days_to < 0 else (
                            f"Due today" if days_to == 0 else f"Due in {days_to}d")
                st.markdown(f"""
                <div class="exp-card" style="border-left-color:{color};">
                  <div class="exp-card-left">
                    <div class="exp-card-name">{urgency} {r['name']}</div>
                    <div class="exp-card-bank">{FREQ_LABELS.get(r['frequency'],'')}
                      {f" &nbsp;&#x2192;&nbsp; {r['bank_name']}" if r.get('bank_name') else ""}
                    </div>
                    <div class="exp-card-date">{label} — {r['next_due']}</div>
                  </div>
                  <div class="exp-card-right">
                    <div class="exp-card-amount" style="color:{color};">{sign}NGN {r['amount']:,}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            if overdue:
                st.markdown("#### Overdue")
                for r in overdue: _bill_card(r)

            if due_soon:
                st.markdown("#### Due within 7 days")
                for r in due_soon: _bill_card(r)

            if due_later:
                st.markdown("#### Due in 8–30 days")
                for r in due_later: _bill_card(r)

            total_expense_bills = sum(r["amount"] for r in upcoming if r["type"] == "expense")
            total_income_bills  = sum(r["amount"] for r in upcoming if r["type"] == "income")
            st.divider()
            c1, c2 = st.columns(2)
            c1.metric("Bills to pay (30 days)", f"NGN {total_expense_bills:,}")
            c2.metric("Income expected (30 days)", f"NGN {total_income_bills:,}")

    # ── TAB 4: Debt / Loan Tracker ────────────────────────────────────────────
    with tab_debt:
        st.subheader("Debt & Loan Tracker")
        st.caption("Track money you owe (borrowed) and money owed to you (lent).")

        with st.expander("Add debt or loan", expanded=False):
            with st.form("add_debt"):
                d_name    = st.text_input("Name / Description (e.g. Bank loan, Owe Chike)")
                d_type    = st.radio("Type", ["borrowed", "lent"],
                                     format_func=lambda x: "I borrowed this money" if x=="borrowed" else "I lent this money")
                d_col1, d_col2 = st.columns(2)
                with d_col1:
                    d_principal = st.number_input("Original amount (NGN)", min_value=1, step=1000)
                    d_remaining = st.number_input("Balance still owed (NGN)", min_value=0, step=1000)
                    d_monthly   = st.number_input("Monthly payment (NGN, 0 if none)", min_value=0, step=500)
                with d_col2:
                    d_rate    = st.number_input("Interest rate (% p.a., 0 if none)", min_value=0.0, step=0.5)
                    d_due     = st.date_input("Due / expected repayment date")
                    d_party   = st.text_input("Counterparty name (person / bank)")
                d_notes = st.text_area("Notes (optional)", height=60)
                d_sub   = st.form_submit_button("Add Debt / Loan")
            if d_sub:
                if d_name and d_principal > 0:
                    with get_db() as (conn, cursor):
                        cursor.execute("""
                            INSERT INTO debts
                                (user_id, name, type, principal, balance_remaining,
                                 interest_rate, monthly_payment, due_date,
                                 counterparty, notes)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (user_id, d_name, d_type, int(d_principal), int(d_remaining),
                              d_rate, int(d_monthly), d_due, d_party.strip() or None,
                              d_notes.strip() or None))
                    st.success("Debt / loan added.")
                    st.rerun()
                else:
                    st.warning("Please enter a name and amount.")

        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT id, name, type, principal, balance_remaining, interest_rate,
                       monthly_payment, due_date, counterparty, notes, status
                FROM debts WHERE user_id=%s ORDER BY status, due_date
            """, (user_id,))
            debts = cursor.fetchall()

        if debts:
            total_owe  = sum(d["balance_remaining"] for d in debts if d["type"]=="borrowed" and d["status"]=="active")
            total_owed = sum(d["balance_remaining"] for d in debts if d["type"]=="lent"     and d["status"]=="active")
            m1, m2 = st.columns(2)
            m1.metric("Total you owe (borrowed)", f"NGN {total_owe:,}", delta=None)
            m2.metric("Total owed to you (lent)", f"NGN {total_owed:,}", delta=None)
            st.divider()

            for d in debts:
                pct_paid = round(((d["principal"] - d["balance_remaining"]) / d["principal"] * 100), 1) if d["principal"] > 0 else 0
                is_lent  = d["type"] == "lent"
                card_col, action_col = st.columns([5, 1])
                with card_col:
                    st.markdown(f"""
                    <div class="exp-card" style="border-left-color:{'#0e7c5b' if is_lent else '#c0392b'};">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{'&#x1F4E4; Lent' if is_lent else '&#x1F4E5; Borrowed'}: {d['name']}</div>
                        <div class="exp-card-bank">
                          {f"{d['counterparty']} &nbsp;&middot;&nbsp;" if d.get('counterparty') else ""}
                          {f"{d['interest_rate']:.1f}% p.a." if d['interest_rate'] else "0% interest"}
                          {f" &nbsp;&middot;&nbsp; NGN {d['monthly_payment']:,}/mo payment" if d['monthly_payment'] else ""}
                        </div>
                        <div class="exp-card-date">Due: {d['due_date'] or 'Not set'} &nbsp;&middot;&nbsp; Status: {d['status'].title()}</div>
                      </div>
                      <div class="exp-card-right">
                        <div class="exp-card-amount" style="color:{'#0e7c5b' if is_lent else '#c0392b'};">
                          NGN {d['balance_remaining']:,}
                        </div>
                        <div style="font-size:0.75rem;color:#95a5a6;">{pct_paid:.0f}% paid</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with action_col:
                    if d["status"] == "active":
                        if st.button("Mark paid", key=f"debt_paid_{d['id']}"):
                            with get_db() as (conn, cursor):
                                cursor.execute("UPDATE debts SET status='paid', balance_remaining=0 WHERE id=%s AND user_id=%s",
                                               (d["id"], user_id))
                            st.rerun()
                    del_key = f"debt_{d['id']}"
                    if st.session_state.confirm_delete.get(del_key):
                        if st.button("✓", key=f"debt_yes_{d['id']}", type="primary"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM debts WHERE id=%s AND user_id=%s", (d["id"], user_id))
                            st.session_state.confirm_delete.pop(del_key, None); st.rerun()
                        if st.button("✗", key=f"debt_no_{d['id']}"):
                            st.session_state.confirm_delete.pop(del_key, None); st.rerun()
                    else:
                        if st.button("🗑️", key=f"debt_del_{d['id']}", help="Delete"):
                            st.session_state.confirm_delete[del_key] = True; st.rerun()
        else:
            st.info("No debts or loans tracked yet. Use the form above to add one.")

    # ── TAB 5: Emergency Fund Planner ─────────────────────────────────────────
    with tab_ef:
        st.subheader("Emergency Fund Planner")
        st.caption(
            "An emergency fund covers 3–6 months of expenses in case of job loss, "
            "medical emergencies, or unexpected events. Build yours here."
        )

        with get_db() as (conn, cursor):
            cursor.execute("SELECT * FROM emergency_fund_plan WHERE user_id=%s", (user_id,))
            ef_plan = cursor.fetchone()

        with st.form("ef_plan_form"):
            ef_months   = st.slider("Target: how many months of expenses to save?",
                                    min_value=1, max_value=12,
                                    value=int(ef_plan["target_months"]) if ef_plan else 6)
            ef_monthly  = st.number_input("Your estimated monthly expenses (NGN)",
                                          min_value=0, step=5000,
                                          value=int(ef_plan["monthly_expenses_estimate"]) if ef_plan else 0)
            ef_saved    = st.number_input("How much have you already saved towards this? (NGN)",
                                          min_value=0, step=5000,
                                          value=int(ef_plan["current_saved"]) if ef_plan else 0)
            ef_save_btn = st.form_submit_button("Update Emergency Fund Plan")

        if ef_save_btn:
            with get_db() as (conn, cursor):
                cursor.execute("""
                    INSERT INTO emergency_fund_plan
                        (user_id, target_months, monthly_expenses_estimate, current_saved, updated_at)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        target_months = EXCLUDED.target_months,
                        monthly_expenses_estimate = EXCLUDED.monthly_expenses_estimate,
                        current_saved = EXCLUDED.current_saved,
                        updated_at = EXCLUDED.updated_at
                """, (user_id, ef_months, int(ef_monthly), int(ef_saved), datetime.now().date()))
            st.success("Emergency fund plan updated.")
            st.rerun()

        if ef_plan or ef_save_btn:
            _months  = ef_months  if ef_save_btn else int(ef_plan["target_months"])
            _monthly = ef_monthly if ef_save_btn else int(ef_plan["monthly_expenses_estimate"])
            _saved   = ef_saved   if ef_save_btn else int(ef_plan["current_saved"])
        else:
            _months, _monthly, _saved = 6, 0, 0

        if _monthly > 0:
            target   = _months * _monthly
            shortfall = max(target - _saved, 0)
            pct      = min(round(_saved / target * 100, 1), 100) if target > 0 else 0

            st.divider()
            m1, m2, m3 = st.columns(3)
            m1.metric("Target amount", f"NGN {target:,}", help=f"{_months} months × NGN {_monthly:,}/mo")
            m2.metric("Already saved", f"NGN {_saved:,}")
            m3.metric("Still needed", f"NGN {shortfall:,}")

            st.progress(pct / 100, text=f"{pct:.0f}% of emergency fund target reached")

            if shortfall > 0:
                st.markdown("**How long will it take?**")
                m3_col, m6_col, m12_col = st.columns(3)
                for col, monthly_contribution in zip([m3_col, m6_col, m12_col], [
                    max(shortfall // 3, 1), max(shortfall // 6, 1), max(shortfall // 12, 1)
                ]):
                    months_needed = -(-shortfall // monthly_contribution)  # ceiling division
                    col.markdown(
                        f'<div style="background:#f0f7f4;border-radius:8px;padding:10px 14px;text-align:center;">'
                        f'<div style="font-size:0.78rem;color:#4a6070;font-weight:600;">Save NGN {monthly_contribution:,}/mo</div>'
                        f'<div style="font-size:1.1rem;font-weight:800;color:#1a3c5e;">{months_needed} months</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                st.markdown("<br>", unsafe_allow_html=True)
                st.info(
                    f"Tip: Create a dedicated **Savings Goal** called 'Emergency Fund' "
                    f"with a target of NGN {target:,} and contribute NGN {shortfall // 6:,} monthly "
                    f"to reach it in 6 months."
                )
            else:
                st.success(f"Your emergency fund target of NGN {target:,} is fully covered. Well done!")
        else:
            st.info("Enter your estimated monthly expenses above to see your emergency fund plan.")

# ================= PAGE: SUMMARIES =================
