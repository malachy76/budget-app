# sales.py — Business Mode: Sales / Point of Sale (Phase 4B)
#
# SAME RULE as business.py/inventory.py: every function takes business_id
# AND the logged-in owner_user_id, and re-verifies ownership via
# business.get_business() before touching anything.
#
# Stock deduction reuses the SAME inventory_movements ledger inventory.py's
# adjust_stock() already writes to — sales do not keep a second, separate
# stock balance. movement_type='sale' is just a new value in that same
# TEXT column, not a schema change.
#
# TRANSACTION SAFETY: db.get_db() commits on ANY normal exit from the
# `with` block — including a plain `return`, not only reaching the end.
# So every validation failure below is raised as SaleError rather than
# returned early, which is the only way a failed sale is guaranteed to
# roll back instead of partially committing. create_sale() has a single
# `with get_db()` block: every product row is locked (SELECT ... FOR
# UPDATE) and validated BEFORE any INSERT/UPDATE happens, so a failure
# partway through never leaves a half-written sale.

from decimal import Decimal, InvalidOperation

from db import get_db
from business import get_business

PAYMENT_METHODS = ["Cash", "Bank Transfer", "POS", "Other"]


class SaleError(Exception):
    """Raised for any validation failure inside the sale transaction, so
    get_db() rolls back instead of committing partial work."""
    pass


def _to_decimal(value, field_name):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise SaleError(f"{field_name} must be a valid number.")
    return d


def _require_business(business_id, owner_user_id):
    biz = get_business(business_id, owner_user_id)
    if biz is None:
        raise SaleError("This business was not found, or does not belong to you.")
    return biz


# ── Products available to sell ──────────────────────────────────────────────

def get_sale_products(business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, name, unit, selling_price, current_stock "
            "FROM products WHERE business_id=%s AND is_active=1 ORDER BY name",
            (business_id,),
        )
        return cursor.fetchall()


# ── Customers (minimal, for Phase 4B — full customer management is 4C) ──────

def get_or_create_customer(business_id, owner_user_id, name, phone):
    """Exact-name match against existing customers for this business, to
    avoid duplicate rows for a repeat customer typed the same way. Not
    fuzzy matching — a proper customer picker is Phase 4C. Returns None
    for a blank name (walk-in customer, not tracked)."""
    _require_business(business_id, owner_user_id)
    name = (name or "").strip()
    if not name:
        return None
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id FROM customers WHERE business_id=%s AND name=%s",
            (business_id, name),
        )
        existing = cursor.fetchone()
        if existing:
            return existing["id"]
        cursor.execute(
            "INSERT INTO customers (business_id, name, phone) "
            "VALUES (%s, %s, %s) RETURNING id",
            (business_id, name, (phone or "").strip() or None),
        )
        return cursor.fetchone()["id"]


# ── Sale creation ────────────────────────────────────────────────────────────

def create_sale(business_id, owner_user_id, created_by_user_id, items,
                 customer_id, amount_paid, payment_method):
    """
    items: list of {"product_id": int, "quantity": <number-like>}
    Returns (sale_id, message). On failure, sale_id is None and message
    explains why — nothing is written to the database in that case.
    """
    _require_business(business_id, owner_user_id)

    if not items:
        return None, "Add at least one product to the sale."

    amount_paid = _to_decimal(amount_paid, "Amount paid")
    if amount_paid < 0:
        return None, "Amount paid cannot be negative."

    clean_items = []
    for it in items:
        qty = _to_decimal(it["quantity"], "Quantity")
        if qty <= 0:
            return None, "Each item's quantity must be greater than zero."
        clean_items.append({"product_id": it["product_id"], "quantity": qty})

    try:
        with get_db() as (conn, cursor):
            total_amount = Decimal("0")
            line_rows = []  # (product_row, qty, unit_price, line_total)

            for it in clean_items:
                # Lock the row for this whole transaction — same technique
                # as inventory.adjust_stock() — so two concurrent sales
                # can't both read the same stale stock and oversell.
                cursor.execute(
                    "SELECT id, name, unit, selling_price, current_stock "
                    "FROM products WHERE id=%s AND business_id=%s FOR UPDATE",
                    (it["product_id"], business_id),
                )
                product = cursor.fetchone()
                if product is None:
                    raise SaleError("One of the selected products was not found.")
                if it["quantity"] > product["current_stock"]:
                    raise SaleError(
                        f"Not enough stock for '{product['name']}' — "
                        f"only {product['current_stock']:g} {product['unit']} available."
                    )

                unit_price = product["selling_price"]
                line_total = (unit_price * it["quantity"]).quantize(Decimal("0.01"))
                total_amount += line_total
                line_rows.append((product, it["quantity"], unit_price, line_total))

            if amount_paid > total_amount:
                raise SaleError("Amount paid cannot be more than the total amount due.")

            if amount_paid >= total_amount:
                payment_status = "paid"
            elif amount_paid > 0:
                payment_status = "partial"
            else:
                payment_status = "unpaid"

            # Everything below this point only runs once every item has
            # already passed validation above — no early exits past here.
            cursor.execute(
                "INSERT INTO sales (business_id, customer_id, total_amount, "
                "amount_paid, payment_status, payment_method, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (business_id, customer_id, total_amount, amount_paid,
                 payment_status, payment_method, created_by_user_id),
            )
            sale_id = cursor.fetchone()["id"]

            for product, qty, unit_price, line_total in line_rows:
                cursor.execute(
                    "INSERT INTO sale_items (sale_id, business_id, product_id, "
                    "product_name, quantity, unit_price, line_total) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (sale_id, business_id, product["id"], product["name"],
                     qty, unit_price, line_total),
                )

                before = product["current_stock"]
                after = before - qty
                cursor.execute(
                    "UPDATE products SET current_stock=%s, updated_at=NOW() "
                    "WHERE id=%s AND business_id=%s",
                    (after, product["id"], business_id),
                )
                cursor.execute(
                    "INSERT INTO inventory_movements (business_id, product_id, "
                    "movement_type, quantity, quantity_before, quantity_after, "
                    "note, created_by) VALUES (%s, %s, 'sale', %s, %s, %s, %s, %s)",
                    (business_id, product["id"], -qty, before, after,
                     f"Sale #{sale_id}", created_by_user_id),
                )

            if amount_paid > 0:
                cursor.execute(
                    "INSERT INTO payments (business_id, sale_id, customer_id, "
                    "amount, payment_method, note, created_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (business_id, sale_id, customer_id, amount_paid,
                     payment_method, "Initial payment at sale", created_by_user_id),
                )

        return sale_id, "Sale recorded"
    except SaleError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)
