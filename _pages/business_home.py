from styles import render_page_header
# business_home.py — Business Mode home (Phase 1)
# List the user's businesses, let them create one, let them view one.
# No products/sales/inventory yet — that's later phases.
import streamlit as st
from datetime import date

from business import (
    create_business, get_user_businesses, get_business, BUSINESS_TYPES,
    set_treatment_management, PHARMACY_TYPE,
    TREATMENT_SETTING_HELP_PHARMACY, TREATMENT_SETTING_HELP_OTHER,
)
from inventory import get_inventory_summary
from customers import get_credit_summary
from daily_report import get_cash_basis_report, business_today
from treatments import get_treatment_dashboard_summary


def render_business_home(user_id):
    render_page_header()
    st.markdown("### \U0001F3EA Business Mode")

    try:
        businesses = get_user_businesses(user_id)
    except Exception as _e:
        # Most likely cause: the `businesses` table migration hasn't run
        # yet in this server process. models.create_tables() is cached
        # with @st.cache_resource — it only runs once per process, so a
        # plain code deploy doesn't always force it to re-run. A full
        # reboot (Manage app -> Reboot) restarts the process and runs it.
        st.error(
            "Business Mode isn't fully set up on this server yet. "
            "Try rebooting the app (Manage app -> Reboot) — if this "
            "persists after that, something else is wrong."
        )
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    # ── If a business is selected, show its (minimal, Phase 1) detail view ────
    active_id = st.session_state.get("active_business_id")
    if active_id:
        biz = get_business(active_id, user_id)  # re-checks ownership every time
        if biz is None:
            # Either deleted, or didn't belong to this user — don't trust the
            # stale id sitting in session_state.
            st.session_state["active_business_id"] = None
            st.rerun()
        else:
            if st.button("\u2190 Back to all businesses", key="biz_back_btn"):
                st.session_state["active_business_id"] = None
                st.rerun()
            st.markdown(f"## {biz['business_name']}")
            st.caption(biz["business_type"] or "No category set")

            # ── Today, cash basis (Phase 5A-5) ──────────────────────────────
            # Only money actually received counts as revenue or profit.
            # Invoice value (sales made on credit) is shown separately as
            # activity. Full breakdown: End-of-Day Summary.
            try:
                today_lagos = business_today()
                rep = get_cash_basis_report(biz["id"], user_id, today_lagos, today_lagos)
                if rep["sales_count"] > 0 or rep["treatments_started"] > 0 or rep["money_collected_total"] > 0:
                    t1, t2 = st.columns(2)
                    t1.metric("Money Collected Today", f"\u20A6{rep['money_collected_total']:,.2f}")
                    t2.metric("Realised Revenue Today", f"\u20A6{rep['realised_operating_revenue']:,.2f}")
                    p1, p2 = st.columns(2)
                    p1.metric("Cost of Goods (on money collected)", f"\u20A6{rep['cogs_on_collected']:,.2f}")
                    p2.metric("Realised Gross Profit Today", f"\u20A6{rep['realised_gross_profit']:,.2f}")
                    _tx_part = (
                        f" \u00b7 Treatment bills today: \u20A6{rep['treatment_activity']:,.2f}"
                        if (biz["treatment_management_enabled"] or rep["treatment_activity"] > 0) else ""
                    )
                    st.caption(
                        f"Sales made today (including unpaid): \u20A6{rep['sales_activity']:,.2f}"
                        f"{_tx_part}. Unpaid amounts are not counted as revenue or profit."
                    )
                    if rep["recoveries"] > 0:
                        st.caption(
                            f"Also received today: \u20A6{rep['recoveries']:,.2f} recovered from "
                            f"written-off debts (not counted in revenue or profit)."
                        )
                    st.caption(
                        "This is gross profit, not net profit \u2014 business expenses aren't "
                        "subtracted. See End-of-Day Summary for the full report."
                    )
                    if rep["profit_incomplete"]:
                        st.caption(
                            "\u26A0\uFE0F Some money collected today is for items with no recorded "
                            "cost (sold before cost tracking), so profit is incomplete."
                        )
            except Exception:
                pass

            # ── Inventory alerts ─────────────────────────────────────────
            try:
                summary = get_inventory_summary(biz["id"], user_id)
                c1, c2, c3 = st.columns(3)
                c1.metric("Products", summary["total_products"])
                c2.metric("Low Stock", summary["low_stock"])
                c3.metric("Out of Stock", summary["out_of_stock"])
                if summary["expiring_soon"] or summary["expired"]:
                    e1, e2 = st.columns(2)
                    e1.metric("Expiring Soon", summary["expiring_soon"])
                    e2.metric("Expired", summary["expired"])
                st.caption(f"Estimated inventory value: \u20A6{summary['inventory_value']:,.2f}")
            except Exception:
                # Non-fatal here — if inventory tables aren't ready yet,
                # the business profile itself still renders fine; the
                # Products page below will show the real error if the
                # person follows the link.
                pass

            # ── Customer credit (combined stock-sale + treatment — 5A-3) ───
            try:
                credit = get_credit_summary(biz["id"], user_id)
                if credit["total_outstanding"] > 0:
                    st.caption(
                        f"\U0001F4B3 Outstanding customer credit: "
                        f"\u20A6{credit['total_outstanding']:,.2f} "
                        f"({credit['customers_owing']} customer(s)) \u2014 this is money owed to you, not profit."
                    )
                    st.caption(
                        f"\u20A6{credit['stock_sale_outstanding']:,.2f} from stock sales, "
                        f"\u20A6{credit['treatment_outstanding']:,.2f} from treatments"
                    )
            except Exception:
                pass

            # ── Treatment activity (only when the feature is on) ─────────
            try:
                tx = get_treatment_dashboard_summary(biz["id"], user_id) if biz["treatment_management_enabled"] else {"total_treatments": 0}
                if tx["total_treatments"] > 0:
                    st.caption(
                        f"\U0001F48A Treatments: {tx['in_progress']} in progress, "
                        f"{tx['scheduled']} scheduled, {tx['completed']} completed"
                    )
            except Exception:
                pass

            st.divider()
            nav_r1c1, nav_r1c2 = st.columns(2)
            with nav_r1c1:
                if st.button("\U0001F4E6 Products & Inventory", key="goto_inventory_btn", use_container_width=True):
                    st.session_state["_pending_biz_nav"] = "Products / Inventory"
                    st.rerun()
            with nav_r1c2:
                if st.button("\U0001F6D2 Sales / POS", key="goto_sales_btn", use_container_width=True):
                    st.session_state["_pending_biz_nav"] = "Sales / Point of Sale"
                    st.rerun()
            nav_r2c1, nav_r2c2 = st.columns(2)
            with nav_r2c1:
                if st.button("\U0001F465 Customers / Credit", key="goto_customers_btn", use_container_width=True):
                    st.session_state["_pending_biz_nav"] = "Customers / Credit"
                    st.rerun()
            with nav_r2c2:
                if biz["treatment_management_enabled"]:
                    if st.button("\U0001F48A Treatments", key="goto_treatments_btn", use_container_width=True):
                        st.session_state["_pending_biz_nav"] = "Treatment Management"
                        st.rerun()

            # ── Settings (Phase 5B-1) ────────────────────────────────────
            st.divider()
            st.markdown("##### \u2699\uFE0F Settings")
            is_pharmacy = biz["business_type"] == PHARMACY_TYPE
            tm_value = st.checkbox(
                "Treatment Management",
                value=bool(biz["treatment_management_enabled"]),
                help=TREATMENT_SETTING_HELP_PHARMACY if is_pharmacy else TREATMENT_SETTING_HELP_OTHER,
                key=f"tm_toggle_{biz['id']}",
            )
            st.caption(TREATMENT_SETTING_HELP_PHARMACY if is_pharmacy else TREATMENT_SETTING_HELP_OTHER)
            if tm_value != bool(biz["treatment_management_enabled"]):
                if st.button("Save setting", key=f"tm_save_{biz['id']}", type="primary"):
                    ok, msg = set_treatment_management(biz["id"], user_id, tm_value)
                    if ok:
                        st.session_state["_tm_flash"] = msg
                        st.rerun()
                    else:
                        st.error(msg)
                if not tm_value:
                    st.caption("Turning this off hides treatment screens. Your existing treatment records, payments and debts are kept.")
            _flash = st.session_state.pop("_tm_flash", None)
            if _flash:
                st.success(_flash)

            st.caption(f"Created {biz['created_at'].strftime('%d %b %Y')}")
        return

    # ── Otherwise: list of businesses + create form ────────────────────────────
    if businesses:
        st.caption(f"{len(businesses)} business{'es' if len(businesses) != 1 else ''}")
        for biz in businesses:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**\U0001F3EA {biz['business_name']}**")
                    st.caption(biz["business_type"] or "No category set")
                with c2:
                    if st.button("Open", key=f"open_biz_{biz['id']}", use_container_width=True):
                        st.session_state["active_business_id"] = biz["id"]
                        st.rerun()
    else:
        st.info("You haven't created a business yet. Add your first one below.")

    st.divider()
    st.markdown("#### \u2795 Add a Business")
    with st.form("create_business_form"):
        biz_name = st.text_input("Business name", placeholder="e.g. My Pharmacy")
        biz_type = st.selectbox("Business type", BUSINESS_TYPES)
        # Phase 5B-1: only pharmacies are offered Treatment Management at
        # creation (pre-ticked). Every other type starts with it OFF; the
        # owner can still enable it later under Settings.
        tm_new = st.checkbox(
            "Enable Treatment Management (pharmacies only)",
            value=True,
            help=TREATMENT_SETTING_HELP_PHARMACY,
            key="create_tm_checkbox",
        )
        st.caption(
            TREATMENT_SETTING_HELP_PHARMACY
            + " Ignored for other business types."
        )
        submitted = st.form_submit_button("Create Business")
    if submitted:
        new_id, msg = create_business(
            user_id, biz_name, biz_type,
            treatment_management_enabled=(tm_new if biz_type == PHARMACY_TYPE else False),
        )
        if new_id:
            st.success(f"'{biz_name}' created!")
            st.session_state["active_business_id"] = new_id
            st.rerun()
        else:
            st.error(msg)
