# expenses.py — expenses page
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from db import get_db
from utils import save_expense, apply_income_filters, apply_expense_filters, \
    render_filter_bar_income, render_filter_bar_expenses, \
    get_category_budgets, compute_daily_safe_to_spend, BUDGET_CATEGORIES, upsert_category_budget
from auth import validate_password, change_password, get_onboarding_status, mark_onboarding_complete


def render_expenses(user_id, pages):
    st.markdown("## Expenses")
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id=%s", (user_id,))
        banks = cursor.fetchall()

    # -- EDIT FORM at top --
    if st.session_state.get("edit_exp_id"):
        edit_id = st.session_state.edit_exp_id
        with get_db() as (conn, cursor):
            cursor.execute("SELECT name, category, amount, bank_id, tx_id FROM expenses WHERE id=%s AND user_id=%s", (edit_id, user_id))
            exp_row = cursor.fetchone()
        if exp_row:
            st.info(f"Editing: {exp_row['name']} — NGN {exp_row['amount']:,.0f}")
            with st.form("edit_expense_form"):
                new_name     = st.text_input("Expense Name", value=exp_row["name"])
                new_category = st.text_input("Category", value=exp_row["category"] or exp_row["name"])
                new_amount   = st.number_input("Amount (NGN)", min_value=1, value=int(exp_row["amount"]))
                save_col, cancel_col = st.columns(2)
                save_clicked   = save_col.form_submit_button("Save Changes")
                cancel_clicked = cancel_col.form_submit_button("Cancel")
            if save_clicked:
                diff = new_amount - exp_row["amount"]
                with get_db() as (conn, cursor):
                    cursor.execute("UPDATE banks SET balance = balance - %s WHERE id=%s", (diff, exp_row["bank_id"]))
                    if exp_row["tx_id"]:
                        cursor.execute("UPDATE transactions SET amount=%s, description=%s WHERE id=%s",
                                       (new_amount, f"Expense: {new_name}", exp_row["tx_id"]))
                    cursor.execute("UPDATE expenses SET name=%s, category=%s, amount=%s WHERE id=%s AND user_id=%s",
                                   (new_name, new_category, new_amount, edit_id, user_id))
                st.success("Expense updated!")
                st.session_state.edit_exp_id = None
                st.rerun()
            if cancel_clicked:
                st.session_state.edit_exp_id = None
                st.rerun()
        else:
            st.warning("Expense not found.")
            st.session_state.edit_exp_id = None
        st.divider()

    if not banks:
        # Empty state — no banks
        st.markdown("""
        <div style="background:#f0f7f4;border-radius:12px;padding:28px 24px;text-align:center;margin:16px 0;">
          <div style="font-size:2.5rem;">&#x1F3E6;</div>
          <div style="font-size:1.1rem;font-weight:700;color:#1a3c5e;margin:8px 0 4px;">No bank account yet</div>
          <div style="color:#4a6070;font-size:0.93rem;">
            You need to add a bank account before you can log expenses.<br>
            Head over to the <strong>Banks</strong> page to get started.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Banks page", key="goto_banks_from_exp"):
            st.session_state.nav_radio = 3  # Banks index
            st.rerun()
        st.stop()

    bank_map = {f"{b['bank_name']} (****{b['account_number']}) - NGN {b['balance']:,}": b["id"] for b in banks}

    # ── QUICK ADD BUTTONS ──────────────────────────────────────────────────
    st.markdown("""
    <style>
    .qa-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }
    .qa-label {
        font-size: 0.82rem; font-weight: 700; color: #1a3c5e;
        text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.subheader("Quick Add Expense")
    st.caption("Tap a category to pre-fill the form below — just enter the amount and submit.")

    # Nigerian daily expense categories
    QUICK_CATEGORIES = [
        ("Foodstuff",              "&#x1F35A;"),
        ("Transport",              "&#x1F695;"),
        ("Airtime/Data",           "&#x1F4F1;"),
        ("Fuel",                   "&#x26FD;"),
        ("Rent",                   "&#x1F3E0;"),
        ("Electricity (NEPA)",     "&#x26A1;"),
        ("POS Charges",            "&#x1F4B3;"),
        ("Transfer Fees",          "&#x1F4B8;"),
        ("School Fees",            "&#x1F393;"),
        ("Church/Mosque Giving",   "&#x1F54C;"),
        ("Business Stock",         "&#x1F4E6;"),
        ("Family Support",         "&#x1F46A;"),
        ("Food & Eating Out",      "&#x1F37D;"),
        ("Internet",               "&#x1F4F6;"),
        ("Groceries",              "&#x1F6D2;"),
        ("Hospital/Drugs",         "&#x1F48A;"),
        ("Water",                  "&#x1F4A7;"),
        ("Generator/Fuel",         "&#x1F527;"),
        ("Laundry",                "&#x1F9FA;"),
        ("Subscription",           "&#x1F4FA;"),
        ("Hair/Beauty",            "&#x1F488;"),
        ("Clothing",               "&#x1F455;"),
        ("Savings Deposit",        "&#x1F4B0;"),
        ("Betting",                "&#x1F3B2;"),
        ("Other",                  "&#x1F4DD;"),
    ]

    # Render in rows of 4 — each button sets session state then reruns
    cols_per_row = 4
    rows = [QUICK_CATEGORIES[i:i+cols_per_row] for i in range(0, len(QUICK_CATEGORIES), cols_per_row)]
    for row in rows:
        cols = st.columns(len(row))
        for col, (cat_name, cat_icon) in zip(cols, row):
            with col:
                if st.button(
                    f"{cat_icon} {cat_name}",
                    key=f"qa_{cat_name}",
                    use_container_width=True,
                    type="secondary" if st.session_state.quick_add_name != cat_name else "primary",
                ):
                    st.session_state.quick_add_name = cat_name
                    st.rerun()  # <-- critical: rerun so the form below picks up the new value

    st.divider()

    # ── ADD EXPENSE FORM (pre-filled from quick-add) ──────────────────────
    prefill_name = st.session_state.get("quick_add_name", "")

    if prefill_name:
        st.info(f"Category selected: **{prefill_name}** — enter the amount and click Add Expense.")

    # All category names for the searchable dropdown
    ALL_EXPENSE_CATEGORIES = [cat for cat, _ in QUICK_CATEGORIES] + ["-- Type custom name --"]

    # Dynamic form key so quick-add pre-fills cleanly
    form_key = f"add_expense_form_{prefill_name or 'custom'}"

    # Determine default index for selectbox
    try:
        default_cat_idx = ALL_EXPENSE_CATEGORIES.index(prefill_name) if prefill_name in ALL_EXPENSE_CATEGORIES else len(ALL_EXPENSE_CATEGORIES) - 1
    except ValueError:
        default_cat_idx = len(ALL_EXPENSE_CATEGORIES) - 1

    with st.form(form_key, clear_on_submit=True):
        selected_category = st.selectbox(
            "Expense Category (search or scroll)",
            ALL_EXPENSE_CATEGORIES,
            index=default_cat_idx,
        )
        # Show custom text input only when "-- Type custom name --" is selected
        custom_name   = st.text_input("Custom expense name (if not in list above)", value="" if selected_category != "-- Type custom name --" else prefill_name)
        expense_name  = custom_name.strip() if selected_category == "-- Type custom name --" else selected_category
        expense_amount = st.number_input("Amount (NGN)", min_value=1, step=100, value=1)
        selected_bank  = st.selectbox("Pay From Bank", list(bank_map.keys()))
        submitted_exp  = st.form_submit_button("Add Expense", use_container_width=True)

    if submitted_exp:
        if expense_name and expense_amount > 1:
            bank_id  = bank_map[selected_bank]
            category = selected_category if selected_category != "-- Type custom name --" else expense_name
            ok, result = save_expense(user_id, bank_id, expense_name, int(expense_amount), category=category)
            if ok:
                st.success(f"'{expense_name}' ({category}) — NGN {int(expense_amount):,} added.")
                st.session_state.quick_add_name = ""
                st.rerun()
            else:
                st.error(result)
        else:
            st.warning("Please enter an expense name and an amount greater than 0.")

    st.divider()
    st.subheader("Expense Summary")
    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT e.id, e.created_at, e.name, e.category, e.amount,
                   e.bank_id, b.bank_name, b.account_number, e.tx_id
            FROM expenses e JOIN banks b ON e.bank_id = b.id
            WHERE e.user_id=%s ORDER BY e.created_at DESC
        """, (user_id,))
        expenses_data = cursor.fetchall()

    if expenses_data:
        all_expense_categories = sorted(set(
            (e["category"] or e["name"]) for e in expenses_data if (e["category"] or e["name"])
        ))

        render_filter_bar_expenses(banks, all_expense_categories)
        filtered_expenses = apply_expense_filters(expenses_data)

        total_shown = sum(e["amount"] for e in filtered_expenses)
        if len(filtered_expenses) != len(expenses_data):
            st.caption(f"Showing {len(filtered_expenses)} of {len(expenses_data)} entries — NGN {total_shown:,.0f} total")
        else:
            st.caption(f"{len(expenses_data)} entries — NGN {total_shown:,.0f} total")

        if not filtered_expenses:
            st.info("No expenses match your search or filters.")
        else:
            for exp in filtered_expenses:
                card_col, edit_col, del_col = st.columns([5, 0.5, 0.5])
                cat_display = exp['category'] if exp.get('category') and exp['category'] != exp['name'] else ""
                with card_col:
                    st.markdown(f"""
                    <div class="exp-card">
                      <div class="exp-card-left">
                        <div class="exp-card-name">{exp['name']}{f' <span style="background:#e8f5f0;color:#0e7c5b;border-radius:10px;padding:1px 8px;font-size:0.75rem;font-weight:600;margin-left:6px;">{cat_display}</span>' if cat_display else ''}</div>
                        <div class="exp-card-bank">Bank: {exp['bank_name']} (****{exp['account_number']})</div>
                        <div class="exp-card-date">Date: {exp['created_at']}</div>
                      </div>
                      <div class="exp-card-right">
                        <div class="exp-card-amount">-NGN {exp['amount']:,.0f}</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with edit_col:
                    if st.button("✏️", key=f"edit_exp_{exp['id']}", help="Edit expense"):
                        st.session_state.edit_exp_id = exp["id"]
                        st.rerun()
                with del_col:
                    del_key = f"exp_{exp['id']}"
                    if st.session_state.confirm_delete.get(del_key):
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✓", key=f"confirm_yes_exp_{exp['id']}", help="Confirm delete", type="primary"):
                                with get_db() as (conn, cursor):
                                    cursor.execute("UPDATE banks SET balance = balance + %s WHERE id=%s", (exp["amount"], exp["bank_id"]))
                                    if exp["tx_id"]:
                                        cursor.execute("DELETE FROM transactions WHERE id=%s", (exp["tx_id"],))
                                    cursor.execute("DELETE FROM expenses WHERE id=%s AND user_id=%s", (exp["id"], user_id))
                                st.session_state.confirm_delete.pop(del_key, None)
                                st.toast(f"Deleted — NGN {exp['amount']:,.0f} refunded to {exp['bank_name']}", icon="🗑️")
                                st.rerun()
                        with c2:
                            if st.button("✗", key=f"confirm_no_exp_{exp['id']}", help="Cancel"):
                                st.session_state.confirm_delete.pop(del_key, None)
                                st.rerun()
                    else:
                        if st.button("🗑️", key=f"delete_exp_{exp['id']}", help=f"Delete '{exp['name']}'"):
                            st.session_state.confirm_delete[del_key] = True
                            st.rerun()

        st.divider()
        st.subheader("Your Expense Breakdown")
        df_exp_pie = pd.DataFrame(
            [(e["category"] or e["name"], e["amount"]) for e in expenses_data],
            columns=["Category", "Amount"]
        )
        df_grouped = df_exp_pie.groupby("Category", as_index=False)["Amount"].sum().sort_values("Amount", ascending=False)
        threshold = df_grouped["Amount"].sum() * 0.02
        df_main   = df_grouped[df_grouped["Amount"] >= threshold]
        df_other  = df_grouped[df_grouped["Amount"] < threshold]
        if not df_other.empty:
            df_main = pd.concat([df_main, pd.DataFrame([{"Category": "Others", "Amount": df_other["Amount"].sum()}])], ignore_index=True)
        fig = px.pie(df_main, names="Category", values="Amount", title="Expenses by Category (NGN)",
                     color_discrete_sequence=px.colors.qualitative.Pastel, hole=0.35)
        fig.update_traces(textposition="inside", textinfo="percent+label",
                          hovertemplate="<b>%{label}</b><br>NGN %{value:,.0f}<br>%{percent}<extra></extra>")
        fig.update_layout(margin=dict(t=40, b=10, l=10, r=10), legend=dict(orientation="v", x=1.02, y=0.5))
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Empty state — no expenses yet
        st.markdown("""
        <div style="background:#fff8f0;border-left:4px solid #f39c12;border-radius:10px;padding:20px 22px;margin:8px 0;">
          <div style="font-size:1.8rem;">&#x1F9FE;</div>
          <div style="font-weight:700;color:#7d5a00;margin:6px 0 4px;">No expenses recorded yet</div>
          <div style="color:#8a6320;font-size:0.92rem;">
            Use the Quick Add buttons above to log your first expense in seconds,
            or type a custom name in the form.
          </div>
        </div>
        """, unsafe_allow_html=True)

# ================= PAGE: BANKS =================
