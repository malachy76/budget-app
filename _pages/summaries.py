# _pages/summaries.py
# Weekly and Monthly financial summaries with charts and AI-style insights
import streamlit as st
import calendar
from datetime import datetime, date, timedelta
from db import get_db

try:
    import plotly.graph_objects as go
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False


# ── helpers ───────────────────────────────────────────────────────────────────

def _ngn(n: int) -> str:
    return f"NGN {n:,}"

def _pct_change(new, old):
    if not old:
        return None
    return round((new - old) / old * 100, 1)

def _delta_str(new, old):
    if old is None or old == 0:
        return None
    diff = new - old
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:,} vs prev period"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def render_summaries(user_id: int):
    st.title("📊 Summaries")

    tab_weekly, tab_monthly = st.tabs(["📅 Weekly Summary", "🗓️ Monthly Summary"])

    with tab_weekly:
        _render_weekly(user_id)
    with tab_monthly:
        _render_monthly(user_id)


# ─────────────────────────────────────────────────────────────────────────────
# WEEKLY SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def _render_weekly(user_id: int):
    today       = date.today()
    # Default: current week Mon–Sun
    week_start_default = today - timedelta(days=today.weekday())
    week_end_default   = week_start_default + timedelta(days=6)

    # Week selector
    col_ws, col_we = st.columns(2)
    with col_ws:
        week_start = st.date_input("Week start", value=week_start_default, key="wsum_start")
    with col_we:
        week_end   = st.date_input("Week end",   value=week_end_default,   key="wsum_end")

    if week_start > week_end:
        st.warning("Start date must be before end date.")
        return

    # Previous week for comparison
    days_span  = (week_end - week_start).days + 1
    prev_start = week_start - timedelta(days=days_span)
    prev_end   = week_start - timedelta(days=1)

    with get_db() as (conn, cursor):
        # Current period
        cursor.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
              COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at BETWEEN %s AND %s
        """, (user_id, week_start, week_end))
        cur = cursor.fetchone()
        income  = int(cur["income"] or 0)
        spent   = int(cur["spent"]  or 0)
        net     = income - spent

        # Previous period
        cursor.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
              COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at BETWEEN %s AND %s
        """, (user_id, prev_start, prev_end))
        prev = cursor.fetchone()
        prev_income = int(prev["income"] or 0)
        prev_spent  = int(prev["spent"]  or 0)

        # Transactions per day
        cursor.execute("""
            SELECT t.created_at AS day,
              COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent,
              COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at BETWEEN %s AND %s
            GROUP BY t.created_at ORDER BY t.created_at
        """, (user_id, week_start, week_end))
        daily_rows = cursor.fetchall()

        # Top categories
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat, SUM(e.amount) AS total, COUNT(*) AS cnt
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at BETWEEN %s AND %s
            GROUP BY cat ORDER BY total DESC LIMIT 5
        """, (user_id, week_start, week_end))
        top_cats = cursor.fetchall()

        # Expense list
        cursor.execute("""
            SELECT e.created_at, e.name, COALESCE(e.category,e.name) AS cat, e.amount, b.bank_name
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at BETWEEN %s AND %s
            ORDER BY e.created_at DESC LIMIT 50
        """, (user_id, week_start, week_end))
        expenses = cursor.fetchall()

        # No-spend days
        days_with_spend = set()
        for r in daily_rows:
            if int(r["spent"]) > 0:
                days_with_spend.add(r["day"])
        no_spend_days = days_span - len(days_with_spend)

    # ── Metric cards ──────────────────────────────────────────────────────────
    label = f"{week_start} → {week_end}"
    st.markdown(f"**{label}**")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Income",       _ngn(income),      _delta_str(income, prev_income))
    m2.metric("Spent",        _ngn(spent),       _delta_str(spent, prev_spent))
    m3.metric("Net Saved",    _ngn(net))
    m4.metric("No-Spend Days", str(no_spend_days), f"out of {days_span} days")

    # ── Daily chart ───────────────────────────────────────────────────────────
    if HAS_PLOTLY and daily_rows:
        # Build a full day-by-day series (including zero days)
        all_days = []
        d = week_start
        while d <= week_end:
            all_days.append(d)
            d += timedelta(days=1)
        day_map_spent  = {r["day"]: int(r["spent"])  for r in daily_rows}
        day_map_income = {r["day"]: int(r["income"]) for r in daily_rows}
        spent_series   = [day_map_spent.get(d, 0)  for d in all_days]
        income_series  = [day_map_income.get(d, 0) for d in all_days]
        day_labels     = [d.strftime("%a %d") for d in all_days]

        fig = go.Figure()
        fig.add_trace(go.Bar(name="Spent",  x=day_labels, y=spent_series,  marker_color="#c0392b"))
        fig.add_trace(go.Bar(name="Income", x=day_labels, y=income_series, marker_color="#0e7c5b"))
        fig.update_layout(
            barmode="group", height=280, margin=dict(l=0,r=0,t=24,b=0),
            title="Daily Income vs Spending",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis_title="NGN",
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Category breakdown ────────────────────────────────────────────────────
    if top_cats:
        st.markdown("**Top Spending Categories**")
        if HAS_PLOTLY:
            cats_  = [r["cat"] for r in top_cats]
            amts_  = [int(r["total"]) for r in top_cats]
            fig2 = px.bar(x=amts_, y=cats_, orientation="h",
                          color=amts_, color_continuous_scale="Reds",
                          labels={"x": "NGN", "y": ""})
            fig2.update_layout(height=200, margin=dict(l=0,r=0,t=4,b=0), coloraxis_showscale=False)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            for r in top_cats:
                pct = round(int(r["total"]) / max(spent, 1) * 100)
                st.markdown(f"- **{r['cat']}**: {_ngn(int(r['total']))} ({pct}%)")

    # ── Insights ─────────────────────────────────────────────────────────────
    _weekly_insights(income, spent, net, prev_income, prev_spent, no_spend_days, days_span, top_cats)

    # ── Expense list ──────────────────────────────────────────────────────────
    if expenses:
        with st.expander(f"📋 All {len(expenses)} Expenses This Period", expanded=False):
            for e in expenses:
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #eee'>"
                    f"<span><b>{e['name']}</b> <span style='color:#888;font-size:0.8rem'>· {e['cat']} · {e['bank_name']}</span></span>"
                    f"<span style='color:#c0392b;font-weight:700'>{_ngn(int(e['amount']))}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )


def _weekly_insights(income, spent, net, prev_income, prev_spent, no_spend_days, days_span, top_cats):
    insights = []

    if spent > prev_spent and prev_spent > 0:
        extra = spent - prev_spent
        pct   = round(extra / prev_spent * 100)
        insights.append(("🔴", "Spending Up", f"You spent NGN {extra:,} more ({pct}%) than the previous period. Review your top categories."))
    elif prev_spent > 0 and spent < prev_spent:
        saved = prev_spent - spent
        pct   = round(saved / prev_spent * 100)
        insights.append(("🟢", "Spending Down", f"Great job — you spent NGN {saved:,} less ({pct}%) than the previous period."))

    if income > 0:
        sr = round((income - spent) / income * 100, 1)
        if sr >= 20:
            insights.append(("🌟", "Strong Savings Rate", f"You saved {sr}% of your income this period. Excellent financial discipline!"))
        elif sr < 0:
            insights.append(("⚠️", "Overspent Income", f"You spent more than you earned. Reduce non-essential spending."))

    if no_spend_days >= days_span // 2:
        insights.append(("🏅", "No-Spend Champion", f"{no_spend_days} of {days_span} days had zero spending. Keep building that habit."))

    if top_cats:
        biggest = top_cats[0]
        pct_of_spend = round(int(biggest["total"]) / max(spent, 1) * 100)
        if pct_of_spend >= 40:
            insights.append(("📌", "One Category Dominates", f"'{biggest['cat']}' took {pct_of_spend}% of your spending. Is that expected?"))

    if not insights:
        return

    st.markdown("**💡 Weekly Insights**")
    for icon, title, body in insights:
        st.markdown(
            f"<div style='background:#f0f7f4;border-left:4px solid #0e7c5b;border-radius:8px;"
            f"padding:10px 14px;margin-bottom:8px'>"
            f"<b>{icon} {title}</b><br><span style='font-size:0.92rem'>{body}</span></div>",
            unsafe_allow_html=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def _render_monthly(user_id: int):
    today = date.today()

    # Month / year selector
    col_m, col_y = st.columns(2)
    with col_m:
        month = st.selectbox("Month", list(range(1, 13)),
                             index=today.month - 1,
                             format_func=lambda m: calendar.month_name[m],
                             key="msum_month")
    with col_y:
        year  = st.selectbox("Year", list(range(today.year - 3, today.year + 1)),
                             index=3, key="msum_year")

    m_start = date(year, month, 1)
    m_end   = date(year, month, calendar.monthrange(year, month)[1])

    # Previous month
    prev_m_end   = m_start - timedelta(days=1)
    prev_m_start = prev_m_end.replace(day=1)

    with get_db() as (conn, cursor):
        def _fetch_totals(start, end):
            cursor.execute("""
                SELECT
                  COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
                  COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.created_at BETWEEN %s AND %s
            """, (user_id, start, end))
            r = cursor.fetchone()
            return int(r["income"] or 0), int(r["spent"] or 0)

        income, spent   = _fetch_totals(m_start, m_end)
        p_income, p_spent = _fetch_totals(prev_m_start, prev_m_end)
        net = income - spent

        # Category breakdown
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat,
                   SUM(e.amount) AS total, COUNT(*) AS cnt
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at BETWEEN %s AND %s
            GROUP BY cat ORDER BY total DESC
        """, (user_id, m_start, m_end))
        categories = cursor.fetchall()

        # Daily spending trend
        cursor.execute("""
            SELECT t.created_at AS day,
              COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent,
              COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at BETWEEN %s AND %s
            GROUP BY t.created_at ORDER BY t.created_at
        """, (user_id, m_start, m_end))
        daily_rows = cursor.fetchall()

        # No-spend days
        days_in_month = calendar.monthrange(year, month)[1]
        days_with_spend = sum(1 for r in daily_rows if int(r["spent"]) > 0)
        no_spend_days   = days_in_month - days_with_spend

        # Budget
        cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
        budget_row = cursor.fetchone()
        budget = int(budget_row["monthly_spending_limit"] or 0) if budget_row else 0

        # Category budgets
        cursor.execute("""
            SELECT cb.category, cb.monthly_limit,
                   COALESCE(SUM(e.amount),0) AS spent
            FROM category_budgets cb
            LEFT JOIN expenses e
                ON COALESCE(e.category, e.name) = cb.category
               AND e.user_id = cb.user_id
               AND e.created_at BETWEEN %s AND %s
            WHERE cb.user_id=%s AND cb.monthly_limit > 0
            GROUP BY cb.category, cb.monthly_limit
            ORDER BY spent DESC
        """, (m_start, m_end, user_id))
        cat_budgets = cursor.fetchall()

        # Recurring items — expected vs actual
        cursor.execute("""
            SELECT name, type, amount, frequency
            FROM recurring_items
            WHERE user_id=%s AND active=1
        """, (user_id,))
        recurring = cursor.fetchall()

        # Bank balances snapshot
        cursor.execute("SELECT bank_name, balance FROM banks WHERE user_id=%s ORDER BY balance DESC", (user_id,))
        banks = cursor.fetchall()

    month_label = f"{calendar.month_name[month]} {year}"
    st.markdown(f"**{month_label}**")

    # ── Key metrics ───────────────────────────────────────────────────────────
    sr = round((income - spent) / income * 100, 1) if income else None
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Income",        _ngn(income),   _delta_str(income, p_income))
    m2.metric("Spent",         _ngn(spent),    _delta_str(spent, p_spent))
    m3.metric("Net Saved",     _ngn(net))
    m4.metric("Savings Rate",  f"{sr}%" if sr is not None else "—")
    m5.metric("No-Spend Days", str(no_spend_days), f"of {days_in_month}")

    # Monthly budget bar
    if budget > 0 and spent > 0:
        pct_used  = min(spent / budget * 100, 100)
        bar_color = "#c0392b" if pct_used >= 100 else ("#f39c12" if pct_used >= 80 else "#0e7c5b")
        filled    = int(pct_used / 5)
        st.markdown(
            f"<div style='margin:8px 0 4px'><span style='font-size:0.85rem;font-weight:600'>Monthly Budget Usage: {pct_used:.0f}%</span><br>"
            f"<span style='color:{bar_color};font-size:1.15rem'>{'█'*filled}<span style='color:#ddd'>{'░'*(20-filled)}</span></span> "
            f"<span style='font-size:0.82rem;color:#666'>{_ngn(spent)} of {_ngn(budget)}</span></div>",
            unsafe_allow_html=True
        )

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    if HAS_PLOTLY:
        chart1, chart2 = st.columns(2)

        with chart1:
            if daily_rows:
                all_days = []
                d = m_start
                while d <= m_end:
                    all_days.append(d)
                    d += timedelta(days=1)
                day_map = {r["day"]: int(r["spent"]) for r in daily_rows}
                # Cumulative spend
                cumulative = []
                running = 0
                for d in all_days:
                    running += day_map.get(d, 0)
                    cumulative.append(running)
                day_labels = [d.strftime("%d") for d in all_days]
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=day_labels, y=cumulative, mode="lines+markers",
                    line=dict(color="#c0392b", width=2),
                    name="Cumulative Spend"
                ))
                if budget > 0:
                    fig.add_hline(y=budget, line_dash="dash", line_color="#f39c12",
                                  annotation_text=f"Budget: {_ngn(budget)}")
                fig.update_layout(
                    title="Cumulative Spending", height=260,
                    margin=dict(l=0,r=0,t=28,b=0), yaxis_title="NGN"
                )
                st.plotly_chart(fig, use_container_width=True)

        with chart2:
            if categories:
                cat_names = [r["cat"] for r in categories[:8]]
                cat_amts  = [int(r["total"]) for r in categories[:8]]
                fig2 = go.Figure(go.Pie(
                    labels=cat_names, values=cat_amts,
                    hole=0.4,
                    marker_colors=px.colors.qualitative.Set2[:len(cat_names)],
                ))
                fig2.update_layout(
                    title="Spending by Category", height=260,
                    margin=dict(l=0,r=0,t=28,b=0),
                    showlegend=True,
                    legend=dict(font=dict(size=10))
                )
                st.plotly_chart(fig2, use_container_width=True)

    # ── Category budget performance ───────────────────────────────────────────
    if cat_budgets:
        st.markdown("**📊 Category Budget Performance**")
        for cb in cat_budgets:
            limit = int(cb["monthly_limit"])
            s     = int(cb["spent"])
            pct   = min(s / limit * 100, 100) if limit else 0
            over  = s > limit
            bar_c = "#c0392b" if over else ("#f39c12" if pct >= 80 else "#0e7c5b")
            filled = int(pct / 5)
            status = f"⚠️ Over by {_ngn(s - limit)}" if over else f"{_ngn(max(limit - s, 0))} left"
            st.markdown(
                f"<div style='margin-bottom:6px'>"
                f"<span style='font-weight:600'>{cb['category']}</span> "
                f"<span style='float:right;font-size:0.85rem'>{_ngn(s)} / {_ngn(limit)} — {status}</span><br>"
                f"<span style='color:{bar_c};font-size:1rem'>{'█'*filled}<span style='color:#ddd'>{'░'*(20-filled)}</span></span>"
                f"</div>",
                unsafe_allow_html=True
            )
        st.divider()

    # ── Recurring items summary ───────────────────────────────────────────────
    if recurring:
        r_expenses = [r for r in recurring if r["type"] == "expense"]
        r_income   = [r for r in recurring if r["type"] == "income"]
        expected_exp = sum(int(r["amount"]) for r in r_expenses if r["frequency"] == "monthly")
        expected_inc = sum(int(r["amount"]) for r in r_income  if r["frequency"] == "monthly")
        if expected_exp > 0 or expected_inc > 0:
            st.markdown("**🔁 Recurring Items (Monthly)**")
            rec1, rec2 = st.columns(2)
            rec1.metric("Expected Recurring Expenses", _ngn(expected_exp))
            rec2.metric("Expected Recurring Income",   _ngn(expected_inc))

    # ── Bank balances ─────────────────────────────────────────────────────────
    if banks:
        st.markdown("**🏦 Current Bank Balances**")
        total_balance = sum(int(b["balance"]) for b in banks)
        for b in banks:
            pct = int(b["balance"]) / total_balance * 100 if total_balance else 0
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #eee'>"
                f"<span style='font-weight:600'>{b['bank_name']}</span>"
                f"<span style='color:#1a3c5e;font-weight:700'>{_ngn(int(b['balance']))} "
                f"<span style='color:#888;font-size:0.8rem'>({pct:.0f}%)</span></span>"
                f"</div>",
                unsafe_allow_html=True
            )
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;padding:8px 0;font-weight:800'>"
            f"<span>Total Balance</span><span style='color:#0e7c5b'>{_ngn(total_balance)}</span></div>",
            unsafe_allow_html=True
        )

    st.divider()

    # ── Insights ─────────────────────────────────────────────────────────────
    _monthly_insights(user_id, income, spent, net, p_income, p_spent,
                      no_spend_days, days_in_month, categories, budget, sr)


