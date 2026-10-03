# inventory.py — Business Mode: products + inventory movements (Phase 2)
#
# SAME RULE as business.py: every function here takes business_id AND the
# logged-in owner_user_id, and the very first thing every function does is
# re-verify ownership via business.get_business() — which returns None if
# the business doesn't exist OR belongs to someone else. business_id alone
# is never trusted. product_id is additionally always scoped by
# business_id in its own WHERE clause too, so a product_id can't be used
# to reach across businesses even if guessed.
#
# NUMERIC, not float, throughout — psycopg2 returns NUMERIC columns as
# Python Decimal, which we keep as Decimal end-to-end to avoid floating
# point drift in stock math.

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from db import get_db
from business import get_business

UNITS = [
    "piece", "tablet", "capsule", "bottle", "sachet", "pack", "box",
    "carton", "kg", "litre", "dozen", "other",
]

# Reasons shown in the UI -> the movement_type actually stored. Several
# reasons can share a movement_type; the specific reason stays in `note`.
ADD_REASONS = {
    "New delivery / Purchase": "purchase",
    "Physical stock count (correction)": "adjustment_in",
}
REMOVE_REASONS = {
    "Physical stock count (correction)": "adjustment_out",
    "Damaged": "damaged",
    "Expired": "expired",
    "Missing / Lost": "adjustment_out",
}

LOW_STOCK_DAYS_SOON = 30


class NotOwner(Exception):
    """Raised when business_id doesn't exist or doesn't belong to this user."""
    pass


def _require_business(business_id, owner_user_id):
    biz = get_business(business_id, owner_user_id)
    if biz is None:
        raise NotOwner("This business was not found, or does not belong to you.")
    return biz


def _to_decimal(value, field_name):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")
    return d


# ── Products ─────────────────────────────────────────────────────────────────

def create_product(business_id, owner_user_id, created_by_user_id, name, category, sku,
                    unit, purchase_price, selling_price, opening_stock,
                    low_stock_threshold, expiry_date):
    _require_business(business_id, owner_user_id)

    name = (name or "").strip()
    if not name:
        return None, "Product name is required."

    try:
        purchase_price = _to_decimal(purchase_price, "Purchase price")
        selling_price = _to_decimal(selling_price, "Selling price")
        opening_stock = _to_decimal(opening_stock, "Opening stock")
        low_stock_threshold = _to_decimal(low_stock_threshold, "Low-stock threshold")
    except ValueError as e:
        return None, str(e)

    if purchase_price < 0 or selling_price < 0:
        return None, "Prices cannot be negative."
    if opening_stock < 0:
        return None, "Opening stock cannot be negative."
    if low_stock_threshold < 0:
        return None, "Low-stock threshold cannot be negative."

    try:
        # Single transaction: product row + its opening-stock movement (if
        # any) either both land or neither does — db.get_db() commits on
        # clean exit and rolls back on any exception.
        with get_db() as (conn, cursor):
            cursor.execute(
                "INSERT INTO products (business_id, name, category, sku, unit, "
                "purchase_price, selling_price, current_stock, low_stock_threshold, "
                "expiry_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (business_id, name, category or None, sku or None, unit,
                 purchase_price, selling_price, opening_stock, low_stock_threshold,
                 expiry_date),
            )
            product_id = cursor.fetchone()["id"]

            if opening_stock > 0:
                cursor.execute(
                    "INSERT INTO inventory_movements (business_id, product_id, "
                    "movement_type, quantity, quantity_before, quantity_after, "
                    "unit_cost, note, created_by) "
                    "VALUES (%s, %s, 'opening_stock', %s, 0, %s, %s, %s, %s)",
                    (business_id, product_id, opening_stock, opening_stock,
                     purchase_price, "Opening stock", created_by_user_id),
                )
        return product_id, "Product created"
    except NotOwner as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


def get_products(business_id, owner_user_id, include_inactive=False):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        if include_inactive:
            cursor.execute(
                "SELECT * FROM products WHERE business_id=%s ORDER BY name",
                (business_id,),
            )
        else:
            cursor.execute(
                "SELECT * FROM products WHERE business_id=%s AND is_active=1 ORDER BY name",
                (business_id,),
            )
        return cursor.fetchall()


