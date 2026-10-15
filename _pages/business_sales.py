# _pages/business_sales.py — Business Mode: Sales / Point of Sale (Phase 4B)
import streamlit as st
from decimal import Decimal

from styles import render_page_header
from sales import get_sale_products, get_or_create_customer, create_sale, PAYMENT_METHODS


def render_business_sales(user_id):
    render_page_header()
    st.markdown("### \U0001F6D2 Sales / Point of Sale")

    business_id = st.session_state.get("active_business_id")
    if not business_id:
        st.info("Select or create a business first, from Business Home.")
        return

    try:
        products = get_sale_products(business_id, user_id)
    except Exception as _e:
        st.error("Could not load products for sale.")
        with st.expander("Technical details"):
            st.code(str(_e))
        return

    if not products:
        st.info("No products in inventory yet. Add products first, in Products / Inventory.")
        return

    cart = st.session_state.setdefault("_sale_cart", [])
    product_lookup = {p["id"]: p for p in products}

    # ── Add item to cart ────────────────────────────────────────────────────
    st.markdown("##### Add a Product to This Sale")
    st.caption("Choose a product already in your inventory and enter how many the customer is buying.")

    def _fmt(pid):
        p = product_lookup[pid]
        return f"{p['name']} \u2014 {p['current_stock']:g} {p['unit']} available @ \u20A6{p['selling_price']:,.2f}"

    col1, col2 = st.columns([3, 1])
    with col1:
        selected_id = st.selectbox(
            "Product", list(product_lookup.keys()), format_func=_fmt,
            key="sale_product_select",
        )
    with col2:
        qty = st.number_input(
            "Quantity", min_value=0.0, value=None, step=0.5, format="%.3f",
            placeholder="e.g. 2", key="sale_qty_input",
        )

    if st.button("Add to Sale", key="add_to_cart_btn", use_container_width=True):
        p = product_lookup[selected_id]
        if not qty or qty <= 0:
            st.error("Enter a quantity greater than zero.")
        elif Decimal(str(qty)) > p["current_stock"]:
            st.error(f"Only {p['current_stock']:g} {p['unit']} of '{p['name']}' in stock.")
        else:
            cart.append({
                "product_id": p["id"], "name": p["name"], "unit": p["unit"],
                "unit_price": p["selling_price"], "quantity": Decimal(str(qty)),
            })
            st.session_state["_sale_cart"] = cart
            st.rerun()

    st.divider()

    # ── Current sale ────────────────────────────────────────────────────────
    st.markdown("##### Current Sale")
    if not cart:
        st.caption("No items added yet.")
        return

    total = Decimal("0")
    for i, item in enumerate(cart):
        line_total = item["unit_price"] * item["quantity"]
        total += line_total
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.markdown(f"**{item['name']}**")
                st.caption(f"{item['quantity']:g} {item['unit']} @ \u20A6{item['unit_price']:,.2f}")
            with c2:
                st.markdown(f"\u20A6{line_total:,.2f}")
            with c3:
                if st.button("Remove", key=f"remove_cart_{i}"):
                    cart.pop(i)
                    st.session_state["_sale_cart"] = cart
                    st.rerun()

    st.markdown(f"### Total Due: \u20A6{total:,.2f}")
    st.divider()

    # ── Customer ────────────────────────────────────────────────────────────
    st.markdown("##### Customer")
    st.caption("Optional. Leave blank for a walk-in customer you don't need to track.")
    customer_name = st.text_input(
        "Customer Name", placeholder="e.g. John Okafor", key="sale_customer_name",
    )
    customer_phone = st.text_input(
        "Phone Number (optional)", placeholder="e.g. 08012345678", key="sale_customer_phone",
    )

    # ── Payment ─────────────────────────────────────────────────────────────
    st.markdown("##### Payment")
    st.caption("Enter how much the customer is paying now. Leave at 0 to record this fully on credit.")
    amount_paid = st.number_input(
        "Amount Paid Now (\u20A6)", min_value=0.0, max_value=float(total),
        value=0.0, step=0.01, format="%.2f", key="sale_amount_paid",
    )
    payment_method = st.selectbox("Payment Method", PAYMENT_METHODS, key="sale_payment_method")

    outstanding = total - Decimal(str(amount_paid))
    if outstanding > 0:
        st.warning(f"Outstanding balance: \u20A6{outstanding:,.2f} \u2014 this will be recorded as customer credit.")
    else:
        st.success("This sale will be fully paid.")

    st.divider()

    processing = st.session_state.get("_sale_processing", False)
    if st.button(
        "Record Sale", key="record_sale_btn", type="primary",
        use_container_width=True, disabled=processing,
    ):
        st.session_state["_sale_processing"] = True
        try:
            customer_id = None
            try:
                customer_id = get_or_create_customer(
                    business_id, user_id, customer_name, customer_phone,
                )
            except Exception as _e:
                st.error(f"Could not save customer details: {_e}")
                st.session_state["_sale_processing"] = False
                return

            sale_id, msg = create_sale(
                business_id, user_id, user_id,
                [{"product_id": it["product_id"], "quantity": it["quantity"]} for it in cart],
                customer_id, amount_paid, payment_method,
            )
            if sale_id:
                st.success(f"Sale recorded \u2014 Total: \u20A6{total:,.2f}")
                st.session_state["_sale_cart"] = []
                st.session_state.pop("sale_customer_name", None)
                st.session_state.pop("sale_customer_phone", None)
                st.session_state.pop("sale_amount_paid", None)
            else:
                st.error(msg)
        finally:
            st.session_state["_sale_processing"] = False
        st.rerun()
