# _pages/demo_pages.py — Demo Mode renderers for all non-dashboard pages
# Each function receives the demo dict and renders read-only UI.
# Zero DB queries. Zero writes. All write actions show a signup prompt.
# Mobile-first: clean cards, no heavy charts.
import streamlit as st
from datetime import datetime, timedelta
import re as _re


# ── Shared helper ─────────────────────────────────────────────────────────────

def _demo_write_guard(label: str = "Sign up to save your data") -> None:
    """Replace write actions with a friendly signup nudge."""
    st.info(f"🔒 **Demo mode** — {label}. [Sign up to use this feature.](#)")


# ── Income ────────────────────────────────────────────────────────────────────

def render_demo_income(demo: dict) -> None:
    st.markdown("## Income")
    st.caption("💡 *Demo mode — data is sample only. Sign up to track your real income.*")

    bank_map = {b["id"]: b["bank_name"] for b in demo["banks"]}
    incomes  = sorted(
        [t for t in demo["transactions"] if t["type"] == "credit"],
        key=lambda t: t["created_at"], reverse=True
    )
    total = sum(t["amount"] for t in incomes)
    st.metric("Total Income Recorded", f"NGN {total:,}")
    st.divider()

    st.subheader("Income History")
    for t in incomes:
        desc  = t["description"].replace("Income: ", "")
        bname = bank_map.get(t["bank_id"], "—")
        st.markdown(f"""
        <div class="exp-card" style="border-left-color:#0e7c5b;">
          <div class="exp-card-left">
            <div class="exp-card-name">{desc}</div>
            <div class="exp-card-bank">{bname}</div>
            <div class="exp-card-date">{t["created_at"]}</div>
          </div>
          <div class="exp-card-right">
            <div class="exp-card-amount" style="color:#0e7c5b;">+NGN {t["amount"]:,}</div>
          </div>
        </div>""", unsafe_allow_html=True)

    st.divider()
    with st.expander("➕ Add Income (Demo)", expanded=False):
        _demo_write_guard("Sign up to record your real income")


# ── Expenses ──────────────────────────────────────────────────────────────────

def render_demo_expenses(demo: dict) -> None:
    st.markdown("## Expenses")
    st.caption("💡 *Demo mode — data is sample only.*")

    expenses = sorted(demo["expenses"], key=lambda e: e["created_at"], reverse=True)
    total    = sum(e["amount"] for e in expenses)
    c1, c2   = st.columns(2)
    c1.metric("Total Expenses",  f"NGN {total:,}")
    c2.metric("Expense Entries", len(expenses))
    st.divider()

    for e in expenses:
        cat_badge = (
            f'<span style="background:#e8f5f0;color:#0e7c5b;border-radius:10px;'
            f'padding:1px 7px;font-size:0.74rem;font-weight:600;margin-left:6px;">'
            f'{e["category"]}</span>' if e.get("category") else ""
        )
        st.markdown(f"""
        <div class="exp-card">
          <div class="exp-card-left">
            <div class="exp-card-name">{e["name"]}{cat_badge}</div>
            <div class="exp-card-date">{e["created_at"]}</div>
          </div>
          <div class="exp-card-right">
            <div class="exp-card-amount">−NGN {e["amount"]:,}</div>
          </div>
        </div>""", unsafe_allow_html=True)

    st.divider()
    with st.expander("➕ Add Expense (Demo)", expanded=False):
        _demo_write_guard("Sign up to log your real expenses")


# ── Banks ─────────────────────────────────────────────────────────────────────

