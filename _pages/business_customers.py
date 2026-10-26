# _pages/business_customers.py — Business Mode: Customers / Credit (Phase 4C)
import streamlit as st

from styles import render_page_header
from customers import (
    get_customers_with_balance, get_credit_summary, get_customer,
    get_customer_sales, get_sale_items, get_sale_payments, record_payment,
    get_customer_treatments,
)
from treatments import get_treatment_payments, record_treatment_payment, STATUS_LABELS as TX_STATUS_LABELS
from sales import PAYMENT_METHODS

_STATUS_LABEL = {"paid": "Paid", "partial": "Partially Paid", "unpaid": "Unpaid / Credit"}


def render_business_customers(user_id):
    render_page_header()
    st.markdown("### \U0001F465 Customers / Credit")

    business_id = st.session_state.get("active_business_id")
    if not business_id:
        st.info("Select or create a business first, from Business Home.")
        return

    detail_id = st.session_state.get("_credit_detail_customer_id")
    if detail_id:
        _render_customer_detail(detail_id, business_id, user_id)
        return

    try:
        summary = get_credit_summary(business_id, user_id)
        customers = get_customers_with_balance(business_id, user_id)
    except Exception as _e:
        st.error("Could not load customer credit data.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Outstanding Debt", f"\u20A6{summary['total_outstanding']:,.2f}")
    c2.metric("Customers Owing", summary["customers_owing"])
    c3.metric("Open Transactions", summary["open_sales_count"] + summary["open_treatments_count"])
    st.caption(
        f"Stock-sale debt: \u20A6{summary['stock_sale_outstanding']:,.2f} "
        f"({summary['open_sales_count']} sale(s))  \u00b7  "
        f"Treatment debt: \u20A6{summary['treatment_outstanding']:,.2f} "
        f"({summary['open_treatments_count']} bill(s))"
    )
    st.caption("This is money owed to you — not profit, and not yet collected.")
    st.divider()

    if not customers:
        st.info("No customers recorded yet. Customers are added automatically when you name one during a sale.")
        return

    for c in customers:
        with st.container(border=True):
            cc1, cc2 = st.columns([3, 1])
            with cc1:
                st.markdown(f"**{c['name']}**")
                st.caption(c["phone"] or "No phone on file")
                if c["total_outstanding"] > 0:
                    st.markdown(f":red[Owes **\u20A6{c['total_outstanding']:,.2f}**]")
                    bits = []
                    if c["unpaid_sales_count"]:
                        bits.append(f"\u20A6{c['stock_sale_outstanding']:,.2f} from {c['unpaid_sales_count']} stock sale(s)")
                    if c["unpaid_treatments_count"]:
                        bits.append(f"\u20A6{c['treatment_outstanding']:,.2f} from {c['unpaid_treatments_count']} treatment(s)")
                    if bits:
                        st.caption(" \u00b7 ".join(bits))
                else:
                    st.markdown(":green[No outstanding balance]")
                if c["last_activity_at"]:
                    st.caption(f"Last activity: {c['last_activity_at'].strftime('%d %b %Y')}")
            with cc2:
                if st.button("View Details", key=f"view_cust_{c['id']}", use_container_width=True):
                    st.session_state["_credit_detail_customer_id"] = c["id"]
                    st.rerun()


