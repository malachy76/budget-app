# demo_data.py — static in-memory sample data for Demo Mode
# Zero DB reads/writes. All values are plain Python dicts.
# Loaded once when demo mode is entered; stays in session_state["_demo"].
from datetime import date, timedelta

_today = date.today()
_d = lambda n: (_today - timedelta(days=n)).isoformat()


def get_demo_data() -> dict:
    """
    Return a single dict with all sample data for every demo page.
    Called once; the result is stored in st.session_state["_demo"].
    Pure Python — no DB, no imports, no side effects.
    """
    return {
        # ── Identity ─────────────────────────────────────────────────────────
        "user": {
            "surname":     "Demo",
            "other_names": "User",
            "role":        "user",
            "monthly_spending_limit": 150_000,
        },

        # ── Banks ─────────────────────────────────────────────────────────────
        "banks": [
            {"id": 1, "bank_name": "GTB",     "account_name": "Demo User",
             "account_number": "1234", "balance": 342_500, "min_balance_alert": 10_000},
            {"id": 2, "bank_name": "Opay",    "account_name": "Demo User",
             "account_number": "5678", "balance": 85_000,  "min_balance_alert": 5_000},
            {"id": 3, "bank_name": "Access",  "account_name": "Demo User",
             "account_number": "9012", "balance": 415_000, "min_balance_alert": 0},
        ],

        # ── Transactions (income = credit, expense = debit) ───────────────────
        "transactions": [
            {"id": 1,  "bank_id": 1, "type": "credit", "amount": 450_000,
             "description": "Income: Monthly Salary",      "created_at": _d(18)},
            {"id": 2,  "bank_id": 2, "type": "credit", "amount": 25_000,
             "description": "Income: Freelance Design",    "created_at": _d(12)},
            {"id": 3,  "bank_id": 1, "type": "debit",  "amount": 18_400,
             "description": "Expense: Shoprite Groceries", "created_at": _d(16)},
            {"id": 4,  "bank_id": 1, "type": "debit",  "amount": 12_000,
             "description": "Expense: NEPA Electricity",   "created_at": _d(15)},
            {"id": 5,  "bank_id": 1, "type": "debit",  "amount": 5_600,
             "description": "Expense: Transport (Bolt)",   "created_at": _d(14)},
            {"id": 6,  "bank_id": 2, "type": "debit",  "amount": 8_500,
             "description": "Expense: Airtime & Data",     "created_at": _d(13)},
            {"id": 7,  "bank_id": 3, "type": "debit",  "amount": 30_000,
             "description": "Expense: Rent (part)",        "created_at": _d(10)},
            {"id": 8,  "bank_id": 1, "type": "debit",  "amount": 4_200,
             "description": "Expense: Food — Chicken",     "created_at": _d(8)},
            {"id": 9,  "bank_id": 2, "type": "debit",  "amount": 6_000,
             "description": "Expense: Generator Fuel",     "created_at": _d(7)},
            {"id": 10, "bank_id": 3, "type": "credit", "amount": 15_000,
             "description": "Income: Business Sales",      "created_at": _d(5)},
            {"id": 11, "bank_id": 1, "type": "debit",  "amount": 3_500,
             "description": "Expense: Transport",          "created_at": _d(3)},
            {"id": 12, "bank_id": 1, "type": "debit",  "amount": 7_000,
             "description": "Expense: Foodstuff",          "created_at": _d(2)},
        ],

        # ── Expenses (mirrors debit transactions) ─────────────────────────────
        "expenses": [
            {"id": 1,  "bank_id": 1, "name": "Shoprite Groceries", "category": "Foodstuff",
             "amount": 18_400, "created_at": _d(16)},
            {"id": 2,  "bank_id": 1, "name": "NEPA Electricity",   "category": "Electricity (NEPA)",
             "amount": 12_000, "created_at": _d(15)},
            {"id": 3,  "bank_id": 1, "name": "Transport (Bolt)",   "category": "Transport",
             "amount": 5_600,  "created_at": _d(14)},
            {"id": 4,  "bank_id": 2, "name": "Airtime & Data",     "category": "Airtime/Data",
             "amount": 8_500,  "created_at": _d(13)},
            {"id": 5,  "bank_id": 3, "name": "Rent (part payment)","category": "Rent",
             "amount": 30_000, "created_at": _d(10)},
            {"id": 6,  "bank_id": 1, "name": "Chicken Republic",   "category": "Food & Eating Out",
             "amount": 4_200,  "created_at": _d(8)},
            {"id": 7,  "bank_id": 2, "name": "Generator Fuel",     "category": "Generator/Fuel",
             "amount": 6_000,  "created_at": _d(7)},
            {"id": 8,  "bank_id": 1, "name": "Transport",          "category": "Transport",
             "amount": 3_500,  "created_at": _d(3)},
            {"id": 9,  "bank_id": 1, "name": "Foodstuff",          "category": "Foodstuff",
             "amount": 7_000,  "created_at": _d(2)},
        ],

        # ── Goals ─────────────────────────────────────────────────────────────
        "goals": [
            {"id": 1, "name": "Emergency Fund",   "target_amount": 500_000,
             "current_amount": 120_000, "status": "active"},
            {"id": 2, "name": "New Laptop",       "target_amount": 250_000,
             "current_amount": 87_500,  "status": "active"},
            {"id": 3, "name": "Rent Deposit",     "target_amount": 150_000,
             "current_amount": 150_000, "status": "completed"},
        ],

        # ── Tracker — recurring items ─────────────────────────────────────────
        "recurring_income": [
            {"id": 1, "name": "Monthly Salary",  "amount": 450_000, "frequency": "monthly",
             "next_due": _d(-3), "auto_post": 1, "allow_overdraft": 0,
             "last_posted_at": _d(18), "bank_name": "GTB"},
        ],
        "recurring_expenses": [
            {"id": 2, "name": "DSTV Subscription","amount": 9_000,  "frequency": "monthly",
             "category": "Subscription", "next_due": _d(-1), "auto_post": 0,
             "allow_overdraft": 0, "last_posted_at": None, "bank_name": "GTB"},
            {"id": 3, "name": "House Rent",       "amount": 80_000, "frequency": "monthly",
             "category": "Rent", "next_due": _d(5), "auto_post": 0,
             "allow_overdraft": 0, "last_posted_at": _d(35), "bank_name": "Access"},
            {"id": 4, "name": "Electricity (NEPA)","amount": 12_000,"frequency": "monthly",
             "category": "Electricity (NEPA)", "next_due": _d(3), "auto_post": 0,
             "allow_overdraft": 0, "last_posted_at": _d(15), "bank_name": "GTB"},
        ],

        # ── Debts ─────────────────────────────────────────────────────────────
        "debts": [
            {"id": 1, "name": "GTB Personal Loan", "type": "borrowed",
             "principal": 200_000, "balance_remaining": 120_000,
             "interest_rate": 18.0, "monthly_payment": 20_000,
             "due_date": _d(-30), "counterparty": "GTBank",
             "notes": "[Bank Loan] ",   "status": "active"},
            {"id": 2, "name": "Owe Chidi",         "type": "borrowed",
             "principal": 30_000, "balance_remaining": 30_000,
             "interest_rate": 0.0,  "monthly_payment": 0,
             "due_date": _d(-5),  "counterparty": "Chidi Okonkwo",
             "notes": "[Family / Friend] Borrowed for medical bill", "status": "active"},
            {"id": 3, "name": "Lent Aisha",         "type": "lent",
             "principal": 15_000, "balance_remaining": 5_000,
             "interest_rate": 0.0,  "monthly_payment": 5_000,
             "due_date": _d(10), "counterparty": "Aisha Bello",
             "notes": "[Personal] Lent for school fees", "status": "active"},
        ],
        "debt_payments": {
            1: [{"amount": 40_000, "payment_date": _d(60), "note": "First instalment"},
                {"amount": 40_000, "payment_date": _d(30), "note": "Second instalment"}],
            2: [],
            3: [{"amount": 10_000, "payment_date": _d(15), "note": "Partial repayment"}],
        },

        # ── Emergency Fund ────────────────────────────────────────────────────
        "emergency_fund": {
            "target_months": 3,
            "monthly_expenses_estimate": 95_000,
            "current_saved": 120_000,
            "goal_id": 1,
            "updated_at": _d(7),
        },

        # ── Notifications ─────────────────────────────────────────────────────
        "notifications": [
            {"id": 1, "type": "milestone", "title": "7-Day Streak! 🏆",
             "body": "You have logged in 7 days in a row. Keep going!",
             "icon": "&#x1F3C6;", "read": 0, "created_at": _d(0)},
            {"id": 2, "type": "reminder",  "title": "Bill Due: DSTV Subscription",
             "body": "DSTV Subscription is due today — NGN 9,000.",
             "icon": "&#x1F514;", "read": 0, "created_at": _d(1)},
            {"id": 3, "type": "alert",     "title": "Budget Alert: 68% Used",
             "body": "You have used 68% of your NGN 150,000 monthly budget.",
             "icon": "&#x26A0;&#xFE0F;",  "read": 1, "created_at": _d(3)},
        ],

        # ── Streak ────────────────────────────────────────────────────────────
        "streak": {"current": 7, "longest": 14},

        # ── Summary data (used by dashboard metrics) ──────────────────────────
        "total_balance":        842_500,
        "expenses_this_month":  95_200,
        "net_savings":          489_800,
    }
