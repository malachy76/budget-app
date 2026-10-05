# _pages/business_inventory.py — Business Mode: Products / Inventory (Phase 2)
import streamlit as st
from datetime import date

from styles import render_page_header
from inventory import (
    create_product, get_products, get_product, adjust_stock,
    get_movement_history, get_inventory_summary, stock_status, expiry_status,
    UNITS, ADD_REASONS, REMOVE_REASONS,
)

_STATUS_LABEL = {
    "IN_STOCK": "In Stock",
    "LOW_STOCK": "Low Stock",
    "OUT_OF_STOCK": "Out of Stock",
}
_EXPIRY_LABEL = {
    "EXPIRED": "Expired",
    "EXPIRING_SOON": "Expiring soon",
}


def render_business_inventory(user_id):
    render_page_header()
    st.markdown("### \U0001F4E6 Products / Inventory")

    business_id = st.session_state.get("active_business_id")
    if not business_id:
        st.info("Select or create a business first, from Business Home.")
        return

    try:
        summary = get_inventory_summary(business_id, user_id)
    except Exception as _e:
        st.error("Could not load inventory. Try rebooting the app if this persists.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Products", summary["total_products"])
    c2.metric("In Stock", summary["in_stock"])
    c3.metric("Low Stock", summary["low_stock"])
    c4.metric("Out of Stock", summary["out_of_stock"])
    st.caption(f"Estimated inventory cost: \u20A6{summary['inventory_value']:,.2f}")
    st.divider()

    # ── Detail view (adjust stock / history) takes over the whole page ────────
    detail_id = st.session_state.get("_inv_detail_product_id")
    if detail_id:
        _render_product_detail(detail_id, business_id, user_id)
        return

    # ── Add product ─────────────────────────────────────────────────────────
    with st.expander("\u2795 Add Product", expanded=True):
        st.caption(
            "Enter the product details below. Each field explains what you should enter."
        )
        with st.form("add_product_form"):
            name = st.text_input(
                "Product name",
                placeholder="e.g. Paracetamol 500mg",
                help="Enter the name customers will recognize. Include the strength or size when useful.",
            )

            col_a, col_b = st.columns(2)

            with col_a:
                category = st.text_input(
                    "Category",
                    placeholder="e.g. Pain Relief",
                    help="Group the product so you can identify similar items easily. Example: Pain Relief, Antibiotics, Drinks.",
                )

                unit = st.selectbox(
                    "Unit of measurement",
                    UNITS,
                    help="Choose how you count or measure this product: piece, pack, bottle, tablet, litre, etc.",
                )

                purchase_price = st.number_input(
                    "Purchase price per unit (\u20a6)",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    help="Enter how much your business paid for ONE unit of this product.",
                )

                opening_stock = st.number_input(
                    "Opening stock / quantity currently available",
                    min_value=0.0,
                    step=0.5,
                    format="%.3f",
                    help="Enter how many units you currently have before you start recording stock movements. Example: 100 tablets or 1.5 litres.",
                )

            with col_b:
                sku = st.text_input(
                    "SKU / product code (optional)",
                    placeholder="e.g. PCM500-001",
                    help="Optional internal code used to identify the product. Leave this blank if you do not use product codes.",
                )

                selling_price = st.number_input(
                    "Selling price per unit (\u20a6)",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    help="Enter the normal selling price for ONE unit of this product.",
                )

                low_stock_threshold = st.number_input(
                    "Low-stock alert level",
                    min_value=0.0,
                    step=0.5,
                    format="%.3f",
                    help="When stock falls to this number or below, Budget Right will show Low Stock. Example: enter 10 to be warned when only 10 units remain.",
                )

                has_expiry = st.checkbox(
                    "This product has an expiry date",
                    help="Tick this if the product expires. Budget Right will then show Expired or Expiring soon when appropriate.",
                )

                expiry_date = (
                    st.date_input(
                        "Expiry date",
                        min_value=date.today(),
                        help="Enter the date printed on the product. Example: 31 Dec 2027.",
                    )
                    if has_expiry
                    else None
                )

            st.caption(
                "Tip: Purchase price and selling price are per unit. Opening stock is the quantity you have right now."
            )
            submitted = st.form_submit_button(
                "Create Product",
                use_container_width=True,
                type="primary",
            )
        if submitted:
            product_id, msg = create_product(
                business_id, user_id, user_id, name, category, sku, unit,
                purchase_price, selling_price, opening_stock, low_stock_threshold,
                expiry_date,
            )
            if product_id:
                st.success(f"'{name}' added.")
                st.rerun()
            else:
                st.error(msg)

    st.divider()

    # ── Product list ────────────────────────────────────────────────────────
    try:
        products = get_products(business_id, user_id)
    except Exception as _e:
        st.error("Could not load products.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    if not products:
        st.info("No products yet. Add your first one above.")
        return

    for p in products:
        status = stock_status(p)
        exp_stat = expiry_status(p)

        with st.container(border=True):
            st.markdown(f"**{p['name']}**")
            st.caption(p["category"] or "No category")
            m1, m2 = st.columns(2)
            with m1:
                st.markdown(f"Stock: **{p['current_stock']:g} {p['unit']}**")
                st.markdown(f"Selling: **\u20A6{p['selling_price']:,.2f}**")
            with m2:
                if status == "IN_STOCK":
                    st.markdown(f":green[**{_STATUS_LABEL[status]}**]")
                else:
                    st.markdown(f":red[**{_STATUS_LABEL[status]}**]")
                if exp_stat == "EXPIRED":
                    st.markdown(f":red[{_EXPIRY_LABEL[exp_stat]}]")
                elif exp_stat == "EXPIRING_SOON":
                    st.markdown(f":orange[{_EXPIRY_LABEL[exp_stat]}]")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Adjust Stock", key=f"adj_{p['id']}", use_container_width=True):
                    st.session_state["_inv_detail_product_id"] = p["id"]
                    st.rerun()
            with b2:
                if st.button("View History", key=f"hist_{p['id']}", use_container_width=True):
                    st.session_state["_inv_detail_product_id"] = p["id"]
                    st.rerun()


def _render_product_detail(product_id, business_id, user_id):
    try:
        product = get_product(product_id, business_id, user_id)
    except Exception as _e:
        st.error("Could not load this product.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return
    if product is None:
        # Deleted, or never belonged to this business/user — don't trust
        # the stale id sitting in session_state.
        st.session_state["_inv_detail_product_id"] = None
        st.rerun()
        return

    if st.button("\u2190 Back to Products", key="inv_back_btn"):
        st.session_state["_inv_detail_product_id"] = None
        st.rerun()

    st.markdown(f"## {product['name']}")
    st.caption(product["category"] or "No category")
    st.markdown(f"Current stock: **{product['current_stock']:g} {product['unit']}**")

    t1, t2 = st.tabs(["Adjust Stock", "History"])

    with t1:
        direction = st.radio("Action", ["Add stock", "Remove stock"], key="adj_direction", horizontal=True)
        reasons = ADD_REASONS if direction == "Add stock" else REMOVE_REASONS
        reason = st.selectbox("Reason", list(reasons.keys()), key="adj_reason")
        qty = st.number_input("Quantity", min_value=0.0, step=0.5, format="%.3f", key="adj_qty")
        if st.button("Confirm Adjustment", key="adj_confirm_btn", type="primary"):
            ok, msg = adjust_stock(
                product_id, business_id, user_id, user_id,
                "add" if direction == "Add stock" else "remove",
                qty, reason,
            )
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with t2:
        try:
            history = get_movement_history(product_id, business_id, user_id)
        except Exception as _e:
            st.error("Could not load history.")
            with st.expander("Technical details"):
                st.code(str(_e))
            return
        if not history:
            st.caption("No movements recorded yet.")
        for m in history:
            with st.container(border=True):
                st.markdown(
                    f"**{m['movement_type'].replace('_', ' ').title()}**"
                    f"  \u2014  {m['created_at'].strftime('%d %b %Y %H:%M')}"
                )
                sign = "+" if m["quantity"] >= 0 else ""
                st.caption(f"{sign}{m['quantity']:g}  ({m['quantity_before']:g} \u2192 {m['quantity_after']:g})")
                if m["note"]:
                    st.caption(f"Note: {m['note']}")
                if m["recorded_by_username"]:
                    st.caption(f"Recorded by: {m['recorded_by_username']}")
