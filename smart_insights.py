# smart_insights.py
# ─────────────────────────────────────────────────────────────────────────────
# Pure-logic module.  No Streamlit imports — safe to call from any page.
#
# Public API
# ──────────
#   generate_all_insights(user_id)  → list[Insight]
#
# Each Insight is a dict:
#   {
#     "category":  str,   # "spending" | "saving" | "goal" | "habit" | "warning"
#     "icon":      str,   # single emoji
#     "title":     str,   # short headline
#     "body":      str,   # 1-2 sentence explanation with numbers
#     "action":    str,   # optional call-to-action label
#     "priority":  int,   # 1 (urgent) … 5 (low)  — lower = shown first
#   }
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import calendar
from datetime import date, timedelta
from db import get_db


# ── tiny data class (plain dict factory) ─────────────────────────────────────

def _insight(category: str, icon: str, title: str, body: str,
             action: str = "", priority: int = 3) -> dict:
    return dict(category=category, icon=icon, title=title,
                body=body, action=action, priority=priority)


def _ngn(n: int) -> str:
    return f"₦{n:,}"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def generate_all_insights(user_id: int) -> list[dict]:
    """
    Run every insight engine and return a deduplicated, priority-sorted list.
    Safe to call multiple times — all reads are inside a single DB context.
    """
    try:
        data = _fetch_all_data(user_id)
    except Exception:
        return []

    insights: list[dict] = []

    insights += _category_vs_last_month(data)
    insights += _small_purchases_add_up(data)
    insights += _goal_savings_pace(data)
    insights += _top_category_concentration(data)
    insights += _no_spend_streak(data)
    insights += _weekend_vs_weekday_spending(data)
    insights += _recurring_vs_discretionary(data)
    insights += _income_volatility(data)
    insights += _budget_pace(data)
    insights += _largest_single_expense(data)
    insights += _savings_rate_trend(data)
    insights += _category_new_spike(data)
    insights += _daily_average_insight(data)
    insights += _debt_payoff_suggestions(data)
    insights += _emergency_fund_insight(data)

    # Sort: priority ASC, then most novel first
    insights.sort(key=lambda i: (i["priority"], i["title"]))

    # Cap at 20 so the page is not overwhelming
    return insights[:20]


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHER  (single round-trip)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_all_data(user_id: int) -> dict:
    today       = date.today()
    m_start     = today.replace(day=1)
    prev_m_end  = m_start - timedelta(days=1)
    prev_m_start= prev_m_end.replace(day=1)
    days_so_far = today.day
    days_in_prev= calendar.monthrange(prev_m_end.year, prev_m_end.month)[1]

    with get_db() as (conn, cursor):

        # ── current month category totals ─────────────────────────────────────
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat,
                   SUM(e.amount)                AS total,
                   COUNT(*)                     AS cnt,
                   AVG(e.amount)                AS avg_amt,
                   MIN(e.amount)                AS min_amt,
                   MAX(e.amount)                AS max_amt
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            GROUP BY cat
        """, (user_id, m_start))
        cur_cats = {r["cat"]: dict(r) for r in cursor.fetchall()}

        # ── previous month category totals ───────────────────────────────────
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat,
                   SUM(e.amount) AS total,
                   COUNT(*)      AS cnt
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at BETWEEN %s AND %s
            GROUP BY cat
        """, (user_id, prev_m_start, prev_m_end))
        prev_cats = {r["cat"]: dict(r) for r in cursor.fetchall()}

        # ── all expenses this month (for small-purchase analysis) ─────────────
        cursor.execute("""
            SELECT e.amount, e.created_at, COALESCE(e.category, e.name) AS cat,
                   EXTRACT(DOW FROM e.created_at) AS dow
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            ORDER BY e.amount DESC
        """, (user_id, m_start))
        cur_expenses = cursor.fetchall()

        # ── monthly totals last 3 months (income + spend) ─────────────────────
        cursor.execute("""
            SELECT DATE_TRUNC('month', t.created_at) AS mo,
                   SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END) AS income,
                   SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END) AS spent
            FROM transactions t JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = %s AND t.created_at >= %s
            GROUP BY mo ORDER BY mo DESC
        """, (user_id, today - timedelta(days=90)))
        monthly_totals = cursor.fetchall()

        # ── goals ─────────────────────────────────────────────────────────────
        cursor.execute("""
            SELECT id, name, target_amount, current_amount, created_at
            FROM goals WHERE user_id = %s AND status = 'active'
        """, (user_id,))
        goals = cursor.fetchall()

        # ── average monthly contribution per goal ────────────────────────────
        goal_monthly_avg = {}
        for g in goals:
            cursor.execute("""
                SELECT COALESCE(AVG(monthly_total), 0) AS avg_mo
                FROM (
                    SELECT DATE_TRUNC('month', contributed_at) AS mo,
                           SUM(amount) AS monthly_total
                    FROM goal_contributions
                    WHERE goal_id = %s
                    GROUP BY mo
                ) sub
            """, (g["id"],))
            goal_monthly_avg[g["id"]] = int(cursor.fetchone()["avg_mo"] or 0)

        # ── monthly spending limit + overdraft ────────────────────────────────
        cursor.execute(
            "SELECT monthly_spending_limit, allow_overdraft FROM users WHERE id = %s",
            (user_id,)
        )
        urow  = cursor.fetchone()
        budget = int(urow["monthly_spending_limit"] or 0) if urow else 0

        # ── debts ─────────────────────────────────────────────────────────────
        cursor.execute("""
            SELECT name, type, balance_remaining, monthly_payment, interest_rate
            FROM debts WHERE user_id = %s AND status = 'active'
        """, (user_id,))
        debts = cursor.fetchall()

        # ── emergency fund plan ───────────────────────────────────────────────
        cursor.execute(
            "SELECT target_months, monthly_expenses_estimate, current_saved "
            "FROM emergency_fund_plan WHERE user_id = %s",
            (user_id,)
        )
        ef_plan = cursor.fetchone()

        # ── recurring items ───────────────────────────────────────────────────
        cursor.execute("""
            SELECT name, type, amount, frequency
            FROM recurring_items WHERE user_id = %s AND active = 1
        """, (user_id,))
        recurring = cursor.fetchall()

    return dict(
        today=today,
        m_start=m_start,
        prev_m_start=prev_m_start,
        prev_m_end=prev_m_end,
        days_so_far=days_so_far,
        cur_cats=cur_cats,
        prev_cats=prev_cats,
        cur_expenses=cur_expenses,
        monthly_totals=monthly_totals,
        goals=goals,
        goal_monthly_avg=goal_monthly_avg,
        budget=budget,
        debts=debts,
        ef_plan=ef_plan,
        recurring=recurring,
    )


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT ENGINES
# ─────────────────────────────────────────────────────────────────────────────