def get_product(product_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM products WHERE id=%s AND business_id=%s",
            (product_id, business_id),
        )
        return cursor.fetchone()


def stock_status(product):
    """IN_STOCK / LOW_STOCK / OUT_OF_STOCK, purely from DB values."""
    stock = product["current_stock"]
    threshold = product["low_stock_threshold"] or 0
    if stock <= 0:
        return "OUT_OF_STOCK"
    if stock <= threshold:
        return "LOW_STOCK"
    return "IN_STOCK"


def expiry_status(product):
    """EXPIRED / EXPIRING_SOON / OK / NONE."""
    exp = product["expiry_date"]
    if exp is None:
        return "NONE"
    today = date.today()
    if exp < today:
        return "EXPIRED"
    if exp <= today + timedelta(days=LOW_STOCK_DAYS_SOON):
        return "EXPIRING_SOON"
    return "OK"


# ── Stock adjustments ────────────────────────────────────────────────────────

def adjust_stock(product_id, business_id, owner_user_id, created_by_user_id,
                  direction, quantity, reason):
    """direction: 'add' or 'remove'. reason must be a key from ADD_REASONS /
    REMOVE_REASONS matching the direction."""
    _require_business(business_id, owner_user_id)

    if direction not in ("add", "remove"):
        return False, "Invalid direction."
    reasons = ADD_REASONS if direction == "add" else REMOVE_REASONS
    if reason not in reasons:
        return False, "Invalid reason."

    try:
        quantity = _to_decimal(quantity, "Quantity")
    except ValueError as e:
        return False, str(e)
    if quantity <= 0:
        return False, "Quantity must be greater than zero."

    movement_type = reasons[reason]
    signed_qty = quantity if direction == "add" else -quantity

    try:
        with get_db() as (conn, cursor):
            # Lock the row for the duration of this transaction so two
            # concurrent adjustments can't both read the same stale
            # current_stock and overwrite each other.
            cursor.execute(
                "SELECT current_stock FROM products "
                "WHERE id=%s AND business_id=%s FOR UPDATE",
                (product_id, business_id),
            )
            row = cursor.fetchone()
            if row is None:
                return False, "Product not found."

            before = row["current_stock"]
            after = before + signed_qty
            if after < 0:
                return False, (
                    f"Cannot remove {quantity} — only {before} in stock."
                )

            cursor.execute(
                "UPDATE products SET current_stock=%s, updated_at=NOW() "
                "WHERE id=%s AND business_id=%s",
                (after, product_id, business_id),
            )
            cursor.execute(
                "INSERT INTO inventory_movements (business_id, product_id, "
                "movement_type, quantity, quantity_before, quantity_after, "
                "note, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (business_id, product_id, movement_type, signed_qty, before, after,
                 reason, created_by_user_id),
            )
        return True, f"Stock updated: {before} \u2192 {after}"
    except NotOwner as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def get_movement_history(product_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT m.*, u.username AS recorded_by_username "
            "FROM inventory_movements m "
            "LEFT JOIN users u ON m.created_by = u.id "
            "WHERE m.product_id=%s AND m.business_id=%s "
            "ORDER BY m.created_at DESC",
            (product_id, business_id),
        )
        return cursor.fetchall()


# ── Summary ──────────────────────────────────────────────────────────────────

def get_inventory_summary(business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT "
            "  COUNT(*) AS total_products, "
            "  COUNT(*) FILTER (WHERE current_stock <= 0) AS out_of_stock, "
            "  COUNT(*) FILTER (WHERE current_stock > 0 AND current_stock <= low_stock_threshold) AS low_stock, "
            "  COUNT(*) FILTER (WHERE current_stock > low_stock_threshold) AS in_stock, "
            "  COALESCE(SUM(current_stock * purchase_price), 0) AS inventory_value "
            "FROM products WHERE business_id=%s AND is_active=1",
            (business_id,),
        )
        return cursor.fetchone()
