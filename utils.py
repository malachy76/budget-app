# utils.py
import re
import calendar
import streamlit as st
from datetime import datetime, timedelta

from db import get_db


# ── Expense saving ───────────────────────────────────────────────────────────

def save_expense(user_id, bank_id, name, amount, category=None):
    """
    Inserts an expense + debit transaction, debits bank balance.
    Checks overdraft: if the bank would go negative and user has not enabled
    overdraft, raises ValueError so callers can show a clear error.
    Returns (True, tx_id) on success, (False, reason_str) on failure.
    """
    today = datetime.now().date()
    amt   = int(amount)
    cat   = category or name
    try:
        with get_db() as (conn, cursor):
            # Check overdraft permission
            cursor.execute("SELECT balance FROM banks WHERE id=%s AND user_id=%s", (bank_id, user_id))
            bank_row = cursor.fetchone()
            if not bank_row:
                return False, "Bank account not found."
            if bank_row["balance"] - amt < 0:
                # Check if user has overdraft enabled
                cursor.execute("SELECT allow_overdraft FROM users WHERE id=%s", (user_id,))
                user_row = cursor.fetchone()
                if not user_row or not user_row["allow_overdraft"]:
                    shortfall = amt - bank_row["balance"]
                    return False, (
                        f"Insufficient funds. Your balance is NGN {bank_row['balance']:,} "
                        f"but this expense is NGN {amt:,} — NGN {shortfall:,} short. "
                        f"Enable overdraft in Settings if you want to allow this."
                    )
            cursor.execute(
                "INSERT INTO transactions (bank_id, type, amount, description, created_at) "
                "VALUES (%s, 'debit', %s, %s, %s) RETURNING id",
                (bank_id, amt, f"Expense: {name}", today)
            )
            tx_id = cursor.fetchone()["id"]
            cursor.execute(
                "INSERT INTO expenses (user_id, bank_id, name, category, amount, created_at, tx_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, bank_id, name, cat, amt, today, tx_id)
            )
            cursor.execute(
                "UPDATE banks SET balance = balance - %s WHERE id=%s",
                (amt, bank_id)
            )
        return True, tx_id
    except Exception as e:
        return False, str(e)


# ── Filter / sort helpers ────────────────────────────────────────────────────

def apply_income_filters(income_data):
    """Apply search, bank filter, date range, and sort to income list."""
    results = list(income_data)

    search = st.session_state.income_search.strip().lower()
    if search:
        results = [r for r in results if search in r["description"].lower() or search in r["bank_name"].lower()]

    bank_f = st.session_state.income_filter_bank
    if bank_f and bank_f != "All":
        results = [r for r in results if r["bank_name"] == bank_f]

    if st.session_state.income_filter_date_from:
        results = [r for r in results if r["created_at"] >= st.session_state.income_filter_date_from]
    if st.session_state.income_filter_date_to:
        results = [r for r in results if r["created_at"] <= st.session_state.income_filter_date_to]

    sort_key = st.session_state.income_sort
    if sort_key == "Newest First":
        results = sorted(results, key=lambda r: r["created_at"], reverse=True)
    elif sort_key == "Oldest First":
        results = sorted(results, key=lambda r: r["created_at"])
    elif sort_key == "Highest Amount":
        results = sorted(results, key=lambda r: r["amount"], reverse=True)
    elif sort_key == "Lowest Amount":
        results = sorted(results, key=lambda r: r["amount"])

    return results


def apply_expense_filters(expenses_data):
    """Apply search, bank, category, date range, and sort to expense list."""
    results = list(expenses_data)

    search = st.session_state.exp_search.strip().lower()
    if search:
        results = [r for r in results if
                   search in (r["name"] or "").lower() or
                   search in (r["category"] or "").lower() or
                   search in r["bank_name"].lower()]

    bank_f = st.session_state.exp_filter_bank
    if bank_f and bank_f != "All":
        results = [r for r in results if r["bank_name"] == bank_f]

    cat_f = st.session_state.exp_filter_category
    if cat_f and cat_f != "All":
        results = [r for r in results if (r["category"] or r["name"]) == cat_f]

    if st.session_state.exp_filter_date_from:
        results = [r for r in results if r["created_at"] >= st.session_state.exp_filter_date_from]
    if st.session_state.exp_filter_date_to:
        results = [r for r in results if r["created_at"] <= st.session_state.exp_filter_date_to]

    sort_key = st.session_state.exp_sort
    if sort_key == "Newest First":
        results = sorted(results, key=lambda r: r["created_at"], reverse=True)
    elif sort_key == "Oldest First":
        results = sorted(results, key=lambda r: r["created_at"])
    elif sort_key == "Highest Amount":
        results = sorted(results, key=lambda r: r["amount"], reverse=True)
    elif sort_key == "Lowest Amount":
        results = sorted(results, key=lambda r: r["amount"])

    return results


