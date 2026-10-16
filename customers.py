# customers.py — Business Mode: Customer Credit & Payments (Phase 4C)
#
# SAME RULE as business.py/inventory.py/sales.py: every function takes
# business_id AND the logged-in owner_user_id, and re-verifies ownership
# via business.get_business() before touching anything. customer_id and
# sale_id are additionally always scoped by business_id in their own
# WHERE clauses.
#
# A debt is never stored as its own number — it's always derived from
# sales.total_amount minus sales.amount_paid, with amount_paid itself
# only ever changed by record_payment() below (which also writes the
# individual payment row). This mirrors the project's own earlier rule
# for inventory: never let a derived balance drift out of sync with the
# ledger that produced it.
#
# TRANSACTION SAFETY: same discipline as sales.create_sale() — db.get_db()
# commits on any normal exit, including a bare return, so every
# validation failure here raises CreditError instead of returning early,
# guaranteeing rollback rather than a partial commit.

from decimal import Decimal, InvalidOperation

from db import get_db
from business import get_business


class CreditError(Exception):
    pass


def _to_decimal(value, field_name):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise CreditError(f"{field_name} must be a valid number.")
    return d


def _require_business(business_id, owner_user_id):
    biz = get_business(business_id, owner_user_id)
    if biz is None:
        raise CreditError("This business was not found, or does not belong to you.")
    return biz


# ── Credit dashboard ─────────────────────────────────────────────────────────

def get_customers_with_balance(business_id, owner_user_id):
    """Every customer for this business, with their outstanding balance,
    count of unpaid/partially-paid sales, and most recent sale date.
    Customers with zero sales or zero balance are still included (balance
    0, count 0) so a fully-paid customer isn't hidden from the list."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT c.id, c.name, c.phone, "
            "  COALESCE(SUM(s.total_amount - s.amount_paid) "
            "    FILTER (WHERE s.payment_status != 'paid'), 0) AS total_outstanding, "
            "  COUNT(s.id) FILTER (WHERE s.payment_status != 'paid') AS unpaid_sales_count, "
            "  MAX(s.created_at) AS last_sale_at "
            "FROM customers c "
            "LEFT JOIN sales s ON s.customer_id = c.id AND s.business_id = c.business_id "
            "WHERE c.business_id = %s "
            "GROUP BY c.id, c.name, c.phone "
            "ORDER BY total_outstanding DESC, c.name",
            (business_id,),
        )
        return cursor.fetchall()


def get_credit_summary(business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT "
            "  COALESCE(SUM(total_amount - amount_paid) FILTER (WHERE payment_status != 'paid'), 0) AS total_outstanding, "
            "  COUNT(*) FILTER (WHERE payment_status != 'paid') AS open_sales_count, "
            "  COUNT(DISTINCT customer_id) FILTER (WHERE payment_status != 'paid') AS customers_owing "
            "FROM sales WHERE business_id=%s",
            (business_id,),
        )
        return cursor.fetchone()


# ── Customer detail ──────────────────────────────────────────────────────────

def get_customer(customer_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM customers WHERE id=%s AND business_id=%s",
            (customer_id, business_id),
        )
        return cursor.fetchone()


def get_customer_sales(customer_id, business_id, owner_user_id):
    """This customer's sales, newest first, each with its outstanding
    balance computed from total_amount - amount_paid."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT *, (total_amount - amount_paid) AS outstanding "
            "FROM sales WHERE customer_id=%s AND business_id=%s "
            "ORDER BY created_at DESC",
            (customer_id, business_id),
        )
        return cursor.fetchall()


def get_sale_items(sale_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM sale_items WHERE sale_id=%s AND business_id=%s ORDER BY id",
            (sale_id, business_id),
        )
        return cursor.fetchall()


def get_sale_payments(sale_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT p.*, u.username AS recorded_by_username "
            "FROM payments p LEFT JOIN users u ON p.created_by = u.id "
            "WHERE p.sale_id=%s AND p.business_id=%s "
            "ORDER BY p.created_at DESC",
            (sale_id, business_id),
        )
        return cursor.fetchall()


# ── Recording a payment ──────────────────────────────────────────────────────

def record_payment(sale_id, business_id, owner_user_id, created_by_user_id,
                    amount, payment_method, note):
    """Records a part- or full payment against an existing sale. Never
    touches sales.total_amount or any previous payment row — only adds a
    new payment row and increases sales.amount_paid by the same amount,
    inside one locked transaction so two near-simultaneous payments can't
    both read the same stale outstanding balance."""
    _require_business(business_id, owner_user_id)

    amount = _to_decimal(amount, "Payment amount")
    if amount <= 0:
        return None, "Payment amount must be greater than zero."

    try:
        with get_db() as (conn, cursor):
            cursor.execute(
                "SELECT id, customer_id, total_amount, amount_paid, payment_status "
                "FROM sales WHERE id=%s AND business_id=%s FOR UPDATE",
                (sale_id, business_id),
            )
            sale = cursor.fetchone()
            if sale is None:
                raise CreditError("Sale not found.")

            outstanding = sale["total_amount"] - sale["amount_paid"]
            if outstanding <= 0:
                raise CreditError("This sale is already fully paid.")
            if amount > outstanding:
                raise CreditError(
                    f"Payment cannot exceed the outstanding balance of \u20A6{outstanding:,.2f}."
                )

            new_amount_paid = sale["amount_paid"] + amount
            new_status = "paid" if new_amount_paid >= sale["total_amount"] else "partial"

            # Only point past here where writes happen — everything above
            # was validation.
            cursor.execute(
                "INSERT INTO payments (business_id, sale_id, customer_id, amount, "
                "payment_method, note, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (business_id, sale_id, sale["customer_id"], amount,
                 payment_method, note or None, created_by_user_id),
            )
            cursor.execute(
                "UPDATE sales SET amount_paid=%s, payment_status=%s "
                "WHERE id=%s AND business_id=%s",
                (new_amount_paid, new_status, sale_id, business_id),
            )

        return True, f"Payment of \u20A6{amount:,.2f} recorded."
    except CreditError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)
