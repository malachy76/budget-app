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
from contacts import normalize_phone
import costing
import integrity
from costing import CostingError
from sales import PAYMENT_METHODS
# Phase 5A-4: collectible debt = total - paid - ACTIVE write-offs. The SQL
# fragment lives in baddebt.py so every balance in the app uses the identical
# definition of "active write-off" (not reversed).
from baddebt import active_write_off_sql, SOURCE_SALE, SOURCE_TREATMENT


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
    """Returns {customer_id: {"outstanding": Decimal, "unpaid_count": int, "last_at": datetime}} for every treatment with an outstanding balance, for this business. A treatment's bill is computed the same way treatments.get_treatment_billing() computes it — service_charge plus every dispensing's own locked-in price — never a stored total."""
    cursor.execute(
        "SELECT t.id, t.customer_id, t.created_at, t.amount_paid, "
        " t.service_charge + COALESCE(SUM(ROUND(d.quantity * d.unit_price, 2)) "
        " FILTER (WHERE d.unit_price IS NOT NULL), 0) AS total_bill, "
        # Scalar subquery, NOT a join — a join would multiply the written-off
        # amount by the number of item/dispensing rows.
        f" {active_write_off_sql(SOURCE_TREATMENT, 't')} AS written_off "
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
        outstanding = t["total_bill"] - t["amount_paid"] - t["written_off"]
        if outstanding > 0:
            agg["outstanding"] += outstanding
            agg["unpaid_count"] += 1
        if agg["last_at"] is None or t["created_at"] > agg["last_at"]:
            agg["last_at"] = t["created_at"]
    return by_customer


def get_customers_with_balance(business_id, owner_user_id):
    """Every customer for this business, with stock-sale and treatment outstanding balances shown separately AND combined, plus the most recent activity date across both. Customers with zero debt are still included (all zeros) so a fully-paid customer isn't hidden."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, name, phone FROM customers WHERE business_id=%s ORDER BY name",
            (business_id,),
        )
        customers = cursor.fetchall()

        # collectible = total - paid - active write-offs (Phase 5A-4). A
        # fully written-off sale keeps payment_status 'unpaid'/'partial'
        # (the sale row is never edited), so "is it still owed?" is decided
        # by the derived balance, not by payment_status.
        cursor.execute(
            "SELECT customer_id, "
            " COALESCE(SUM(collectible) FILTER (WHERE collectible > 0), 0) AS outstanding, "
            " COUNT(*) FILTER (WHERE collectible > 0) AS unpaid_count, "
            " MAX(created_at) AS last_at "
            "FROM (SELECT s.customer_id, s.created_at, "
            f" s.total_amount - s.amount_paid - {active_write_off_sql(SOURCE_SALE, 's')} AS collectible "
            " FROM sales s WHERE s.business_id=%s) x GROUP BY customer_id",
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
    """Combined totals across both sources. Deliberately built by aggregating get_customers_with_balance()'s own output rather than a second, separate query — guarantees this summary can never disagree with the per-customer breakdown shown right below it."""
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
    """This customer's sales, newest first, each with its outstanding balance computed from total_amount - amount_paid."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT s.*, "
            f" {active_write_off_sql(SOURCE_SALE, 's')} AS written_off, "
            f" (s.total_amount - s.amount_paid - {active_write_off_sql(SOURCE_SALE, 's')}) AS outstanding "
            "FROM sales s WHERE s.customer_id=%s AND s.business_id=%s "
            "ORDER BY s.created_at DESC",
            (customer_id, business_id),
        )
        return cursor.fetchall()


def get_customer_treatments(customer_id, business_id, owner_user_id):
    """This customer's treatments, newest first, each with its computed total_bill and outstanding balance — same computation as treatments.get_treatment_billing(), just for a whole list at once."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT t.*, "
            " t.service_charge + COALESCE(SUM(ROUND(d.quantity * d.unit_price, 2)) "
            " FILTER (WHERE d.unit_price IS NOT NULL), 0) AS total_bill, "
            f" {active_write_off_sql(SOURCE_TREATMENT, 't')} AS written_off "
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
            r["outstanding"] = r["total_bill"] - r["amount_paid"] - r["written_off"]
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

def record_payment(sale_id, business_id, owner_user_id, created_by_user_id, amount, payment_method, note, idempotency_key=None):
    """Records a part- or full payment against an existing sale. Never touches sales.total_amount or any previous payment row — only adds a new payment row and increases sales.amount_paid by the same amount, inside one locked transaction so two near-simultaneous payments can't both read the same stale outstanding balance. Phase 5B-3 * idempotency_key: the same submission reference sent again returns (True, "...already recorded...") and writes nothing. Checked first, so a retry after a successful-but-unconfirmed attempt reports success rather than "already fully paid". * Amount must have at most 2 decimals (never silently rounded) so the payment row and sales.amount_paid can never drift apart. * The payment method must be one of sales.PAYMENT_METHODS."""
    _require_business(business_id, owner_user_id)

    try:
        key = integrity.clean_key(idempotency_key)
        try:
            amount = costing.money_amount(amount, "Payment amount")
        except CostingError as e:
            raise CreditError(str(e))
        if amount <= 0:
            return None, "Payment amount must be greater than zero."
        if payment_method not in PAYMENT_METHODS:
            return None, "Please choose a valid payment method."

        with get_db() as (conn, cursor):
            if key is not None:
                integrity.lock_key(cursor, business_id, "payment", key)
                cursor.execute(
                    "SELECT id, sale_id, amount FROM payments "
                    "WHERE business_id=%s AND idempotency_key=%s",
                    (business_id, key),
                )
                prior = cursor.fetchone()
                if prior:
                    if prior["sale_id"] != sale_id or prior["amount"] != amount:
                        raise CreditError(
                            "This submission reference was already used for a different payment. "
                            "Please reopen the form and try again.")
                    return True, (f"Payment of \u20A6{amount:,.2f} (ref #{prior['id']}) was "
                                  f"{integrity.REPLAY_NOTE}.")

            cursor.execute(
                "SELECT id, customer_id, total_amount, amount_paid, payment_status "
                "FROM sales WHERE id=%s AND business_id=%s FOR UPDATE",
                (sale_id, business_id),
            )
            sale = cursor.fetchone()
            if sale is None:
                raise CreditError("Sale not found.")

            # Phase 5A-4: written-off money is no longer collectible, so an
            # ordinary payment may only go against what is still collectible.
            # (Money received against a written-off amount is a RECOVERY —
            # baddebt.record_recovery — never an ordinary payment.)
            cursor.execute(
                "SELECT COALESCE(SUM(w.amount), 0) AS wo FROM debt_write_offs w "
                "WHERE w.business_id=%s AND w.sale_id=%s AND NOT EXISTS "
                "(SELECT 1 FROM debt_write_off_reversals r WHERE r.write_off_id = w.id)",
                (business_id, sale_id),
            )
            written_off = cursor.fetchone()["wo"]
            outstanding = sale["total_amount"] - sale["amount_paid"] - written_off
            if outstanding <= 0:
                if written_off > 0:
                    raise CreditError(
                        "Nothing is left to collect on this sale — the balance was written off. "
                        "Use Bad Debts \u2192 Record Recovery if the customer is paying it back."
                    )
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
                "payment_method, note, created_by, idempotency_key) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (business_id, sale_id, sale["customer_id"], amount,
                 payment_method, note or None, created_by_user_id, key),
            )
            pay_id = cursor.fetchone()["id"]
            cursor.execute(
                "UPDATE sales SET amount_paid=%s, payment_status=%s "
                "WHERE id=%s AND business_id=%s",
                (new_amount_paid, new_status, sale_id, business_id),
            )

        return True, f"Payment of \u20A6{amount:,.2f} recorded (ref #{pay_id})."
    except CreditError as e:
        return None, str(e)
    except Exception as e:
        return None, integrity.friendly_db_error(e)


