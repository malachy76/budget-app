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

# Phase 5B-1: Treatment Management is a pharmacy-style feature and is a
# per-business setting (businesses.treatment_management_enabled), NOT
# something every business receives. Defaults: ON for a new Pharmacy,
# OFF for every other business type; the owner can change it either way.
PHARMACY_TYPE = "Pharmacy"
TREATMENT_SETTING_HELP_PHARMACY = (
    "Enable this feature if your pharmacy records treatments and medicines "
    "or supplies used during patient care."
)
TREATMENT_SETTING_HELP_OTHER = (
    "Enable this only if your business records treatments or services and the "
    "medicines or supplies used during patient or customer care. Most shops do not need it."
)

# SQL for the effective setting. A NULL (a business row written by older code
# before the 5B-1 migration ran) falls back to the same rule the migration
# uses, so such a business never silently loses — or gains — access.
_TM_ENABLED_SQL = (
    "COALESCE(b.treatment_management_enabled, "
    "(b.business_type = 'Pharmacy' OR EXISTS "
    "(SELECT 1 FROM treatments t WHERE t.business_id = b.id))) AS treatment_management_enabled"
)

BUSINESS_TYPES = [
    "Pharmacy", "Supermarket / Provision Store", "Mini Mart",
    "Fashion / Clothing", "Restaurant / Food", "Electronics",
    "Beauty / Cosmetics", "Distributor / Wholesale", "Other Retail",
]


def default_treatment_setting(business_type):
    """Default for a NEW business: on for pharmacies only."""
    return business_type == PHARMACY_TYPE


def create_business(owner_user_id, business_name, business_type,
                     treatment_management_enabled=None):
    business_name = (business_name or "").strip()
    if not business_name:
        return None, "Business name is required."
    if treatment_management_enabled is None:
        treatment_management_enabled = default_treatment_setting(business_type)
    try:
        with get_db() as (conn, cursor):
            cursor.execute(
                "INSERT INTO businesses (owner_user_id, business_name, business_type, "
                "treatment_management_enabled) VALUES (%s, %s, %s, %s) RETURNING id",
                (owner_user_id, business_name, business_type, bool(treatment_management_enabled)),
            )
            new_id = cursor.fetchone()["id"]
        return new_id, "Business created"
    except Exception as e:
        return None, str(e)


def get_user_businesses(owner_user_id):
    """All businesses owned by this user — never returns another user's rows."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT b.id, b.business_name, b.business_type, b.created_at, "
            + _TM_ENABLED_SQL +
            " FROM businesses b WHERE b.owner_user_id=%s ORDER BY b.created_at DESC, b.id DESC",
            (owner_user_id,),
        )
        return cursor.fetchall()


def get_business(business_id, owner_user_id):
    """A single business — returns None if it doesn't exist OR belongs to
    someone else. owner_user_id is always required, never optional."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT b.id, b.owner_user_id, b.business_name, b.business_type, b.created_at, "
            + _TM_ENABLED_SQL +
            " FROM businesses b WHERE b.id=%s AND b.owner_user_id=%s",
            (business_id, owner_user_id),
        )
        return cursor.fetchone()


def is_treatment_management_enabled(business_id, owner_user_id):
    """True only if the business exists, belongs to this owner AND has the
    feature switched on. Fails closed (False) for any other business."""
    biz = get_business(business_id, owner_user_id)
    return bool(biz and biz["treatment_management_enabled"])


def set_treatment_management(business_id, owner_user_id, enabled):
    """Owner switches Treatment Management on or off. Turning it off NEVER
    deletes or edits anything: existing treatments, payments, balances and
    reports stay exactly as they are; only creating/dispensing/editing
    treatments and the menu entry points are hidden. Returns (True, msg) or
    (None, error)."""
    try:
        with get_db() as (conn, cursor):
            cursor.execute(
                "UPDATE businesses SET treatment_management_enabled=%s "
                "WHERE id=%s AND owner_user_id=%s",
                (bool(enabled), business_id, owner_user_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("This business was not found, or does not belong to you.")
        return True, ("Treatment Management is now ON." if enabled else
                      "Treatment Management is now OFF. Your existing treatment records are kept.")
    except Exception as e:
        return None, str(e)
