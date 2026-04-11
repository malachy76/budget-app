# summaries.py — summaries page
import calendar
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db
from utils import save_expense, apply_income_filters, apply_expense_filters, \
    render_filter_bar_income, render_filter_bar_expenses, \
    get_category_budgets, compute_daily_safe_to_spend, BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password, get_onboarding_status, mark_onboarding_complete


def render_summaries(user_id):
    st.markdown("## Weekly & Monthly Summaries")

    _today      = datetime.now().date()
    _month_start = _today.replace(day=1)
    _week_start  = _today - timedelta(days=_today.weekday())

    tab_week, tab_month = st.tabs(["&#x1F4C5; This Week", "&#x1F4CA; This Month"])

    # ── WEEKLY SUMMARY TAB ────────────────────────────────────────────────────
    with tab_week:
        prev_week_start = _week_start - timedelta(days=7)
        prev_week_end   = _week_start - timedelta(days=1)

        with get_db() as (conn, cursor):
            # This week totals
            cursor.execute("""
                SELECT COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
                       COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.created_at>=%s
            """, (user_id, _week_start))
            w = cursor.fetchone()
            week_income = int(w["income"] or 0)
            week_spent  = int(w["spent"]  or 0)

            # Last week totals
            cursor.execute("""
                SELECT COALESCE(SUM(CASE WHEN t.type='debit' THEN t.amount ELSE 0 END),0) AS spent
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
            """, (user_id, prev_week_start, prev_week_end))
            prev_week_spent = int(cursor.fetchone()["spent"] or 0)

            # Top 5 categories this week
            cursor.execute("""
                SELECT COALESCE(e.category, e.name) AS cat, SUM(e.amount) AS total
                FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s AND e.created_at>=%s
                GROUP BY cat ORDER BY total DESC LIMIT 5
            """, (user_id, _week_start))
            week_top_cats = cursor.fetchall()

            # Daily spending this week (Mon–today)
            cursor.execute("""
                SELECT t.created_at AS day, SUM(t.amount) AS total
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.type='debit' AND t.created_at>=%s
                GROUP BY t.created_at ORDER BY t.created_at
            """, (user_id, _week_start))
            daily_rows = cursor.fetchall()

            # Transaction count
            cursor.execute("""
                SELECT COUNT(*) AS n FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s AND e.created_at>=%s
            """, (user_id, _week_start))
            week_tx_count = int(cursor.fetchone()["n"] or 0)

        week_net   = week_income - week_spent
        spend_diff = week_spent - prev_week_spent
        spend_arrow = "&#x1F53C;" if spend_diff > 0 else ("&#x1F53D;" if spend_diff < 0 else "&#x27A1;")

        # Summary card
        st.markdown(f"""
        <div class="week-card">
          <div class="week-title">&#x1F4C5; Week of {_week_start.strftime('%d %b %Y')}</div>
          <div class="week-grid">
            <div class="week-stat">
              <div class="week-stat-label">Income</div>
              <div class="week-stat-value">NGN {week_income:,}</div>
            </div>
            <div class="week-stat">
              <div class="week-stat-label">Spent</div>
              <div class="week-stat-value">NGN {week_spent:,}</div>
            </div>
            <div class="week-stat">
              <div class="week-stat-label">Net</div>
              <div class="week-stat-value" style="color:{'#a8d8c8' if week_net>=0 else '#f1948a'};">
                {"+" if week_net>=0 else ""}NGN {week_net:,}
              </div>
            </div>
            <div class="week-stat">
              <div class="week-stat-label">Transactions</div>
              <div class="week-stat-value">{week_tx_count}</div>
            </div>
            <div class="week-stat">
              <div class="week-stat-label">vs Last Week</div>
              <div class="week-stat-value" style="font-size:0.85rem;">
                {spend_arrow} NGN {abs(spend_diff):,}
                {"more" if spend_diff > 0 else "less" if spend_diff < 0 else "same"}
              </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Top categories
        if week_top_cats:
            st.subheader("Top categories this week")
            for cat_row in week_top_cats:
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:8px 12px;'
                    f'background:#f0f7f4;border-radius:8px;margin-bottom:6px;">'
                    f'<span style="font-weight:600;color:#1a3c5e;">{cat_row["cat"] or "Uncategorised"}</span>'
                    f'<span style="color:#c0392b;font-weight:700;">NGN {int(cat_row["total"]):,}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # Daily breakdown bar chart
        if daily_rows:
            st.subheader("Daily spending this week")
            df_daily = pd.DataFrame(
                [(str(r["day"]), int(r["total"])) for r in daily_rows],
                columns=["Day", "Spent (NGN)"]
            )
            df_daily["Day"] = pd.to_datetime(df_daily["Day"]).dt.strftime("%a %d")
            st.bar_chart(df_daily.set_index("Day")["Spent (NGN)"])

    # ── MONTHLY SUMMARY TAB ───────────────────────────────────────────────────
    with tab_month:
        # Month selector
        months_available = []
        for i in range(12):
            d = (_today.replace(day=1) - timedelta(days=i * 28)).replace(day=1)
            months_available.append(d)
        months_available = sorted(set(months_available), reverse=True)

        sel_month_dt = st.selectbox(
            "Select month",
            months_available,
            format_func=lambda d: d.strftime("%B %Y"),
            key="summaries_month_select"
        )
        m_start = sel_month_dt
        import calendar as _cal
        m_end   = sel_month_dt.replace(
            day=_cal.monthrange(sel_month_dt.year, sel_month_dt.month)[1]
        )

        with get_db() as (conn, cursor):
            # Income and expenses
            cursor.execute("""
                SELECT COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
                       COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
            """, (user_id, m_start, m_end))
            mn = cursor.fetchone()
            m_income = int(mn["income"] or 0)
            m_spent  = int(mn["spent"]  or 0)

            # Category breakdown
            cursor.execute("""
                SELECT COALESCE(e.category, e.name) AS cat, SUM(e.amount) AS total, COUNT(*) AS cnt
                FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
                GROUP BY cat ORDER BY total DESC
            """, (user_id, m_start, m_end))
            m_cats = cursor.fetchall()

            # Weekly breakdown within month
            cursor.execute("""
                SELECT DATE_TRUNC('week', t.created_at) AS wk, SUM(t.amount) AS total
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.type='debit'
                  AND t.created_at>=%s AND t.created_at<=%s
                GROUP BY wk ORDER BY wk
            """, (user_id, m_start, m_end))
            m_weekly = cursor.fetchall()

            # Transaction count
            cursor.execute("""
                SELECT COUNT(*) AS n FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
            """, (user_id, m_start, m_end))
            m_tx_count = int(cursor.fetchone()["n"] or 0)

            # Savings rate
            cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
            m_limit = cursor.fetchone()["monthly_spending_limit"] or 0

        m_net         = m_income - m_spent
        savings_rate  = round(m_net / m_income * 100, 1) if m_income > 0 else 0

        # Key metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Income", f"NGN {m_income:,}")
        c2.metric("Expenses", f"NGN {m_spent:,}")
        c3.metric("Net saved", f"NGN {m_net:,}",
                  delta=f"{savings_rate:.1f}% savings rate")
        c4.metric("Transactions", str(m_tx_count))

        if m_limit > 0:
            pct = min(round(m_spent / m_limit * 100, 1), 100)
            st.progress(pct / 100,
                        text=f"Budget: {pct:.0f}% used — NGN {m_spent:,} of NGN {m_limit:,}")

        # Category table
        if m_cats:
            st.subheader("Spending by category")
            total_exp = sum(int(r["total"]) for r in m_cats) or 1
            for cr in m_cats:
                pct_cat = round(int(cr["total"]) / total_exp * 100, 1)
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:8px 12px;background:#f0f7f4;border-radius:8px;margin-bottom:6px;">'
                    f'<div style="flex:1;">'
                    f'  <span style="font-weight:600;color:#1a3c5e;">{cr["cat"] or "Uncategorised"}</span>'
                    f'  <span style="font-size:0.78rem;color:#95a5a6;margin-left:8px;">{cr["cnt"]} transactions</span>'
                    f'</div>'
                    f'<div style="text-align:right;">'
                    f'  <span style="color:#c0392b;font-weight:700;">NGN {int(cr["total"]):,}</span>'
                    f'  <span style="font-size:0.78rem;color:#95a5a6;margin-left:8px;">{pct_cat:.0f}%</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # Weekly bar chart within month
        if m_weekly:
            st.subheader("Weekly spending breakdown")
            df_wk = pd.DataFrame(
                [(str(r["wk"])[:10], int(r["total"])) for r in m_weekly],
                columns=["Week starting", "Spent (NGN)"]
            )
            st.bar_chart(df_wk.set_index("Week starting")["Spent (NGN)"])

# ================= PAGE: IMPORT CSV =================