def render_demo_banks(demo: dict) -> None:
    st.markdown("## Bank Accounts")
    st.caption("💡 *Demo mode — sample bank accounts shown.*")

    total = sum(b["balance"] for b in demo["banks"])
    st.metric("Total Balance Across All Banks", f"NGN {total:,}")
    st.divider()

    for b in demo["banks"]:
        bal_color = "#0e7c5b" if b["balance"] > b["min_balance_alert"] else "#c0392b"
        st.markdown(f"""
        <div class="exp-card" style="border-left-color:{bal_color};">
          <div class="exp-card-left">
            <div class="exp-card-name">{b["bank_name"]}</div>
            <div class="exp-card-bank">{b["account_name"]} &middot; ****{b["account_number"]}</div>
          </div>
          <div class="exp-card-right">
            <div class="exp-card-amount" style="color:{bal_color};">NGN {b["balance"]:,}</div>
          </div>
        </div>""", unsafe_allow_html=True)

    st.divider()
    with st.expander("➕ Add Bank Account (Demo)", expanded=False):
        _demo_write_guard("Sign up to link your real accounts")


# ── Goals ─────────────────────────────────────────────────────────────────────

def render_demo_goals(demo: dict) -> None:
    st.markdown("## Savings Goals")
    st.caption("💡 *Demo mode — sample goals shown.*")

    active    = [g for g in demo["goals"] if g["status"] == "active"]
    completed = [g for g in demo["goals"] if g["status"] == "completed"]
    total_saved = sum(g["current_amount"] for g in active)
    c1, c2 = st.columns(2)
    c1.metric("Active Goals",   len(active))
    c2.metric("Total Saved",    f"NGN {total_saved:,}")
    st.divider()

    for g in active + completed:
        pct       = min(round(g["current_amount"] / g["target_amount"] * 100, 1), 100) \
                    if g["target_amount"] > 0 else 0
        remaining = max(g["target_amount"] - g["current_amount"], 0)
        color     = "#0e7c5b" if g["status"] == "completed" else (
                    "#f39c12" if pct >= 50 else "#c0392b")
        done_badge = (
            '<span style="background:#e8f5f0;color:#0e7c5b;border-radius:10px;'
            'padding:1px 8px;font-size:0.72rem;font-weight:600;">Completed ✓</span>'
            if g["status"] == "completed" else ""
        )
        st.markdown(f"""
        <div class="exp-card" style="border-left-color:{color};">
          <div class="exp-card-left" style="width:100%;">
            <div class="exp-card-name">{g["name"]} {done_badge}</div>
            <div style="background:#eef5f2;border-radius:6px;height:7px;
                        margin:8px 0 4px;overflow:hidden;">
              <div style="background:{color};width:{pct:.1f}%;height:7px;border-radius:6px;"></div>
            </div>
            <div style="font-size:0.78rem;color:#7a9aaa;">
              NGN {g["current_amount"]:,} of NGN {g["target_amount"]:,}
              &nbsp;&middot;&nbsp; {pct:.0f}% complete
              {"" if g["status"] == "completed" else f" &nbsp;&middot;&nbsp; NGN {remaining:,} left"}
            </div>
          </div>
          <div class="exp-card-right">
            <div style="font-size:1rem;font-weight:800;color:{color};">{pct:.0f}%</div>
          </div>
        </div>""", unsafe_allow_html=True)

    st.divider()
    with st.expander("➕ Create Savings Goal (Demo)", expanded=False):
        _demo_write_guard("Sign up to create and track your real savings goals")


# ── Transfers ─────────────────────────────────────────────────────────────────

def render_demo_transfers(demo: dict) -> None:
    st.markdown("## Transfers")
    st.caption("💡 *Demo mode — no real transfers will be made.*")
    st.info("Transfer money between your linked bank accounts. Sign up to use this feature.")
    st.divider()
    with st.expander("➕ Transfer Funds (Demo)", expanded=False):
        _demo_write_guard("Sign up to transfer money between your real accounts")


# ── Tracker ───────────────────────────────────────────────────────────────────

