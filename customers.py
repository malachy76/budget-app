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


# ── Credit dashboard (Phase 5A-3: combined stock-sale + treatment debt) ──────
#
# Debt from the two sources is aggregated in two SEPARATE, independently
# grouped queries and combined in Python — deliberately NOT one query that
# LEFT JOINs both sales and treatments onto customers at once. Joining two
# one-to-many relationships (customer -> many sales, customer -> many
# treatments) in a single query creates a cross-product of each customer's
# sales x their treatments, which would silently inflate every SUM()/COUNT()
# by however many rows the other side happened to have. Aggregating each
# source on its own, then merging the two already-correct per-customer
# totals, avoids that class of bug entirely.

def _get_treatment_outstanding_by_customer(business_id, cursor):
    """Returns {customer_id: {"outstanding": Decimal, "unpaid_count": int,
    "last_at": datetime}} for every treatment with an outstanding balance,
    for this business. A treatment's bill is computed the same way
    treatments.get_treatment_billing() computes it — service_charge plus
    every dispensing's own locked-in price — never a stored total."""
    cursor.execute(
        "SELECT t.id, t.customer_id, t.created_at, t.amount_paid, "
        "  t.service_charge + COALESCE(SUM(d.quantity * d.unit_price) "
        "    FILTER (WHERE d.unit_price IS NOT NULL), 0) AS total_bill "
        "FROM treatments t "
        "LEFT JOIN treatment_items ti ON ti.treatment_id = t.id "
        "LEFT JOIN treatment_dispensing d ON d.treatment_item_id = ti.id "
        "WHERE t.business_id = %s "
        "GROUP BY t.id",
        (business_id,),
    )
    by_customer = {}
    for t in cursor.fetchall():
        cid = t["customer_id"]
        if cid is None:
            continue
        agg = by_customer.setdefault(cid, {"outstanding": Decimal("0"), "unpaid_count": 0, "last_at": None})
        outstanding = t["total_bill"] - t["amount_paid"]
        if outstanding > 0:
            agg["outstanding"] += outstanding
            agg["unpaid_count"] += 1
        if agg["last_at"] is None or t["created_at"] > agg["last_at"]:
            agg["last_at"] = t["created_at"]
    return by_customer


def get_customers_with_balance(business_id, owner_user_id):
    """Every customer for this business, with stock-sale and treatment
    outstanding balances shown separately AND combined, plus the most
    recent activity date across both. Customers with zero debt are still
    included (all zeros) so a fully-paid customer isn't hidden."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, name, phone FROM customers WHERE business_id=%s ORDER BY name",
            (business_id,),
        )
        customers = cursor.fetchall()

        cursor.execute(
            "SELECT customer_id, "
            "  COALESCE(SUM(total_amount - amount_paid) FILTER (WHERE payment_status != 'paid'), 0) AS outstanding, "
            "  COUNT(*) FILTER (WHERE payment_status != 'paid') AS unpaid_count, "
            "  MAX(created_at) AS last_at "
            "FROM sales WHERE business_id=%s GROUP BY customer_id",
            (business_id,),
        )
        sale_by_customer = {r["customer_id"]: r for r in cursor.fetchall()}

        treatment_by_customer = _get_treatment_outstanding_by_customer(business_id, cursor)

    results = []
    for c in customers:
        s = sale_by_customer.get(c["id"])
        t = treatment_by_customer.get(c["id"])
        stock_sale_outstanding = s["outstanding"] if s else Decimal("0")
        unpaid_sales_count = s["unpaid_count"] if s else 0
        treatment_outstanding = t["outstanding"] if t else Decimal("0")
        unpaid_treatments_count = t["unpaid_count"] if t else 0
        last_sale_at = s["last_at"] if s else None
        last_treatment_at = t["last_at"] if t else None
        dates = [d for d in (last_sale_at, last_treatment_at) if d is not None]

        results.append({
            "id": c["id"], "name": c["name"], "phone": c["phone"],
            "stock_sale_outstanding": stock_sale_outstanding,
            "unpaid_sales_count": unpaid_sales_count,
            "treatment_outstanding": treatment_outstanding,
            "unpaid_treatments_count": unpaid_treatments_count,
            "total_outstanding": stock_sale_outstanding + treatment_outstanding,
            "last_activity_at": max(dates) if dates else None,
        })

    results.sort(key=lambda r: (-r["total_outstanding"], r["name"]))
    return results


def get_credit_summary(business_id, owner_user_id):
    """Combined totals across both sources. Deliberately built by
    aggregating get_customers_with_balance()'s own output rather than a
    second, separate query — guarantees this summary can never disagree
    with the per-customer breakdown shown right below it."""
    customers = get_customers_with_balance(business_id, owner_user_id)
    stock_sale_outstanding = sum((c["stock_sale_outstanding"] for c in customers), Decimal("0"))
    treatment_outstanding = sum((c["treatment_outstanding"] for c in customers), Decimal("0"))
    return {
        "stock_sale_outstanding": stock_sale_outstanding,
        "treatment_outstanding": treatment_outstanding,
        "total_outstanding": stock_sale_outstanding + treatment_outstanding,
        "open_sales_count": sum(c["unpaid_sales_count"] for c in customers),
        "open_treatments_count": sum(c["unpaid_treatments_count"] for c in customers),
        "customers_owing": sum(1 for c in customers if c["total_outstanding"] > 0),
    }


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


def get_customer_treatments(customer_id, business_id, owner_user_id):
    """This customer's treatments, newest first, each with its computed
    total_bill and outstanding balance — same computation as
    treatments.get_treatment_billing(), just for a whole list at once."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT t.*, "
            "  t.service_charge + COALESCE(SUM(d.quantity * d.unit_price) "
            "    FILTER (WHERE d.unit_price IS NOT NULL), 0) AS total_bill "
            "FROM treatments t "
            "LEFT JOIN treatment_items ti ON ti.treatment_id = t.id "
            "LEFT JOIN treatment_dispensing d ON d.treatment_item_id = ti.id "
            "WHERE t.customer_id=%s AND t.business_id=%s "
            "GROUP BY t.id "
            "ORDER BY t.created_at DESC",
            (customer_id, business_id),
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            r = dict(r)
            r["outstanding"] = r["total_bill"] - r["amount_paid"]
            results.append(r)
        return results


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

    try:
        amount = _to_decimal(amount, "Payment amount")
        if amount <= 0:
            return None, "Payment amount must be greater than zero."

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
