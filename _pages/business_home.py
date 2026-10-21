from styles import render_page_header
# business_home.py — Business Mode home (Phase 1)
# List the user's businesses, let them create one, let them view one.
# No products/sales/inventory yet — that's later phases.
import streamlit as st
from datetime import date

from business import create_business, get_user_businesses, get_business, BUSINESS_TYPES
from inventory import get_inventory_summary
from customers import get_credit_summary
from sales import get_today_sales_summary, get_stock_sales_profit_summary
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

            # ── Today ────────────────────────────────────────────────────
            try:
                today = get_today_sales_summary(biz["id"], user_id)
                t1, t2 = st.columns(2)
                t1.metric("Sales Today", f"\u20A6{today['sales_today']:,.2f}")
                t2.metric("Payments Received Today", f"\u20A6{today['payments_today']:,.2f}")
                st.caption(
                    "These are sales made and cash collected \u2014 cash collected "
                    "isn't the same as sales made, since some of today's sales may "
                    "still be unpaid or partly paid."
                )
            except Exception:
                pass

            # ── Today's gross profit (stock sales only — Phase 5A-1) ───────
            try:
                profit = get_stock_sales_profit_summary(biz["id"], user_id, date.today(), date.today())
                if profit["sales_count"] > 0:
                    p1, p2 = st.columns(2)
                    p1.metric("Cost of Goods Sold Today", f"\u20A6{profit['cogs']:,.2f}")
                    p2.metric("Gross Profit Today", f"\u20A6{profit['gross_profit']:,.2f}")
                    margin_text = (
                        f"{profit['gross_margin_pct']:.1f}%" if profit["gross_margin_pct"] is not None else "n/a"
                    )
                    st.caption(f"Gross profit margin: {margin_text}. This is gross profit "
                               f"from stock sales only \u2014 not net profit, since business "
                               f"expenses aren't subtracted here.")
                    if profit["incomplete"]:
                        st.caption(
                            f"\u26A0\uFE0F {profit['lines_missing_cost']} item(s) sold today have no "
                            f"recorded cost (sold before cost tracking was added), so this figure "
                            f"may understate today's true cost and overstate profit slightly."
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

            # ── Customer credit ──────────────────────────────────────────
            try:
                credit = get_credit_summary(biz["id"], user_id)
                if credit["total_outstanding"] > 0:
                    st.caption(
                        f"\U0001F4B3 Outstanding customer credit: "
                        f"\u20A6{credit['total_outstanding']:,.2f} "
                        f"({credit['customers_owing']} customer(s)) \u2014 this is money owed to you, not profit."
                    )
            except Exception:
                pass

            # ── Treatment activity ───────────────────────────────────────
            try:
                tx = get_treatment_dashboard_summary(biz["id"], user_id)
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
                if st.button("\U0001F48A Treatments", key="goto_treatments_btn", use_container_width=True):
                    st.session_state["_pending_biz_nav"] = "Treatment Management"
                    st.rerun()

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
        submitted = st.form_submit_button("Create Business")
    if submitted:
        new_id, msg = create_business(user_id, biz_name, biz_type)
        if new_id:
            st.success(f"'{biz_name}' created!")
            st.session_state["active_business_id"] = new_id
            st.rerun()
        else:
            st.error(msg)
