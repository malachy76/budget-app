# _pages/business_daily_report.py — Business Mode: End-of-Day Summary (cash basis)
from datetime import timedelta

import streamlit as st

from styles import render_page_header
from daily_report import get_cash_basis_report, business_today

_PERIODS = ["Today", "Yesterday", "This week", "This month", "Custom range"]
_COLLECTION_LABELS = [
    ("stock_initial", "Stock sales \u2014 payment made at the time of sale"),
    ("stock_repayment", "Stock sales \u2014 later repayment of customer debt"),
    ("treatment_initial", "Treatments \u2014 first payment"),
    ("treatment_repayment", "Treatments \u2014 later repayment of customer debt"),
]


def _n(v):
    return f"\u20A6{v:,.2f}"


def _dates():
    choice = st.selectbox("Period", _PERIODS, key="eod_period")
    today = business_today()
    if choice == "Today":
        return today, today
    if choice == "Yesterday":
        y = today - timedelta(days=1)
        return y, y
    if choice == "This week":
        return today - timedelta(days=today.weekday()), today
    if choice == "This month":
        return today.replace(day=1), today
    c1, c2 = st.columns(2)
    s = c1.date_input("From", value=today.replace(day=1), key="eod_from")
    e = c2.date_input("To", value=today, key="eod_to")
    if s > e:
        st.error("'From' date must not be after 'To' date.")
        return None, None
    return s, e


