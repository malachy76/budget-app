# goals.py — goals page
import streamlit as st
from datetime import datetime, timedelta

from db import get_db


def render_goals(user_id, pages):
    st.title("🎯 Savings Goals")

    # ── Single preflight: bank count + goals list in one connection ───────────
    with get_db() as (conn, cursor):
        cursor.execute("SELECT COUNT(*) AS n FROM banks WHERE user_id=%s", (user_id,))
        goals_bank_count = cursor.fetchone()["n"]

        cursor.execute("""
            SELECT id, name, target_amount, current_amount, status
            FROM goals WHERE user_id=%s
            ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, created_at DESC
        """, (user_id,))
        goals = cursor.fetchall()

    if goals_bank_count == 0:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:12px;padding:24px;text-align:center;color:#6b7f8e;margin:12px 0;">
          <div style="font-size:2rem;">&#x1F3AF;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a2e3b;">Add a bank account first</div>
          <div style="font-size:0.92rem;">
            Savings goal contributions are deducted from a bank account.<br>
            Add your bank on the <strong>Banks</strong> page, then set up your goals here.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Banks page", key="goals_goto_banks"):
            st.session_state.nav_radio = pages.index("Banks")
            st.rerun()
        st.stop()

    # ── Create New Goal form (always at top so it's always visible) ──
    GOAL_PRESETS = [
        ("Wedding",          "&#x1F492;"),
        ("Rent",             "&#x1F3E0;"),
        ("House Project",    "&#x1F3D7;"),
        ("Emergency Fund",   "&#x1F6A8;"),
        ("School Fees",      "&#x1F393;"),
        ("Business Restock", "&#x1F4E6;"),
        ("New Phone",        "&#x1F4F1;"),
        ("Car/Okada",        "&#x1F697;"),
        ("Travel",           "&#x2708;"),
        ("Medical",          "&#x1F48A;"),
        ("Bride Price",      "&#x1F48D;"),
        ("Generator",        "&#x1F50B;"),
        ("Tithe/Offering",   "&#x26EA;"),
        ("Custom",           "&#x270F;"),
    ]

    with st.expander("Create New Goal", expanded=False):
        st.caption("Pick a preset or type your own goal name below.")

        # Preset chips rendered as Streamlit buttons in a grid
        preset_cols = st.columns(4)
        for idx, (preset_name, preset_icon) in enumerate(GOAL_PRESETS):
            with preset_cols[idx % 4]:
                is_selected = st.session_state.get("goal_preset") == preset_name
                btn_type = "primary" if is_selected else "secondary"
                if st.button(
                    f"{preset_icon} {preset_name}",
                    key=f"gp_{preset_name}",
                    use_container_width=True,
                    type=btn_type,
                ):
                    st.session_state.goal_preset = preset_name
                    st.rerun()

        selected_preset = st.session_state.get("goal_preset", "")
        # Dynamic form key so preset pre-fills cleanly
        goal_form_key = f"create_goal_form_{selected_preset or 'custom'}"

        ALL_GOAL_NAMES = [name for name, _ in GOAL_PRESETS if name != "Custom"] + ["-- Type custom name --"]

        try:
            default_goal_idx = ALL_GOAL_NAMES.index(selected_preset) if selected_preset and selected_preset in ALL_GOAL_NAMES else len(ALL_GOAL_NAMES) - 1
        except ValueError:
            default_goal_idx = len(ALL_GOAL_NAMES) - 1

        with st.form(goal_form_key):
            selected_goal_label = st.selectbox(
                "Goal Name (search or scroll)",
                ALL_GOAL_NAMES,
                index=default_goal_idx,
            )
            custom_goal_name = st.text_input(
                "Custom goal name (if not in list above)",
                value="" if selected_goal_label != "-- Type custom name --" else ""
            )
            goal_name   = custom_goal_name.strip() if selected_goal_label == "-- Type custom name --" else selected_goal_label
            goal_target = st.number_input("Target Amount (NGN)", min_value=1, step=5000, value=50000)
            submitted   = st.form_submit_button("Create Goal", use_container_width=True)

        if submitted:
            if goal_name and goal_target > 0:
                with get_db() as (conn, cursor):
                    cursor.execute(
                        "INSERT INTO goals (user_id, name, target_amount, created_at, current_amount, status) "
                        "VALUES (%s, %s, %s, %s, 0, 'active')",
                        (user_id, goal_name, int(goal_target), datetime.now().date())
                    )
                st.success(f"Goal '{goal_name}' created!")
                st.session_state.goal_preset = ""
                st.rerun()
            else:
                st.warning("Please enter a name and a target amount greater than 0.")

    st.divider()

    # ── Contribution form (shown above goal list when "Add Money" is clicked) ──
    if st.session_state.show_goal_contribution and st.session_state.selected_goal:
        goal_id = st.session_state.selected_goal
        with get_db() as (conn, cursor):
            cursor.execute(
                "SELECT name, target_amount, current_amount FROM goals WHERE id=%s AND user_id=%s",
                (goal_id, user_id)
            )
            g = cursor.fetchone()
        if g:
            remaining = g["target_amount"] - g["current_amount"]
            st.info(f"Adding money to: **{g['name']}** — ₦{g['current_amount']:,} saved, ₦{remaining:,} remaining")
            with get_db() as (conn, cursor):
                cursor.execute("SELECT id, bank_name, balance FROM banks WHERE user_id=%s", (user_id,))
                bank_list = cursor.fetchall()
            if bank_list:
                bank_options = {f"{b['bank_name']} (₦{b['balance']:,})": b["id"] for b in bank_list}
                bank_labels  = list(bank_options.keys())

                with st.form("goal_contribution_form"):
                    selected_bank  = st.selectbox("From Bank", bank_labels)
                    contrib_amount = st.number_input("Amount to add (NGN)", min_value=1, step=1, value=1)
                    confirm_col, cancel_col = st.columns(2)
                    confirm = confirm_col.form_submit_button("Confirm Contribution")
                    cancel  = cancel_col.form_submit_button("Cancel")

                    if confirm:
                        # Cast everything to int — number_input returns float
                        amt     = int(contrib_amount)
                        bank_id = bank_options[selected_bank]
                        try:
                            with get_db() as (conn, cursor):
                                cursor.execute("SELECT balance FROM banks WHERE id=%s", (bank_id,))
                                bank_balance = int(cursor.fetchone()["balance"])
                                if amt > bank_balance:
                                    st.error(f"Insufficient funds. Bank balance is ₦{bank_balance:,}.")
                                else:
                                    today       = datetime.now().date()
                                    new_current = int(g["current_amount"]) + amt
                                    new_status  = "completed" if new_current >= int(g["target_amount"]) else "active"
                                    cursor.execute(
                                        "UPDATE goals SET current_amount=%s, status=%s WHERE id=%s AND user_id=%s",
                                        (new_current, new_status, goal_id, user_id)
                                    )
                                    cursor.execute(
                                        "UPDATE banks SET balance = balance - %s WHERE id=%s",
                                        (amt, bank_id)
                                    )
                                    cursor.execute(
                                        "INSERT INTO transactions (bank_id, type, amount, description, created_at) "
                                        "VALUES (%s, 'debit', %s, %s, %s)",
                                        (bank_id, amt, f"Savings goal: {g['name']}", today)
                                    )
                                    # Record in goal_contributions history table
                                    cursor.execute(
                                        "INSERT INTO goal_contributions (goal_id, user_id, bank_id, amount, contributed_at) "
                                        "VALUES (%s, %s, %s, %s, %s)",
                                        (goal_id, user_id, bank_id, amt, today)
                                    )
                            st.success(f"Added ₦{amt:,} to '{g['name']}'.")
                            st.session_state.show_goal_contribution = False
                            st.session_state.selected_goal = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"Something went wrong: {e}")

                    if cancel:
                        st.session_state.show_goal_contribution = False
                        st.session_state.selected_goal = None
                        st.rerun()
            else:
                st.warning("You need a bank account to transfer from.")
                if st.button("Cancel", key="cancel_contrib_no_bank"):
                    st.session_state.show_goal_contribution = False
                    st.session_state.selected_goal = None
                    st.rerun()
        else:
            st.session_state.show_goal_contribution = False
            st.session_state.selected_goal = None

    # ── Goals list — active first, then completed ──

    if not goals:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:12px;padding:24px;text-align:center;color:#6b7f8e;margin-top:8px;">
          <div style="font-size:2.2rem;">&#x1F3AF;</div>
          <div style="font-weight:700;margin:8px 0 4px;color:#1a2e3b;">No savings goals yet</div>
          <div style="font-size:0.93rem;">
            Use the <strong>Create New Goal</strong> form above to set a target — emergency fund,
            new phone, school fees, rent, or anything you're saving towards.
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        active_goals    = [g for g in goals if g["status"] == "active"]
        completed_goals = [g for g in goals if g["status"] == "completed"]

        def render_goal(goal):
            progress  = (goal["current_amount"] / goal["target_amount"] * 100) if goal["target_amount"] > 0 else 0
            remaining = max(int(goal["target_amount"]) - int(goal["current_amount"]), 0)
            pct_capped = min(progress / 100, 1.0)
            is_done   = goal["status"] == "completed"
            bar_color = "#0e7c5b" if not is_done else "#16a085"
            # Goal header card
            st.markdown(
                f'<div style="background:#fff;border:1px solid #d8eae2;border-radius:14px;padding:14px 18px 10px;margin-bottom:6px;">' +
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">' +
                f'<div><div style="font-weight:800;font-size:1rem;color:#1a2e3b;">{goal["name"]}</div>' +
                f'<div style="font-size:0.8rem;color:#6b7f8e;margin-top:2px;">'
                + (f'₦{remaining:,} remaining' if not is_done else '🎉 Completed!') +
                f'</div></div>' +
                f'<div style="text-align:right;">' +
                f'<div style="font-size:1.15rem;font-weight:800;color:{bar_color};">₦{int(goal["current_amount"]):,}</div>' +
                f'<div style="font-size:0.75rem;color:#6b7f8e;">of ₦{int(goal["target_amount"]):,}</div>' +
                f'</div></div></div>',
                unsafe_allow_html=True
            )
            st.progress(pct_capped, text=f"{progress:.0f}%")
            col1, col2, col3 = st.columns([5, 1, 1])
            with col1:
                pass
            with col2:
                if goal["status"] == "active":
                    if st.button("💰 Add", key=f"add_goal_{goal['id']}", use_container_width=True):
                        st.session_state.selected_goal          = goal["id"]
                        st.session_state.show_goal_contribution = True
                        st.rerun()
                else:
                    st.markdown("<div style='font-size:0.8rem;color:#0e7c5b;font-weight:700;padding-top:6px;'>✅ Done</div>", unsafe_allow_html=True)
            with col3:
                del_key = f"goal_{goal['id']}"
                if st.session_state.confirm_delete.get(del_key):
                    st.error(f"Delete '{goal['name']}'?")
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("Yes", key=f"confirm_yes_goal_{goal['id']}"):
                            with get_db() as (conn, cursor):
                                cursor.execute("DELETE FROM goals WHERE id=%s AND user_id=%s", (goal["id"], user_id))
                            st.session_state.confirm_delete.pop(del_key, None)
                            st.success(f"'{goal['name']}' deleted.")
                            st.rerun()
                    with cc2:
                        if st.button("No", key=f"confirm_no_goal_{goal['id']}"):
                            st.session_state.confirm_delete.pop(del_key, None)
                            st.rerun()
                else:
                    if st.button("🗑️", key=f"delete_goal_{goal['id']}", help="Delete goal"):
                        st.session_state.confirm_delete[del_key] = True
                        st.rerun()

        if active_goals:
            st.subheader(f"Active Goals ({len(active_goals)})")
            for goal in active_goals:
                render_goal(goal)
                st.divider()

        if completed_goals:
            st.subheader(f"Completed Goals ({len(completed_goals)})")
            for goal in completed_goals:
                render_goal(goal)
                st.divider()

        # ── Contribution history ──────────────────────────────────────────────
        st.divider()
        st.subheader("Contribution History")
        with get_db() as (conn, cursor):
            cursor.execute("""
                SELECT gc.contributed_at, g.name AS goal_name, b.bank_name,
                       gc.amount
                FROM goal_contributions gc
                JOIN goals g ON gc.goal_id = g.id
                JOIN banks b ON gc.bank_id = b.id
                WHERE gc.user_id = %s
                ORDER BY gc.contributed_at DESC
                LIMIT 50
            """, (user_id,))
            contrib_history = cursor.fetchall()

        if contrib_history:
            for c in contrib_history:
                st.markdown(
                    f'<div class="exp-card" style="border-left-color:#0e7c5b;">'
                    f'<div class="exp-card-left">'
                    f'<div class="exp-card-name">{c["goal_name"]}</div>'
                    f'<div class="exp-card-bank">From: {c["bank_name"]}</div>'
                    f'<div class="exp-card-date">Date: {c["contributed_at"]}</div>'
                    f'</div>'
                    f'<div class="exp-card-right">'
                    f'<div class="exp-card-amount" style="color:#0e7c5b;">+₦{c["amount"]:,}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )
        else:
            st.caption("No contributions recorded yet. Add money to a goal to see the history here.")

# ================= PAGE: TRACKER =================