def _monthly_insights(user_id, income, spent, net, p_income, p_spent,
                      no_spend_days, days_in_month, categories, budget, sr):
    insights = []

    # Savings rate
    if sr is not None:
        if sr >= 30:
            insights.append(("🏆", "Excellent Savings Rate", f"You saved {sr}% of your income. Consistently saving above 20% builds real wealth."))
        elif sr >= 10:
            insights.append(("✅", "Healthy Savings Rate", f"A {sr}% savings rate is solid. Aim for 20%+ for faster goal achievement."))
        elif sr >= 0:
            insights.append(("⚠️", "Low Savings Rate", f"You saved only {sr}% this month. Try cutting your top spending category first."))
        else:
            insights.append(("🔴", "Spending Exceeded Income", f"You overspent by {_ngn(abs(net))}. This month was deficit. Review immediately."))

    # Month-over-month
    if p_spent > 0:
        diff = spent - p_spent
        if diff > 0:
            pct = round(diff / p_spent * 100)
            insights.append(("📈", "Spending Increased", f"You spent {_ngn(diff)} more ({pct}%) than last month. Is this a one-time event or a trend?"))
        elif diff < 0:
            saved_extra = abs(diff)
            insights.append(("📉", "Spending Reduced", f"You spent {_ngn(saved_extra)} less than last month. Keep the momentum going."))

    # Budget
    if budget > 0 and spent > budget:
        over = spent - budget
        insights.append(("🚨", "Budget Exceeded", f"You exceeded your NGN {budget:,} monthly budget by {_ngn(over)}. Identify which category drove this."))
    elif budget > 0 and spent <= budget * 0.7:
        insights.append(("💪", "Well Under Budget", f"You used only {round(spent/budget*100)}% of your budget. Consider moving the surplus to savings."))

    # No-spend days
    if no_spend_days >= 10:
        insights.append(("🏅", "Great No-Spend Habit", f"{no_spend_days} of {days_in_month} days had no spending. That discipline adds up significantly."))

    # Top category
    if categories:
        top = categories[0]
        pct_of_spend = round(int(top["total"]) / max(spent, 1) * 100)
        if pct_of_spend >= 50:
            insights.append(("🔍", "Review Your Top Category", f"'{top['cat']}' made up {pct_of_spend}% of all spending ({_ngn(int(top['total']))}). Is this aligned with your priorities?"))

    if not insights:
        if not income and not spent:
            insights.append(("📭", "No Data Yet", "No transactions recorded for this period. Start logging income and expenses to see your summary."))

    st.markdown("**💡 Monthly Insights**")
    for icon, title, body in insights:
        bg = "#fff0f0" if icon in ("🔴", "🚨") else "#f0f7f4"
        border = "#c0392b" if icon in ("🔴", "🚨") else "#0e7c5b"
        st.markdown(
            f"<div style='background:{bg};border-left:4px solid {border};border-radius:8px;"
            f"padding:10px 14px;margin-bottom:8px'>"
            f"<b>{icon} {title}</b><br><span style='font-size:0.92rem'>{body}</span></div>",
            unsafe_allow_html=True
        )
