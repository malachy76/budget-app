# business.py — Business Mode data access (Phase 1: business profile only)
#
# RULE for every function here and everything we add on top of it later:
# a business is only ever read or written through a query that filters on
# BOTH the business's own id AND owner_user_id in the same WHERE clause.
# business_id alone (e.g. from session_state or a URL) is never trusted —
# it must always be re-checked against the logged-in user on every call.
# This mirrors how banks/expenses/goals are already scoped by user_id
# throughout the rest of the app; businesses add one more layer on top.

from db import get_db

BUSINESS_TYPES = [
    "Pharmacy", "Supermarket / Provision Store", "Mini Mart",
    "Fashion / Clothing", "Restaurant / Food", "Electronics",
    "Beauty / Cosmetics", "Distributor / Wholesale", "Other Retail",
]


def create_business(owner_user_id, business_name, business_type):
    business_name = (business_name or "").strip()
    if not business_name:
        return None, "Business name is required."
    try:
        with get_db() as (conn, cursor):
            cursor.execute(
                "INSERT INTO businesses (owner_user_id, business_name, business_type) "
                "VALUES (%s, %s, %s) RETURNING id",
                (owner_user_id, business_name, business_type),
            )
            new_id = cursor.fetchone()["id"]
        return new_id, "Business created"
    except Exception as e:
        return None, str(e)


def get_user_businesses(owner_user_id):
    """All businesses owned by this user — never returns another user's rows."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, business_name, business_type, created_at "
            "FROM businesses WHERE owner_user_id=%s ORDER BY created_at DESC, id DESC",
            (owner_user_id,),
        )
        return cursor.fetchall()


def get_business(business_id, owner_user_id):
    """A single business — returns None if it doesn't exist OR belongs to
    someone else. owner_user_id is always required, never optional."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, owner_user_id, business_name, business_type, created_at "
            "FROM businesses WHERE id=%s AND owner_user_id=%s",
            (business_id, owner_user_id),
        )
        return cursor.fetchone()