def reverse_payment(payment_id, business_id, owner_user_id, created_by_user_id, reason, idempotency_key=None):
    """Correct a payment recorded by mistake (wrong amount, wrong sale, ...). NOTHING is edited or deleted: a NEW compensating payment row with the NEGATIVE amount is added, pointing at the payment it reverses (payments.reverses_payment_id, UNIQUE — a payment can be reversed once), and sales.amount_paid goes down by the same amount inside the same locked transaction. The original row stays forever, so the history reads 'payment +X' then 'reversal -X', each with who and when. Reports net the two correctly on the day the reversal was made. Rules: the reason is mandatory; only an original (positive) payment can be reversed; if undoing it leaves money owing, the customer must exist and have a valid phone number (the same rule as a credit sale)."""
    _require_business(business_id, owner_user_id)
    try:
        key = integrity.clean_key(idempotency_key)
        reason = (reason or "").strip()
        if not reason:
            raise CreditError("Please give a reason for reversing this payment.")

        with get_db() as (conn, cursor):
            if key is not None:
                integrity.lock_key(cursor, business_id, "payment", key)
                cursor.execute(
                    "SELECT id, reverses_payment_id FROM payments "
                    "WHERE business_id=%s AND idempotency_key=%s", (business_id, key))
                prior = cursor.fetchone()
                if prior:
                    if prior["reverses_payment_id"] != payment_id:
                        raise CreditError(
                            "This submission reference was already used for a different action. "
                            "Please reopen the form and try again.")
                    return True, f"This payment reversal was {integrity.REPLAY_NOTE}."

            cursor.execute(
                "SELECT id, sale_id, customer_id, amount, payment_method, reverses_payment_id "
                "FROM payments WHERE id=%s AND business_id=%s",
                (payment_id, business_id),
            )
            pay = cursor.fetchone()
            if pay is None:
                raise CreditError("Payment not found.")
            if pay["reverses_payment_id"] is not None or pay["amount"] <= 0:
                raise CreditError("A reversal cannot itself be reversed. Record a new payment instead.")

            # Lock the parent sale — the same lock record_payment takes — so a
            # reversal and a payment on the same sale can't interleave.
            cursor.execute(
                "SELECT id, customer_id, total_amount, amount_paid FROM sales "
                "WHERE id=%s AND business_id=%s FOR UPDATE",
                (pay["sale_id"], business_id),
            )
            sale = cursor.fetchone()
            if sale is None:
                raise CreditError("Sale not found.")

            cursor.execute("SELECT 1 FROM payments WHERE reverses_payment_id=%s", (payment_id,))
            if cursor.fetchone():
                raise CreditError("This payment has already been reversed.")

            new_paid = sale["amount_paid"] - pay["amount"]
            if new_paid < 0:
                raise CreditError("This payment can't be reversed: it is larger than the amount recorded as paid.")
            cursor.execute(
                "SELECT COALESCE(SUM(w.amount), 0) AS wo FROM debt_write_offs w "
                "WHERE w.business_id=%s AND w.sale_id=%s AND NOT EXISTS "
                "(SELECT 1 FROM debt_write_off_reversals r WHERE r.write_off_id = w.id)",
                (business_id, pay["sale_id"]),
            )
            written_off = cursor.fetchone()["wo"]
            owed_after = sale["total_amount"] - new_paid - written_off
            if owed_after > 0:
                if sale["customer_id"] is None:
                    raise CreditError(
                        "This payment can't be reversed: it would leave money owing on a sale "
                        "with no customer. Money owed always needs a customer with a phone number.")
                cursor.execute("SELECT phone FROM customers WHERE id=%s AND business_id=%s",
                               (sale["customer_id"], business_id))
                cust = cursor.fetchone()
                if cust is None or normalize_phone(cust["phone"])[0] is None:
                    raise CreditError(
                        "This payment can't be reversed until the customer has a valid phone number, "
                        "because reversing it leaves money owing.")

            new_status = ("paid" if new_paid >= sale["total_amount"]
                          else "partial" if new_paid > 0 else "unpaid")
            cursor.execute(
                "INSERT INTO payments (business_id, sale_id, customer_id, amount, payment_method, "
                "note, created_by, idempotency_key, reverses_payment_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (business_id, pay["sale_id"], pay["customer_id"], -pay["amount"],
                 pay["payment_method"], f"Reversal of payment #{payment_id}: {reason}",
                 created_by_user_id, key, payment_id),
            )
            rev_id = cursor.fetchone()["id"]
            cursor.execute(
                "UPDATE sales SET amount_paid=%s, payment_status=%s WHERE id=%s AND business_id=%s",
                (new_paid, new_status, pay["sale_id"], business_id),
            )
        return True, (f"Payment #{payment_id} of \u20A6{pay['amount']:,.2f} reversed "
                      f"(reversal ref #{rev_id}). The amount is owed again.")
    except CreditError as e:
        return None, str(e)
    except Exception as e:
        return None, integrity.friendly_db_error(e)


def update_customer_phone(customer_id, business_id, owner_user_id, phone):
    """Add or correct an existing customer's phone number (Phase 5B-1). Blank / whitespace-only / invalid numbers are rejected and nothing is changed. Scoped to the business AND its verified owner. Returns (True, message) or (None, error)."""
    try:
        _require_business(business_id, owner_user_id)
        clean, err = normalize_phone(phone)
        if err:
            return None, err
        with get_db() as (conn, cursor):
            cursor.execute(
                "UPDATE customers SET phone=%s WHERE id=%s AND business_id=%s",
                (clean, customer_id, business_id),
            )
            if cursor.rowcount == 0:
                raise CreditError("Customer not found.")
        return True, "Phone number saved."
    except Exception as e:
        return None, str(e)