def _render_customer_detail(customer_id, business_id, user_id):
    try:
        customer = get_customer(customer_id, business_id, user_id)
    except Exception as _e:
        st.error("Could not load this customer.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return
    if customer is None:
        st.session_state["_credit_detail_customer_id"] = None
        st.rerun()
        return

    if st.button("\u2190 Back to Customers", key="cust_back_btn"):
        st.session_state["_credit_detail_customer_id"] = None
        st.rerun()

    st.markdown(f"## {customer['name']}")
    st.caption(customer["phone"] or "No phone on file")

    try:
        sales = get_customer_sales(customer_id, business_id, user_id)
        tx_list = get_customer_treatments(customer_id, business_id, user_id)
    except Exception as _e:
        st.error("Could not load this customer's transactions.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    if not sales and not tx_list:
        st.caption("No transactions recorded for this customer yet.")
        return

    st.markdown("##### Stock Sales")
    if not sales:
        st.caption("No stock sales for this customer yet.")

    for sale in sales:
        with st.container(border=True):
            st.markdown(f"**Sale #{sale['id']}** \U0001F3EA Stock Sale \u2014 {sale['created_at'].strftime('%d %b %Y %H:%M')}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Total", f"\u20A6{sale['total_amount']:,.2f}")
            m2.metric("Paid", f"\u20A6{sale['amount_paid']:,.2f}")
            m3.metric("Outstanding", f"\u20A6{sale['outstanding']:,.2f}")
            st.caption(f"Status: {_STATUS_LABEL.get(sale['payment_status'], sale['payment_status'])}")

            # NOTE: deliberately NOT using st.expander for these two
            # sections. Streamlit's expander component had documented
            # content-rendering bugs introduced in its 1.47+ redesign
            # (text/content failing to display correctly), and this
            # project's requirements.txt pins an unbounded streamlit
            # version — so rather than gamble on exactly which version is
            # deployed, this uses a plain toggle button + container, which
            # has no such known issue.
            ic1, ic2 = st.columns(2)
            with ic1:
                if st.button("View items purchased", key=f"toggle_items_{sale['id']}", use_container_width=True):
                    st.session_state[f"_show_items_{sale['id']}"] = not st.session_state.get(f"_show_items_{sale['id']}", False)
            with ic2:
                if st.button("Payment history", key=f"toggle_payments_{sale['id']}", use_container_width=True):
                    st.session_state[f"_show_payments_{sale['id']}"] = not st.session_state.get(f"_show_payments_{sale['id']}", False)

            if st.session_state.get(f"_show_items_{sale['id']}", False):
                with st.container(border=True):
                    try:
                        items = get_sale_items(sale["id"], business_id, user_id)
                    except Exception as _e:
                        st.error("Could not load items.")
                        items = []
                    if not items:
                        st.caption("No items recorded for this sale.")
                    for it in items:
                        st.caption(
                            f"{it['product_name']} \u2014 {it['quantity']:g} "
                            f"@ \u20A6{it['unit_price']:,.2f} = \u20A6{it['line_total']:,.2f}"
                        )

            if st.session_state.get(f"_show_payments_{sale['id']}", False):
                with st.container(border=True):
                    try:
                        payments = get_sale_payments(sale["id"], business_id, user_id)
                    except Exception as _e:
                        st.error("Could not load payment history.")
                        payments = []
                    if not payments:
                        st.caption("No payments recorded yet.")
                    for p in payments:
                        st.caption(
                            f"\u20A6{p['amount']:,.2f} via {p['payment_method'] or 'unspecified'} "
                            f"\u2014 {p['created_at'].strftime('%d %b %Y %H:%M')}"
                            + (f" \u2014 {p['note']}" if p["note"] else "")
                        )

            if sale["outstanding"] > 0:
                if st.button("Record a payment", key=f"toggle_pay_{sale['id']}", use_container_width=True):
                    st.session_state[f"_show_pay_{sale['id']}"] = not st.session_state.get(f"_show_pay_{sale['id']}", False)

            if sale["outstanding"] > 0 and st.session_state.get(f"_show_pay_{sale['id']}", False):
                with st.container(border=True):
                    st.caption(f"Enter the amount the customer is paying now (max \u20A6{sale['outstanding']:,.2f}).")
                    pay_key = f"pay_amount_{sale['id']}"
                    pay_amount = st.number_input(
                        "Payment Amount (\u20A6)", min_value=0.0,
                        max_value=float(sale["outstanding"]),
                        value=None, step=0.01, format="%.2f",
                        placeholder="e.g. 5000", key=pay_key,
                    )
                    pay_method = st.selectbox(
                        "Payment Method", PAYMENT_METHODS, key=f"pay_method_{sale['id']}",
                    )
                    pay_note = st.text_input(
                        "Note (optional)", key=f"pay_note_{sale['id']}",
                        placeholder="e.g. Paid at shop counter",
                    )
                    processing_key = f"_paying_{sale['id']}"
                    processing = st.session_state.get(processing_key, False)
                    if st.button(
                        "Confirm Payment", key=f"confirm_pay_{sale['id']}",
                        type="primary", disabled=processing,
                    ):
                        st.session_state[processing_key] = True
                        try:
                            if not pay_amount or pay_amount <= 0:
                                st.error("Enter a payment amount greater than zero.")
                            else:
                                ok, msg = record_payment(
                                    sale["id"], business_id, user_id, user_id,
                                    pay_amount, pay_method, pay_note,
                                )
                                if ok:
                                    st.success(msg)
                                    st.session_state.pop(pay_key, None)
                                    st.session_state.pop(f"pay_note_{sale['id']}", None)
                                else:
                                    st.error(msg)
                        finally:
                            st.session_state[processing_key] = False
                        st.rerun()

    st.divider()
    st.markdown("##### Treatments")
    if not tx_list:
        st.caption("No treatments for this customer yet.")

    for tx in tx_list:
        with st.container(border=True):
            st.markdown(f"**{tx['patient_identifier']}** \U0001F48A Treatment \u2014 {tx['created_at'].strftime('%d %b %Y %H:%M')}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Bill", f"\u20A6{tx['total_bill']:,.2f}")
            m2.metric("Paid", f"\u20A6{tx['amount_paid']:,.2f}")
            m3.metric("Outstanding", f"\u20A6{tx['outstanding']:,.2f}")
            status = "paid" if tx["outstanding"] <= 0 and tx["total_bill"] > 0 else ("partial" if tx["amount_paid"] > 0 else "unpaid")
            st.caption(f"Payment status: {_STATUS_LABEL.get(status, status)}  \u00b7  "
                       f"Treatment status: {TX_STATUS_LABELS.get(tx['status'], tx['status'])}")

            if st.button("Payment history", key=f"toggle_tx_hist_{tx['id']}", use_container_width=True):
                st.session_state[f"_show_tx_hist_{tx['id']}"] = not st.session_state.get(f"_show_tx_hist_{tx['id']}", False)
            if st.session_state.get(f"_show_tx_hist_{tx['id']}", False):
                with st.container(border=True):
                    try:
                        tx_payments = get_treatment_payments(tx["id"], business_id, user_id)
                    except Exception as _e:
                        st.error("Could not load payment history.")
                        tx_payments = []
                    if not tx_payments:
                        st.caption("No payments recorded yet.")
                    for p in tx_payments:
                        st.caption(
                            f"\u20A6{p['amount']:,.2f} via {p['payment_method'] or 'unspecified'} "
                            f"\u2014 {p['created_at'].strftime('%d %b %Y %H:%M')}"
                            + (f" \u2014 {p['note']}" if p["note"] else "")
                        )

            if tx["outstanding"] > 0:
                if st.button("Record a payment", key=f"toggle_tx_pay2_{tx['id']}", use_container_width=True):
                    st.session_state[f"_show_tx_pay2_{tx['id']}"] = not st.session_state.get(f"_show_tx_pay2_{tx['id']}", False)

            if tx["outstanding"] > 0 and st.session_state.get(f"_show_tx_pay2_{tx['id']}", False):
                with st.container(border=True):
                    st.caption(f"Enter the amount being paid now (max \u20A6{tx['outstanding']:,.2f}).")
                    pay_key = f"tx_pay2_amount_{tx['id']}"
                    pay_amount = st.number_input(
                        "Payment Amount (\u20A6)", min_value=0.0,
                        max_value=float(tx["outstanding"]),
                        value=None, step=0.01, format="%.2f",
                        placeholder="e.g. 5000", key=pay_key,
                    )
                    pay_method = st.selectbox(
                        "Payment Method", PAYMENT_METHODS, key=f"tx_pay2_method_{tx['id']}",
                    )
                    pay_note = st.text_input(
                        "Note (optional)", key=f"tx_pay2_note_{tx['id']}",
                        placeholder="e.g. Paid at shop counter",
                    )
                    processing_key = f"_tx_paying2_{tx['id']}"
                    processing = st.session_state.get(processing_key, False)
                    if st.button(
                        "Confirm Payment", key=f"tx_confirm_pay2_{tx['id']}",
                        type="primary", disabled=processing,
                    ):
                        st.session_state[processing_key] = True
                        try:
                            if not pay_amount or pay_amount <= 0:
                                st.error("Enter a payment amount greater than zero.")
                            else:
                                ok, msg = record_treatment_payment(
                                    tx["id"], business_id, user_id, user_id,
                                    pay_amount, pay_method, pay_note,
                                )
                                if ok:
                                    st.success(msg)
                                    st.session_state.pop(pay_key, None)
                                    st.session_state.pop(f"tx_pay2_note_{tx['id']}", None)
                                else:
                                    st.error(msg)
                        finally:
                            st.session_state[processing_key] = False
                        st.rerun()