def _category_vs_last_month(data: dict) -> list[dict]:
    """
    "You spent more on Transport this month than last month"
    Compares current-month spend per category to the full previous month,
    pro-rating the previous month's total to the same number of days so far.
    """
    insights = []
    days_so_far  = data["days_so_far"]
    prev_m_end   = data["prev_m_end"]
    days_in_prev = calendar.monthrange(prev_m_end.year, prev_m_end.month)[1]

    for cat, cur in data["cur_cats"].items():
        prev = data["prev_cats"].get(cat)
        if not prev:
            continue
        cur_total  = int(cur["total"])
        prev_total = int(prev["total"])
        # Pro-rate prev to same elapsed days
        prev_prorated = int(prev_total * days_so_far / max(days_in_prev, 1))
        if prev_prorated == 0:
            continue
        pct_change = round((cur_total - prev_prorated) / prev_prorated * 100)

        if pct_change >= 30 and cur_total >= 5_000:
            priority = 1 if pct_change >= 60 else 2
            insights.append(_insight(
                "spending", "📈",
                f"Higher {cat} Spending",
                f"You've spent {_ngn(cur_total)} on {cat} so far this month — "
                f"{pct_change}% more than the same point last month "
                f"({_ngn(prev_prorated)} prorated). "
                f"At this pace you'll spend {_ngn(int(cur_total / days_so_far * 30))} by month-end.",
                f"Review {cat} expenses",
                priority=priority,
            ))
        elif pct_change <= -25 and prev_prorated >= 5_000:
            insights.append(_insight(
                "saving", "📉",
                f"Less Spent on {cat}",
                f"You've spent {_ngn(cur_total)} on {cat} this month — "
                f"{abs(pct_change)}% less than the same point last month. "
                f"That's {_ngn(prev_prorated - cur_total)} saved so far. Keep it up!",
                priority=4,
            ))

    return insights