def render_demo_tracker(demo: dict) -> None:
    st.markdown("## Tracker")
    st.caption("💡 *Demo mode — recurring items, debts, and emergency fund shown as sample.*")

    today = datetime.now().date()

    tab_ri, tab_re, tab_bill, tab_debt, tab_ef = st.tabs([
        "💰 Recurring Income", "💸 Recurring Expenses",
        "🔔 Bill Reminders",   "💳 Debt / Loan",
        "🛡️ Emergency Fund",
    ])

    freq_labels = {"monthly": "Monthly", "weekly": "Weekly",
                   "daily": "Daily", "yearly": "Yearly"}

    def _due_badge(nd_str):
        if not nd_str: return "No date", "#95a5a6"
        nd   = datetime.strptime(nd_str, "%Y-%m-%d").date()
        days = (nd - today).days
        if days < 0:  return f"Overdue {abs(days)}d", "#c0392b"
        if days == 0: return "Due today", "#e67e22"
        if days <= 7: return f"Due in {days}d", "#f39c12"
        return f"Due in {days}d", "#1a3c5e"

    with tab_ri:
        st.subheader("Recurring Income")
        for r in demo["recurring_income"]:
            label, color = _due_badge(r["next_due"])
            st.markdown(f"""
            <div class="exp-card" style="border-left-color:#0e7c5b;">
              <div class="exp-card-left">
                <div class="exp-card-name">{r["name"]}</div>
                <div class="exp-card-bank">{freq_labels.get(r["frequency"],"Monthly")}
                  {"→ " + r["bank_name"] if r.get("bank_name") else ""}
                  {"&nbsp;<em style='font-size:0.74rem;'>auto-post</em>" if r["auto_post"] else ""}
                </div>
                <div class="exp-card-date" style="color:{color};">{label} — {r["next_due"]}</div>
              </div>
              <div class="exp-card-right">
                <div class="exp-card-amount" style="color:#0e7c5b;">+NGN {r["amount"]:,}</div>
              </div>
            </div>""", unsafe_allow_html=True)
        st.divider()
        _demo_write_guard("Sign up to add real recurring income")

    with tab_re:
        st.subheader("Recurring Expenses")
        for r in demo["recurring_expenses"]:
            label, color = _due_badge(r["next_due"])
            cat_badge = (
                f'<span style="background:#e8f5f0;color:#0e7c5b;border-radius:10px;'
                f'padding:1px 7px;font-size:0.74rem;font-weight:600;margin-left:5px;">'
                f'{r["category"]}</span>' if r.get("category") else ""
            )
            st.markdown(f"""
            <div class="exp-card">
              <div class="exp-card-left">
                <div class="exp-card-name">{r["name"]}{cat_badge}</div>
                <div class="exp-card-bank">{freq_labels.get(r["frequency"],"Monthly")}
                  {"→ " + r["bank_name"] if r.get("bank_name") else ""}
                </div>
                <div class="exp-card-date" style="color:{color};">{label} — {r["next_due"]}</div>
              </div>
              <div class="exp-card-right">
                <div class="exp-card-amount">−NGN {r["amount"]:,}</div>
              </div>
            </div>""", unsafe_allow_html=True)
        st.divider()
        _demo_write_guard("Sign up to add real recurring expenses")

    with tab_bill:
        st.subheader("Bill Reminders")
        all_items = demo["recurring_income"] + demo["recurring_expenses"]
        upcoming  = sorted(all_items, key=lambda r: r["next_due"] or "9999-12-31")
        if upcoming:
            for r in upcoming[:6]:
                label, color = _due_badge(r["next_due"])
                icon = "🔴" if color == "#c0392b" else ("🟠" if color == "#f39c12" else "🟢")
                st.markdown(f"""
                <div class="exp-card">
                  <div class="exp-card-left">
                    <div class="exp-card-name">{icon} {r["name"]}</div>
                    <div class="exp-card-date" style="color:{color};">{label} — {r["next_due"]}</div>
                  </div>
                  <div class="exp-card-right">
                    <div class="exp-card-amount">NGN {r["amount"]:,}</div>
                  </div>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("No upcoming bills in demo data.")

    with tab_debt:
        st.subheader("Debt & Loan Tracker")
        debts = demo["debts"]
        total_owe  = sum(d["balance_remaining"] for d in debts
                         if d["type"] == "borrowed" and d["status"] == "active")
        total_lent = sum(d["balance_remaining"] for d in debts
                         if d["type"] == "lent"     and d["status"] == "active")
        c1, c2 = st.columns(2)
        c1.metric("You Owe (active)",    f"NGN {total_owe:,}")
        c2.metric("Owed to You (active)",f"NGN {total_lent:,}")
        st.divider()
        for d in debts:
            is_lent   = d["type"] == "lent"
            principal = int(d["principal"])
            balance   = int(d["balance_remaining"])
            paid      = principal - balance
            pct_paid  = round(paid / principal * 100, 1) if principal > 0 else 0
            color     = "#0e7c5b" if is_lent else "#c0392b"
            direction = "📤 Lent" if is_lent else "📥 Borrowed"
            notes_raw = d.get("notes","")
            cat_m = _re.match(r'^\[([^\]]+)\]', notes_raw)
            debt_cat = cat_m.group(1) if cat_m else ""
            cat_badge = (
                f'<span style="background:#e8f0f7;color:#6a1b9a;border-radius:10px;'
                f'padding:1px 8px;font-size:0.72rem;font-weight:600;">{debt_cat}</span>'
                if debt_cat else ""
            )
            bar_color = "#0e7c5b" if pct_paid >= 100 else ("#f39c12" if pct_paid >= 50 else color)
            st.markdown(f"""
            <div class="exp-card" style="border-left-color:{color};">
              <div class="exp-card-left" style="width:100%;">
                <div class="exp-card-name">{direction}: {d["name"]} {cat_badge}</div>
                <div class="exp-card-bank">
                  {d.get("counterparty","") + " · " if d.get("counterparty") else ""}
                  {f"{d['interest_rate']:.1f}% p.a." if d["interest_rate"] else "0% interest"}
                </div>
                <div class="exp-card-date">Due: {d["due_date"] or "Not set"}</div>
                <div style="background:#eef5f2;border-radius:6px;height:7px;margin-top:7px;overflow:hidden;">
                  <div style="background:{bar_color};width:{min(pct_paid,100):.1f}%;height:7px;border-radius:6px;"></div>
                </div>
                <div style="font-size:0.72rem;color:#95a5a6;margin-top:3px;">
                  NGN {paid:,} paid of NGN {principal:,} ({pct_paid:.0f}%)
                </div>
              </div>
              <div class="exp-card-right">
                <div style="font-size:1rem;font-weight:800;color:{color};">NGN {balance:,}</div>
                <div style="font-size:0.72rem;color:#95a5a6;">remaining</div>
              </div>
            </div>""", unsafe_allow_html=True)
        st.divider()
        _demo_write_guard("Sign up to track your real debts and loan repayments")

    with tab_ef:
        st.subheader("Emergency Fund Planner")
        ef      = demo["emergency_fund"]
        target  = ef["target_months"] * ef["monthly_expenses_estimate"]
        saved   = ef["current_saved"]
        pct     = min(round(saved / target * 100, 1), 100) if target > 0 else 0
        shortfall = max(target - saved, 0)
        st.info(
            f"📊 Sample monthly expenses: **NGN {ef['monthly_expenses_estimate']:,}**. "
            f"Target: {ef['target_months']}-month fund."
        )
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Target ({ef['target_months']}-month)", f"NGN {target:,}")
        c2.metric("Saved So Far",  f"NGN {saved:,}")
        c3.metric("Still Needed",  f"NGN {shortfall:,}")
        st.progress(pct / 100, text=f"{pct:.0f}% complete — NGN {saved:,} of NGN {target:,}")
        st.divider()
        _demo_write_guard("Sign up to set up and track your real emergency fund")


# ── Notifications ─────────────────────────────────────────────────────────────

def render_demo_notifications(demo: dict) -> None:
    st.markdown("## Notifications")
    st.caption("💡 *Demo mode — sample notifications shown.*")

    streak = demo["streak"]
    st.markdown(f"""
    <div class="streak-banner">
      <div><span class="streak-num">{streak["current"]}</span>
        <span style="font-size:0.9rem;color:#a8d8c8;">-day streak</span>
        <div class="streak-label">Keep logging daily to build your streak</div>
      </div>
      <div class="streak-right">
        <div class="streak-best">Best streak</div>
        <div class="streak-best-num">{streak["longest"]} days</div>
      </div>
    </div>""", unsafe_allow_html=True)

    badge_colors = {"milestone":"#6a1b9a","reminder":"#1a3c5e","alert":"#c0392b",
                    "nudge":"#d4850a","tip":"#0e7c5b"}
    for n in demo["notifications"]:
        opacity  = "1" if not n["read"] else "0.55"
        bg       = "#fafcfb" if n["read"] else "#ffffff"
        bc       = badge_colors.get(n["type"], "#7a9aaa")
        st.markdown(f"""
        <div class="notif-card" style="background:{bg};opacity:{opacity};">
          <div class="notif-icon">{n["icon"]}</div>
          <div class="notif-body">
            <div class="notif-title">{n["title"]}
              <span class="notif-badge" style="background:{bc};">{n["type"]}</span>
              {"" if not n["read"] else '<span style="font-size:0.7rem;color:#95a5a6;">Read</span>'}
            </div>
            <div class="notif-text">{n["body"]}</div>
            <div class="notif-time">{n["created_at"]}</div>
          </div>
        </div>""", unsafe_allow_html=True)


# ── Summaries ─────────────────────────────────────────────────────────────────

def render_demo_summaries(demo: dict) -> None:
    st.markdown("## Summaries")
    st.caption("💡 *Demo mode — sample summary shown.*")

    from datetime import date
    today  = date.today()
    mo_start = today.replace(day=1).isoformat()
    txns = demo["transactions"]
    mo_inc = sum(t["amount"] for t in txns
                 if t["type"] == "credit" and t["created_at"] >= mo_start)
    mo_exp = sum(t["amount"] for t in txns
                 if t["type"] == "debit"  and t["created_at"] >= mo_start)
    mo_net = mo_inc - mo_exp

    c1, c2, c3 = st.columns(3)
    c1.metric("Income This Month",   f"NGN {mo_inc:,}")
    c2.metric("Expenses This Month", f"NGN {mo_exp:,}")
    c3.metric("Net This Month",      f"NGN {mo_net:,}")

    st.divider()
    cat_totals: dict = {}
    for e in demo["expenses"]:
        if e["created_at"] >= mo_start:
            cat_totals[e["category"]] = cat_totals.get(e["category"], 0) + e["amount"]
    if cat_totals:
        st.subheader("Expense Categories This Month")
        for cat, total in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
            pct = round(total / mo_exp * 100) if mo_exp > 0 else 0
            st.markdown(f"""
            <div style="background:#fff;border:1px solid #e2ede9;border-radius:10px;
                        padding:11px 14px;margin-bottom:7px;
                        display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="font-weight:700;color:#1a3c5e;font-size:0.9rem;">{cat}</div>
                <div style="background:#e2ede9;border-radius:4px;height:5px;
                            margin-top:6px;width:140px;overflow:hidden;">
                  <div style="background:#0e7c5b;width:{pct}%;height:5px;border-radius:4px;"></div>
                </div>
              </div>
              <div style="font-weight:800;color:#c0392b;font-size:0.98rem;">
                NGN {total:,}<br>
                <span style="font-size:0.72rem;color:#95a5a6;font-weight:400;">{pct}% of total</span>
              </div>
            </div>""", unsafe_allow_html=True)


# ── Settings ──────────────────────────────────────────────────────────────────

def render_demo_settings() -> None:
    st.markdown("## Settings")
    st.caption("💡 *Demo mode — settings are read-only.*")
    st.info("Sign up to set your monthly budget, category limits, and change your password.")
    st.metric("Monthly Budget Limit", "NGN 150,000")
    st.metric("Overdraft",            "Disabled")


# ── Import CSV ────────────────────────────────────────────────────────────────

def render_demo_import_csv() -> None:
    st.markdown("## Import CSV")
    st.caption("💡 *Demo mode — CSV import is disabled.*")
    st.info(
        "Budget Right auto-detects GTB, Access, Zenith, Opay, Kuda, and 7 other Nigerian bank "
        "statement formats. Sign up to import your real bank statement in seconds."
    )
    _demo_write_guard("Sign up to import your bank statement")
