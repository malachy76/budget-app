# _pages/business_returns.py — Business Mode: Sales Returns & Refunds (Phase 5C)
#
# Flow: find the sale -> pick goods + quantities + condition -> review what will happen
# to the customer's balance / refund -> confirm -> see the completed return record.
# All the money and stock rules live in returns.py; this page only collects input,
# shows the preview that returns.preview_return() computes, and calls
# returns.create_sale_return() with ONE submission reference per attempt.
import streamlit as st

from styles import render_page_header
from returns import (get_sale_for_return, get_recent_sales, get_returns, get_return, preview_return,
                     create_sale_return, CONDITIONS, CONDITION_LABELS, ReturnError)
from sales import PAYMENT_METHODS
from ui_idempotency import get_key, clear_key

_NAIRA = "\u20A6"


def _n(x):
    return f"{_NAIRA}{x:,.2f}"


def _render_return_record(business_id, user_id, return_id):
    rec = get_return(business_id, user_id, return_id)
    if rec is None:
        st.warning("That return record was not found.")
        return
    r, items = rec["return"], rec["items"]
    with st.container(border=True):
        st.markdown(f"**Return #{r['id']}** \u2014 Sale #{r['sale_id']} \u2014 {r['created_at'].strftime('%d %b %Y %H:%M')}")
        st.caption(
            f"Customer: {r['customer_name'] or 'Walk-in'}"
            + (f" \u00b7 Processed by: {r['processed_by']}" if r["processed_by"] else "")
        )
        for it in items:
            cond = "back in stock" if it["condition"] == "saleable" else "damaged \u2014 not restocked"
            st.markdown(f"\u2022 {it['quantity']:g} \u00d7 {it['product_name']} ({cond}) \u2014 {_n(it['line_value'])}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Goods returned", _n(r["return_value"]))
        m2.metric("Debt reduced", _n(r["debt_reduction"]))
        m3.metric("Refunded", _n(r["refund_amount"]))
        if r["refund_amount"] > 0:
            st.caption(f"Refund paid by {r['refund_method']}.")
        st.caption(f"Reason: {r['reason']}" + (f" \u2014 {r['note']}" if r["note"] else ""))


