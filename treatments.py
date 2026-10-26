# treatments.py — Business Mode: Treatment Management (Phase 4D)
#
# SAME RULE as business.py/inventory.py/sales.py/customers.py: every
# function takes business_id AND the logged-in owner_user_id, and
# re-verifies ownership via business.get_business() before touching
# anything. treatment_id / treatment_item_id are additionally always
# scoped by business_id in their own WHERE clauses.
#
# CRITICAL POLICY (per the project spec): creating a treatment plan is
# NOT an inventory event. create_treatment() never writes to products or
# inventory_movements — it only records what was planned. Only
# record_dispensing(), one call per actual "stock issued" action, ever
# touches inventory — and it reuses the SAME inventory_movements ledger
# sales.py and inventory.py already write to (movement_type =
# 'treatment_dispensing'), not a second stock system.
#
# This file does NOT record "administration" separately from
# "dispensing" — the project spec distinguishes dispensed vs.
# administered, but only dispensing has an inventory effect (stock
# actually leaving the business), so that's the event this phase
# implements. A free-text note on each dispensing row lets staff record
# what it covered.
#
# This file does not diagnose, prescribe, or recommend anything — every
# field here records an instruction or action a qualified person already
# decided; nothing is calculated except the optional planned_quantity
# arithmetic the spec explicitly asks for.

from datetime import date
from decimal import Decimal, InvalidOperation

from db import get_db
from business import get_business
from sales import get_or_create_customer

ROUTES = ["Oral", "Injection", "Topical", "Other / Not specified"]
STATUSES = ["planned", "in_progress", "completed", "cancelled"]
STATUS_LABELS = {
    "planned": "Planned", "in_progress": "In Progress",
    "completed": "Completed", "cancelled": "Cancelled",
}


class TreatmentError(Exception):
    pass


def _to_decimal(value, field_name, allow_none=False):
    if value is None or value == "":
        if allow_none:
            return None
        raise TreatmentError(f"{field_name} is required.")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise TreatmentError(f"{field_name} must be a valid number.")


def _require_business(business_id, owner_user_id):
    biz = get_business(business_id, owner_user_id)
    if biz is None:
        raise TreatmentError("This business was not found, or does not belong to you.")
    return biz


# ── Create ───────────────────────────────────────────────────────────────────