def render_business_daily_report(user_id):
    render_page_header()
    st.markdown("### \U0001F4CA End-of-Day Summary")

    business_id = st.session_state.get("active_business_id")
    if not business_id:
        st.info("Select or create a business first, from Business Home.")
        return

    start, end = _dates()
    if start is None:
        return
    st.caption(
        "Business days use Nigerian time (Africa/Lagos). Revenue and profit here are counted "
        "only when money has actually been received."
    )

    try:
        r = get_cash_basis_report(business_id, user_id, start, end)
    except Exception as _e:
        st.error("Could not build the report.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    if r["payment_history_mismatches"] > 0:
        st.warning(
            f"\u26A0\uFE0F {r['payment_history_mismatches']} sale/treatment record(s) have a paid "
            f"total that doesn't match their payment history (older data). Figures for past days "
            f"may be slightly off."
        )

    # ── 1. Activity — invoices and bills, paid or not ──
    st.markdown("#### Sales and bills created (not revenue yet)")
    a1, a2 = st.columns(2)
    a1.metric("Total Sales Activity", _n(r["sales_activity"]))
    a2.metric("Total Treatment Bills", _n(r["treatment_activity"]))
    st.caption(
        f"{r['sales_count']} sale(s) and {r['treatments_started']} new treatment(s). These are the "
        f"full values including anything still unpaid \u2014 unpaid money is not revenue or profit."
    )
    st.divider()

    # ── 2. Money actually received ──
    st.markdown("#### Money received")
    st.metric("Actual Money Collected", _n(r["money_collected_total"]))
    c = r["collections"]
    for key, label in _COLLECTION_LABELS:
        st.markdown(f"{label}: **{_n(c[key]['amount'])}**" + (f" ({c[key]['count']})" if c[key]["count"] else ""))
    st.markdown(
        f":orange[Recovery of previously written-off debt: **{_n(c['recovery']['amount'])}**] "
        + (f"({c['recovery']['count']})" if c["recovery"]["count"] else "")
    )
    if r["by_method"]:
        st.caption("By payment method:")
        for m, v in r["by_method"].items():
            st.caption(f"\u2022 {m}: {_n(v['total'])}")
    st.divider()

    # ── 3. Realised revenue and gross profit ──
    st.markdown("#### Realised revenue and gross profit")
    st.caption("Counted only from money received. Recoveries of written-off debt are not included.")
    v1, v2 = st.columns(2)
    v1.metric("Realised Stock Sales Revenue", _n(r["realised_stock_revenue"]))
    v2.metric("Realised Treatment Revenue", _n(r["realised_treatment_revenue"]))
    v3, v4 = st.columns(2)
    v3.metric("Total Realised Operating Revenue", _n(r["realised_operating_revenue"]))
    v4.metric("Realised Gross Profit", _n(r["realised_gross_profit"]))
    margin = f"{r['gross_margin_pct']:.1f}%" if r["gross_margin_pct"] is not None else "n/a"
    st.caption(
        f"Cost of goods on the money collected: {_n(r['cogs_on_collected'])} \u00b7 Gross margin: {margin}. "
        f"This is gross profit, not net profit \u2014 business expenses (rent, salaries, etc.) are not "
        f"recorded yet, so net profit is not calculated."
    )
    if r["profit_incomplete"]:
        st.warning(
            f"\u26A0\uFE0F Profit is incomplete. {_n(r['revenue_with_unknown_cost'])} of the money "
            f"collected is for items whose purchase cost isn't known. It is counted as revenue but "
            f"left out of gross profit (it is never treated as a cost of \u20A60)."
        )
    if r["unknown_cost_items"]:
        st.caption(
            f"Items with no recorded cost \u2014 {r['unknown_cost_sales']} sale(s)"
            + (f", {r['unknown_cost_treatments']} treatment(s)" if r["unknown_cost_treatments"] else "")
            + ". Set each product's cost in Products / Inventory so future sales are costed:"
        )
        for it in r["unknown_cost_items"][:10]:
            st.caption(
                f"\u2022 {it['product']} ({it['source'].lower()}): {it['lines']} line(s), "
                f"quantity {it['quantity']:g}, worth {_n(it['value'])}"
            )
        if len(r["unknown_cost_items"]) > 10:
            st.caption(f"\u2026and {len(r['unknown_cost_items']) - 10} more product(s).")
    st.divider()

    # ── 4. Customer debts outstanding ──
    st.markdown("### CUSTOMER DEBTS OUTSTANDING")
    d1, d2 = st.columns(2)
    d1.metric("Total Still Owed", _n(r["closing_debt"]))
    d2.metric("Debt at Start of Period", _n(r["opening_debt"]))
    st.caption(
        f"{_n(r['closing_stock_debt'])} from stock sales \u00b7 {_n(r['closing_treatment_debt'])} from "
        f"treatments. Balances are as they stood at the end of {end:%d %b %Y}. This is money owed to "
        f"you \u2014 it is not profit."
    )
    if r["debtors"]:
        for d in r["debtors"][:30]:
            with st.container(border=True):
                st.markdown(f"**{d['name']}** \u2014 {_n(d['total'])}")
                st.caption(
                    (d["phone"] or "No phone on file")
                    + f" \u00b7 stock sales {_n(d['stock'])} \u00b7 treatments {_n(d['treatment'])}"
                )
        if len(r["debtors"]) > 30:
            st.caption(f"\u2026and {len(r['debtors']) - 30} more customer(s). See Customers / Credit.")
    else:
        st.info("No customer owes you money at the end of this period.")

    st.markdown("##### How the debt figure adds up")
    st.markdown(
        f"Debt at start: **{_n(r['opening_debt'])}**  \n"
        f"+ New sales and treatment charges: **{_n(r['new_charges'])}**  \n"
        f"\u2212 Payments received: **{_n(r['payments_received'])}**  \n"
        f"\u2212 Written off: **{_n(r['written_off'])}**  \n"
        f"+ Write-offs reversed: **{_n(r['write_offs_reversed'])}**  \n"
        f"= **{_n(r['expected_closing_debt'])}** (debt at end: **{_n(r['closing_debt'])}**)"
    )
    if r["reconciles"]:
        st.caption("\u2705 These figures balance.")
    else:
        st.warning(
            "\u26A0\uFE0F These figures do not balance. This usually means older records that "
            "don't match their payment history \u2014 please check Customers / Credit."
        )
    st.divider()

    # ── 5. Bad debt — separate from everything above ──
    st.markdown("#### Bad debts (kept separate)")
    b1, b2 = st.columns(2)
    b1.metric("Debts Written Off", _n(r["written_off"]))
    b2.metric("Bad-Debt Recoveries", _n(r["recoveries"]))
    if r["write_offs_reversed"] > 0:
        st.caption(f"Write-offs reversed in this period: {_n(r['write_offs_reversed'])}.")
    st.caption(
        "A write-off is not money received and is not part of revenue or gross profit. Money "
        "recovered later is not new sales revenue."
    )
