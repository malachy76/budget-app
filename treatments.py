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
                      start_date, duration_days, notes, items):
    """
    patient_phone and diagnosis are both optional — this records what a
    qualified person already determined (a condition name, a phone
    number for contact), never something the app infers or suggests.
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

    try:
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
                "diagnosis, start_date, duration_days, status, notes, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'planned', %s, %s) RETURNING id",
                (business_id, patient_identifier, (patient_phone or "").strip() or None,
                 (diagnosis or "").strip() or None, start_date, duration_days or None,
                 notes or None, created_by_user_id),
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

    quantity = _to_decimal(quantity, "Quantity")
    if quantity <= 0:
        return None, "Quantity must be greater than zero."

    try:
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
                "SELECT id, name, unit, current_stock FROM products "
                "WHERE id=%s AND business_id=%s FOR UPDATE",
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

            cursor.execute(
                "UPDATE products SET current_stock=%s, updated_at=NOW() "
                "WHERE id=%s AND business_id=%s",
                (after, product["id"], business_id),
            )
            cursor.execute(
                "INSERT INTO inventory_movements (business_id, product_id, movement_type, "
                "quantity, quantity_before, quantity_after, note, created_by) "
                "VALUES (%s, %s, 'treatment_dispensing', %s, %s, %s, %s, %s)",
                (business_id, product["id"], -quantity, before, after,
                 f"Treatment item #{treatment_item_id}" + (f" \u2014 {note}" if note else ""),
                 created_by_user_id),
            )
            cursor.execute(
                "INSERT INTO treatment_dispensing (treatment_item_id, business_id, "
                "quantity, created_by) VALUES (%s, %s, %s, %s)",
                (treatment_item_id, business_id, quantity, created_by_user_id),
            )
            cursor.execute(
                "UPDATE treatment_items SET quantity_dispensed = quantity_dispensed + %s "
                "WHERE id=%s AND business_id=%s",
                (quantity, treatment_item_id, business_id),
            )

        return True, f"Dispensed {quantity:g} {product['unit']} of '{product['name']}'."
    except TreatmentError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)
