# _pages/demo_dashboard.py — Demo Mode dashboard
# Renders the same layout as the real dashboard using static demo_data.
# Zero DB queries. Zero real-user interaction. Pure rendering.
import streamlit as st
from datetime import datetime, timedelta


def render_demo_dashboard(demo: dict, pages: list) -> None:
    st.markdown("## My Dashboard")

    d   = demo
    today = datetime.now().date()
    bal   = d["total_balance"]
    spent = d["expenses_this_month"]
    net   = d["net_savings"]
    limit = d["user"]["monthly_spending_limit"]

    # ── Top 4 metrics ────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Balance (NGN)",       f"{bal:,.0f}")
    c2.metric("Expenses This Month (NGN)", f"{spent:,.0f}")
    c3.metric("Bank Accounts",             len(d["banks"]))
    c4.metric("Net Savings (NGN)",         f"{net:,.0f}")

    # ── Daily Money Summary (lightweight — no DB) ─────────────────────────────
    txns_today = [t for t in d["transactions"] if t["created_at"] == today.isoformat()]
    inc_today   = sum(t["amount"] for t in txns_today if t["type"] == "credit")
    spent_today = sum(t["amount"] for t in txns_today if t["type"] == "debit")
    net_today   = inc_today - spent_today
    net_color   = "#0e7c5b" if net_today >= 0 else "#c0392b"
    net_sign    = "+" if net_today >= 0 else ""

    st.divider()
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'flex-wrap:wrap;gap:6px;margin-bottom:10px;">'
        f'<div style="font-size:1.05rem;font-weight:800;color:#1a3c5e;">📅 Today</div>'
        f'<div style="font-size:0.78rem;color:#7a9aaa;">{today.strftime("%A, %d %b %Y")}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    smart = ("No transactions recorded yet today." if not txns_today
             else "Your spending was low today. 💚" if spent_today < 5_000
             else f"Net positive day — NGN {net_today:,} more in than out." if net_today > 0
             else f"You spent more than you received today by NGN {abs(net_today):,}.")
    smart_bg     = "#e8f5f0" if net_today >= 0 else "#fdf2f2"
    smart_border = "#0e7c5b" if net_today >= 0 else "#e74c3c"
    st.markdown(
        f'<div style="background:{smart_bg};border-left:3px solid {smart_border};'
        f'border-radius:8px;padding:10px 14px;margin-bottom:12px;'
        f'font-size:0.9rem;color:#1a3c5e;font-weight:500;">{smart}</div>',
        unsafe_allow_html=True
    )

    st.markdown(f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px;">
      <div style="background:#fff;border:1px solid #e2ede9;border-radius:12px;padding:13px 14px;">
        <div style="font-size:0.7rem;font-weight:700;color:#7a9aaa;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Money In</div>
        <div style="font-size:1.2rem;font-weight:800;color:#0e7c5b;">NGN {inc_today:,}</div>
      </div>
      <div style="background:#fff;border:1px solid #e2ede9;border-radius:12px;padding:13px 14px;">
        <div style="font-size:0.7rem;font-weight:700;color:#7a9aaa;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Money Out</div>
        <div style="font-size:1.2rem;font-weight:800;color:#c0392b;">NGN {spent_today:,}</div>
      </div>
      <div style="background:#fff;border:1px solid #e2ede9;border-radius:12px;padding:13px 14px;">
        <div style="font-size:0.7rem;font-weight:700;color:#7a9aaa;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Net Today</div>
        <div style="font-size:1.2rem;font-weight:800;color:{net_color};">{net_sign}NGN {abs(net_today):,}</div>
      </div>
      <div style="background:#fff;border:1px solid #e2ede9;border-radius:12px;padding:13px 14px;">
        <div style="font-size:0.7rem;font-weight:700;color:#7a9aaa;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Total Balance</div>
        <div style="font-size:1.2rem;font-weight:800;color:#1a3c5e;">NGN {bal:,}</div>
        <div style="font-size:0.72rem;color:#95a5a6;margin-top:3px;">across all banks</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── At a Glance stat cards ────────────────────────────────────────────────
    st.divider()
    st.subheader("At a Glance")

    # Compute lightweight stats from demo data
    expenses = d["expenses"]
    week_start = today - timedelta(days=today.weekday())
    week_exps  = [e for e in expenses if e["created_at"] >= week_start.isoformat()]
    biggest_week = max(week_exps, key=lambda e: e["amount"]) if week_exps else None

    from collections import Counter
    cat_totals = {}
    for e in expenses:
        cat_totals[e["category"]] = cat_totals.get(e["category"], 0) + e["amount"]
    top_cat = max(cat_totals, key=cat_totals.get) if cat_totals else None

    month_start = today.replace(day=1)
    mo_inc  = sum(t["amount"] for t in d["transactions"]
                  if t["type"] == "credit" and t["created_at"] >= month_start.isoformat())
    mo_exp  = sum(t["amount"] for t in d["transactions"]
                  if t["type"] == "debit"  and t["created_at"] >= month_start.isoformat())
    sav_rate = round((mo_inc - mo_exp) / mo_inc * 100, 1) if mo_inc > 0 else None

    bank_usage = Counter(t["bank_id"] for t in d["transactions"])
    most_used_bank_id = bank_usage.most_common(1)[0][0] if bank_usage else None
    most_used_bank = next((b["bank_name"] for b in d["banks"] if b["id"] == most_used_bank_id), "—")

    # Render as a grid
    cards_html = '<div class="sc-grid">'
    if biggest_week:
        cards_html += (
            f'<div class="sc-card"><div class="sc-label">🔥 Biggest Expense This Week</div>'
            f'<div class="sc-value sc-accent-red">NGN {biggest_week["amount"]:,}</div>'
            f'<div class="sc-sub">{biggest_week["name"]}</div></div>'
        )
    if top_cat:
        cards_html += (
            f'<div class="sc-card"><div class="sc-label">🏷️ Top Category This Month</div>'
            f'<div class="sc-value">{top_cat}</div>'
            f'<div class="sc-sub">NGN {cat_totals[top_cat]:,} spent</div></div>'
        )
    if sav_rate is not None:
        rate_cls = "sc-accent-green" if sav_rate >= 20 else ("sc-accent-amber" if sav_rate >= 0 else "sc-accent-red")
        cards_html += (
            f'<div class="sc-card"><div class="sc-label">📊 Savings Rate</div>'
            f'<div class="sc-value {rate_cls}">{sav_rate:.1f}%</div>'
            f'<div class="sc-sub">of this month\'s income</div></div>'
        )
    if limit > 0:
        days_left = (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1) - today).days + 1
        remaining = max(limit - spent, 0)
        daily_rem = int(remaining / days_left) if days_left > 0 else 0
        cards_html += (
            f'<div class="sc-card"><div class="sc-label">💰 Daily Budget Left</div>'
            f'<div class="sc-value sc-accent-green">NGN {daily_rem:,}</div>'
            f'<div class="sc-sub">{days_left} days left in month</div></div>'
        )
    cards_html += (
        f'<div class="sc-card"><div class="sc-label">🏦 Most Used Bank</div>'
        f'<div class="sc-value">{most_used_bank}</div>'
        f'<div class="sc-sub">by transaction count</div></div>'
    )
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)

    # ── Budget alert ─────────────────────────────────────────────────────────
    if limit > 0:
        pct = (spent / limit) * 100
        if pct >= 80:
            st.warning(f"Spending alert: {pct:.0f}% of your NGN {limit:,} monthly budget used.")
        elif pct >= 50:
            st.info(f"Halfway through your monthly budget — {pct:.0f}% used.")

    # ── Weekly summary card ───────────────────────────────────────────────────
    st.divider()
    st.subheader("This Week at a Glance")
    wi = sum(t["amount"] for t in d["transactions"]
             if t["type"] == "credit" and t["created_at"] >= week_start.isoformat())
    ws = sum(t["amount"] for t in d["transactions"]
             if t["type"] == "debit"  and t["created_at"] >= week_start.isoformat())
    wn = wi - ws
    wn_color = "#2ecc71" if wn >= 0 else "#e74c3c"
    wn_label = f"+NGN {wn:,}" if wn >= 0 else f"-NGN {abs(wn):,}"
    wcount   = len([t for t in d["transactions"] if t["created_at"] >= week_start.isoformat()])
    st.markdown(f"""
    <div class="week-card">
      <div class="week-title">📅 {week_start.strftime("%d %b")} → Today</div>
      <div class="week-grid">
        <div class="week-stat"><div class="week-stat-label">Income</div>
          <div class="week-stat-value">NGN {wi:,}</div></div>
        <div class="week-stat"><div class="week-stat-label">Spent</div>
          <div class="week-stat-value">NGN {ws:,}</div></div>
        <div class="week-stat"><div class="week-stat-label">Net</div>
          <div class="week-stat-value" style="color:{wn_color};">{wn_label}</div></div>
        <div class="week-stat"><div class="week-stat-label">Transactions</div>
          <div class="week-stat-value">{wcount}</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Recent transactions ───────────────────────────────────────────────────
    st.divider()
    st.subheader("Recent Transactions")
    bank_map = {b["id"]: b["bank_name"] for b in d["banks"]}
    recent = sorted(d["transactions"], key=lambda t: t["created_at"], reverse=True)[:8]
    for t in recent:
        is_credit = t["type"] == "credit"
        color = "#0e7c5b" if is_credit else "#c0392b"
        sign  = "+" if is_credit else "−"
        desc  = t["description"].replace("Income: ", "").replace("Expense: ", "")
        bname = bank_map.get(t["bank_id"], "")
        st.markdown(f"""
        <div class="exp-card" style="border-left-color:{color};">
          <div class="exp-card-left">
            <div class="exp-card-name">{desc}</div>
            <div class="exp-card-bank">{bname}</div>
            <div class="exp-card-date">{t["created_at"]}</div>
          </div>
          <div class="exp-card-right">
            <div class="exp-card-amount" style="color:{color};">{sign}NGN {t["amount"]:,}</div>
          </div>
        </div>""", unsafe_allow_html=True)