def create_treatment(business_id, owner_user_id, created_by_user_id,
                      patient_identifier, patient_phone, diagnosis,
                      start_date, duration_days, notes, items, service_charge=0):
    """
    patient_phone and diagnosis are both optional — this records what a
    qualified person already determined (a condition name, a phone
    number for contact), never something the app infers or suggests.
    service_charge is a flat fee (e.g. a consultation charge), separate
    from whatever medicines end up dispensed — see get_treatment_billing().
    items: list of dicts with keys product_id, quantity_per_administration,
    administrations_per_day (optional), duration_days (optional),
    route (optional), notes (optional).
    Writes treatments + treatment_items only — no inventory effect.
    """
    _require_business(business_id, owner_user_id)

    patient_identifier = (patient_identifier or "").strip()
    if not patient_identifier:
        return None, "Patient name or identifier is required."
    if not start_date:
        return None, "Treatment date is required."
    if not items:
        return None, "Add at least one product to the treatment."

    try:
        service_charge_dec = _to_decimal(service_charge, "Service charge") if service_charge else Decimal("0")
        if service_charge_dec < 0:
            return None, "Service charge cannot be negative."

        clean_items = []
        for it in items:
            qty = _to_decimal(it.get("quantity_per_administration"), "Quantity per administration")
            if qty <= 0:
                return None, "Quantity per administration must be greater than zero."
            admins_per_day = _to_decimal(it.get("administrations_per_day"), "Administrations per day", allow_none=True)
            item_duration = it.get("duration_days") or None

            planned_quantity = None
            if admins_per_day is not None and item_duration:
                planned_quantity = qty * admins_per_day * Decimal(str(item_duration))

            clean_items.append({
                "product_id": it["product_id"],
                "quantity_per_administration": qty,
                "administrations_per_day": admins_per_day,
                "duration_days": item_duration,
                "route": it.get("route") or None,
                "planned_quantity": planned_quantity,
                "notes": it.get("notes") or None,
            })

        # Link to the SAME customers table stock sales use, via the
        # existing name-based dedup in get_or_create_customer() — so a
        # patient who also has a stock-sale debt is the one customer
        # record, not two. Called BEFORE opening the treatment's own
        # transaction below: calling it from inside would open a second
        # database connection mid-transaction, the same nested-connection
        # bug already fixed once in record_treatment_payment().
        # Limitation: matching is exact-name, scoped to this business —
        # if two different anonymous patients are both given the same
        # generic identifier (e.g. both called "Patient 001"), they will
        # be merged into one customer record. Distinct identifiers avoid
        # this; there's no other way to tell two "Patient 001"s apart.
        customer_id = get_or_create_customer(business_id, owner_user_id, patient_identifier, patient_phone)

        with get_db() as (conn, cursor):
            # Confirm every referenced product genuinely belongs to this
            # business before writing anything — a product_id from the
            # dropdown should always be real, but this is the hard
            # guarantee, not an assumption.
            for it in clean_items:
                cursor.execute(
                    "SELECT id FROM products WHERE id=%s AND business_id=%s",
                    (it["product_id"], business_id),
                )
                if cursor.fetchone() is None:
                    raise TreatmentError("One of the selected products was not found in this business's inventory.")

            cursor.execute(
                "INSERT INTO treatments (business_id, patient_identifier, patient_phone, "
                "diagnosis, start_date, duration_days, status, notes, service_charge, "
                "customer_id, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'planned', %s, %s, %s, %s, %s) RETURNING id",
                (business_id, patient_identifier, (patient_phone or "").strip() or None,
                 (diagnosis or "").strip() or None, start_date, duration_days or None,
                 notes or None, service_charge_dec, customer_id, created_by_user_id),
            )
            treatment_id = cursor.fetchone()["id"]

            for it in clean_items:
                cursor.execute(
                    "INSERT INTO treatment_items (treatment_id, business_id, product_id, "
                    "quantity_per_administration, administrations_per_day, duration_days, "
                    "route, planned_quantity, notes) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (treatment_id, business_id, it["product_id"],
                     it["quantity_per_administration"], it["administrations_per_day"],
                     it["duration_days"], it["route"], it["planned_quantity"], it["notes"]),
                )

        return treatment_id, "Treatment plan created"
    except TreatmentError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


# ── Reads ────────────────────────────────────────────────────────────────────