def _small_purchases_add_up(data: dict) -> list[dict]:
    """
    "Small purchases under ₦5,000 added up to ₦40,000 this month"
    """
    threshold = 5_000
    small = [e for e in data["cur_expenses"] if int(e["amount"]) < threshold]
    if not small:
        return []
    total      = sum(int(e["amount"]) for e in small)
    count      = len(small)
    all_total  = sum(int(e["amount"]) for e in data["cur_expenses"])
    pct        = round(total / all_total * 100) if all_total else 0

    if total < 10_000 or count < 5:
        return []

    avg = total // count
    return [_insight(
        "spending", "🪣",
        "Small Purchases Add Up",
        f"You've made {count} purchases under {_ngn(threshold)} this month, "
        f"totalling {_ngn(total)} — {pct}% of all your spending. "
        f"Average small spend: {_ngn(avg)}. "
        f"These micro-spends are easy to overlook but hard to recover.",
        "See small expenses",
        priority=2,
    )]


def _goal_savings_pace(data: dict) -> list[dict]:
    """
    "Save ₦10,000 weekly and reach your goal in 3 months"
    For each active goal, show weekly/monthly amount needed and estimated completion.
    """
    insights = []
    today = data["today"]

    for g in data["goals"]:
        target   = int(g["target_amount"])
        saved    = int(g["current_amount"])
        shortfall= target - saved
        if shortfall <= 0:
            continue

        avg_monthly = data["goal_monthly_avg"].get(g["id"], 0)

        # Completion time projections
        monthly_3  = -(-shortfall // 3)   # ceiling div
        monthly_6  = -(-shortfall // 6)
        monthly_12 = -(-shortfall // 12)
        weekly_3   = -(-shortfall // 13)
        weekly_6   = -(-shortfall // 26)

        # How long at current pace?
        if avg_monthly > 0:
            months_at_current = round(shortfall / avg_monthly, 1)
            pace_sentence = (
                f"At your current pace of {_ngn(avg_monthly)}/month, "
                f"you'll reach it in about {months_at_current} more month(s). "
            )
        else:
            pace_sentence = "You haven't made any contributions yet. "

        insights.append(_insight(
            "goal", "🎯",
            f"Goal: {g['name']}",
            f"{pace_sentence}"
            f"To finish in 3 months: save {_ngn(monthly_3)}/month (or {_ngn(weekly_3)}/week). "
            f"To finish in 6 months: save {_ngn(monthly_6)}/month (or {_ngn(weekly_6)}/week). "
            f"{_ngn(shortfall)} remaining out of {_ngn(target)} target.",
            f"Contribute to {g['name']}",
            priority=2,
        ))

    return insights


def _top_category_concentration(data: dict) -> list[dict]:
    """
    Warn when one category eats >45% of total monthly spending.
    """
    if not data["cur_cats"]:
        return []
    total_spent = sum(int(c["total"]) for c in data["cur_cats"].values())
    if total_spent == 0:
        return []
    sorted_cats = sorted(data["cur_cats"].items(), key=lambda x: int(x[1]["total"]), reverse=True)
    top_cat, top_data = sorted_cats[0]
    top_total = int(top_data["total"])
    pct = round(top_total / total_spent * 100)

    if pct >= 45 and top_total >= 10_000:
        return [_insight(
            "spending", "⚠️",
            f"{top_cat} Is Dominating Your Budget",
            f"'{top_cat}' accounts for {pct}% of your total spending this month "
            f"({_ngn(top_total)} of {_ngn(total_spent)}). "
            f"A single category above 40% often signals an area to review.",
            f"Review {top_cat}",
            priority=2,
        )]
    return []


def _no_spend_streak(data: dict) -> list[dict]:
    """
    Celebrate consecutive no-spend days in the current month.
    """
    today    = data["today"]
    m_start  = data["m_start"]
    spend_days = {e["created_at"] for e in data["cur_expenses"]}

    # Find the longest consecutive no-spend streak ending today or yesterday
    streak = 0
    d = today
    while d >= m_start:
        if d not in spend_days:
            streak += 1
        else:
            break
        d -= timedelta(days=1)

    if streak >= 3:
        return [_insight(
            "habit", "🏅",
            f"{streak}-Day No-Spend Streak",
            f"You haven't logged any expenses for {streak} consecutive days. "
            f"No-spend days are one of the fastest ways to boost your savings rate. "
            f"Keep going!",
            priority=4,
        )]
    return []


def _weekend_vs_weekday_spending(data: dict) -> list[dict]:
    """
    "You spend 3× more on weekends than weekdays"
    DOW: 0=Sunday, 6=Saturday in PostgreSQL EXTRACT(DOW).
    """
    weekend_total   = sum(int(e["amount"]) for e in data["cur_expenses"] if int(e["dow"]) in (0, 6))
    weekday_total   = sum(int(e["amount"]) for e in data["cur_expenses"] if int(e["dow"]) not in (0, 6))
    weekend_days    = len({e["created_at"] for e in data["cur_expenses"] if int(e["dow"]) in (0, 6)})
    weekday_days    = len({e["created_at"] for e in data["cur_expenses"] if int(e["dow"]) not in (0, 6)})

    if weekend_days == 0 or weekday_days == 0:
        return []

    weekend_daily = weekend_total / weekend_days
    weekday_daily = weekday_total / max(weekday_days, 1)
    if weekday_daily == 0:
        return []

    ratio = round(weekend_daily / weekday_daily, 1)
    if ratio >= 2.0 and weekend_total >= 5_000:
        return [_insight(
            "spending", "📅",
            "Weekend Spending Spike",
            f"Your average daily spend on weekends ({_ngn(int(weekend_daily))}/day) is "
            f"{ratio}× higher than weekdays ({_ngn(int(weekday_daily))}/day). "
            f"Weekend totals this month: {_ngn(weekend_total)}. "
            f"Planning weekend activities in advance can cut this significantly.",
            priority=3,
        )]
    return []


def _recurring_vs_discretionary(data: dict) -> list[dict]:
    """
    Break down how much of spending is locked-in (recurring) vs discretionary.
    """
    monthly_recurring = sum(
        int(r["amount"]) for r in data["recurring"]
        if r["type"] == "expense" and r["frequency"] == "monthly"
    )
    total_spent = sum(int(c["total"]) for c in data["cur_cats"].values())
    if total_spent == 0 or monthly_recurring == 0:
        return []

    pct_locked = round(monthly_recurring / total_spent * 100)
    discretionary = max(total_spent - monthly_recurring, 0)

    if pct_locked >= 60:
        return [_insight(
            "spending", "🔒",
            "Most Spending Is Fixed Costs",
            f"{pct_locked}% of your spending ({_ngn(monthly_recurring)}) comes from recurring "
            f"fixed expenses. Only {_ngn(discretionary)} is discretionary. "
            f"To save more, you'll need to reduce a fixed cost — not just cut small ones.",
            priority=3,
        )]
    return []


def _income_volatility(data: dict) -> list[dict]:
    """
    Flag if income varied more than 30% month-to-month over the last 3 months.
    """
    months = [dict(r) for r in data["monthly_totals"]]
    incomes = [int(m["income"]) for m in months if int(m["income"]) > 0]
    if len(incomes) < 2:
        return []

    avg_income = sum(incomes) / len(incomes)
    if avg_income == 0:
        return []
    deviation  = max(abs(i - avg_income) for i in incomes) / avg_income * 100

    if deviation >= 30:
        return [_insight(
            "warning", "📊",
            "Variable Income Detected",
            f"Your income has varied by up to {round(deviation)}% across the last {len(incomes)} months "
            f"(avg: {_ngn(int(avg_income))}). "
            f"With variable income, target saving 30%+ in high-income months to buffer the low ones.",
            priority=2,
        )]
    return []


def _budget_pace(data: dict) -> list[dict]:
    """
    Project end-of-month spending based on daily average so far.
    """
    budget = data["budget"]
    if budget <= 0:
        return []
    total_spent = sum(int(c["total"]) for c in data["cur_cats"].values())
    if total_spent == 0:
        return []

    days_so_far = data["days_so_far"]
    today       = data["today"]
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    daily_avg   = total_spent / days_so_far
    projected   = int(daily_avg * days_in_month)
    pct_now     = round(total_spent / budget * 100)

    if projected > budget * 1.1:
        overshoot = projected - budget
        return [_insight(
            "warning", "🚨",
            "On Track to Exceed Budget",
            f"You've used {pct_now}% of your {_ngn(budget)} budget in {days_so_far} days. "
            f"At this daily rate ({_ngn(int(daily_avg))}/day), you'll spend "
            f"~{_ngn(projected)} by month-end — {_ngn(overshoot)} over budget. "
            f"You need to spend under {_ngn(int((budget - total_spent) / max(days_in_month - days_so_far, 1)))}/day for the rest of the month.",
            "Review budget",
            priority=1,
        )]
    elif projected < budget * 0.75:
        surplus = budget - projected
        return [_insight(
            "saving", "✅",
            "Well Under Budget Pace",
            f"At your current pace you'll spend ~{_ngn(projected)} this month — "
            f"{_ngn(surplus)} under your {_ngn(budget)} budget. "
            f"Consider moving that surplus to a savings goal before month-end.",
            "Add to a goal",
            priority=4,
        )]
    return []


def _largest_single_expense(data: dict) -> list[dict]:
    """
    Highlight the single biggest expense this month if it's unusually large.
    """
    if not data["cur_expenses"]:
        return []
    total_spent = sum(int(e["amount"]) for e in data["cur_expenses"])
    largest     = max(data["cur_expenses"], key=lambda e: int(e["amount"]))
    amt         = int(largest["amount"])
    pct         = round(amt / total_spent * 100) if total_spent else 0

    if pct >= 30 and amt >= 20_000:
        return [_insight(
            "spending", "🔍",
            "One Large Expense Stands Out",
            f"Your biggest single expense this month is {_ngn(amt)} "
            f"on '{largest['cat']}' ({pct}% of all spending). "
            f"Was this planned? If not, this is where to start cutting.",
            priority=3,
        )]
    return []


def _savings_rate_trend(data: dict) -> list[dict]:
    """
    Compute savings rate for current and last month, show direction.
    """
    months = [dict(r) for r in data["monthly_totals"]]
    if len(months) < 2:
        return []

    def _sr(income, spent):
        if not income:
            return None
        return round((income - spent) / income * 100, 1)

    cur_m  = months[0]
    prev_m = months[1]
    cur_sr  = _sr(int(cur_m["income"]), int(cur_m["spent"]))
    prev_sr = _sr(int(prev_m["income"]), int(prev_m["spent"]))

    if cur_sr is None or prev_sr is None:
        return []

    diff = round(cur_sr - prev_sr, 1)

    if diff <= -10 and cur_sr < 20:
        return [_insight(
            "warning", "⬇️",
            "Savings Rate Dropping",
            f"Your savings rate this month is {cur_sr}%, down {abs(diff)} percentage points "
            f"from last month ({prev_sr}%). "
            f"A consistent rate below 20% makes it hard to build a financial cushion.",
            priority=2,
        )]
    elif diff >= 10 and cur_sr >= 20:
        return [_insight(
            "saving", "⬆️",
            "Savings Rate Improving",
            f"Your savings rate climbed to {cur_sr}% this month, up {diff} points from "
            f"last month ({prev_sr}%). Above 20% is where real wealth-building starts.",
            priority=4,
        )]
    return []


def _category_new_spike(data: dict) -> list[dict]:
    """
    Detect a category that appeared this month but had zero spend last month —
    only flag it if the amount is significant (≥ ₦10,000).
    """
    insights = []
    for cat, cur in data["cur_cats"].items():
        if cat in data["prev_cats"]:
            continue
        amt = int(cur["total"])
        if amt >= 10_000:
            insights.append(_insight(
                "spending", "🆕",
                f"New Spending Category: {cat}",
                f"You spent {_ngn(amt)} on '{cat}' this month — "
                f"a category you had no spend on last month. "
                f"Is this a one-time cost or a new regular expense?",
                priority=3,
            ))
    return insights[:2]  # cap at 2 to avoid noise


def _daily_average_insight(data: dict) -> list[dict]:
    """
    Show daily average spending and how it compares to income daily rate.
    """
    total_spent = sum(int(c["total"]) for c in data["cur_cats"].values())
    if total_spent == 0 or data["days_so_far"] == 0:
        return []

    daily_avg = int(total_spent / data["days_so_far"])
    monthly   = [dict(r) for r in data["monthly_totals"]]
    if not monthly:
        return []

    income = int(monthly[0]["income"])
    if income == 0:
        return []

    today = data["today"]
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    daily_income_budget = income // days_in_month

    if daily_avg > daily_income_budget * 1.2:
        return [_insight(
            "warning", "⏱️",
            "Daily Spend Exceeds Income Rate",
            f"You're spending an average of {_ngn(daily_avg)}/day this month, "
            f"but your income only supports {_ngn(daily_income_budget)}/day "
            f"({_ngn(income)} ÷ {days_in_month} days). "
            f"You're drawing down your balance by ~{_ngn((daily_avg - daily_income_budget) * days_in_month)}/month at this rate.",
            priority=1,
        )]
    return []


def _debt_payoff_suggestions(data: dict) -> list[dict]:
    """
    For each active debt, suggest accelerated payoff and interest saved.
    """
    insights = []
    for d in data["debts"]:
        if d["type"] != "borrowed":
            continue
        balance  = int(d["balance_remaining"])
        rate     = float(d["interest_rate"] or 0)
        monthly  = int(d["monthly_payment"] or 0)
        if balance <= 0:
            continue

        if monthly > 0:
            months_standard = -(-balance // monthly)
        else:
            months_standard = None

        double_monthly = monthly * 2 if monthly else None
        months_double  = -(-balance // double_monthly) if double_monthly else None

        if rate > 0 and months_standard:
            # Rough interest cost
            monthly_rate = rate / 100 / 12
            interest_std = int(monthly * months_standard - balance)
            interest_dbl = int(double_monthly * months_double - balance) if double_monthly and months_double else 0
            interest_saved = max(interest_std - interest_dbl, 0)

            if interest_saved >= 5_000:
                insights.append(_insight(
                    "goal", "💳",
                    f"Pay Off '{d['name']}' Faster",
                    f"At {_ngn(monthly)}/month you'll pay off this debt in {months_standard} months "
                    f"and pay ~{_ngn(interest_std)} in interest. "
                    f"Doubling to {_ngn(double_monthly)}/month cuts it to {months_double} months "
                    f"and saves you ~{_ngn(interest_saved)} in interest.",
                    "Record a payment",
                    priority=2,
                ))
        elif months_standard and months_standard <= 6:
            insights.append(_insight(
                "goal", "🏁",
                f"Almost Debt-Free: {d['name']}",
                f"Only {_ngn(balance)} remaining on '{d['name']}'. "
                f"At {_ngn(monthly)}/month you'll clear it in {months_standard} months. "
                f"One extra payment now could cut that timeline significantly.",
                "Record a payment",
                priority=2,
            ))

    return insights[:3]


def _emergency_fund_insight(data: dict) -> list[dict]:
    ef = data["ef_plan"]
    if not ef:
        return [_insight(
            "warning", "🛡️",
            "No Emergency Fund Plan Set",
            "You haven't set up an emergency fund plan. "
            "A 3–6 month expense buffer is the single most important financial safety net. "
            "Set it up under Tracker → Emergency Fund.",
            "Set up emergency fund",
            priority=3,
        )]

    target_months = int(ef["target_months"])
    monthly_exp   = int(ef["monthly_expenses_estimate"] or 0)
    current_saved = int(ef["current_saved"] or 0)
    fund_target   = target_months * monthly_exp

    if fund_target == 0:
        return []

    pct = round(current_saved / fund_target * 100)
    shortfall = fund_target - current_saved

    if pct >= 100:
        return [_insight(
            "saving", "🛡️",
            "Emergency Fund: Fully Funded!",
            f"Your emergency fund is complete ({_ngn(current_saved)} saved, "
            f"{target_months} months of expenses covered). "
            f"Maintain it and consider investing anything above this threshold.",
            priority=5,
        )]
    elif pct < 50:
        monthly_to_fund_12 = -(-shortfall // 12)
        return [_insight(
            "warning", "🛡️",
            f"Emergency Fund at {pct}%",
            f"You've saved {_ngn(current_saved)} toward your {_ngn(fund_target)} emergency fund target. "
            f"You need {_ngn(shortfall)} more to reach {target_months} months of coverage. "
            f"Saving {_ngn(monthly_to_fund_12)}/month would get you there in 12 months.",
            "Update emergency fund",
            priority=2,
        )]
    return []
