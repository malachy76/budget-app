from styles import render_page_header
# business_home.py — Business Mode home (Phase 1)
# List the user's businesses, let them create one, let them view one.
# No products/sales/inventory yet — that's later phases.
import streamlit as st

from business import create_business, get_user_businesses, get_business, BUSINESS_TYPES


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
            st.info(
                "This is your business profile. Sales, inventory, customers, "
                "and expenses for this business will appear here in later phases."
            )
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