def render_filter_bar_income(banks):
    """Render the search + filter + sort controls for Income History."""
    st.markdown("""
    <style>
    .filter-bar-title {
        font-size: 0.8rem; font-weight: 700; color: #1a3c5e;
        text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown('<div class="filter-bar-title">&#x1F50D; Search &amp; Filter</div>', unsafe_allow_html=True)
    s_col, sort_col = st.columns([3, 1])
    with s_col:
        st.session_state.income_search = st.text_input(
            "Search income", value=st.session_state.income_search,
            placeholder="Search by source or bank name…",
            label_visibility="collapsed", key="income_search_input"
        )
    with sort_col:
        sort_opts = ["Newest First", "Oldest First", "Highest Amount", "Lowest Amount"]
        st.session_state.income_sort = st.selectbox(
            "Sort", sort_opts,
            index=sort_opts.index(st.session_state.income_sort),
            key="income_sort_select", label_visibility="collapsed"
        )
    f1, f2, f3 = st.columns(3)
    bank_names = ["All"] + sorted(set(b["bank_name"] for b in banks))
    with f1:
        sel_bank = st.selectbox(
            "Bank", bank_names,
            index=bank_names.index(st.session_state.income_filter_bank) if st.session_state.income_filter_bank in bank_names else 0,
            key="income_bank_filter"
        )
        st.session_state.income_filter_bank = sel_bank
    with f2:
        date_from = st.date_input("From date", value=st.session_state.income_filter_date_from, key="income_date_from")
        st.session_state.income_filter_date_from = date_from if date_from else None
    with f3:
        date_to = st.date_input("To date", value=st.session_state.income_filter_date_to, key="income_date_to")
        st.session_state.income_filter_date_to = date_to if date_to else None
    if st.button("Clear filters", key="income_clear_filters"):
        st.session_state.income_search = ""
        st.session_state.income_filter_bank = "All"
        st.session_state.income_filter_date_from = None
        st.session_state.income_filter_date_to = None
        st.session_state.income_sort = "Newest First"
        st.rerun()


def render_filter_bar_expenses(banks, all_categories):
    """Render the search + filter + sort controls for Expense Summary."""
    st.markdown('<div class="filter-bar-title">&#x1F50D; Search &amp; Filter</div>', unsafe_allow_html=True)
    s_col, sort_col = st.columns([3, 1])
    with s_col:
        st.session_state.exp_search = st.text_input(
            "Search expenses", value=st.session_state.exp_search,
            placeholder="Search by name, category, or bank…",
            label_visibility="collapsed", key="exp_search_input"
        )
    with sort_col:
        sort_opts = ["Newest First", "Oldest First", "Highest Amount", "Lowest Amount"]
        st.session_state.exp_sort = st.selectbox(
            "Sort", sort_opts,
            index=sort_opts.index(st.session_state.exp_sort),
            key="exp_sort_select", label_visibility="collapsed"
        )
    f1, f2, f3, f4 = st.columns(4)
    bank_names = ["All"] + sorted(set(b["bank_name"] for b in banks))
    cat_names  = ["All"] + sorted(all_categories)
    with f1:
        sel_bank = st.selectbox(
            "Bank", bank_names,
            index=bank_names.index(st.session_state.exp_filter_bank) if st.session_state.exp_filter_bank in bank_names else 0,
            key="exp_bank_filter"
        )
        st.session_state.exp_filter_bank = sel_bank
    with f2:
        sel_cat = st.selectbox(
            "Category", cat_names,
            index=cat_names.index(st.session_state.exp_filter_category) if st.session_state.exp_filter_category in cat_names else 0,
            key="exp_cat_filter"
        )
        st.session_state.exp_filter_category = sel_cat
    with f3:
        date_from = st.date_input("From date", value=st.session_state.exp_filter_date_from, key="exp_date_from")
        st.session_state.exp_filter_date_from = date_from if date_from else None
    with f4:
        date_to = st.date_input("To date", value=st.session_state.exp_filter_date_to, key="exp_date_to")
        st.session_state.exp_filter_date_to = date_to if date_to else None
    if st.button("Clear filters", key="exp_clear_filters"):
        st.session_state.exp_search = ""
        st.session_state.exp_filter_bank = "All"
        st.session_state.exp_filter_category = "All"
        st.session_state.exp_filter_date_from = None
        st.session_state.exp_filter_date_to = None
        st.session_state.exp_sort = "Newest First"
        st.rerun()


# ---------------- CATEGORY BUDGET HELPERS ----------------

# Default categories users can budget for (pre-populated list)
BUDGET_CATEGORIES = [
    "Food & Eating Out",
    "Foodstuff",
    "Transport",
    "Airtime/Data",
    "Rent",
    "Family Support",
    "Electricity (NEPA)",
    "Fuel",
    "Internet",
    "School Fees",
    "Hospital/Drugs",
    "Business Stock",
    "Subscription",
    "Church/Mosque Giving",
    "Generator/Fuel",
    "POS Charges",
    "Transfer Fees",
    "Betting",
    "Hair/Beauty",
    "Clothing",
    "Water",
    "Savings Deposit",
]


# ── Category budget helpers ──────────────────────────────────────────────────

# Default categories users can budget for (pre-populated list)
BUDGET_CATEGORIES = [
    "Food & Eating Out",
    "Foodstuff",
    "Transport",
    "Airtime/Data",
    "Rent",
    "Family Support",
    "Electricity (NEPA)",
    "Fuel",
    "Internet",
    "School Fees",
    "Hospital/Drugs",
    "Business Stock",
    "Subscription",
    "Church/Mosque Giving",
    "Generator/Fuel",
    "POS Charges",
    "Transfer Fees",
    "Betting",
    "Hair/Beauty",
    "Clothing",
    "Water",
    "Savings Deposit",
]


def get_category_budgets(user_id):
    """
    Load all category budgets for user and compute how much has been
    spent in each category this month.

    Returns a list of dicts:
        category, monthly_limit, spent, remaining, pct_used
    """
    today = datetime.now().date()
    month_start = today.replace(day=1)

    with get_db() as (conn, cursor):
        # All category budgets set by the user
        cursor.execute(
            "SELECT category, monthly_limit FROM category_budgets "
            "WHERE user_id = %s ORDER BY category",
            (user_id,)
        )
        budgets = {r["category"]: int(r["monthly_limit"]) for r in cursor.fetchall()}

        if not budgets:
            return []

        # Spending per category this month
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat, SUM(e.amount) AS total
            FROM expenses e
            JOIN banks b ON e.bank_id = b.id
            WHERE b.user_id = %s AND e.created_at >= %s
            GROUP BY cat
        """, (user_id, month_start))
        spent_map = {r["cat"]: int(r["total"]) for r in cursor.fetchall()}

    result = []
    for cat, limit in budgets.items():
        spent     = spent_map.get(cat, 0)
        remaining = max(limit - spent, 0)
        pct_used  = round((spent / limit * 100), 1) if limit > 0 else 0
        result.append({
            "category":      cat,
            "monthly_limit": limit,
            "spent":         spent,
            "remaining":     remaining,
            "pct_used":      pct_used,
        })

    # Sort: most-used % first so urgent ones surface
    result.sort(key=lambda r: r["pct_used"], reverse=True)
    return result


