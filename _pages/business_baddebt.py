# _pages/business_baddebt.py — Business Mode: Bad Debts (Phase 5A-4)
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import streamlit as st

from styles import render_page_header
from sales import PAYMENT_METHODS
from baddebt import (
    WRITE_OFF_REASONS, OTHER_REASON, SOURCE_SALE, SOURCE_TREATMENT, SOURCE_LABELS,
    write_off_debt, reverse_write_off, record_recovery,
    get_bad_debt_summary, get_collectible_debts, get_unrecovered_write_offs,
    get_write_off_events, get_recovery_events, get_transaction_history,
    get_transaction_snapshot,
)

_LAGOS = ZoneInfo("Africa/Lagos")
_VIEWS = ["Write Off a Debt", "Record Recovery", "Written-Off Debts", "Recovery History"]
_TYPE_FILTERS = {"All types": None, "Stock sales": SOURCE_SALE, "Treatment bills": SOURCE_TREATMENT}
_PERIODS = ["All time", "Today", "Yesterday", "This week", "This month", "Custom range"]


def _naira(v):
    return f"\u20A6{v:,.2f}"


def _fmt_dt(dt):
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_LAGOS).strftime("%d %b %Y %H:%M")


def _phone(p):
    return p or "No phone on file"


def _period_dates(prefix):
    """Returns (start, end) business dates in Africa/Lagos, or (None, None)
    for all time."""
    choice = st.selectbox("Period", _PERIODS, key=f"{prefix}_period")
    today = datetime.now(_LAGOS).date()
    if choice == "Today":
        return today, today
    if choice == "Yesterday":
        y = today - timedelta(days=1)
        return y, y
    if choice == "This week":
        return today - timedelta(days=today.weekday()), today
    if choice == "This month":
        return today.replace(day=1), today
    if choice == "Custom range":
        c1, c2 = st.columns(2)
        s = c1.date_input("From", value=today.replace(day=1), key=f"{prefix}_from")
        e = c2.date_input("To", value=today, key=f"{prefix}_to")
        if s > e:
            st.error("'From' date must not be after 'To' date.")
            return None, None
        return s, e
    return None, None


def _new_key():
    return uuid.uuid4().hex