def render_business_returns(user_id):
    render_page_header()
    st.markdown("### \u21A9\uFE0F Sales Returns")

    business_id = st.session_state.get("active_business_id")
    if not business_id:
        st.info("Select or create a business first, from Business Home.")
        return

    flash = st.session_state.pop("_ret_flash", None)
    if flash:
        st.success(flash)
    done_id = st.session_state.get("_ret_done_id")
    if done_id:
        st.markdown("#### Completed return")
        _render_return_record(business_id, user_id, done_id)
        if st.button("Start another return", key="ret_new_btn", use_container_width=True):
            st.session_state.pop("_ret_done_id", None)
            st.session_state.pop("_ret_sale_id", None)
            st.rerun()
        return

    # ── 1. Find the sale ──
    sale_id = st.session_state.get("_ret_sale_id")
    if not sale_id:
        st.caption("Find the original sale by its receipt number (the number after \u2018Sale #\u2019), "
                   "or pick one of the recent sales below.")
        no = st.number_input("Receipt / Sale number", min_value=1, step=1, value=1, key="ret_sale_no")
        if st.button("Find sale", key="ret_find_btn", type="primary", use_container_width=True):
            try:
                found = get_sale_for_return(business_id, user_id, int(no))
            except ReturnError as e:
                st.error(str(e))
                return
            if found is None:
                st.error(f"Sale #{int(no)} was not found in this business.")
            else:
                st.session_state["_ret_sale_id"] = int(no)
                st.rerun()
        st.markdown("**Recent sales**")
        try:
            recent = get_recent_sales(business_id, user_id, limit=12)
        except ReturnError as e:
            st.error(str(e))
            return
        if not recent:
            st.info("No sales yet.")
        for s in recent:
            label = (f"Sale #{s['id']} \u00b7 {_n(s['total_amount'])} \u00b7 {s['customer_name'] or 'Walk-in'} \u00b7 "
                     f"{s['created_at'].strftime('%d %b %H:%M')}" + (" \u00b7 \u21A9\uFE0F has returns" if s["has_returns"] else ""))
            if st.button(label, key=f"ret_pick_{s['id']}", use_container_width=True):
                st.session_state["_ret_sale_id"] = s["id"]
                st.rerun()
        _recent_returns(business_id, user_id)
        return

    try:
        info = get_sale_for_return(business_id, user_id, int(sale_id))
    except ReturnError as e:
        st.error(str(e))
        return
    if info is None:
        st.error("That sale was not found.")
        st.session_state.pop("_ret_sale_id", None)
        return
    sale, items, money = info["sale"], info["items"], info["money"]

    if st.button("\u2190 Choose a different sale", key="ret_back_btn"):
        st.session_state.pop("_ret_sale_id", None)
        st.rerun()

    # ── 2. The original sale ──
    with st.container(border=True):
        st.markdown(f"**Sale #{sale['id']}** \u2014 {sale['created_at'].strftime('%d %b %Y %H:%M')}")
        st.caption(f"Customer: {sale['customer_name'] or 'Walk-in'}"
                   + (f" \u00b7 Sold by: {sale['sold_by']}" if sale["sold_by"] else ""))
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", _n(money["total"]))
        c2.metric("Paid", _n(money["paid"]))
        c3.metric("Owed now", _n(money["outstanding"]))
        if money["returned_value"] > 0:
            st.caption(f"\u21A9\uFE0F Already returned: {_n(money['returned_value'])}"
                       + (f" \u00b7 refunded: {_n(money['refunded'])}" if money["refunded"] > 0 else ""))
        if money["written_off"] > 0:
            st.warning("This sale has a written-off balance. Reverse the write-off in Bad Debts before "
                       "recording a return.")

    # ── 3. Choose goods ──
    st.markdown("#### What is being returned?")
    lines = []
    any_eligible = False
    for it in items:
        with st.container(border=True):
            st.markdown(f"**{it['product_name']}** \u2014 {_n(it['unit_price'])} each")
            st.caption(f"Sold {it['sold']:g} \u00b7 already returned {it['returned']:g} \u00b7 "
                       f"**can still return {it['eligible']:g}** {it['unit']}")
            if it["eligible"] <= 0:
                st.caption("Fully returned.")
                continue
            any_eligible = True
            qty = st.number_input(f"Quantity to return ({it['unit'] or 'units'})", min_value=0.0,
                                  max_value=float(it["eligible"]), step=1.0, value=0.0, format="%g",
                                  key=f"ret_qty_{sale['id']}_{it['sale_item_id']}")
            cond = st.selectbox("Condition of the returned goods", list(CONDITIONS),
                                format_func=lambda c: CONDITION_LABELS[c],
                                key=f"ret_cond_{sale['id']}_{it['sale_item_id']}")
            if qty > 0:
                lines.append({"sale_item_id": it["sale_item_id"], "quantity": qty, "condition": cond})
    if not any_eligible:
        st.info("Everything on this sale has already been returned.")
        _history(business_id, user_id, sale["id"])
        return

    reason = st.text_input("Reason for the return (required)", key=f"ret_reason_{sale['id']}",
                           placeholder="e.g. Wrong item, expired, customer changed mind")
    note = st.text_input("Note (optional)", key=f"ret_note_{sale['id']}")

    # ── 4. Review ──
    if not lines:
        st.caption("Enter a quantity for at least one item to see the review.")
        _history(business_id, user_id, sale["id"])
        return
    preview, err = preview_return(business_id, user_id, sale["id"], lines)
    if err:
        st.error(err)
        return

    st.markdown("#### Review")
    with st.container(border=True):
        for ln in preview["lines"]:
            where = "back to stock" if ln["condition"] == "saleable" else "damaged \u2014 NOT added to stock"
            st.markdown(f"\u2022 {ln['quantity']:g} \u00d7 {ln['product_name']} \u2014 {_n(ln['line_value'])} ({where})")
        st.markdown(f"**Value of goods returned: {_n(preview['return_value'])}**")
        if preview["debt_reduction"] > 0:
            st.info(f"The customer's balance owed goes down by {_n(preview['debt_reduction'])} "
                    f"(from {_n(preview['outstanding_before'])} to {_n(preview['outstanding_after'])}). "
                    "This is NOT a cash refund.")
        refund = preview["refund_amount"]
        method = None
        if refund > 0:
            st.warning(f"You must refund {_n(refund)} to the customer \u2014 money they have already paid.")
            method = st.selectbox("How is the refund being paid?", PAYMENT_METHODS, key=f"ret_method_{sale['id']}")
        elif preview["debt_reduction"] == 0:
            st.caption("No money changes hands for this return.")
        if any(ln["condition"] == "damaged" for ln in preview["lines"]):
            st.warning("Damaged goods are recorded but will NOT be put back into your stock.")
        st.caption("Once confirmed, the return is saved permanently with your name and cannot be edited or deleted. "
                   "The original sale stays exactly as it was.")

    # ── 5. Confirm ──
    if st.button("Confirm return", key="ret_confirm_btn", type="primary", use_container_width=True):
        if not (reason or "").strip():
            st.error("Please give a reason for the return.")
            return
        rid, msg = create_sale_return(
            business_id, user_id, user_id, sale["id"], lines, reason, method, note,
            idempotency_key=get_key(f"return_{sale['id']}"),
        )
        if rid:
            clear_key(f"return_{sale['id']}")
            for k in [k for k in st.session_state.keys() if k.startswith(f"ret_qty_{sale['id']}_")
                      or k.startswith(f"ret_cond_{sale['id']}_")
                      or k in (f"ret_reason_{sale['id']}", f"ret_note_{sale['id']}", f"ret_method_{sale['id']}")]:
                st.session_state.pop(k, None)
            st.session_state["_ret_flash"] = msg
            st.session_state["_ret_done_id"] = rid
            st.rerun()
        else:
            st.error(msg)
    _history(business_id, user_id, sale["id"])


def _history(business_id, user_id, sale_id):
    past = get_returns(business_id, user_id, sale_id=sale_id, limit=20)
    if past:
        st.markdown("#### Returns already recorded on this sale")
        for r in past:
            _render_return_record(business_id, user_id, r["id"])


def _recent_returns(business_id, user_id):
    recent = get_returns(business_id, user_id, limit=10)
    if not recent:
        return
    st.markdown("#### Recent returns")
    for r in recent:
        st.caption(
            f"Return #{r['id']} \u00b7 Sale #{r['sale_id']} \u00b7 {_n(r['return_value'])} \u00b7 "
            f"{r['created_at'].strftime('%d %b %H:%M')} \u00b7 {r['customer_name'] or 'Walk-in'}"
            + (f" \u00b7 refunded {_n(r['refund_amount'])}" if r["refund_amount"] > 0 else "")
        )