def get_treatments(business_id, owner_user_id, status_filter=None):
    """Includes drug_names — a single comma-joined summary of every
    product used in each treatment, computed in one aggregate query
    rather than one extra query per treatment row (which would otherwise
    be an N+1 query pattern on this list page)."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        base = (
            "SELECT t.*, STRING_AGG(DISTINCT p.name, ', ' ORDER BY p.name) AS drug_names "
            "FROM treatments t "
            "LEFT JOIN treatment_items ti ON ti.treatment_id = t.id "
            "LEFT JOIN products p ON ti.product_id = p.id "
            "WHERE t.business_id=%s "
        )
        if status_filter:
            cursor.execute(
                base + "AND t.status=%s GROUP BY t.id ORDER BY t.start_date DESC, t.id DESC",
                (business_id, status_filter),
            )
        else:
            cursor.execute(
                base + "GROUP BY t.id ORDER BY t.start_date DESC, t.id DESC",
                (business_id,),
            )
        return cursor.fetchall()


def get_treatment(treatment_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM treatments WHERE id=%s AND business_id=%s",
            (treatment_id, business_id),
        )
        return cursor.fetchone()


def get_treatment_items(treatment_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT ti.*, p.name AS product_name, p.unit AS product_unit, "
            "p.current_stock AS product_current_stock "
            "FROM treatment_items ti "
            "JOIN products p ON ti.product_id = p.id "
            "WHERE ti.treatment_id=%s AND ti.business_id=%s ORDER BY ti.id",
            (treatment_id, business_id),
        )
        return cursor.fetchall()


def get_dispensing_history(treatment_item_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT d.*, u.username AS recorded_by_username "
            "FROM treatment_dispensing d LEFT JOIN users u ON d.created_by = u.id "
            "WHERE d.treatment_item_id=%s AND d.business_id=%s "
            "ORDER BY d.dispensed_at DESC",
            (treatment_item_id, business_id),
        )
        return cursor.fetchall()


def get_treatment_dashboard_summary(business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    today = date.today()
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT "
            "  COUNT(*) AS total_treatments, "
            "  COUNT(*) FILTER (WHERE status='in_progress') AS in_progress, "
            "  COUNT(*) FILTER (WHERE status='completed') AS completed, "
            "  COUNT(*) FILTER (WHERE status='planned' AND start_date > %s) AS scheduled, "
            "  COUNT(*) FILTER (WHERE status='cancelled') AS cancelled "
            "FROM treatments WHERE business_id=%s",
            (today, business_id),
        )
        return cursor.fetchone()


# ── Status changes (always explicit — never date-driven) ────────────────────

def update_treatment_status(treatment_id, business_id, owner_user_id, new_status):
    _require_business(business_id, owner_user_id)
    if new_status not in STATUSES:
        return None, "Invalid status."
    try:
        with get_db() as (conn, cursor):
            cursor.execute(
                "UPDATE treatments SET status=%s WHERE id=%s AND business_id=%s",
                (new_status, treatment_id, business_id),
            )
            if cursor.rowcount == 0:
                raise TreatmentError("Treatment not found.")
        return True, f"Status updated to {STATUS_LABELS.get(new_status, new_status)}."
    except TreatmentError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


# ── Dispensing (the only treatment event that touches inventory) ────────────

def record_dispensing(treatment_item_id, business_id, owner_user_id,
                       created_by_user_id, quantity, note):
    _require_business(business_id, owner_user_id)

    try:
        quantity = _to_decimal(quantity, "Quantity")
        if quantity <= 0:
            return None, "Quantity must be greater than zero."

        with get_db() as (conn, cursor):
            cursor.execute(
                "SELECT ti.id, ti.product_id, ti.quantity_dispensed "
                "FROM treatment_items ti "
                "WHERE ti.id=%s AND ti.business_id=%s FOR UPDATE",
                (treatment_item_id, business_id),
            )
            item = cursor.fetchone()
            if item is None:
                raise TreatmentError("Treatment item not found.")

            # Lock the product row too — same technique as inventory.py
            # and sales.py — so a sale and a dispensing happening at the
            # same moment can't both read the same stale stock.
            cursor.execute(
                "SELECT id, name, unit, current_stock, selling_price, purchase_price "
                "FROM products WHERE id=%s AND business_id=%s FOR UPDATE",
                (item["product_id"], business_id),
            )
            product = cursor.fetchone()
            if product is None:
                raise TreatmentError("The product for this treatment item was not found.")
            if quantity > product["current_stock"]:
                raise TreatmentError(
                    f"Not enough stock of '{product['name']}' — "
                    f"only {product['current_stock']:g} {product['unit']} available."
                )

            before = product["current_stock"]
            after = before - quantity
            # Snapshot both price (what the patient is billed for this
            # dispensing) and cost (for treatment gross-profit reporting)
            # at the moment stock actually leaves the shop — same
            # immutability principle as sale_items in sales.py. A later
            # change to the product's price/cost must never rewrite what
            # this dispensing was actually billed or cost at the time.
            unit_price = product["selling_price"]
            unit_cost = product["purchase_price"]

            cursor.execute(
                "UPDATE products SET current_stock=%s, updated_at=NOW() "
                "WHERE id=%s AND business_id=%s",
                (after, product["id"], business_id),
            )
            cursor.execute(
                "INSERT INTO inventory_movements (business_id, product_id, movement_type, "
                "quantity, quantity_before, quantity_after, unit_cost, note, created_by) "
                "VALUES (%s, %s, 'treatment_dispensing', %s, %s, %s, %s, %s, %s)",
                (business_id, product["id"], -quantity, before, after, unit_cost,
                 f"Treatment item #{treatment_item_id}" + (f" \u2014 {note}" if note else ""),
                 created_by_user_id),
            )
            cursor.execute(
                "INSERT INTO treatment_dispensing (treatment_item_id, business_id, "
                "quantity, unit_price, unit_cost, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
                (treatment_item_id, business_id, quantity, unit_price, unit_cost, created_by_user_id),
            )
            cursor.execute(
                "UPDATE treatment_items SET quantity_dispensed = quantity_dispensed + %s "
                "WHERE id=%s AND business_id=%s",
                (quantity, treatment_item_id, business_id),
            )

        return True, (
            f"Dispensed {quantity:g} {product['unit']} of '{product['name']}' "
            f"\u2014 \u20A6{(quantity * unit_price):,.2f} added to the treatment bill."
        )
    except TreatmentError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


# ── Treatment billing (Phase 5A-2) ──────────────────────────────────────────
#
# A treatment's total bill is NOT stored as a single number — it's computed
# live as service_charge + SUM(every dispensing's own snapshotted
# quantity x unit_price). This is deliberate: a treatment accrues charges
# over potentially several days of dispensing, unlike a sale which is a
# one-shot transaction with a fixed total at creation. Each individual
# dispensing event IS immutable once recorded (its unit_price/unit_cost
# never change after the fact), so the aggregate is always an honest sum
# of real, historical, locked-in events — never a number that could have
# been retroactively altered by a later price change.

def get_treatment_billing(treatment_id, business_id, owner_user_id):
    """Returns total_bill, amount_paid, outstanding, payment_status, and
    (where every dispensing line has a known cost) cogs/gross_profit.
    Lines dispensed before the 5A-2 migration have NULL unit_price/
    unit_cost — excluded from the bill and cost sums, counted separately
    as `lines_missing_price`, never treated as free or zero-cost."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT t.service_charge, t.amount_paid, "
            "  COALESCE(SUM(d.quantity * d.unit_price) FILTER (WHERE d.unit_price IS NOT NULL), 0) "
            "    AS dispensed_charges, "
            "  COALESCE(SUM(d.quantity * d.unit_cost) FILTER (WHERE d.unit_cost IS NOT NULL), 0) "
            "    AS cogs, "
            "  COUNT(d.id) FILTER (WHERE d.unit_price IS NULL) AS lines_missing_price "
            "FROM treatments t "
            "LEFT JOIN treatment_items ti ON ti.treatment_id = t.id "
            "LEFT JOIN treatment_dispensing d ON d.treatment_item_id = ti.id "
            "WHERE t.id=%s AND t.business_id=%s "
            "GROUP BY t.id",
            (treatment_id, business_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        total_bill = row["service_charge"] + row["dispensed_charges"]
        amount_paid = row["amount_paid"]
        outstanding = total_bill - amount_paid
        if outstanding <= 0 and total_bill > 0:
            payment_status = "paid"
        elif amount_paid > 0:
            payment_status = "partial"
        else:
            payment_status = "unpaid"

        gross_profit = row["dispensed_charges"] - row["cogs"]
        return {
            "total_bill": total_bill,
            "service_charge": row["service_charge"],
            "dispensed_charges": row["dispensed_charges"],
            "amount_paid": amount_paid,
            "outstanding": outstanding,
            "payment_status": payment_status,
            "cogs": row["cogs"],
            "gross_profit": gross_profit,
            "lines_missing_price": row["lines_missing_price"],
            "incomplete": row["lines_missing_price"] > 0,
        }


def record_treatment_payment(treatment_id, business_id, owner_user_id,
                              created_by_user_id, amount, payment_method, note):
    _require_business(business_id, owner_user_id)

    try:
        amount = _to_decimal(amount, "Payment amount")
        if amount <= 0:
            return None, "Payment amount must be greater than zero."

        with get_db() as (conn, cursor):
            # Lock the treatment row for this whole transaction so two
            # near-simultaneous payments can't both read the same stale
            # outstanding balance. (Does not lock treatment_dispensing —
            # a dispensing happening at the exact same instant as a
            # payment is a rare edge case not guarded against here.)
            cursor.execute(
                "SELECT service_charge, amount_paid FROM treatments "
                "WHERE id=%s AND business_id=%s FOR UPDATE",
                (treatment_id, business_id),
            )
            treatment = cursor.fetchone()
            if treatment is None:
                raise TreatmentError("Treatment not found.")

            # Compute the current bill on the SAME cursor/transaction —
            # never call get_treatment_billing() here, since that opens
            # its own separate connection and wouldn't see this lock.
            cursor.execute(
                "SELECT COALESCE(SUM(d.quantity * d.unit_price) "
                "  FILTER (WHERE d.unit_price IS NOT NULL), 0) AS dispensed_charges "
                "FROM treatment_items ti "
                "LEFT JOIN treatment_dispensing d ON d.treatment_item_id = ti.id "
                "WHERE ti.treatment_id=%s AND ti.business_id=%s",
                (treatment_id, business_id),
            )
            dispensed_charges = cursor.fetchone()["dispensed_charges"]
            total_bill = treatment["service_charge"] + dispensed_charges
            outstanding = total_bill - treatment["amount_paid"]

            if outstanding <= 0:
                raise TreatmentError("This treatment bill is already fully paid.")
            if amount > outstanding:
                raise TreatmentError(
                    f"Payment cannot exceed the outstanding balance of \u20A6{outstanding:,.2f}."
                )

            cursor.execute(
                "INSERT INTO treatment_payments (treatment_id, business_id, amount, "
                "payment_method, note, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
                (treatment_id, business_id, amount, payment_method, note or None,
                 created_by_user_id),
            )
            cursor.execute(
                "UPDATE treatments SET amount_paid = amount_paid + %s "
                "WHERE id=%s AND business_id=%s",
                (amount, treatment_id, business_id),
            )

        return True, f"Payment of \u20A6{amount:,.2f} recorded."
    except TreatmentError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


def get_today_treatment_summary(business_id, owner_user_id):
    """Treatment-side revenue and collections for today, using the same
    transaction-dated convention as sales.get_today_sales_summary():
    revenue is dated by when it was actually earned (dispensing date for
    medicine charges, creation date for the flat service charge),
    collections are dated by when the payment was actually received —
    these can be two different dates for the same treatment."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT "
            "  COALESCE((SELECT SUM(service_charge) FROM treatments "
            "    WHERE business_id=%s AND created_at::date = CURRENT_DATE), 0) AS service_charges_today, "
            "  COALESCE((SELECT SUM(d.quantity * d.unit_price) "
            "    FROM treatment_dispensing d "
            "    WHERE d.business_id=%s AND d.dispensed_at::date = CURRENT_DATE "
            "    AND d.unit_price IS NOT NULL), 0) AS dispensed_charges_today, "
            "  COALESCE((SELECT SUM(amount) FROM treatment_payments "
            "    WHERE business_id=%s AND created_at::date = CURRENT_DATE), 0) AS payments_today",
            (business_id, business_id, business_id),
        )
        row = cursor.fetchone()
        return {
            "revenue_today": row["service_charges_today"] + row["dispensed_charges_today"],
            "payments_today": row["payments_today"],
        }


def get_treatment_payments(treatment_id, business_id, owner_user_id):
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT p.*, u.username AS recorded_by_username "
            "FROM treatment_payments p LEFT JOIN users u ON p.created_by = u.id "
            "WHERE p.treatment_id=%s AND p.business_id=%s "
            "ORDER BY p.created_at DESC",
            (treatment_id, business_id),
        )
        return cursor.fetchall()
