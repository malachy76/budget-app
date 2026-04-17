# summaries.py — Weekly & Monthly Summaries page
import calendar
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db


def render_summaries(user_id):
    st.markdown("## Weekly & Monthly Summaries")

    today        = datetime.now().date()
    month_start  = today.replace(day=1)
    week_start   = today - timedelta(days=today.weekday())

    tab_week, tab_month = st.tabs(["📅 This Week", "📊 This Month"])

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1 — WEEKLY SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    with tab_week:
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end   = week_start - timedelta(days=1)

        # All weekly data in ONE connection
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT
                  COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
                  COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.created_at>=%s
            """, (user_id, week_start))
            w = cursor.fetchone()
            week_income = int(w["income"] or 0)
            week_spent  = int(w["spent"]  or 0)

            cursor.execute("""
                SELECT COALESCE(SUM(t.amount),0) AS spent
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.type='debit'
                  AND t.created_at>=%s AND t.created_at<=%s
            """, (user_id, prev_week_start, prev_week_end))
            prev_week_spent = int(cursor.fetchone()["spent"] or 0)

            cursor.execute("""
                SELECT COALESCE(e.category, e.name) AS cat, SUM(e.amount) AS total
                FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s AND e.created_at>=%s
                GROUP BY cat ORDER BY total DESC LIMIT 5
            """, (user_id, week_start))
            week_top_cats = cursor.fetchall()

            cursor.execute("""
                SELECT t.created_at AS day, SUM(t.amount) AS total
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.type='debit' AND t.created_at>=%s
                GROUP BY t.created_at ORDER BY t.created_at
            """, (user_id, week_start))
            daily_rows = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) AS n FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s AND e.created_at>=%s
            """, (user_id, week_start))
            week_tx_count = int(cursor.fetchone()["n"] or 0)

        week_net    = week_income - week_spent
        spend_diff  = week_spent - prev_week_spent
        spend_arrow = "⬆️" if spend_diff > 0 else ("⬇️" if spend_diff < 0 else "➡️")
        vs_label    = f"{spend_arrow} NGN {abs(spend_diff):,} {'more' if spend_diff > 0 else 'less' if spend_diff < 0 else 'same'}"

        # Hero summary card
        st.markdown(f"""
        <div class="week-card">
          <div class="week-title">📅 Week of {week_start.strftime('%d %b %Y')}</div>
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
              <div class="week-stat-value" style="color:{'#a8d8c8' if week_net >= 0 else '#f1948a'};">
                {"+" if week_net >= 0 else ""}NGN {week_net:,}
              </div>
            </div>
            <div class="week-stat">
              <div class="week-stat-label">Transactions</div>
              <div class="week-stat-value">{week_tx_count}</div>
            </div>
            <div class="week-stat">
              <div class="week-stat-label">vs Last Week</div>
              <div class="week-stat-value" style="font-size:0.82rem;">{vs_label}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Quick insight banner
        if prev_week_spent > 0 and spend_diff > 0:
            pct_more = round(spend_diff / prev_week_spent * 100)
            st.warning(f"You are spending **{pct_more}% more** than last week. Review your categories below.")
        elif prev_week_spent > 0 and spend_diff < 0:
            saved = abs(spend_diff)
            st.success(f"Great job — you spent **NGN {saved:,} less** than last week!")

        # Top categories
        if week_top_cats:
            st.subheader("Top categories this week")
            total_wk = sum(int(r["total"]) for r in week_top_cats) or 1
            for r in week_top_cats:
                pct = round(int(r["total"]) / total_wk * 100)
                bar_w = max(int(r["total"]) / total_wk * 100, 2)
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:8px 12px;background:#f0f7f4;border-radius:8px;margin-bottom:6px;">'
                    f'<div style="flex:1;">'
                    f'  <span style="font-weight:600;color:#1a3c5e;">{r["cat"] or "Uncategorised"}</span>'
                    f'  <div style="background:#d0e8df;border-radius:4px;height:4px;margin-top:4px;">'
                    f'    <div style="background:#0e7c5b;width:{bar_w:.0f}%;height:4px;border-radius:4px;"></div>'
                    f'  </div>'
                    f'</div>'
                    f'<div style="text-align:right;margin-left:12px;">'
                    f'  <span style="color:#c0392b;font-weight:700;">NGN {int(r["total"]):,}</span>'
                    f'  <span style="font-size:0.75rem;color:#95a5a6;margin-left:4px;">{pct}%</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.caption("No expenses this week yet.")

        # Daily spending chart
        if daily_rows:
            st.subheader("Daily spending")
            df_d = pd.DataFrame(
                [(str(r["day"]), int(r["total"])) for r in daily_rows],
                columns=["Day", "Spent (NGN)"]
            )
            df_d["Day"] = pd.to_datetime(df_d["Day"]).dt.strftime("%a %d %b")
            fig = px.bar(df_d, x="Day", y="Spent (NGN)",
                         color_discrete_sequence=["#0e7c5b"],
                         text_auto=True)
            fig.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=280)
            fig.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2 — MONTHLY SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    with tab_month:
        # Build last-12-months dropdown
        months_available = sorted(
            set(
                (today.replace(day=1) - timedelta(days=i * 28)).replace(day=1)
                for i in range(12)
            ),
            reverse=True
        )
        sel_month = st.selectbox(
            "Select month",
            months_available,
            format_func=lambda d: d.strftime("%B %Y"),
            key="summaries_month_select"
        )
        m_start = sel_month
        m_end   = sel_month.replace(
            day=calendar.monthrange(sel_month.year, sel_month.month)[1]
        )

        # All monthly data in ONE connection
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT
                  COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
                  COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
            """, (user_id, m_start, m_end))
            mn = cursor.fetchone()
            m_income = int(mn["income"] or 0)
            m_spent  = int(mn["spent"]  or 0)

            cursor.execute("""
                SELECT COALESCE(e.category, e.name) AS cat,
                       SUM(e.amount) AS total, COUNT(*) AS cnt
                FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
                GROUP BY cat ORDER BY total DESC
            """, (user_id, m_start, m_end))
            m_cats = cursor.fetchall()

            cursor.execute("""
                SELECT DATE_TRUNC('week', t.created_at) AS wk, SUM(t.amount) AS total
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.type='debit'
                  AND t.created_at>=%s AND t.created_at<=%s
                GROUP BY wk ORDER BY wk
            """, (user_id, m_start, m_end))
            m_weekly = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) AS n FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
            """, (user_id, m_start, m_end))
            m_tx_count = int(cursor.fetchone()["n"] or 0)

            cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
            m_limit = int(cursor.fetchone()["monthly_spending_limit"] or 0)

            # Previous month for comparison
            prev_m_end   = m_start - timedelta(days=1)
            prev_m_start = prev_m_end.replace(day=1)
            cursor.execute("""
                SELECT COALESCE(SUM(t.amount),0) AS spent
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%s AND t.type='debit'
                  AND t.created_at>=%s AND t.created_at<=%s
            """, (user_id, prev_m_start, prev_m_end))
            prev_m_spent = int(cursor.fetchone()["spent"] or 0)

        m_net        = m_income - m_spent
        savings_rate = round(m_net / m_income * 100, 1) if m_income > 0 else 0
        mom_diff     = m_spent - prev_m_spent
        mom_delta    = (f"+NGN {mom_diff:,} vs last month" if mom_diff > 0
                        else f"-NGN {abs(mom_diff):,} vs last month" if mom_diff < 0 else None)

        # Key metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Income",       f"NGN {m_income:,}")
        c2.metric("Expenses",     f"NGN {m_spent:,}", delta=mom_delta,
                  delta_color="inverse")
        c3.metric("Net Saved",    f"NGN {m_net:,}",
                  delta=f"{savings_rate:.1f}% savings rate")
        c4.metric("Transactions", str(m_tx_count))

        # Budget progress bar
        if m_limit > 0:
            pct = min(round(m_spent / m_limit * 100, 1), 100)
            bar_color = "normal" if pct < 80 else ("off" if pct < 100 else "inverse")
            st.progress(pct / 100,
                        text=f"Budget: {pct:.0f}% used — NGN {m_spent:,} of NGN {m_limit:,}")

        st.divider()

        # Category breakdown table with mini progress bars
        if m_cats:
            st.subheader("Spending by category")
            total_exp = sum(int(r["total"]) for r in m_cats) or 1
            for cr in m_cats:
                pct_cat = round(int(cr["total"]) / total_exp * 100, 1)
                bar_w   = max(pct_cat, 1)
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:8px 12px;background:#f0f7f4;border-radius:8px;margin-bottom:6px;">'
                    f'<div style="flex:1;">'
                    f'  <span style="font-weight:600;color:#1a3c5e;">{cr["cat"] or "Uncategorised"}</span>'
                    f'  <span style="font-size:0.75rem;color:#95a5a6;margin-left:8px;">{cr["cnt"]} transactions</span>'
                    f'  <div style="background:#d0e8df;border-radius:4px;height:4px;margin-top:4px;">'
                    f'    <div style="background:#0e7c5b;width:{bar_w:.0f}%;height:4px;border-radius:4px;"></div>'
                    f'  </div>'
                    f'</div>'
                    f'<div style="text-align:right;margin-left:12px;">'
                    f'  <span style="color:#c0392b;font-weight:700;">NGN {int(cr["total"]):,}</span>'
                    f'  <span style="font-size:0.75rem;color:#95a5a6;margin-left:4px;">{pct_cat:.0f}%</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No expenses recorded for this month.")

        # Weekly bar chart within the month
        if m_weekly:
            st.subheader("Weekly spending breakdown")
            df_wk = pd.DataFrame(
                [(str(r["wk"])[:10], int(r["total"])) for r in m_weekly],
                columns=["Week", "Spent (NGN)"]
            )
            fig = px.bar(df_wk, x="Week", y="Spent (NGN)",
                         color_discrete_sequence=["#1a3c5e"],
                         text_auto=True)
            fig.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=280)
            fig.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)

        # All-time expense pie chart
        if m_cats:
            st.subheader("Category breakdown")
            df_pie = pd.DataFrame(
                [(r["cat"] or "Uncategorised", int(r["total"])) for r in m_cats],
                columns=["Category", "Amount"]
            )
            threshold  = df_pie["Amount"].sum() * 0.02
            df_main    = df_pie[df_pie["Amount"] >= threshold]
            df_other   = df_pie[df_pie["Amount"] < threshold]
            if not df_other.empty:
                df_main = pd.concat([
                    df_main,
                    pd.DataFrame([{"Category": "Others", "Amount": int(df_other["Amount"].sum())}])
                ], ignore_index=True)
            fig2 = px.pie(df_main, names="Category", values="Amount",
                          color_discrete_sequence=px.colors.qualitative.Pastel,
                          hole=0.35)
            fig2.update_traces(textposition="inside", textinfo="percent+label",
                               hovertemplate="<b>%{label}</b><br>NGN %{value:,.0f}<br>%{percent}<extra></extra>")
            fig2.update_layout(margin=dict(t=20, b=10, l=10, r=10),
                               legend=dict(orientation="v", x=1.02, y=0.5))
            st.plotly_chart(fig2, use_container_width=True)