def compute_daily_safe_to_spend(user_id, spending_limit):
    """
    Daily safe-to-spend = (monthly_limit - spent_so_far) / days_remaining_in_month.
    Returns (daily_amount, days_remaining, spent_so_far, monthly_limit).
    Returns None if no monthly limit is set.
    """
    if not spending_limit:
        return None

    today       = datetime.now().date()
    month_start = today.replace(day=1)

    # Days remaining (including today)
    import calendar
    days_in_month   = calendar.monthrange(today.year, today.month)[1]
    days_remaining  = days_in_month - today.day + 1

    with get_db() as (conn, cursor):
        cursor.execute("""
            SELECT COALESCE(SUM(t.amount), 0) AS n FROM transactions t
            JOIN banks b ON t.bank_id = b.id
            WHERE b.user_id = %s AND t.type = 'debit' AND t.created_at >= %s
        """, (user_id, month_start))
        spent = int(cursor.fetchone()["n"] or 0)

    budget_remaining = spending_limit - spent
    daily            = max(budget_remaining, 0) // max(days_remaining, 1)
    return {
        "daily":           daily,
        "days_remaining":  days_remaining,
        "spent":           spent,
        "monthly_limit":   spending_limit,
        "budget_remaining": budget_remaining,
    }


def upsert_category_budget(user_id, category, monthly_limit):
    """Insert or update a category budget. Deletes if limit is 0."""
    with get_db() as (conn, cursor):
        if monthly_limit <= 0:
            cursor.execute(
                "DELETE FROM category_budgets WHERE user_id = %s AND category = %s",
                (user_id, category)
            )
        else:
            cursor.execute("""
                INSERT INTO category_budgets (user_id, category, monthly_limit)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, category)
                DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit
            """, (user_id, category, monthly_limit))

