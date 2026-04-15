# admin.py — Admin Panel and Analytics pages
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from db import get_db
from analytics import get_analytics, notify_admin_new_signup, send_reengagement_email


def render_admin(user_id):
    st.subheader("Admin Panel")
    tabs_admin = st.tabs(["Users", "Banks", "Expenses & Income"])
    with tabs_admin[0]:
        st.write("All Users:")
        with get_db() as (conn, cursor):
            cursor.execute("SELECT id, surname, other_names, username, email, role FROM users")
            all_users = cursor.fetchall()
        for u in all_users:
            st.write(f"{u['surname']} {u['other_names']} | {u['username']} | {u['email']} | Role: {u['role']}")
    with tabs_admin[1]:
        st.write("All Bank Accounts:")
        with get_db() as (conn, cursor):
            cursor.execute("SELECT b.id, u.username, b.bank_name, b.account_name, b.account_number, b.balance FROM banks b JOIN users u ON b.user_id = u.id")
            all_banks = cursor.fetchall()
        for b in all_banks:
            st.write(dict(b))
    with tabs_admin[2]:
        st.info("You can paste your existing Expenses & Income code here for admin view.")


def render_analytics(user_id):
    if st.session_state.user_role != "admin":
        st.error("Access denied.")
        st.stop()
    st.markdown("## Analytics Dashboard")
    data = get_analytics()
    if not data:
        st.warning("Could not load analytics data.")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Registered", data["total_registered"])
        c2.metric("Verified Users",    data["total_verified"])
        c3.metric("Active Today",      data["dau"])
        c4.metric("Active This Week",  data["wau"])
        c5.metric("Active This Month", data["mau"])
        st.divider()
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("Signups")
            s1, s2 = st.columns(2)
            s1.metric("Signups Today",     data["signups_today"])
            s2.metric("Signups (30 days)", data["new_signups_30d"])
            st.subheader("Daily Active Users — Last 14 Days")
            if data["daily_rows"]:
                df_dau = pd.DataFrame(data["daily_rows"], columns=["date", "active_users"])
                df_dau["date"] = pd.to_datetime(df_dau["date"])
                st.bar_chart(df_dau.set_index("date")["active_users"])
            else:
                st.info("No login data yet.")
        with col_right:
            st.subheader(f"Inactive Users ({len(data['inactive_users'])} total)")
            st.caption("Verified accounts with no login in the last 7 days.")
            inactive = data["inactive_users"]
            if inactive:
                df_inactive = pd.DataFrame(inactive, columns=["id","Surname","Other Names","Email","Last Login"])
                df_inactive["Last Login"] = df_inactive["Last Login"].fillna("Never")
                st.dataframe(df_inactive[["Surname","Other Names","Email","Last Login"]], use_container_width=True)
                st.divider()
                st.subheader("Send Re-engagement Email")
                email_options = {f"{r[1]} {r[2]} ({r[3]})": (r[3], r[1]) for r in inactive}
                selected_user = st.selectbox("Select user to email", list(email_options.keys()), key="reeng_select")
                if st.button("Send Re-engagement Email", key="reeng_send_btn"):
                    target_email, target_name = email_options[selected_user]
                    ok, msg = send_reengagement_email(target_email, target_name)
                    st.success(f"Email sent to {target_email}") if ok else st.error(f"Failed: {msg}")
                st.divider()
                st.subheader("Bulk Email All Inactive Users")
                st.caption(f"This will send to all {len(inactive)} inactive verified accounts.")
                if st.button("Send to All Inactive", key="reeng_bulk_btn"):
                    sent, failed = 0, 0
                    for row in inactive:
                        ok, _ = send_reengagement_email(row[3], row[1])
                        if ok: sent += 1
                        else:  failed += 1
                    st.success(f"Sent: {sent}  |  Failed: {failed}")
            else:
                st.success("No inactive users right now - everyone's engaged!")
    
    # ================= PAGE: DASHBOARD =================