def render_business_baddebt(user_id):
    render_page_header()
    st.markdown("### \U0001F9FE Bad Debts")

    business_id = st.session_state.get("active_business_id")
    if not business_id:
        st.info("Select or create a business first, from Business Home.")
        return

    flash = st.session_state.pop("_bd_flash", None)
    if flash:
        st.success(flash)

    try:
        s = get_bad_debt_summary(business_id, user_id)
    except Exception as _e:
        st.error("Could not load bad-debt data.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    c1, c2 = st.columns(2)
    c1.metric("Total Written Off", _naira(s["total_written_off"]))
    c2.metric("Total Recovered", _naira(s["total_recovered"]))
    c3, c4 = st.columns(2)
    c3.metric("Still Unrecovered", _naira(s["unrecovered"]))
    c4.metric("Written-Off Transactions", s["written_off_transactions"])
    st.caption(
        f"Transactions with a recovery: {s['transactions_with_recovery']}. "
        "Writing off a debt is not a payment and does not change your sales or profit "
        "figures. Money recovered later is reported separately \u2014 it is not new sales."
    )
    st.divider()

    # A write-off or recovery form in progress takes over the screen.
    if st.session_state.get("_bd_wo_target"):
        _render_write_off_form(business_id, user_id)
        return
    if st.session_state.get("_bd_rec_target"):
        _render_recovery_form(business_id, user_id)
        return

    view = st.radio("Section", _VIEWS, horizontal=True, key="bd_view", label_visibility="collapsed")
    if view == _VIEWS[0]:
        _render_write_off_list(business_id, user_id)
    elif view == _VIEWS[1]:
        _render_recovery_list(business_id, user_id)
    elif view == _VIEWS[2]:
        _render_written_off_history(business_id, user_id)
    else:
        _render_recovery_history(business_id, user_id)


# ── Write off ────────────────────────────────────────────────────────────────

def _render_write_off_list(business_id, user_id):
    st.caption(
        "Only write off a debt when you do not expect to collect it. An overdue debt is "
        "not automatically a bad debt \u2014 nothing is ever written off for you."
    )
    type_label = st.selectbox("Show", list(_TYPE_FILTERS), key="bd_wo_type")
    try:
        rows = get_collectible_debts(business_id, user_id, _TYPE_FILTERS[type_label])
    except Exception as _e:
        st.error("Could not load customer debts.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return
    if not rows:
        st.info("No customer debts waiting to be collected.")
        return
    for r in rows:
        with st.container(border=True):
            st.markdown(f"**{r['customer_name']}**")
            st.caption(_phone(r["customer_phone"]))
            st.markdown(f"{r['label']} \u00b7 {SOURCE_LABELS[r['source_type']]} \u00b7 {_fmt_dt(r['tx_created_at'])[:11]}")
            m1, m2 = st.columns(2)
            m1.metric("Original", _naira(r["total"]))
            m2.metric("Paid", _naira(r["paid"]))
            m3, m4 = st.columns(2)
            m3.metric("Written off", _naira(r["written_off"]))
            m4.metric("Still collectible", _naira(r["collectible"]))
            if st.button("Write off\u2026", key=f"bd_wo_btn_{r['source_type']}_{r['tx_id']}",
                         use_container_width=True):
                st.session_state["_bd_wo_target"] = (r["source_type"], r["tx_id"])
                st.session_state.pop("_bd_wo_review", None)
                st.rerun()


def _clear_write_off_state():
    for k in ("_bd_wo_target", "_bd_wo_review", "bd_wo_mode", "bd_wo_amount",
              "bd_wo_reason", "bd_wo_note", "bd_wo_ack"):
        st.session_state.pop(k, None)


def _render_write_off_form(business_id, user_id):
    source_type, tx_id = st.session_state["_bd_wo_target"]
    try:
        snap = get_transaction_snapshot(source_type, tx_id, business_id, user_id)
    except Exception as _e:
        st.error("Could not load this transaction.")
        with st.expander("Technical details"):
            st.code(str(_e))
        snap = None
    if snap is None or snap["collectible"] <= 0:
        st.warning("This transaction no longer has a collectible balance.")
        if st.button("\u2190 Back", key="bd_wo_back_missing"):
            _clear_write_off_state()
            st.rerun()
        return

    if st.button("\u2190 Cancel", key="bd_wo_cancel"):
        _clear_write_off_state()
        st.rerun()

    review = st.session_state.get("_bd_wo_review")

    st.markdown(f"#### Write off \u2014 {snap['label']}")
    st.markdown(f"**{snap['customer_name']}**")
    st.caption(_phone(snap["customer_phone"]))

    if review is None:
        st.caption(f"{SOURCE_LABELS[source_type]} \u00b7 Still collectible: {_naira(snap['collectible'])}")
        mode = st.radio("How much?", ["Write off the full balance", "Write off part of it"],
                        key="bd_wo_mode")
        if mode == "Write off the full balance":
            amount = snap["collectible"]
            st.markdown(f"Amount: **{_naira(amount)}**")
        else:
            amt = st.number_input(
                "Amount to write off (\u20A6)", min_value=0.0,
                max_value=float(snap["collectible"]), value=None, step=0.01,
                format="%.2f", placeholder="e.g. 8000", key="bd_wo_amount",
            )
            amount = Decimal(str(amt)) if amt else None
        reason = st.selectbox("Reason", WRITE_OFF_REASONS, key="bd_wo_reason")
        note = st.text_input(
            "Explanation" + (" (required)" if reason == OTHER_REASON else " (optional)"),
            key="bd_wo_note",
        )
        if st.button("Review write-off", type="primary", key="bd_wo_review_btn",
                     use_container_width=True):
            if not amount or amount <= 0:
                st.error("Enter an amount greater than zero.")
            elif amount > snap["collectible"]:
                st.error(f"You can write off at most {_naira(snap['collectible'])}.")
            elif reason == OTHER_REASON and not (note or "").strip():
                st.error("Please explain the reason when choosing 'Other'.")
            else:
                st.session_state["_bd_wo_review"] = {
                    "amount": str(amount), "reason": reason, "note": (note or "").strip(),
                    "key": _new_key(),
                }
                st.rerun()
        return

    # ── Confirmation screen ──
    amount = Decimal(review["amount"])
    st.markdown("##### Please confirm")
    with st.container(border=True):
        st.markdown(f"**Customer:** {snap['customer_name']}  \n**Phone:** {_phone(snap['customer_phone'])}")
        st.markdown(f"**Transaction:** {snap['label']} ({SOURCE_LABELS[source_type]})")
        st.markdown(
            f"Original amount: **{_naira(snap['total'])}**  \n"
            f"Already paid: **{_naira(snap['paid'])}**  \n"
            f"Previously written off: **{_naira(snap['written_off'])}**  \n"
            f"Current outstanding: **{_naira(snap['collectible'])}**"
        )
        st.markdown(f":red[Proposed write-off: **{_naira(amount)}**]")
        st.markdown(f"Still collectible afterwards: **{_naira(snap['collectible'] - amount)}**")
        st.markdown(f"Reason: {review['reason']}" + (f" \u2014 {review['note']}" if review["note"] else ""))
    st.caption(
        "This is recorded as bad debt \u2014 it is not a payment. The original "
        "transaction, your sales figures and your stock stay exactly as they are."
    )
    ack = st.checkbox("I confirm I want to write off this amount.", key="bd_wo_ack")
    b1, b2 = st.columns(2)
    if b1.button("Confirm write-off", type="primary", key="bd_wo_confirm",
                 disabled=not ack, use_container_width=True):
        wid, msg = write_off_debt(
            source_type, tx_id, business_id, user_id, user_id, amount,
            review["reason"], review["note"], review["key"],
        )
        if wid:
            st.session_state["_bd_flash"] = msg
            _clear_write_off_state()
            st.rerun()
        else:
            st.error(msg)
    if b2.button("Edit", key="bd_wo_edit", use_container_width=True):
        st.session_state.pop("_bd_wo_review", None)
        st.rerun()


# ── Recovery ────────────────────────────────────────────────────────────────

def _render_recovery_list(business_id, user_id):
    st.caption(
        "Use this only when a customer pays money back on a debt you already wrote off. "
        "For a debt that is still collectible, record the payment under Customers / Credit."
    )
    type_label = st.selectbox("Show", list(_TYPE_FILTERS), key="bd_rec_type")
    try:
        rows = get_unrecovered_write_offs(business_id, user_id, _TYPE_FILTERS[type_label])
    except Exception as _e:
        st.error("Could not load written-off debts.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return
    if not rows:
        st.info("No written-off debts waiting to be recovered.")
        return
    for r in rows:
        with st.container(border=True):
            st.markdown(f"**{r['customer_name']}**")
            st.caption(_phone(r["customer_phone"]))
            st.markdown(f"{r['label']} \u00b7 {SOURCE_LABELS[r['source_type']]}")
            m1, m2 = st.columns(2)
            m1.metric("Written off", _naira(r["written_off"]))
            m2.metric("Recovered so far", _naira(r["recovered"]))
            st.markdown(f":orange[Still unrecovered: **{_naira(r['unrecovered'])}**]")
            if st.button("Record recovery\u2026", key=f"bd_rec_btn_{r['source_type']}_{r['tx_id']}",
                         use_container_width=True):
                st.session_state["_bd_rec_target"] = (r["source_type"], r["tx_id"])
                st.session_state["_bd_rec_key"] = _new_key()
                st.rerun()


def _clear_recovery_state():
    for k in ("_bd_rec_target", "_bd_rec_key", "bd_rec_amount", "bd_rec_method", "bd_rec_note"):
        st.session_state.pop(k, None)


def _render_recovery_form(business_id, user_id):
    source_type, tx_id = st.session_state["_bd_rec_target"]
    try:
        snap = get_transaction_snapshot(source_type, tx_id, business_id, user_id)
    except Exception as _e:
        st.error("Could not load this transaction.")
        with st.expander("Technical details"):
            st.code(str(_e))
        snap = None
    if snap is None or snap["unrecovered"] <= 0:
        st.warning("Nothing is left to recover on this transaction.")
        if st.button("\u2190 Back", key="bd_rec_back_missing"):
            _clear_recovery_state()
            st.rerun()
        return

    if st.button("\u2190 Cancel", key="bd_rec_cancel"):
        _clear_recovery_state()
        st.rerun()

    st.markdown(f"#### Record recovery \u2014 {snap['label']}")
    st.markdown(f"**{snap['customer_name']}**")
    st.caption(_phone(snap["customer_phone"]))
    st.markdown(
        f"Written off: **{_naira(snap['written_off'])}**  \n"
        f"Recovered so far: **{_naira(snap['recovered'])}**  \n"
        f"Still unrecovered: **{_naira(snap['unrecovered'])}**"
    )
    amt = st.number_input(
        "Amount received (\u20A6)", min_value=0.0, max_value=float(snap["unrecovered"]),
        value=None, step=0.01, format="%.2f", placeholder="e.g. 5000", key="bd_rec_amount",
    )
    method = st.selectbox("Payment method", PAYMENT_METHODS, key="bd_rec_method")
    note = st.text_input("Note (optional)", key="bd_rec_note", placeholder="e.g. Customer paid at the shop")
    st.caption(
        "This is recorded as recovery of a written-off debt. It is not a new sale, "
        "does not change stock, and does not increase your sales revenue."
    )
    if st.button("Confirm recovery", type="primary", key="bd_rec_confirm", use_container_width=True):
        if not amt or amt <= 0:
            st.error("Enter an amount greater than zero.")
        else:
            rid, msg = record_recovery(
                source_type, tx_id, business_id, user_id, user_id,
                Decimal(str(amt)), method, note, st.session_state["_bd_rec_key"],
            )
            if rid:
                st.session_state["_bd_flash"] = msg
                _clear_recovery_state()
                st.rerun()
            else:
                st.error(msg)


# ── Histories ───────────────────────────────────────────────────────────────

def _render_history_block(source_type, tx_id, business_id, user_id):
    snap, events = get_transaction_history(source_type, tx_id, business_id, user_id)
    with st.container(border=True):
        if snap is None:
            st.caption("Transaction not found.")
            return
        st.caption(
            f"{snap['label']}: original {_naira(snap['total'])} \u00b7 paid {_naira(snap['paid'])} \u00b7 "
            f"written off {_naira(snap['written_off'])} \u00b7 recovered {_naira(snap['recovered'])} \u00b7 "
            f"collectible {_naira(max(snap['collectible'], Decimal('0')))}"
        )
        for e in events:
            st.caption(
                f"{_fmt_dt(e['at'])} \u2014 **{e['kind']}** {_naira(e['amount'])} \u2014 {e['detail']}"
                + (f" (by {e['by']})" if e["by"] else "")
            )


def _render_written_off_history(business_id, user_id):
    type_label = st.selectbox("Show", list(_TYPE_FILTERS), key="bd_hist_type")
    start, end = _period_dates("bd_hist")
    if st.session_state.get("bd_hist_period") == "Custom range" and start is None:
        return
    try:
        events = get_write_off_events(business_id, user_id, start, end, _TYPE_FILTERS[type_label])
    except Exception as _e:
        st.error("Could not load write-offs.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return
    if not events:
        st.info("No write-offs found for this selection.")
        return
    total = sum((e["amount"] for e in events if not e["reversed"]), Decimal("0"))
    st.caption(f"{len(events)} write-off(s) \u00b7 total written off in this selection: {_naira(total)}")
    for e in events:
        with st.container(border=True):
            st.markdown(f"**{e['customer_name']}**")
            st.caption(_phone(e["customer_phone"]))
            st.markdown(f"{e['tx_label']} \u00b7 {SOURCE_LABELS[e['source_type']]}")
            m1, m2 = st.columns(2)
            m1.metric("Original", _naira(e["original_total"]))
            m2.metric("Paid before write-off", _naira(e["paid_before_write_off"]))
            m3, m4 = st.columns(2)
            m3.metric("Written off", _naira(e["amount"]))
            m4.metric("Recovered so far", _naira(e["recovered"]))
            st.markdown(f"Still unrecovered (whole transaction): **{_naira(e['unrecovered'])}**")
            st.caption(
                f"{_fmt_dt(e['created_at'])} \u00b7 {e['reason_category']}"
                + (f" \u2014 {e['reason_note']}" if e["reason_note"] else "")
                + (f" \u00b7 by {e['authorized_by']}" if e["authorized_by"] else "")
            )
            st.caption(f"Status: {e['status']}")
            if e["reversed"]:
                st.caption(f"Reversed {_fmt_dt(e['reversed_at'])} \u2014 {e['reversal_reason']}")

            hk = f"_bd_show_hist_{e['id']}"
            if st.button("Full history", key=f"bd_hist_btn_{e['id']}", use_container_width=True):
                st.session_state[hk] = not st.session_state.get(hk, False)
            if st.session_state.get(hk, False):
                _render_history_block(e["source_type"], e["tx_id"], business_id, user_id)

            if not e["reversed"]:
                rk = f"_bd_show_rev_{e['id']}"
                if st.button("Reverse this write-off\u2026", key=f"bd_rev_btn_{e['id']}", use_container_width=True):
                    st.session_state[rk] = not st.session_state.get(rk, False)
                if st.session_state.get(rk, False):
                    with st.container(border=True):
                        st.caption(
                            "Use this only to correct a mistake. The original write-off stays "
                            "in your history and the amount becomes collectible again."
                        )
                        reason = st.text_input("Why is it being reversed? (required)", key=f"bd_rev_reason_{e['id']}")
                        if st.button("Confirm reversal", key=f"bd_rev_confirm_{e['id']}", type="primary"):
                            ok, msg = reverse_write_off(e["id"], business_id, user_id, user_id, reason)
                            if ok:
                                st.session_state["_bd_flash"] = msg
                                st.session_state.pop(rk, None)
                                st.rerun()
                            else:
                                st.error(msg)


def _render_recovery_history(business_id, user_id):
    type_label = st.selectbox("Show", list(_TYPE_FILTERS), key="bd_recH_type")
    start, end = _period_dates("bd_recH")
    if st.session_state.get("bd_recH_period") == "Custom range" and start is None:
        return
    try:
        events = get_recovery_events(business_id, user_id, start, end, _TYPE_FILTERS[type_label])
    except Exception as _e:
        st.error("Could not load recoveries.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return
    if not events:
        st.info("No recoveries found for this selection.")
        return
    total = sum((e["amount"] for e in events), Decimal("0"))
    st.caption(f"{len(events)} recovery payment(s) \u00b7 total recovered in this selection: {_naira(total)}")
    for e in events:
        with st.container(border=True):
            st.markdown(f"**{e['customer_name']}** \u2014 {_naira(e['amount'])}")
            st.caption(_phone(e["customer_phone"]))
            st.markdown(f"{e['tx_label']} \u00b7 {SOURCE_LABELS[e['source_type']]}")
            st.caption(
                f"{_fmt_dt(e['created_at'])} \u00b7 {e['payment_method']}"
                + (f" \u00b7 by {e['authorized_by']}" if e["authorized_by"] else "")
                + (f" \u2014 {e['note']}" if e["note"] else "")
            )
            st.caption(f"Remaining recoverable on this transaction: {_naira(e['remaining_recoverable'])}")
