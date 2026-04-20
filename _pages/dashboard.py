# dashboard.py — dashboard page
import io
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db
from utils import save_expense, apply_income_filters, apply_expense_filters, \
    render_filter_bar_income, render_filter_bar_expenses, \
    get_category_budgets, compute_daily_safe_to_spend, BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password, get_onboarding_status, mark_onboarding_complete




# ── Stat card CSS (injected once per session via st.markdown) ─────────────────
_STAT_CARD_CSS = """
<style>
.sc-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 14px;
    margin: 4px 0 18px 0;
}
.sc-card {
    background: #ffffff;
    border: 1px solid #d8eae2;
    border-radius: 14px;
    padding: 16px 18px 14px 18px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    transition: box-shadow 0.15s;
}
.sc-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.09); }
.sc-label {
    font-size: 0.72rem;
    font-weight: 700;
    color: #6b7f8e;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.sc-value {
    font-size: 1.35rem;
    font-weight: 800;
    color: #1a2e3b;
    line-height: 1.2;
    word-break: break-word;
}
.sc-sub {
    font-size: 0.76rem;
    color: #95a5a6;
    margin-top: 1px;
}
.sc-accent-green { color: #0e7c5b !important; }
.sc-accent-red   { color: #c0392b !important; }
.sc-accent-amber { color: #d4850a !important; }
@media (max-width: 640px) {
    .sc-grid { grid-template-columns: 1fr 1fr; gap: 9px; }
    .sc-value { font-size: 1.1rem; }
}
</style>
"""


