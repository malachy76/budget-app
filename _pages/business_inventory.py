# _pages/business_inventory.py — Business Mode: Products / Inventory
# Phase 2: base functionality. Phase 3: expiry-date form bug fix + full
# label/description redesign + delete/archive (see inline comments below).
import streamlit as st
from datetime import date

from styles import render_page_header
from inventory import (
    create_product, get_products, get_product, adjust_stock, delete_product,
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

    # ── Detail view (adjust stock / history / delete) takes over the page ─────
    detail_id = st.session_state.get("_inv_detail_product_id")
    if detail_id:
        _render_product_detail(detail_id, business_id, user_id)
        return

    # ── Add product ─────────────────────────────────────────────────────────
    # NOTE: this section deliberately does NOT use st.form. Streamlit forms
    # only rerun the script once, on submit — they don't rerun when you
    # interact with a widget inside them. The expiry date picker needs to
    # be conditionally shown based on a checkbox, and a widget that's
    # created for the first time only in that one submit-triggered run
    # always returns its untouched default, never whatever the user
    # actually clicked (it never existed as a real interactive widget
    # before that instant) — that was the exact cause of expiry dates not
    # saving. Using plain widgets + a plain button instead of a form
    # sidesteps this for every field here, not just the date picker.
    with st.expander("\u2795 Add Product", expanded=True):
        st.caption("Fill in the details below. Every field explains what to enter.")

        st.markdown("##### Product Information")

        st.markdown("**Product Name**")
        st.caption("Enter the name of the medicine or item you are adding.")
        name = st.text_input(
            "Product Name", label_visibility="collapsed",
            placeholder="e.g. Paracetamol 500mg",
            key="add_product_name",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Category**")
            st.caption("Choose or enter the category this product belongs to.")
            category = st.text_input(
                "Category", label_visibility="collapsed",
                placeholder="e.g. Medicine, Provision, Cosmetics",
                key="add_product_category",
            )
        with col_b:
            st.markdown("**Unit**")
            st.caption("Enter what one quantity represents.")
            unit = st.selectbox(
                "Unit", UNITS, label_visibility="collapsed",
                key="add_product_unit",
            )

        st.markdown("##### Pricing")
        col_c, col_d = st.columns(2)
        with col_c:
            st.markdown("**Purchase Price**")
            st.caption("How much you paid for one unit of this product.")
            purchase_price = st.number_input(
                "Purchase Price", label_visibility="collapsed",
                min_value=0.0, value=None, step=0.01, format="%.2f",
                placeholder="e.g. 500", key="add_product_purchase_price",
            )
        with col_d:
            st.markdown("**Selling Price**")
            st.caption("The price you sell one unit to your customer.")
            selling_price = st.number_input(
                "Selling Price", label_visibility="collapsed",
                min_value=0.0, value=None, step=0.01, format="%.2f",
                placeholder="e.g. 700", key="add_product_selling_price",
            )

        st.markdown("##### Stock")
        col_e, col_f = st.columns(2)
        with col_e:
            st.markdown("**Opening Stock**")
            st.caption("The quantity of this product you currently have.")
            opening_stock = st.number_input(
                "Opening Stock", label_visibility="collapsed",
                min_value=0.0, value=None, step=0.5, format="%.3f",
                placeholder="e.g. 100", key="add_product_opening_stock",
            )
        with col_f:
            st.markdown("**Low Stock Alert**")
            st.caption("Warn me when stock falls to this quantity.")
            low_stock_threshold = st.number_input(
                "Low Stock Alert", label_visibility="collapsed",
                min_value=0.0, value=None, step=0.5, format="%.3f",
                placeholder="e.g. 10", key="add_product_low_stock",
            )

        st.markdown("##### Expiry")
        st.caption("Select the expiry date printed on the product, if it has one.")
        has_expiry = st.checkbox(
            "This product has an expiry date",
            help="Tick this if the product expires. Leave it unticked if it "
                 "doesn't (e.g. provisions, cosmetics without a printed date).",
            key="add_product_has_expiry",
        )
        expiry_date = None
        if has_expiry:
            expiry_date = st.date_input(
                "Expiry Date",
                min_value=date.today(),
                help="Pick the date from the calendar.",
                key="add_product_expiry_date",
            )
            st.caption(f"\u2705 Selected: {expiry_date.strftime('%d %b %Y')}")

        st.markdown("##### Optional Information")
        st.markdown("**Product Code / SKU**")
        st.caption("Optional: enter a code you use to identify this product.")
        sku = st.text_input(
            "SKU", label_visibility="collapsed",
            placeholder="e.g. PARA-500-001",
            key="add_product_sku",
        )

        if st.button("Create Product", use_container_width=True, type="primary", key="create_product_btn"):
            product_id, msg = create_product(
                business_id, user_id, user_id, name, category, sku, unit,
                purchase_price or 0, selling_price or 0, opening_stock or 0,
                low_stock_threshold or 0, expiry_date,
            )
            if product_id:
                st.success(f"'{name}' added.")
                for _k in ("add_product_name", "add_product_category", "add_product_purchase_price",
                           "add_product_selling_price", "add_product_opening_stock",
                           "add_product_low_stock", "add_product_has_expiry",
                           "add_product_expiry_date", "add_product_sku"):
                    st.session_state.pop(_k, None)
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
                st.markdown(f"Purchase: **\u20A6{p['purchase_price']:,.2f}**")
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
                elif p["expiry_date"]:
                    st.caption(f"Expires {p['expiry_date'].strftime('%d %b %Y')}")
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

    t1, t2, t3 = st.tabs(["Adjust Stock", "History", "Delete Product"])

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

    with t3:
        st.warning(
            f"Are you sure you want to remove **{product['name']}**? "
            f"This may affect how the product appears in your inventory records."
        )
        confirm = st.checkbox(
            "Yes, I'm sure I want to delete this product.",
            key="del_confirm_checkbox",
        )
        if st.button(
            "Delete Product", key="del_confirm_btn", type="primary",
            disabled=not confirm,
        ):
            action, msg = delete_product(product_id, business_id, user_id)
            if action:
                st.success(msg)
                st.session_state["_inv_detail_product_id"] = None
                st.session_state.pop("del_confirm_checkbox", None)
                st.rerun()
            else:
                st.error(msg)
