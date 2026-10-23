# _pages/business_treatments.py — Business Mode: Treatment Management (Phase 4D)
import streamlit as st
from datetime import date

from styles import render_page_header
from inventory import get_products
from treatments import (
    create_treatment, get_treatments, get_treatment, get_treatment_items,
    get_dispensing_history, get_treatment_dashboard_summary,
    update_treatment_status, record_dispensing,
    get_treatment_billing, record_treatment_payment, get_treatment_payments,
    ROUTES, STATUSES, STATUS_LABELS,
)
from sales import PAYMENT_METHODS

_BILLING_STATUS_LABELS = {"paid": "Paid", "partial": "Partially Paid", "unpaid": "Unpaid"}

# NOTE: this page deliberately avoids st.expander for the same reason as
# business_customers.py — a documented Streamlit rendering bug in that
# component — using toggle buttons + plain containers instead.


def render_business_treatments(user_id):
    render_page_header()
    st.markdown("### \U0001F48A Treatment Management")

    business_id = st.session_state.get("active_business_id")
    if not business_id:
        st.info("Select or create a business first, from Business Home.")
        return

    detail_id = st.session_state.get("_treatment_detail_id")
    if detail_id:
        _render_treatment_detail(detail_id, business_id, user_id)
        return

    try:
        summary = get_treatment_dashboard_summary(business_id, user_id)
    except Exception as _e:
        st.error("Could not load treatment data.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", summary["total_treatments"])
    c2.metric("In Progress", summary["in_progress"])
    c3.metric("Completed", summary["completed"])
    c4.metric("Scheduled", summary["scheduled"])
    st.divider()

    if st.button("\u2795 Add New Treatment", key="show_add_treatment_btn", use_container_width=True):
        st.session_state["_show_add_treatment"] = not st.session_state.get("_show_add_treatment", False)

    if st.session_state.get("_show_add_treatment", False):
        _render_add_treatment_form(business_id, user_id)

    st.divider()

    st.markdown("##### Treatments")
    filter_status = st.selectbox(
        "Filter by status", ["All"] + [STATUS_LABELS[s] for s in STATUSES],
        key="treatment_status_filter",
    )
    status_filter = None
    if filter_status != "All":
        status_filter = {v: k for k, v in STATUS_LABELS.items()}[filter_status]

    try:
        treatments = get_treatments(business_id, user_id, status_filter)
    except Exception as _e:
        st.error("Could not load treatments.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    if not treatments:
        st.caption("No treatments recorded yet.")
        return

    for t in treatments:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{t['patient_identifier']}**")
                if t["patient_phone"]:
                    st.caption(f"\U0001F4DE {t['patient_phone']}")
                if t["diagnosis"]:
                    st.caption(f"Condition: {t['diagnosis']}")
                st.caption(f"Started {t['start_date'].strftime('%d %b %Y')}" + (
                    f" \u2014 {t['duration_days']} day(s)" if t["duration_days"] else " \u2014 duration not set"
                ))
                st.caption(f"Drugs used: {t['drug_names'] or 'None added'}")
                st.caption(f"Status: {STATUS_LABELS.get(t['status'], t['status'])}")
            with c2:
                if st.button("View", key=f"view_treatment_{t['id']}", use_container_width=True):
                    st.session_state["_treatment_detail_id"] = t["id"]
                    st.rerun()


def _render_add_treatment_form(business_id, user_id):
    try:
        products = get_products(business_id, user_id)
    except Exception as _e:
        st.error("Could not load products.")
        return
    if not products:
        st.warning("No products in inventory yet. Add products first, in Products / Inventory.")
        return
    product_lookup = {p["id"]: p for p in products}

    st.markdown("##### Add New Treatment")

    st.markdown("###### Patient Information")
    patient_identifier = st.text_input(
        "Patient Name", placeholder="e.g. John Okafor, or Patient 001",
        help="Enter the patient's full name, or an identifier if you'd rather not record a name.",
        key="tx_patient",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        tx_phone = st.text_input(
            "Phone Number (optional)", placeholder="e.g. 08012345678",
            help="Optional: for contact purposes.", key="tx_phone",
        )
    with col_b:
        start_date = st.date_input(
            "Treatment Date", value=date.today(),
            help="Select the date this treatment begins.", key="tx_start_date",
        )
    tx_diagnosis = st.text_input(
        "Condition / Diagnosis Being Treated (optional)",
        placeholder="e.g. Malaria, Typhoid, Wound dressing",
        help="Record the condition already determined by a qualified person. "
             "This field does not diagnose or suggest anything — it just documents it.",
        key="tx_diagnosis",
    )
    tx_duration = st.number_input(
        "Treatment Duration (days)", min_value=0, value=None, step=1,
        placeholder="e.g. 3",
        help="How many days the treatment is scheduled to last.", key="tx_duration",
    )
    tx_notes = st.text_area(
        "Treatment Notes (optional)", placeholder="Relevant administrative notes.",
        key="tx_notes",
    )
    tx_service_charge = st.number_input(
        "Service Charge (\u20A6, optional)", min_value=0.0, value=None, step=0.01, format="%.2f",
        placeholder="e.g. 2000",
        help="A flat consultation/service fee, separate from any medicines used. "
             "Leave blank if you only bill for medicines dispensed.",
        key="tx_service_charge",
    )

    st.divider()
    st.markdown("###### Products and Medicines Used")
    st.caption("Add each product used in this treatment, with its already-established instructions.")

    draft = st.session_state.setdefault("_tx_items_draft", [])

    def _fmt(pid):
        p = product_lookup[pid]
        return f"{p['name']} ({p['unit']}) \u2014 {p['current_stock']:g} available"

    pcol1, pcol2 = st.columns(2)
    with pcol1:
        item_product_id = st.selectbox(
            "Product", list(product_lookup.keys()), format_func=_fmt,
            help="Select a medicine or product already registered in this business's inventory.",
            key="tx_item_product",
        )
    with pcol2:
        item_route = st.selectbox("Route / Method", ROUTES, key="tx_item_route")

    qcol1, qcol2, qcol3 = st.columns(3)
    with qcol1:
        item_qty = st.number_input(
            "Quantity per Administration", min_value=0.0, value=None, step=0.5, format="%.3f",
            placeholder="e.g. 1",
            help="Quantity used each time this item is administered.", key="tx_item_qty",
        )
    with qcol2:
        item_admins = st.number_input(
            "Administrations per Day", min_value=0.0, value=None, step=1.0, format="%.2f",
            placeholder="e.g. 2",
            help="Number of times per day per the approved instructions.", key="tx_item_admins",
        )
    with qcol3:
        item_days = st.number_input(
            "Duration (days)", min_value=0, value=None, step=1,
            placeholder="e.g. 3",
            help="Number of days this item is scheduled to be used.", key="tx_item_days",
        )
    item_notes = st.text_input("Item Notes (optional)", key="tx_item_notes")

    if item_qty and item_admins and item_days:
        planned = item_qty * item_admins * item_days
        st.caption(f"Planned quantity: **{planned:g} {product_lookup[item_product_id]['unit']}** "
                   f"({item_qty:g} \u00d7 {item_admins:g} \u00d7 {item_days:g})")

    if st.button("Add Another Product", key="add_tx_item_btn", use_container_width=True):
        if not item_qty or item_qty <= 0:
            st.error("Enter a quantity per administration greater than zero.")
        else:
            p = product_lookup[item_product_id]
            draft.append({
                "product_id": item_product_id, "product_name": p["name"], "unit": p["unit"],
                "quantity_per_administration": item_qty,
                "administrations_per_day": item_admins,
                "duration_days": int(item_days) if item_days else None,
                "route": item_route, "notes": item_notes or None,
            })
            st.session_state["_tx_items_draft"] = draft
            st.rerun()

    if draft:
        st.markdown("**Items added so far:**")
        for i, it in enumerate(draft):
            with st.container(border=True):
                dcol1, dcol2 = st.columns([4, 1])
                with dcol1:
                    st.markdown(f"**{it['product_name']}** ({it['unit']}) \u2014 {it['route']}")
                    bits = [f"{it['quantity_per_administration']:g} per administration"]
                    if it["administrations_per_day"]:
                        bits.append(f"{it['administrations_per_day']:g}/day")
                    if it["duration_days"]:
                        bits.append(f"{it['duration_days']} day(s)")
                    st.caption(" \u00b7 ".join(bits))
                with dcol2:
                    if st.button("Remove", key=f"remove_tx_item_{i}", use_container_width=True):
                        draft.pop(i)
                        st.session_state["_tx_items_draft"] = draft
                        st.rerun()

    st.divider()
    processing = st.session_state.get("_tx_processing", False)
    if st.button("Create Treatment", key="create_treatment_btn", type="primary",
                 use_container_width=True, disabled=processing):
        st.session_state["_tx_processing"] = True
        try:
            if not draft:
                st.error("Add at least one product before creating the treatment.")
            else:
                treatment_id, msg = create_treatment(
                    business_id, user_id, user_id, patient_identifier, tx_phone,
                    tx_diagnosis, start_date,
                    int(tx_duration) if tx_duration else None, tx_notes, draft,
                    tx_service_charge or 0,
                )
                if treatment_id:
                    st.success(msg)
                    st.session_state["_tx_items_draft"] = []
                    st.session_state["_show_add_treatment"] = False
                    for k in ["tx_patient", "tx_phone", "tx_diagnosis", "tx_duration",
                              "tx_notes", "tx_item_notes", "tx_service_charge"]:
                        st.session_state.pop(k, None)
                else:
                    st.error(msg)
        finally:
            st.session_state["_tx_processing"] = False
        st.rerun()


def _render_treatment_detail(treatment_id, business_id, user_id):
    try:
        treatment = get_treatment(treatment_id, business_id, user_id)
    except Exception as _e:
        st.error("Could not load this treatment.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return
    if treatment is None:
        st.session_state["_treatment_detail_id"] = None
        st.rerun()
        return

    if st.button("\u2190 Back to Treatments", key="tx_back_btn"):
        st.session_state["_treatment_detail_id"] = None
        st.rerun()

    st.markdown(f"## {treatment['patient_identifier']}")
    if treatment["patient_phone"]:
        st.caption(f"\U0001F4DE {treatment['patient_phone']}")
    if treatment["diagnosis"]:
        st.caption(f"**Condition:** {treatment['diagnosis']}")
    st.caption(f"Started {treatment['start_date'].strftime('%d %b %Y')}" + (
        f" \u2014 planned {treatment['duration_days']} day(s)" if treatment["duration_days"] else " \u2014 duration not set"
    ))
    st.markdown(f"**Status:** {STATUS_LABELS.get(treatment['status'], treatment['status'])}")
    if treatment["notes"]:
        st.caption(f"Notes: {treatment['notes']}")

    # Status changes — always an explicit action, never date-driven.
    status = treatment["status"]
    if status in ("planned", "in_progress"):
        sc1, sc2 = st.columns(2)
        with sc1:
            if status == "planned" and st.button("Start Treatment", key="start_tx_btn", use_container_width=True):
                ok, msg = update_treatment_status(treatment_id, business_id, user_id, "in_progress")
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
            if status == "in_progress" and st.button("Mark Completed", key="complete_tx_btn", use_container_width=True):
                ok, msg = update_treatment_status(treatment_id, business_id, user_id, "completed")
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
        with sc2:
            if st.button("Cancel Treatment", key="cancel_tx_btn", use_container_width=True):
                ok, msg = update_treatment_status(treatment_id, business_id, user_id, "cancelled")
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

    st.divider()
    st.markdown("##### Billing")
    try:
        billing = get_treatment_billing(treatment_id, business_id, user_id)
    except Exception as _e:
        st.error("Could not load billing for this treatment.")
        billing = None

    if billing:
        b1, b2, b3 = st.columns(3)
        b1.metric("Total Bill", f"\u20A6{billing['total_bill']:,.2f}")
        b2.metric("Paid", f"\u20A6{billing['amount_paid']:,.2f}")
        b3.metric("Outstanding", f"\u20A6{billing['outstanding']:,.2f}")
        st.caption(
            f"Status: {_BILLING_STATUS_LABELS.get(billing['payment_status'], billing['payment_status'])} "
            f"\u2014 service charge \u20A6{billing['service_charge']:,.2f} + "
            f"medicines/supplies \u20A6{billing['dispensed_charges']:,.2f}"
        )
        if billing["incomplete"]:
            st.caption(
                f"\u26A0\uFE0F {billing['lines_missing_price']} dispensing record(s) predate billing "
                f"and aren't included above \u2014 this bill may understate what's actually owed."
            )

        if billing["outstanding"] > 0:
            if st.button("Record a payment", key="toggle_tx_pay", use_container_width=True):
                st.session_state["_show_tx_pay"] = not st.session_state.get("_show_tx_pay", False)
            if st.session_state.get("_show_tx_pay", False):
                with st.container(border=True):
                    st.caption(f"Enter the amount being paid now (max \u20A6{billing['outstanding']:,.2f}).")
                    pay_amount = st.number_input(
                        "Payment Amount (\u20A6)", min_value=0.0, max_value=float(billing["outstanding"]),
                        value=None, step=0.01, format="%.2f", placeholder="e.g. 5000",
                        key="tx_pay_amount",
                    )
                    pay_method = st.selectbox("Payment Method", PAYMENT_METHODS, key="tx_pay_method")
                    pay_note = st.text_input("Note (optional)", key="tx_pay_note")
                    processing = st.session_state.get("_tx_paying", False)
                    if st.button("Confirm Payment", key="confirm_tx_pay", type="primary", disabled=processing):
                        st.session_state["_tx_paying"] = True
                        try:
                            ok, msg = record_treatment_payment(
                                treatment_id, business_id, user_id, user_id,
                                pay_amount, pay_method, pay_note,
                            )
                            if ok:
                                st.success(msg)
                                st.session_state.pop("tx_pay_amount", None)
                                st.session_state.pop("tx_pay_note", None)
                            else:
                                st.error(msg)
                        finally:
                            st.session_state["_tx_paying"] = False
                        st.rerun()

        if st.button("Payment history", key="toggle_tx_pay_hist", use_container_width=True):
            st.session_state["_show_tx_pay_hist"] = not st.session_state.get("_show_tx_pay_hist", False)
        if st.session_state.get("_show_tx_pay_hist", False):
            with st.container(border=True):
                try:
                    payments = get_treatment_payments(treatment_id, business_id, user_id)
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

    st.divider()
    st.markdown("##### Products and Medicines")

    try:
        items = get_treatment_items(treatment_id, business_id, user_id)
    except Exception as _e:
        st.error("Could not load treatment items.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    for it in items:
        with st.container(border=True):
            st.markdown(f"**{it['product_name']}** ({it['product_unit']}) \u2014 {it['route'] or 'Route not specified'}")
            bits = [f"{it['quantity_per_administration']:g} per administration"]
            if it["administrations_per_day"]:
                bits.append(f"{it['administrations_per_day']:g}/day")
            if it["duration_days"]:
                bits.append(f"{it['duration_days']} day(s)")
            st.caption(" \u00b7 ".join(bits))
            if it["planned_quantity"]:
                st.caption(f"Planned quantity: {it['planned_quantity']:g} {it['product_unit']}")
            st.caption(f"Dispensed so far: **{it['quantity_dispensed']:g} {it['product_unit']}**")
            if it["notes"]:
                st.caption(f"Note: {it['notes']}")

            dcol1, dcol2 = st.columns(2)
            with dcol1:
                if st.button("Record Dispensing", key=f"toggle_dispense_{it['id']}", use_container_width=True):
                    st.session_state[f"_show_dispense_{it['id']}"] = not st.session_state.get(f"_show_dispense_{it['id']}", False)
            with dcol2:
                if st.button("Dispensing History", key=f"toggle_disp_hist_{it['id']}", use_container_width=True):
                    st.session_state[f"_show_disp_hist_{it['id']}"] = not st.session_state.get(f"_show_disp_hist_{it['id']}", False)

            if st.session_state.get(f"_show_dispense_{it['id']}", False):
                with st.container(border=True):
                    st.caption(f"Available stock: {it['product_current_stock']:g} {it['product_unit']}")
                    dispense_qty = st.number_input(
                        "Quantity to dispense", min_value=0.0, value=None, step=0.5, format="%.3f",
                        placeholder="e.g. 10", key=f"dispense_qty_{it['id']}",
                    )
                    dispense_note = st.text_input(
                        "Note (optional)", key=f"dispense_note_{it['id']}",
                        placeholder="e.g. Day 1 dose issued",
                    )
                    proc_key = f"_dispensing_{it['id']}"
                    processing = st.session_state.get(proc_key, False)
                    if st.button("Confirm Dispensing", key=f"confirm_dispense_{it['id']}",
                                 type="primary", disabled=processing):
                        st.session_state[proc_key] = True
                        try:
                            ok, msg = record_dispensing(
                                it["id"], business_id, user_id, user_id,
                                dispense_qty, dispense_note,
                            )
                            if ok:
                                st.success(msg)
                                st.session_state.pop(f"dispense_qty_{it['id']}", None)
                                st.session_state.pop(f"dispense_note_{it['id']}", None)
                            else:
                                st.error(msg)
                        finally:
                            st.session_state[proc_key] = False
                        st.rerun()

            if st.session_state.get(f"_show_disp_hist_{it['id']}", False):
                with st.container(border=True):
                    try:
                        history = get_dispensing_history(it["id"], business_id, user_id)
                    except Exception as _e:
                        st.error("Could not load dispensing history.")
                        history = []
                    if not history:
                        st.caption("No dispensing recorded yet for this item.")
                    for h in history:
                        st.caption(
                            f"{h['quantity']:g} {it['product_unit']} \u2014 "
                            f"{h['dispensed_at'].strftime('%d %b %Y %H:%M')}"
                            + (f" \u2014 by {h['recorded_by_username']}" if h["recorded_by_username"] else "")
                        )