def _fetch_stat_cards_data(user_id: int) -> dict:
    """Run all stat card queries in a single DB round-trip."""
    today       = datetime.now().date()
    month_start = today.replace(day=1)
    week_start  = today - timedelta(days=today.weekday())
    last_month_end   = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    with get_db() as (conn, cursor):

        # 1. Biggest single expense this week
        cursor.execute("""
            SELECT e.name, e.category, e.amount, b.bank_name
            FROM expenses e
            JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            ORDER BY e.amount DESC LIMIT 1
        """, (user_id, week_start))
        biggest_week = cursor.fetchone()

        # 2. Highest spending category this month
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat, SUM(e.amount) AS total
            FROM expenses e
            JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            GROUP BY cat ORDER BY total DESC LIMIT 1
        """, (user_id, month_start))
        top_cat_month = cursor.fetchone()

        # 3. Income and expenses this month for savings rate
        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END), 0) AS spent
            FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = %s AND t.created_at >= %s
        """, (user_id, month_start))
        month_totals = cursor.fetchone()
        m_income = int(month_totals["income"] or 0)
        m_spent  = int(month_totals["spent"]  or 0)

        # 4. Most used bank this month (by transaction count)
        cursor.execute("""
            SELECT b.bank_name, COUNT(*) AS cnt
            FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = %s AND t.created_at >= %s AND t.type = 'debit'
            GROUP BY b.bank_name ORDER BY cnt DESC LIMIT 1
        """, (user_id, month_start))
        most_used_bank = cursor.fetchone()

        # 5. Days with zero spending this month (up to today)
        cursor.execute("""
            SELECT DISTINCT e.created_at AS day
            FROM expenses e
            JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s AND e.created_at <= %s
        """, (user_id, month_start, today))
        days_spent = {r["day"] for r in cursor.fetchall()}
        days_elapsed = today.day
        days_zero = days_elapsed - len(days_spent)

        # 6. Trend vs last month — total spent
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = %s AND t.type = 'debit'
              AND t.created_at >= %s AND t.created_at <= %s
        """, (user_id, last_month_start, last_month_end))
        last_month_spent = int(cursor.fetchone()["total"] or 0)

        # 7. Monthly spending limit for remaining daily budget
        cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
        spending_limit = int(cursor.fetchone()["monthly_spending_limit"] or 0)

    import calendar
    days_in_month   = calendar.monthrange(today.year, today.month)[1]
    days_remaining  = days_in_month - today.day + 1
    budget_remaining = max(spending_limit - m_spent, 0)
    daily_remaining  = int(budget_remaining / days_remaining) if spending_limit > 0 else None

    savings_rate = round((m_income - m_spent) / m_income * 100, 1) if m_income > 0 else None

    trend_diff = m_spent - last_month_spent
    trend_pct  = round(trend_diff / last_month_spent * 100, 1) if last_month_spent > 0 else None

    return {
        "biggest_week":      biggest_week,
        "top_cat_month":     top_cat_month,
        "m_income":          m_income,
        "m_spent":           m_spent,
        "savings_rate":      savings_rate,
        "most_used_bank":    most_used_bank,
        "days_zero":         days_zero,
        "days_elapsed":      days_elapsed,
        "last_month_spent":  last_month_spent,
        "trend_diff":        trend_diff,
        "trend_pct":         trend_pct,
        "daily_remaining":   daily_remaining,
        "spending_limit":    spending_limit,
        "today":             today,
        "month_start":       month_start,
    }


def _render_stat_cards(data: dict):
    """Render the 7 stat cards in a responsive CSS grid."""
    st.markdown(_STAT_CARD_CSS, unsafe_allow_html=True)
    d = data

    # ── Card 1: Biggest expense this week ─────────────────────────────────────
    if d["biggest_week"]:
        bw = d["biggest_week"]
        bw_name  = (bw["name"] or "")[:28] + ("…" if len(bw["name"] or "") > 28 else "")
        bw_cat   = bw["category"] or ""
        card1 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F525; Biggest Expense This Week</div>'
            f'<div class="sc-value sc-accent-red">₦{int(bw["amount"]):,}</div>'
            f'<div class="sc-sub">{bw_name}'
            + (f' &bull; {bw_cat}' if bw_cat else '') +
            f'<br>{bw["bank_name"]}</div>'
            '</div>'
        )
    else:
        card1 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F525; Biggest Expense This Week</div>'
            '<div class="sc-value" style="color:#95a5a6;">—</div>'
            '<div class="sc-sub">No expenses yet this week</div>'
            '</div>'
        )

    # ── Card 2: Highest spending category this month ───────────────────────────
    if d["top_cat_month"]:
        tc = d["top_cat_month"]
        card2 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F4CA; Top Category This Month</div>'
            f'<div class="sc-value">{tc["cat"] or "Uncategorised"}</div>'
            f'<div class="sc-sub">₦{int(tc["total"]):,} spent</div>'
            '</div>'
        )
    else:
        card2 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F4CA; Top Category This Month</div>'
            '<div class="sc-value" style="color:#95a5a6;">—</div>'
            '<div class="sc-sub">No expenses this month yet</div>'
            '</div>'
        )

    # ── Card 3: Remaining daily budget ─────────────────────────────────────────
    if d["daily_remaining"] is not None:
        dr_color = "sc-accent-green" if d["daily_remaining"] > 0 else "sc-accent-red"
        dr_label = f"₦{d['daily_remaining']:,}" if d["daily_remaining"] > 0 else "Budget exceeded"
        import calendar
        month_name = d["today"].strftime("%B")
        days_in_month = calendar.monthrange(d["today"].year, d["today"].month)[1]
        days_remaining = days_in_month - d["today"].day + 1
        card3 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F4B0; Remaining Daily Budget</div>'
            f'<div class="sc-value {dr_color}">{dr_label}</div>'
            f'<div class="sc-sub">{days_remaining} days left in {month_name} &bull; '
            f'₦{max(d["spending_limit"] - d["m_spent"], 0):,} budget remaining</div>'
            '</div>'
        )
    else:
        card3 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F4B0; Remaining Daily Budget</div>'
            '<div class="sc-value" style="color:#95a5a6;">—</div>'
            '<div class="sc-sub">Set a monthly budget in Settings</div>'
            '</div>'
        )

    # ── Card 4: Savings rate this month ────────────────────────────────────────
    if d["savings_rate"] is not None:
        sr = d["savings_rate"]
        sr_color = "sc-accent-green" if sr >= 20 else ("sc-accent-amber" if sr >= 0 else "sc-accent-red")
        sr_tip = (
            "Great savings rate — keep it up!" if sr >= 20 else
            "You are saving something — aim for 20%+" if sr >= 5 else
            "Spending more than you earn this month" if sr < 0 else
            "Low savings rate — review your biggest expenses"
        )
        card4 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F4C8; Savings Rate</div>'
            f'<div class="sc-value {sr_color}">{sr:.1f}%</div>'
            f'<div class="sc-sub">{sr_tip}<br>'
            f'₦{d["m_income"]:,} in &bull; ₦{d["m_spent"]:,} out</div>'
            '</div>'
        )
    else:
        card4 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F4C8; Savings Rate</div>'
            '<div class="sc-value" style="color:#95a5a6;">—</div>'
            '<div class="sc-sub">Add income and expenses to calculate</div>'
            '</div>'
        )

    # ── Card 5: Most used bank ─────────────────────────────────────────────────
    if d["most_used_bank"]:
        mb = d["most_used_bank"]
        card5 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F3E6; Most Used Bank</div>'
            f'<div class="sc-value">{mb["bank_name"]}</div>'
            f'<div class="sc-sub">{int(mb["cnt"])} debit transaction{"s" if mb["cnt"] != 1 else ""} this month</div>'
            '</div>'
        )
    else:
        card5 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F3E6; Most Used Bank</div>'
            '<div class="sc-value" style="color:#95a5a6;">—</div>'
            '<div class="sc-sub">No transactions this month</div>'
            '</div>'
        )

    # ── Card 6: Days you spent nothing ─────────────────────────────────────────
    dz = d["days_zero"]
    de = d["days_elapsed"]
    dz_color = "sc-accent-green" if dz >= 5 else ("sc-accent-amber" if dz >= 2 else "sc-accent-red")
    dz_tip = (
        "Excellent discipline — lots of no-spend days!" if dz >= 8 else
        "Good — you have several no-spend days this month" if dz >= 4 else
        "Try to have more no-spend days each week" if dz >= 1 else
        "No no-spend days yet this month"
    )
    card6 = (
        '<div class="sc-card">'
        '<div class="sc-label">&#x1F7E2; No-Spend Days</div>'
        f'<div class="sc-value {dz_color}">{dz} / {de}</div>'
        f'<div class="sc-sub">{dz_tip}</div>'
        '</div>'
    )

    # ── Card 7: Trend vs last month ────────────────────────────────────────────
    if d["trend_pct"] is not None:
        td   = d["trend_diff"]
        tp   = d["trend_pct"]
        less = td < 0
        trend_color  = "sc-accent-green" if less else "sc-accent-red"
        trend_arrow  = "&#x1F53D;" if less else "&#x1F53C;"
        trend_word   = "less" if less else "more"
        trend_lm_str = f"₦{d['last_month_spent']:,} last month"
        card7 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F5D3; Trend vs Last Month</div>'
            f'<div class="sc-value {trend_color}">{trend_arrow} {abs(tp):.1f}%</div>'
            f'<div class="sc-sub">₦{abs(td):,} {trend_word} than last month<br>{trend_lm_str}</div>'
            '</div>'
        )
    elif d["last_month_spent"] == 0:
        card7 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F5D3; Trend vs Last Month</div>'
            '<div class="sc-value" style="color:#95a5a6;">First month</div>'
            '<div class="sc-sub">No data from last month to compare</div>'
            '</div>'
        )
    else:
        card7 = (
            '<div class="sc-card">'
            '<div class="sc-label">&#x1F5D3; Trend vs Last Month</div>'
            '<div class="sc-value" style="color:#95a5a6;">—</div>'
            '<div class="sc-sub">No spending this month yet</div>'
            '</div>'
        )

    # ── Render all 7 as one CSS grid ───────────────────────────────────────────
    html = (
        '<div class="sc-grid">'
        + card1 + card2 + card3 + card4 + card5 + card6 + card7
        + '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)



# ─────────────────────────────────────────────────────────────────────────────
# SMART SUGGESTIONS ENGINE  (17 suggestion rules)
#
# Each suggestion dict:  icon, label, text, action, bg, border, color, priority
# priority 1 = urgent/warning   2 = useful nudge   3 = positive/celebratory
# Rules fire only when there is real data — no suggestion on zero/empty input.
# Sorted by priority before rendering; capped at 8 shown at once.
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_smart_suggestions(user_id: int, spending_limit: int, expenses_this_month: int) -> list:
    """Run all suggestion queries in one DB connection, return sorted list."""
    import calendar as _cal

    today            = datetime.now().date()
    month_start      = today.replace(day=1)
    week_start       = today - timedelta(days=today.weekday())
    last_month_end   = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    last_week_start  = week_start - timedelta(days=7)
    last_week_end    = week_start - timedelta(days=1)
    days_in_month    = _cal.monthrange(today.year, today.month)[1]
    days_remaining   = days_in_month - today.day + 1
    days_elapsed     = today.day

    with get_db() as (conn, cursor):

        # ── A. Category totals this month vs last month ───────────────────────
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat,
                   SUM(CASE WHEN e.created_at >= %s THEN e.amount ELSE 0 END)              AS this_month,
                   SUM(CASE WHEN e.created_at >= %s AND e.created_at <= %s THEN e.amount ELSE 0 END) AS last_month
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            GROUP BY cat
        """, (month_start, last_month_start, last_month_end, user_id, last_month_start))
        cat_rows = cursor.fetchall()

        # ── B. Small purchases ────────────────────────────────────────────────
        cursor.execute("""
            SELECT COUNT(*) AS n, COALESCE(SUM(e.amount), 0) AS total
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s AND e.amount < 5000
        """, (user_id, month_start))
        small = cursor.fetchone()
        small_count = int(small["n"]     or 0)
        small_total = int(small["total"] or 0)

        # ── C. Weekend vs weekday ─────────────────────────────────────────────
        cursor.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN EXTRACT(DOW FROM e.created_at) IN (0,6) THEN e.amount ELSE 0 END),0) AS weekend,
              COALESCE(SUM(CASE WHEN EXTRACT(DOW FROM e.created_at) NOT IN (0,6) THEN e.amount ELSE 0 END),0) AS weekday
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
        """, (user_id, month_start))
        wd = cursor.fetchone()
        weekend_spend = int(wd["weekend"] or 0)
        weekday_spend = int(wd["weekday"] or 0)

        # ── D. Possible duplicate charges (same name + amount, ≥3× this month) ─
        cursor.execute("""
            SELECT e.amount, e.name, COUNT(*) AS n
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            GROUP BY e.amount, e.name
            HAVING COUNT(*) >= 3 AND e.amount > 2000
            ORDER BY n DESC LIMIT 1
        """, (user_id, month_start))
        dup_row = cursor.fetchone()

        # ── E. Active savings goals with shortfall ────────────────────────────
        cursor.execute("""
            SELECT name, target_amount, current_amount,
                   (target_amount - current_amount) AS shortfall
            FROM goals
            WHERE user_id = %s AND status = 'active' AND target_amount > current_amount
            ORDER BY shortfall ASC LIMIT 3
        """, (user_id,))
        goals_open = cursor.fetchall()

        # ── F. Income this month ──────────────────────────────────────────────
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = %s AND t.type = 'credit' AND t.created_at >= %s
        """, (user_id, month_start))
        income_this_month = int(cursor.fetchone()["total"] or 0)

        # ── G. Last month total spent ─────────────────────────────────────────
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = %s AND t.type = 'debit'
              AND t.created_at >= %s AND t.created_at <= %s
        """, (user_id, last_month_start, last_month_end))
        last_month_total = int(cursor.fetchone()["total"] or 0)

        # ── H. Bank below minimum balance alert ───────────────────────────────
        cursor.execute("""
            SELECT bank_name, balance, min_balance_alert
            FROM banks
            WHERE user_id = %s AND min_balance_alert > 0 AND balance <= min_balance_alert
            ORDER BY balance ASC LIMIT 1
        """, (user_id,))
        low_balance_bank = cursor.fetchone()

        # ── I. Overdue recurring items ────────────────────────────────────────
        cursor.execute("""
            SELECT name, type, amount, frequency, next_due
            FROM recurring_items
            WHERE user_id = %s AND active = 1 AND next_due < %s
            ORDER BY next_due ASC LIMIT 3
        """, (user_id, today))
        overdue_recurring = cursor.fetchall()

        # ── J. Days with no spending this month ───────────────────────────────
        cursor.execute("""
            SELECT COUNT(DISTINCT e.created_at) AS spent_days
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s AND e.created_at <= %s
        """, (user_id, month_start, today))
        spent_days      = int(cursor.fetchone()["spent_days"] or 0)
        zero_spend_days = days_elapsed - spent_days

        # ── K. Category budgets: overspent ───────────────────────────────────
        cursor.execute("""
            SELECT cb.category, cb.monthly_limit,
                   COALESCE(SUM(e.amount), 0) AS spent
            FROM category_budgets cb
            LEFT JOIN expenses e
                ON COALESCE(e.category, e.name) = cb.category
               AND e.user_id = cb.user_id
               AND e.created_at >= %s
            WHERE cb.user_id = %s AND cb.monthly_limit > 0
            GROUP BY cb.category, cb.monthly_limit
            HAVING COALESCE(SUM(e.amount), 0) > cb.monthly_limit
            ORDER BY (COALESCE(SUM(e.amount), 0) - cb.monthly_limit) DESC LIMIT 2
        """, (month_start, user_id))
        overbudget_cats = cursor.fetchall()

        # ── L. Single biggest expense this month ─────────────────────────────
        cursor.execute("""
            SELECT e.name, e.category, e.amount, e.created_at
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            ORDER BY e.amount DESC LIMIT 1
        """, (user_id, month_start))
        biggest_expense = cursor.fetchone()

        # ── M. Frequency of a single recurring category this week ────────────
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat, COUNT(*) AS cnt,
                   SUM(e.amount) AS total
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            GROUP BY cat ORDER BY cnt DESC LIMIT 1
        """, (user_id, week_start))
        most_frequent_this_week = cursor.fetchone()

        # ── N. Debts due within 14 days ───────────────────────────────────────
        cursor.execute("""
            SELECT name, balance_remaining, due_date, type
            FROM debts
            WHERE user_id = %s AND status = 'active'
              AND due_date IS NOT NULL AND due_date <= %s
            ORDER BY due_date ASC LIMIT 2
        """, (user_id, today + timedelta(days=14)))
        upcoming_debts = cursor.fetchall()

        # ── O. Top category this week vs daily average ────────────────────────
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat, SUM(e.amount) AS total
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            GROUP BY cat ORDER BY total DESC LIMIT 1
        """, (user_id, week_start))
        top_week_cat = cursor.fetchone()

        # ── P. Same-category daily-average vs monthly for food/transport ─────
        # (already captured via cat_rows above — no extra query needed)

    # ─────────────────────────────────────────────────────────────────────────
    # BUILD SUGGESTIONS
    # ─────────────────────────────────────────────────────────────────────────
    S = []

    def _s(icon, label, text, bg, border, color, priority=2, action=None):
        S.append(dict(icon=icon, label=label, text=text,
                      bg=bg, border=border, color=color,
                      priority=priority, action=action))

    # Colour palette
    RED    = ("#fdf2f2", "#e74c3c", "#922b21")
    ORANGE = ("#fffbea", "#f39c12", "#7d5a00")
    BLUE   = ("#e8f4fd", "#3498db", "#1a2e3b")
    GREEN  = ("#f4f7f6", "#0e7c5b", "#0a5c44")
    PURPLE = ("#fdf0ff", "#9b59b6", "#4a235a")
    TEAL   = ("#e0f4f0", "#16a085", "#0d6b57")

    # ── 1. Category up vs last month (up to 3 categories) ────────────────────
    rising = []
    for r in cat_rows:
        this_m   = int(r["this_month"] or 0)
        last_m   = int(r["last_month"] or 0)
        cat_name = r["cat"] or "Uncategorised"
        if this_m > 0 and last_m > 0 and this_m > last_m * 1.2:
            diff = this_m - last_m
            pct  = round(diff / last_m * 100)
            rising.append((cat_name, this_m, last_m, diff, pct))
    rising.sort(key=lambda x: x[4], reverse=True)

    for cat_name, this_m, last_m, diff, pct in rising[:3]:
        is_airtime   = any(k in cat_name.lower() for k in ("airtime","data"))
        is_transport = any(k in cat_name.lower() for k in ("transport","bolt","uber","fuel"))
        is_food      = any(k in cat_name.lower() for k in ("food","eating","restaurant","snack"))
        if is_airtime:
            tip = (f"Consider buying a monthly data bundle — it is usually cheaper than "
                   f"topping up in small amounts. A ₦3,000–₦5,000 bundle could save you "
                   f"₦{int(diff * 0.3):,} next month.")
        elif is_transport:
            tip = (f"Review your transport routine — try public transport, carpooling, or "
                   f"batch your errands into fewer trips. You could cut this by "
                   f"₦{int(diff * 0.4):,} with some planning.")
        elif is_food:
            tip = (f"Meal prepping on Sundays or cooking at home 3 more days a week could "
                   f"save you ₦{int(diff * 0.5):,}. Small changes add up fast.")
        else:
            tip = (f"Review if this spending was necessary. "
                   f"Cutting it back to last month's level would save you ₦{diff:,}.")
        _s("&#x1F53C;",
           f"{cat_name} Spending Up {pct}%",
           f"You spent <strong>₦{this_m:,}</strong> on <em>{cat_name}</em> this month — "
           f"<strong>{pct}% more</strong> than last month's ₦{last_m:,} "
           f"(₦{diff:,} extra). {tip}",
           *ORANGE, priority=1)

    # ── 2. Category down vs last month (positive reinforcement) ──────────────
    falling = []
    for r in cat_rows:
        this_m   = int(r["this_month"] or 0)
        last_m   = int(r["last_month"] or 0)
        cat_name = r["cat"] or "Uncategorised"
        if last_m > 0 and this_m < last_m * 0.75 and (last_m - this_m) > 2000:
            falling.append((cat_name, this_m, last_m, last_m - this_m))
    if falling:
        falling.sort(key=lambda x: x[3], reverse=True)
        cat_name, this_m, last_m, saved = falling[0]
        weekly_save = int(saved / 4)
        _s("&#x1F53D;",
           f"Great Cut: {cat_name} Down",
           f"Your <em>{cat_name}</em> spending dropped from ₦{last_m:,} last month to "
           f"<strong>₦{this_m:,} this month</strong> — you saved <strong>₦{saved:,}</strong>. "
           f"If you keep this up, that is ₦{saved * 12:,} saved over a year. "
           f"Transfer ₦{weekly_save:,} weekly to a savings goal and make it count.",
           *GREEN, priority=3, action="Go to Savings Goals")

    # ── 3. Small purchases accumulation ──────────────────────────────────────
    if small_count >= 4 and small_total >= 5000:
        daily_equiv  = int(small_total / max(days_elapsed, 1))
        monthly_proj = int(daily_equiv * days_in_month)
        _s("&#x1F4A7;",
           "Small Purchases Add Up Fast",
           f"You made <strong>{small_count} purchases under ₦5,000</strong> this month, "
           f"totalling <strong>₦{small_total:,}</strong>. "
           f"At that rate you will spend about ₦{monthly_proj:,} on small items this month alone — "
           f"₦{monthly_proj * 12:,} over a year. "
           f"Skipping just one small purchase a day could save you ₦{int(daily_equiv * 30):,} monthly.",
           *PURPLE, priority=1)

    # ── 4. Weekend vs weekday spending ───────────────────────────────────────
    weekdays_elapsed = sum(
        1 for d in range(1, days_elapsed + 1)
        if datetime(today.year, today.month, d).weekday() < 5
    )
    weekends_elapsed = days_elapsed - weekdays_elapsed
    if weekends_elapsed > 0 and weekdays_elapsed > 0 and weekend_spend > 0:
        daily_wkend = int(weekend_spend / weekends_elapsed)
        daily_wkday = int(weekday_spend / weekdays_elapsed) if weekday_spend > 0 else 0
        if daily_wkend > daily_wkday * 1.5 and daily_wkend > 3000:
            monthly_wkend_proj = int(daily_wkend * 8)  # ~8 weekend days/month
            _s("&#x1F37B;",
               "Weekend Spending is High",
               f"You spend <strong>₦{daily_wkend:,}/day on weekends</strong> vs "
               f"₦{daily_wkday:,} on weekdays — {round(daily_wkend/max(daily_wkday,1))}× more. "
               f"Weekend outings, food delivery and entertainment total ₦{weekend_spend:,} so far. "
               f"Setting a weekend cash limit of ₦{int(daily_wkday * 1.3):,}/day could save "
               f"₦{monthly_wkend_proj - int(daily_wkday * 1.3 * 8):,} this month.",
               *ORANGE, priority=2)

    # ── 5. Budget pace warning ────────────────────────────────────────────────
    if spending_limit > 0 and days_elapsed > 0 and expenses_this_month > 0:
        daily_rate    = expenses_this_month / days_elapsed
        projected_end = int(daily_rate * days_in_month)
        pct_used      = expenses_this_month / spending_limit * 100
        if projected_end > spending_limit * 1.1:
            overshoot = projected_end - spending_limit
            safe_daily = int((spending_limit - expenses_this_month) / max(days_remaining, 1))
            _s("&#x1F4C9;",
               "Budget Pace Warning",
               f"At your current rate of <strong>₦{int(daily_rate):,}/day</strong>, you will spend "
               f"<strong>₦{projected_end:,} this month</strong> — ₦{overshoot:,} over your "
               f"₦{spending_limit:,} budget. "
               f"To finish within budget you need to stay under "
               f"<strong>₦{safe_daily:,}/day</strong> for the rest of {today.strftime('%B')}.",
               *RED, priority=1)
        elif pct_used >= 50 and days_elapsed < days_in_month // 2:
            _s("&#x26A0;&#xFE0F;",
               "Half Budget Gone — Month Not Half Over",
               f"You have used <strong>{pct_used:.0f}% of your monthly budget</strong> "
               f"but only {days_elapsed} of {days_in_month} days have passed. "
               f"At this pace you will exhaust your budget around day "
               f"{int(days_in_month * (spending_limit / max(expenses_this_month, 1)) * (days_elapsed / days_in_month))}. "
               f"Review your biggest categories now.",
               *ORANGE, priority=1)

    # ── 6. Savings rate ───────────────────────────────────────────────────────
    if income_this_month > 0 and expenses_this_month > 0:
        net          = income_this_month - expenses_this_month
        savings_rate = round(net / income_this_month * 100, 1)
        if savings_rate < 0:
            _s("&#x1F6A8;",
               "Spending More Than You Earn",
               f"This month you earned ₦{income_this_month:,} but spent "
               f"<strong>₦{expenses_this_month:,}</strong> — "
               f"<strong>₦{abs(net):,} in deficit</strong>. "
               f"Your top two spending categories are likely the culprit. "
               f"Cutting just ₦{abs(int(net * 0.5)):,} from your biggest category would halve the deficit.",
               *RED, priority=1)
        elif savings_rate < 10:
            target_cut = int(income_this_month * 0.1)
            _s("&#x1F4C8;",
               "Low Savings Rate — Fix It Now",
               f"Your savings rate is only <strong>{savings_rate:.1f}%</strong> "
               f"(₦{net:,} saved of ₦{income_this_month:,} earned). "
               f"The 50/30/20 rule says 20% should go to savings. "
               f"You need to cut ₦{target_cut:,} more to reach 10% — "
               f"start by trimming your top spending category.",
               *ORANGE, priority=2)
        elif savings_rate >= 20:
            annual_proj = int(net * 12)
            _s("&#x1F3C6;",
               "Strong Savings Rate",
               f"You are saving <strong>{savings_rate:.1f}%</strong> of your income this month "
               f"— ₦{net:,} out of ₦{income_this_month:,}. "
               f"At this rate you will save about <strong>₦{annual_proj:,}</strong> over the next 12 months. "
               f"Consider putting the surplus into a high-yield savings plan or a goal.",
               *GREEN, priority=3, action="Go to Savings Goals")

    # ── 7. Goal funding suggestions ───────────────────────────────────────────
    for goal in goals_open[:2]:
        shortfall  = int(goal["shortfall"])
        goal_name  = goal["name"]
        if shortfall <= 0:
            continue
        # Pick the best realistic timeline
        weekly_4  = int(shortfall / 4)
        weekly_12 = int(shortfall / 12)
        weekly_26 = int(shortfall / 26)
        ref_income = income_this_month or shortfall  # fallback if no income recorded
        if weekly_12 > 0 and weekly_12 <= ref_income * 0.25:
            timeline, weekly_amt = "3 months", weekly_12
        elif weekly_26 > 0 and weekly_26 <= ref_income * 0.25:
            timeline, weekly_amt = "6 months", weekly_26
        else:
            timeline, weekly_amt = "12 months", int(shortfall / 52)
        daily_amt = int(weekly_amt / 7)
        _s("&#x1F3AF;",
           f"Goal Boost: {goal_name[:30]}",
           f"You need <strong>₦{shortfall:,}</strong> more to complete your "
           f"<em>{goal_name}</em> goal. "
           f"Save <strong>₦{weekly_amt:,} every week</strong> and you will reach it in "
           f"<strong>{timeline}</strong> — that is just <strong>₦{daily_amt:,} per day</strong>. "
           f"Set up a recurring transfer on the Tracker page to make it automatic.",
           *TEAL, priority=2, action="Set up recurring transfer")

    # ── 8. Low bank balance alert ─────────────────────────────────────────────
    if low_balance_bank:
        _s("&#x1F3E6;",
           "Low Bank Balance Alert",
           f"<strong>{low_balance_bank['bank_name']}</strong> balance is "
           f"<strong>₦{int(low_balance_bank['balance']):,}</strong> — "
           f"at or below your ₦{int(low_balance_bank['min_balance_alert']):,} alert threshold. "
           f"Top it up before your next scheduled payment or automatic debit bounces.",
           *RED, priority=1, action="Go to Banks")

    # ── 9. Overdue recurring items ────────────────────────────────────────────
    if overdue_recurring:
        names = ", ".join(r["name"] for r in overdue_recurring[:3])
        total_overdue = sum(int(r["amount"]) for r in overdue_recurring)
        plural = len(overdue_recurring) > 1
        _s("&#x1F514;",
           f"{'Recurring Bills' if plural else 'Recurring Bill'} Overdue",
           f"<strong>{len(overdue_recurring)} recurring item{'s' if plural else ''}</strong> "
           f"{'are' if plural else 'is'} overdue: <em>{names}</em>. "
           f"Total owed: <strong>₦{total_overdue:,}</strong>. "
           f"Update them on the Tracker page so your records stay accurate.",
           *ORANGE, priority=1, action="Go to Tracker")

    # ── 10. No-spend days ─────────────────────────────────────────────────────
    if zero_spend_days >= 5:
        amount_saved_est = int(expenses_this_month / max(spent_days, 1) * zero_spend_days)
        _s("&#x1F7E2;",
           "Excellent No-Spend Discipline",
           f"You have had <strong>{zero_spend_days} no-spend days</strong> so far this month "
           f"out of {days_elapsed} days — that is {round(zero_spend_days/days_elapsed*100)}% of the month. "
           f"Estimated saving vs spending every day: <strong>₦{amount_saved_est:,}</strong>. "
           f"Keep it up through month-end!",
           *GREEN, priority=3)
    elif days_elapsed >= 7 and zero_spend_days == 0:
        avg_daily = int(expenses_this_month / max(days_elapsed, 1))
        _s("&#x1F534;",
           "No No-Spend Days Yet",
           f"You have spent money every single day this month ({days_elapsed} days straight). "
           f"Skipping even one day could save you ~₦{avg_daily:,}. "
           f"Pick a day this week and spend nothing — pack lunch, avoid the ATM.",
           *ORANGE, priority=2)

    # ── 11. Category budget overspend ─────────────────────────────────────────
    for ob in overbudget_cats:
        overspend = int(ob["spent"]) - int(ob["monthly_limit"])
        pct_over  = round(overspend / int(ob["monthly_limit"]) * 100)
        _s("&#x1F4B8;",
           f"Over Budget: {ob['category'][:25]}",
           f"Your <em>{ob['category']}</em> spending (₦{int(ob['spent']):,}) has exceeded "
           f"your ₦{int(ob['monthly_limit']):,} limit by "
           f"<strong>₦{overspend:,} ({pct_over}% over)</strong>. "
           f"Pause {ob['category'].lower()} spending for the rest of the month — "
           f"every unspent naira now comes straight off this overshoot.",
           *RED, priority=1)

    # ── 12. Possible duplicate charge ────────────────────────────────────────
    if dup_row and int(dup_row["n"]) >= 3:
        total_dup = int(dup_row["amount"]) * int(dup_row["n"])
        _s("&#x1F50D;",
           "Possible Duplicate Charges",
           f"<em>{dup_row['name']}</em> appears <strong>{int(dup_row['n'])} times</strong> "
           f"this month at ₦{int(dup_row['amount']):,} each "
           f"(total ₦{total_dup:,}). "
           f"Check your Expenses page — if any are errors, delete them to get an accurate balance.",
           *PURPLE, priority=2, action="Check Expenses")

    # ── 13. Month-over-month projected spend ─────────────────────────────────
    if last_month_total > 0 and expenses_this_month > 0:
        pace_this = int(expenses_this_month / days_elapsed * days_in_month)
        diff      = pace_this - last_month_total
        pct_diff  = round(diff / last_month_total * 100, 1)
        if abs(pct_diff) >= 15:
            direction = "higher" if diff > 0 else "lower"
            arrow     = "&#x1F53C;" if diff > 0 else "&#x1F53D;"
            if diff > 0:
                cut_needed = int(diff * 0.5)
                extra = (f"Identify and cut ₦{cut_needed:,} from your top category "
                         f"this week to bring spending back in line.")
            else:
                extra = (f"You are on track to save ₦{abs(int(diff)):,} compared to last month. "
                         f"Consider moving that saving directly into a goal.")
            _s(arrow,
               f"Pace vs Last Month",
               f"At your current rate you will spend about <strong>₦{pace_this:,}</strong> "
               f"this month — <strong>{abs(pct_diff):.0f}% {direction}</strong> than last month's "
               f"₦{last_month_total:,}. {extra}",
               *(ORANGE if diff > 0 else GREEN), priority=2)

    # ── 14. Biggest single expense this month ────────────────────────────────
    if biggest_expense and int(biggest_expense["amount"]) > 10000:
        bamt = int(biggest_expense["amount"])
        bpct = round(bamt / max(expenses_this_month, 1) * 100)
        bname = (biggest_expense["name"] or "")[:35]
        bcat  = biggest_expense["category"] or ""
        _s("&#x1F4B5;",
           "Largest Single Expense",
           f"Your biggest expense this month is <strong>{bname}</strong>"
           + (f" ({bcat})" if bcat and bcat != bname else "") +
           f" at <strong>₦{bamt:,}</strong> — "
           f"<strong>{bpct}% of your total spending</strong>. "
           f"If this is a recurring cost, consider negotiating a better rate or finding an alternative.",
           *BLUE, priority=3)

    # ── 15. Most frequent category this week ─────────────────────────────────
    if most_frequent_this_week and int(most_frequent_this_week["cnt"]) >= 4:
        mf     = most_frequent_this_week
        mfcat  = mf["cat"] or "this category"
        mfcnt  = int(mf["cnt"])
        mftotal= int(mf["total"])
        _s("&#x1F501;",
           f"Frequent Spending: {mfcat[:25]}",
           f"You logged <strong>{mfcnt} {mfcat} expenses</strong> this week totalling "
           f"<strong>₦{mftotal:,}</strong>. "
           f"That is {mfcnt} transactions in 7 days. "
           f"Batching these into fewer, planned purchases could save both money and decision fatigue.",
           *BLUE, priority=3)

    # ── 16. Debt due soon ─────────────────────────────────────────────────────
    if upcoming_debts:
        for debt in upcoming_debts:
            days_to_due = (debt["due_date"] - today).days
            label_due   = "today" if days_to_due == 0 else f"in {days_to_due} day{'s' if days_to_due != 1 else ''}"
            is_borrowed = debt["type"] == "borrowed"
            _s("&#x1F4CB;",
               f"{'Payment Due' if is_borrowed else 'Repayment Due'} Soon",
               f"<strong>{debt['name']}</strong> — "
               f"₦{int(debt['balance_remaining']):,} is due <strong>{label_due}</strong> "
               f"({debt['due_date']}). "
               + ("Make sure you have enough balance to cover this payment."
                  if is_borrowed else
                  "Follow up with the person to arrange repayment."),
               *ORANGE, priority=1, action="Go to Tracker")

    # ── 17. No income recorded this month ────────────────────────────────────
    if income_this_month == 0 and expenses_this_month > 0 and days_elapsed >= 7:
        _s("&#x1F4B0;",
           "No Income Recorded This Month",
           f"You have logged ₦{expenses_this_month:,} in expenses this month but "
           f"<strong>no income has been recorded</strong>. "
           f"If you received your salary or any payment, add it on the Income page — "
           f"your savings rate and net balance will only be accurate when income is tracked.",
           *BLUE, priority=2, action="Go to Income")

    # Sort by priority (1=urgent first) and cap at 8
    S.sort(key=lambda x: x["priority"])
    return S[:8]


def _render_smart_suggestions(suggestions: list):
    """Render smart suggestion cards with action CTAs."""
    for s in suggestions:
        action_html = (
            f'<div style="margin-top:8px;">'
            f'<span style="background:{s["border"]};color:#fff;border-radius:20px;'
            f'padding:3px 14px;font-size:0.75rem;font-weight:700;">'
            f'&#x2192; {s["action"]}</span></div>'
            if s.get("action") else ""
        )
        st.markdown(
            f'<div class="insight-card" '
            f'style="background:{s["bg"]};border-left:4px solid {s["border"]};">'
            f'<div class="insight-icon">{s["icon"]}</div>'
            f'<div class="insight-body">'
            f'<div class="insight-title" style="color:{s["border"]};">{s["label"]}</div>'
            f'<div class="insight-text" style="color:{s["color"]};">{s["text"]}</div>'
            f'{action_html}'
            f'</div></div>',
            unsafe_allow_html=True
        )
def render_dashboard(user_id, pages):
    st.title("📊 Dashboard")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT COALESCE(SUM(balance),0) AS n FROM banks WHERE user_id=%s", (user_id,))
        total_balance = cursor.fetchone()["n"]
        current_month_start = datetime.now().date().replace(day=1)
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount),0) AS n FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id=%s AND t.type='debit'
              AND t.created_at >= %s
        """, (user_id, current_month_start))
        expenses_this_month = cursor.fetchone()["n"]
        cursor.execute("SELECT COUNT(*) AS n FROM banks WHERE user_id=%s", (user_id,))
        num_banks = cursor.fetchone()["n"]
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN type='credit' THEN amount ELSE -amount END),0) AS n
            FROM transactions t JOIN banks b ON t.bank_id = b.id WHERE b.user_id=%s
        """, (user_id,))
        net_savings = cursor.fetchone()["n"]
        cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
        spending_limit = cursor.fetchone()["monthly_spending_limit"] or 0

    # ── Empty state: no banks at all ──
    if num_banks == 0:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:12px;padding:28px 24px;text-align:center;margin:16px 0;">
          <div style="font-size:2.5rem;">&#x1F3E6;</div>
          <div style="font-size:1.1rem;font-weight:700;color:#1a2e3b;margin:8px 0 4px;">Welcome! Let's get you set up.</div>
          <div style="color:#6b7f8e;font-size:0.93rem;">
            Your dashboard will show your balances, charts, and insights once you add a bank account.<br>
            Start by adding your first bank on the <strong>Banks</strong> page.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Add my first bank account", key="dash_goto_banks"):
            st.session_state.nav_radio = pages.index("Banks")
            st.rerun()
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("💰 Total Balance",   f"₦{int(total_balance):,}")
    with col2: st.metric("📉 Spent (MTD)",     f"₦{int(expenses_this_month):,}")
    with col3: st.metric("🏦 Bank Accounts",   num_banks)
    with col4: st.metric("💚 Net Savings",     f"₦{int(net_savings):,}")

    # ── STAT CARDS — 7 insight cards ─────────────────────────────────────────
    st.divider()
    st.subheader("At a Glance")
    _stat_data = _fetch_stat_cards_data(user_id)
    _render_stat_cards(_stat_data)

    # ── Spending budget alert ──
    if spending_limit > 0 and expenses_this_month > 0:
        pct = (expenses_this_month / spending_limit) * 100
        if pct >= 100:
            st.error(
                f"Budget exceeded! You have spent ₦{expenses_this_month:,} — "
                f"₦{expenses_this_month - spending_limit:,.0f} over your ₦{spending_limit:,} monthly limit."
            )
        elif pct >= 80:
            st.warning(
                f"Spending alert: You have used {pct:.0f}% of your ₦{spending_limit:,} monthly budget "
                f"(₦{expenses_this_month:,} spent). Only ₦{spending_limit - expenses_this_month:,.0f} left."
            )
        elif pct >= 50:
            st.info(
                f"You are halfway through your monthly budget — {pct:.0f}% used "
                f"(₦{expenses_this_month:,} of ₦{spending_limit:,})."
            )
    elif spending_limit == 0:
        st.caption("Tip: Set a monthly spending limit in Settings to get budget alerts here.")

    # ── DAILY SAFE-TO-SPEND ───────────────────────────────────────────────────
    dss = compute_daily_safe_to_spend(user_id, spending_limit)
    if dss:
        dss_color  = "#0e7c5b" if dss["daily"] > 0 else "#c0392b"
        dss_label  = f"₦{dss['daily']:,}" if dss["daily"] > 0 else "Budget exceeded"
        days_label = f"{dss['days_remaining']} day{'s' if dss['days_remaining'] != 1 else ''} left"
        st.markdown(f"""
        <div style="background:linear-gradient(90deg,#1a2e3b,#0e7c5b);border-radius:12px;
                    padding:14px 20px;margin:10px 0;display:flex;
                    justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <div>
            <div style="color:#a8d8c8;font-size:0.78rem;font-weight:700;
                        text-transform:uppercase;letter-spacing:0.05em;">
              Daily safe-to-spend
            </div>
            <div style="color:#ffffff;font-size:1.6rem;font-weight:800;margin-top:2px;">
              {dss_label}
            </div>
            <div style="color:#a8d8c8;font-size:0.82rem;margin-top:2px;">
              {days_label} &nbsp;&middot;&nbsp;
              ₦{dss['budget_remaining']:,} remaining of ₦{dss['monthly_limit']:,}
            </div>
          </div>
          <div style="text-align:right;">
            <div style="color:#a8d8c8;font-size:0.78rem;">Spent this month</div>
            <div style="color:#ffffff;font-size:1.15rem;font-weight:700;">
              ₦{dss['spent']:,}
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── CATEGORY BUDGET CARDS ─────────────────────────────────────────────────
    cat_budgets = get_category_budgets(user_id)
    if cat_budgets:
        st.divider()
        st.subheader("Category Budgets")
        st.caption("How you are tracking against each spending category this month.")

        st.markdown("""
        <style>
        .cb-grid  { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr));
                    gap:12px; margin-bottom:4px; }
        .cb-card  { background:#ffffff; border:1px solid #d8eae2; border-radius:12px;
                    padding:14px 16px; }
        .cb-cat   { font-size:0.82rem; font-weight:700; color:#1a2e3b;
                    text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px;
                    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .cb-row   { display:flex; justify-content:space-between; font-size:0.88rem;
                    color:#6b7f8e; margin-bottom:8px; }
        .cb-spent { color:#c0392b; font-weight:700; }
        .cb-rem   { color:#0e7c5b; font-weight:700; }
        .cb-over  { color:#c0392b; font-style:italic; font-size:0.8rem; margin-top:4px; }
        .cb-bar-bg{ background:#eef5f2; border-radius:6px; height:8px; overflow:hidden; }
        .cb-bar-fg{ height:8px; border-radius:6px; transition:width 0.3s; }
        @media(max-width:640px) { .cb-grid { grid-template-columns:1fr 1fr !important; gap:8px !important; } }
        </style>
        """, unsafe_allow_html=True)

        cards_html = '<div class="cb-grid">'
        for cb in cat_budgets:
            pct       = min(cb["pct_used"], 100)
            bar_color = "#e74c3c" if cb["pct_used"] >= 100 else (
                        "#f39c12" if cb["pct_used"] >= 80 else "#0e7c5b")
            over_html = (
                f'<div class="cb-over">Over by ₦{cb["spent"] - cb["monthly_limit"]:,}</div>'
                if cb["pct_used"] >= 100 else ""
            )
            cards_html += f"""
            <div class="cb-card">
              <div class="cb-cat">{cb['category']}</div>
              <div class="cb-row">
                <span>Spent: <span class="cb-spent">₦{cb['spent']:,}</span></span>
                <span>Left: <span class="cb-rem">₦{cb['remaining']:,}</span></span>
              </div>
              <div class="cb-bar-bg">
                <div class="cb-bar-fg"
                     style="width:{pct}%;background:{bar_color};"></div>
              </div>
              <div style="font-size:0.75rem;color:#95a5a6;margin-top:4px;">
                {cb['pct_used']:.0f}% of ₦{cb['monthly_limit']:,}
              </div>
              {over_html}
            </div>"""
        cards_html += "</div>"
        st.markdown(cards_html, unsafe_allow_html=True)

        if st.button("Manage category budgets", key="dash_goto_cat_budgets"):
            st.session_state.nav_radio = pages.index("Settings")
            st.rerun()

    # ── CATEGORY BUDGETS ─────────────────────────────────────────────────────
    _today_dash      = datetime.now().date()
    _month_start_dash = _today_dash.replace(day=1)
    import calendar as _cal
    _days_in_month   = _cal.monthrange(_today_dash.year, _today_dash.month)[1]
    _days_elapsed    = _today_dash.day
    _days_remaining  = _days_in_month - _today_dash.day + 1   # include today

    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT category, monthly_limit FROM category_budgets WHERE user_id=%s AND monthly_limit > 0 ORDER BY category",
            (user_id,)
        )
        cat_budgets = cursor.fetchall()

        if cat_budgets:
            # Fetch actual spend per budgeted category this month
            budgeted_cats = [b["category"] for b in cat_budgets]
            cursor.execute("""
                SELECT COALESCE(e.category, e.name) AS cat, COALESCE(SUM(e.amount), 0) AS spent
                FROM expenses e JOIN banks b ON e.bank_id = b.id
                WHERE b.user_id = %s
                  AND e.created_at >= %s
                  AND COALESCE(e.category, e.name) = ANY(%s)
                GROUP BY cat
            """, (user_id, _month_start_dash, budgeted_cats))
            cat_spent_rows = {r["cat"]: int(r["spent"]) for r in cursor.fetchall()}

    if cat_budgets:
        st.divider()
        st.subheader("Category Budgets")

        # Daily safe-to-spend across all budgeted categories
        total_budget_all  = sum(int(b["monthly_limit"]) for b in cat_budgets)
        total_spent_all   = sum(cat_spent_rows.get(b["category"], 0) for b in cat_budgets)
        total_remain_all  = max(total_budget_all - total_spent_all, 0)
        daily_safe        = int(total_remain_all / _days_remaining) if _days_remaining > 0 else 0

        st.markdown(f"""
        <div style="background:linear-gradient(90deg,#1a2e3b 0%,#0e7c5b 100%);
                    border-radius:12px;padding:16px 20px;margin-bottom:14px;
                    display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
          <div>
            <div style="color:#a8d8c8;font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;">
              Daily Safe-to-Spend
            </div>
            <div style="color:#ffffff;font-size:1.6rem;font-weight:800;margin-top:2px;">
              ₦{daily_safe:,}
            </div>
            <div style="color:#a8d8c8;font-size:0.8rem;margin-top:2px;">
              {_days_remaining} day{'s' if _days_remaining != 1 else ''} left in {_today_dash.strftime('%B')}
            </div>
          </div>
          <div style="text-align:right;">
            <div style="color:#a8d8c8;font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;">
              Remaining (all categories)
            </div>
            <div style="color:#ffffff;font-size:1.4rem;font-weight:800;margin-top:2px;">
              ₦{total_remain_all:,}
            </div>
            <div style="color:#a8d8c8;font-size:0.8rem;margin-top:2px;">
              of ₦{total_budget_all:,} budgeted
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Per-category cards — 2 columns on desktop, 1 on mobile
        _cols = st.columns(2)
        for i, b in enumerate(cat_budgets):
            cat        = b["category"]
            limit      = int(b["monthly_limit"])
            spent      = cat_spent_rows.get(cat, 0)
            remaining  = limit - spent
            pct        = min((spent / limit) * 100, 100) if limit > 0 else 0
            daily_cat  = int(remaining / _days_remaining) if _days_remaining > 0 and remaining > 0 else 0

            if pct >= 100:
                bar_color  = "#e74c3c"
                badge_bg   = "#fdf2f2"
                badge_col  = "#c0392b"
                status_txt = "Over budget"
                overspend  = spent - limit
                detail_txt = f"₦{overspend:,} over limit"
            elif pct >= 80:
                bar_color  = "#f39c12"
                badge_bg   = "#fffbea"
                badge_col  = "#b7770d"
                status_txt = f"{pct:.0f}% used"
                detail_txt = f"₦{remaining:,} left &bull; ₦{daily_cat:,}/day"
            else:
                bar_color  = "#0e7c5b"
                badge_bg   = "#e8f5f0"
                badge_col  = "#0e7c5b"
                status_txt = f"{pct:.0f}% used"
                detail_txt = f"₦{remaining:,} left &bull; ₦{daily_cat:,}/day"

            bar_pct = min(pct, 100)

            with _cols[i % 2]:
                st.markdown(f"""
                <div style="background:#ffffff;border:1px solid #d8eae2;border-radius:12px;
                            padding:14px 16px;margin-bottom:10px;">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <div style="font-weight:700;color:#1a2e3b;font-size:0.96rem;">{cat}</div>
                    <div style="background:{badge_bg};color:{badge_col};border-radius:20px;
                                padding:2px 10px;font-size:0.75rem;font-weight:700;">
                      {status_txt}
                    </div>
                  </div>
                  <div style="background:#eef5f2;border-radius:6px;height:8px;margin-bottom:8px;overflow:hidden;">
                    <div style="background:{bar_color};width:{bar_pct:.1f}%;height:8px;border-radius:6px;
                                transition:width 0.3s;"></div>
                  </div>
                  <div style="display:flex;justify-content:space-between;font-size:0.8rem;color:#6b7f8e;">
                    <span>₦{spent:,} spent</span>
                    <span>₦{limit:,} limit</span>
                  </div>
                  <div style="font-size:0.78rem;color:#6b7f8e;margin-top:4px;">{detail_txt}</div>
                </div>
                """, unsafe_allow_html=True)

        if st.button("Manage category budgets", key="dash_cat_budget_link"):
            st.session_state.nav_radio = pages.index("Settings")
            st.rerun()
    # ── SMART SUGGESTIONS ────────────────────────────────────────────────────
    _suggestions = _fetch_smart_suggestions(user_id, spending_limit, expenses_this_month)
    if _suggestions:
        st.divider()
        st.subheader("Smart Suggestions")
        st.caption("Personalised insights based on your actual spending — updated every time you visit.")
        _render_smart_suggestions(_suggestions)

    # ── WEEKLY SUMMARY ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("This Week at a Glance")

    week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
    week_end   = datetime.now().date()

    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END), 0) AS income,
                   COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END), 0) AS spent
            FROM transactions t JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = %s AND t.created_at >= %s
        """, (user_id, week_start))
        week_totals = cursor.fetchone()

        cursor.execute("""
            SELECT e.category, SUM(e.amount) AS total
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            GROUP BY e.category ORDER BY total DESC LIMIT 1
        """, (user_id, week_start))
        week_top = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) AS n FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
        """, (user_id, week_start))
        week_txn_count = cursor.fetchone()["n"] or 0

    week_income = int(week_totals["income"] or 0)
    week_spent  = int(week_totals["spent"]  or 0)
    week_net    = week_income - week_spent
    net_color   = "#2ecc71" if week_net >= 0 else "#e74c3c"
    net_label   = f"+₦{week_net:,}" if week_net >= 0 else f"-₦{abs(week_net):,}"
    top_spend_html = (
        f'<div class="week-stat"><div class="week-stat-label">Top Spend</div>'
        f'<div class="week-stat-value" style="font-size:0.9rem;">{week_top["category"]}</div></div>'
        if week_top else ""
    )

    st.markdown(f"""
    <div class="week-card">
      <div class="week-title">&#x1F4C5; {week_start.strftime("%d %b")} &rarr; Today</div>
      <div class="week-grid">
        <div class="week-stat">
          <div class="week-stat-label">Income</div>
          <div class="week-stat-value">₦{week_income:,}</div>
        </div>
        <div class="week-stat">
          <div class="week-stat-label">Spent</div>
          <div class="week-stat-value">₦{week_spent:,}</div>
        </div>
        <div class="week-stat">
          <div class="week-stat-label">Net</div>
          <div class="week-stat-value" style="color:{net_color};">{net_label}</div>
        </div>
        <div class="week-stat">
          <div class="week-stat-label">Expenses</div>
          <div class="week-stat-value">{week_txn_count}</div>
        </div>
        {top_spend_html}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── PDF REPORTS ───────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Download Reports (PDF)")
    st.caption(
        "Generate professional PDF reports for any month. "
        "Each report opens in a new tab and can be printed or saved."
    )

    # Month selector — shared by all 4 reports
    _report_months = []
    for _i in range(12):
        _d = (datetime.now().replace(day=1) - timedelta(days=_i * 28)).replace(day=1)
        _report_months.append((_d.year, _d.month))
    _report_months = sorted(set(_report_months), reverse=True)

    _sel_ym = st.selectbox(
        "Select month for reports",
        _report_months,
        format_func=lambda ym: datetime(ym[0], ym[1], 1).strftime("%B %Y"),
        key="pdf_report_month_select"
    )
    _sel_year, _sel_month = _sel_ym
    _month_label = datetime(_sel_year, _sel_month, 1).strftime("%B %Y")

    st.markdown("""
    <style>
    .rpt-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
        gap: 12px;
        margin: 8px 0 16px 0;
    }
    .rpt-card {
        background: #f4f7f6;
        border: 1px solid #d8eae2;
        border-radius: 12px;
        padding: 16px 18px;
    }
    .rpt-title { font-weight: 700; color: #1a2e3b; font-size: 0.95rem; margin-bottom: 4px; }
    .rpt-desc  { color: #6b7f8e; font-size: 0.82rem; line-height: 1.5; }
    @media(max-width:640px){ .rpt-grid{ grid-template-columns:1fr; } }
    </style>
    <div class="rpt-grid">
      <div class="rpt-card">
        <div class="rpt-title">&#x1F4CB; Monthly Statement</div>
        <div class="rpt-desc">Full summary of income, expenses by category, and every transaction for the month.</div>
      </div>
      <div class="rpt-card">
        <div class="rpt-title">&#x1F3AF; Goal Progress Report</div>
        <div class="rpt-desc">All savings goals with progress bars, contribution history, and completion projections.</div>
      </div>
      <div class="rpt-card">
        <div class="rpt-title">&#x1F4CA; Category Budget Report</div>
        <div class="rpt-desc">Every category budget vs actual spend, with colour-coded over/under status for the month.</div>
      </div>
      <div class="rpt-card">
        <div class="rpt-title">&#x1F3E6; Bank-by-Bank Report</div>
        <div class="rpt-desc">Each bank account with its monthly income, spending, net, and full transaction list.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    _col1, _col2 = st.columns(2)
    _col3, _col4 = st.columns(2)

    with _col1:
        if st.button(
            f"Generate Monthly Statement — {_month_label}",
            key="pdf_monthly_btn",
            use_container_width=True
        ):
            with st.spinner("Building PDF…"):
                try:
                    from pdf_report import fetch_monthly_data, build_monthly_statement
                    _data = fetch_monthly_data(user_id, _sel_year, _sel_month)
                    _pdf_bytes = build_monthly_statement(_data)
                    st.download_button(
                        label=f"Download Monthly Statement ({_month_label})",
                        data=_pdf_bytes,
                        file_name=f"BudgetRight_Statement_{_sel_year}_{_sel_month:02d}.pdf",
                        mime="application/pdf",
                        key="dl_monthly_pdf",
                        use_container_width=True,
                        type="primary",
                    )
                except Exception as _e:
                    st.error(f"Could not generate PDF: {_e}")

    with _col2:
        if st.button(
            "Generate Goal Progress Report",
            key="pdf_goals_btn",
            use_container_width=True
        ):
            with st.spinner("Building PDF…"):
                try:
                    from pdf_report import fetch_goal_data, build_goal_progress_report
                    _data = fetch_goal_data(user_id)
                    _pdf_bytes = build_goal_progress_report(_data)
                    st.download_button(
                        label="Download Goal Progress Report",
                        data=_pdf_bytes,
                        file_name=f"BudgetRight_Goals_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        key="dl_goals_pdf",
                        use_container_width=True,
                        type="primary",
                    )
                except Exception as _e:
                    st.error(f"Could not generate PDF: {_e}")

    with _col3:
        if st.button(
            f"Generate Category Budget Report — {_month_label}",
            key="pdf_catbudget_btn",
            use_container_width=True
        ):
            with st.spinner("Building PDF…"):
                try:
                    from pdf_report import fetch_category_budget_data, build_category_budget_report
                    _data = fetch_category_budget_data(user_id, _sel_year, _sel_month)
                    _pdf_bytes = build_category_budget_report(_data)
                    st.download_button(
                        label=f"Download Category Budget Report ({_month_label})",
                        data=_pdf_bytes,
                        file_name=f"BudgetRight_CategoryBudget_{_sel_year}_{_sel_month:02d}.pdf",
                        mime="application/pdf",
                        key="dl_catbudget_pdf",
                        use_container_width=True,
                        type="primary",
                    )
                except Exception as _e:
                    st.error(f"Could not generate PDF: {_e}")

    with _col4:
        if st.button(
            f"Generate Bank Report — {_month_label}",
            key="pdf_bank_btn",
            use_container_width=True
        ):
            with st.spinner("Building PDF…"):
                try:
                    from pdf_report import fetch_bank_data, build_bank_report
                    _data = fetch_bank_data(user_id, _sel_year, _sel_month)
                    _pdf_bytes = build_bank_report(_data)
                    st.download_button(
                        label=f"Download Bank Report ({_month_label})",
                        data=_pdf_bytes,
                        file_name=f"BudgetRight_Banks_{_sel_year}_{_sel_month:02d}.pdf",
                        mime="application/pdf",
                        key="dl_bank_pdf",
                        use_container_width=True,
                        type="primary",
                    )
                except Exception as _e:
                    st.error(f"Could not generate PDF: {_e}")

    # Legacy CSV download still available
    with st.expander("Download raw CSV data instead", expanded=False):
        _csv_month_opts = [ym for ym in _report_months]
        _csv_sel = st.selectbox(
            "Month",
            _csv_month_opts,
            format_func=lambda ym: datetime(ym[0], ym[1], 1).strftime("%B %Y"),
            key="csv_report_month_select"
        )
        if st.button("Generate CSV", key="generate_csv_btn", use_container_width=True):
            _r_start = datetime(_csv_sel[0], _csv_sel[1], 1).date()
            import calendar as _cal2
            _r_end = datetime(
                _csv_sel[0], _csv_sel[1],
                _cal2.monthrange(_csv_sel[0], _csv_sel[1])[1]
            ).date()
            _csv_label = _r_start.strftime("%B %Y")
            with get_db() as (conn, cursor):
                cursor.execute("""
                    SELECT e.created_at, e.category, b.bank_name, e.amount
                    FROM expenses e JOIN banks b ON e.bank_id=b.id
                    WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
                    ORDER BY e.created_at
                """, (user_id, _r_start, _r_end))
                _exp_rows = cursor.fetchall()
                cursor.execute("""
                    SELECT t.created_at,
                           CASE WHEN t.type='credit' THEN 'Income' ELSE 'Expense' END AS txn_type,
                           t.description, b.bank_name, t.amount
                    FROM transactions t JOIN banks b ON t.bank_id=b.id
                    WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
                    ORDER BY t.created_at
                """, (user_id, _r_start, _r_end))
                _txn_rows = cursor.fetchall()
                cursor.execute("""
                    SELECT COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS ti,
                           COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS ts
                    FROM transactions t JOIN banks b ON t.bank_id=b.id
                    WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
                """, (user_id, _r_start, _r_end))
                _sr = cursor.fetchone()
            _ti = int(_sr["ti"] or 0)
            _ts = int(_sr["ts"] or 0)
            _out = io.StringIO()
            _out.write(f"Budget Right - {_csv_label}\nGenerated: {datetime.now().strftime('%d %b %Y %H:%M')}\n\n")
            _out.write(f"SUMMARY\nTotal Income,₦{_ti:,}\nTotal Spent,₦{_ts:,}\nNet Saved,₦{_ti-_ts:,}\n\n")
            _out.write("EXPENSES\nDate,Category,Bank,Amount (NGN)\n")
            for _r in _exp_rows:
                _out.write(f"{_r['created_at']},{_r['category']},{_r['bank_name']},{_r['amount']}\n")
            _out.write("\nALL TRANSACTIONS\nDate,Type,Description,Bank,Amount (NGN)\n")
            for _r in _txn_rows:
                _desc = (_r["description"] or "").replace(",", " ")
                _out.write(f"{_r['created_at']},{_r['txn_type']},{_desc},{_r['bank_name']},{_r['amount']}\n")
            st.download_button(
                label=f"Download {_csv_label} CSV",
                data=_out.getvalue().encode("utf-8"),
                file_name=f"BudgetRight_{_csv_sel[0]}_{_csv_sel[1]:02d}.csv",
                mime="text/csv",
                key="dl_csv_btn",
                use_container_width=True,
            )

    st.divider()
    st.subheader("Income vs Expenses Over Time")
    period_map = {
        "Last 30 Days": timedelta(days=30), "Last 3 Months": timedelta(days=90),
        "Last 6 Months": timedelta(days=180), "Last Year": timedelta(days=365), "All Time": None,
    }
    selected_period = st.selectbox("Select Period", list(period_map.keys()), key="period_select")
    start_date = (datetime.now() - period_map[selected_period]).date() if period_map[selected_period] else datetime(2000,1,1).date()
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT t.created_at, t.type, t.amount FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id=%s AND t.created_at >= %s ORDER BY t.created_at
        """, (user_id, start_date))
        rows = cursor.fetchall()
    if rows:
        df = pd.DataFrame([(r["created_at"], r["type"], r["amount"]) for r in rows], columns=["date","type","amount"])
        df["date"] = pd.to_datetime(df["date"])
        df_pivot = df.pivot_table(index="date", columns="type", values="amount", aggfunc="sum", fill_value=0)
        for col in ["credit","debit"]:
            if col not in df_pivot.columns: df_pivot[col] = 0
        df_pivot = df_pivot.rename(columns={"credit":"Income","debit":"Expenses"}).sort_index().reset_index()
        fig_trend = px.line(
            df_pivot, x="date", y=["Income","Expenses"],
            color_discrete_map={"Income":"#0e7c5b","Expenses":"#c0392b"},
            labels={"date":"Date","value":"Amount (₦)","variable":""},
        )
        fig_trend.update_traces(line_width=2)
        fig_trend.update_layout(
            margin=dict(t=10,b=20,l=10,r=10), height=280,
            legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="left",x=0),
            hovermode="x unified",
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:10px;padding:20px 22px;text-align:center;color:#6b7f8e;">
          <div style="font-size:2rem;">&#x1F4C8;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a2e3b;">No transactions yet</div>
          <div style="font-size:0.92rem;">Add income on the <strong>Income</strong> page or log an expense on the <strong>Expenses</strong> page to see your chart here.</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    st.subheader("Expense Breakdown by Category")
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT COALESCE(category, name) AS cat, SUM(amount) AS total
            FROM expenses
            WHERE user_id = %s
            GROUP BY COALESCE(category, name)
            ORDER BY total DESC
        """, (user_id,))
        pie_rows = cursor.fetchall()
    if pie_rows:
        df_pie = pd.DataFrame([(r["cat"], r["total"]) for r in pie_rows], columns=["Category", "Amount"])
        threshold    = df_pie["Amount"].sum() * 0.02
        df_pie_main  = df_pie[df_pie["Amount"] >= threshold]
        df_pie_other = df_pie[df_pie["Amount"] < threshold]
        if not df_pie_other.empty:
            df_pie_main = pd.concat([df_pie_main, pd.DataFrame([{"Category": "Others", "Amount": df_pie_other["Amount"].sum()}])], ignore_index=True)
        fig = px.pie(df_pie_main, names="Category", values="Amount",
                     color_discrete_sequence=px.colors.qualitative.Set3, hole=0.38)
        fig.update_traces(
            textposition="inside", textinfo="percent",
            hovertemplate="<b>%{label}</b><br>₦%{value:,.0f}<br>%{percent}<extra></extra>",
        )
        fig.update_layout(
            margin=dict(t=10, b=10, l=0, r=0), height=340,
            legend=dict(orientation="v", x=1.02, y=0.5, font_size=11),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:10px;padding:20px 22px;text-align:center;color:#6b7f8e;">
          <div style="font-size:2rem;">&#x1F967;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a2e3b;">Expense breakdown will appear here</div>
          <div style="font-size:0.92rem;">
            Log your first expense on the <strong>Expenses</strong> page —
            or use the Quick Add buttons for Transport, Food, Airtime and more.
          </div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: INCOME =================
