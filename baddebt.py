# baddebt.py — Business Mode: Bad-Debt Write-Off & Recovery (Phase 5A-4)
#
# ACCOUNTING MODEL (read this before changing anything here)
#
#   * The original sale / treatment bill is NEVER modified by a write-off or
#     a recovery — not its total, not amount_paid, not payment_status, not
#     its stock movements or COGS. Revenue and gross profit therefore stay
#     exactly as they were.
#   * Collectible debt for a transaction is DERIVED, never stored:
#         collectible = total - amount_paid - SUM(active write-offs)
#     "Active" means the write-off has no row in debt_write_off_reversals.
#   * A write-off is NOT a payment: it never touches the payments tables.
#   * A recovery is NOT a payment against collectible debt and NOT a sale:
#     it only reduces the unrecovered written-off balance
#         unrecovered = SUM(active write-offs) - SUM(recoveries)
#     and never touches sales, treatments, payments or inventory.
#   * One money event lands in exactly one bucket: an ordinary payment
#     (customers.record_payment / treatments.record_treatment_payment) or a
#     recovery (record_recovery below) — never both.
#
# SAME RULES as business.py/sales.py/customers.py:
#   - every public function takes business_id AND the logged-in
#     owner_user_id and re-verifies ownership via business.get_business();
#   - db.get_db() commits on ANY normal exit (even a bare return), so every
#     validation failure inside a transaction is RAISED (BadDebtError),
#     never returned, guaranteeing rollback instead of a partial commit;
#   - the parent sale/treatment row is locked (SELECT ... FOR UPDATE) for
#     the whole transaction — the same lock the payment functions take — so
#     a write-off, a recovery and an ordinary payment on the same
#     transaction can never interleave and read stale balances.
#   - Decimal / NUMERIC only. No floats for money.

from datetime import timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import psycopg2.errors

from db import get_db
from business import get_business
from sales import PAYMENT_METHODS

BUSINESS_TZ = "Africa/Lagos"

SOURCE_SALE = "sale"
SOURCE_TREATMENT = "treatment"
SOURCE_LABELS = {SOURCE_SALE: "Stock Sale", SOURCE_TREATMENT: "Treatment Bill"}

OTHER_REASON = "Other (please explain)"
WRITE_OFF_REASONS = [
    "Customer cannot be located",
    "Customer is unable to repay",
    "Customer has permanently closed their business",
    "Debt is too old to recover",
    "Customer has passed away",
    OTHER_REASON,
]

_CENT = Decimal("0.01")
_ZERO = Decimal("0")


class BadDebtError(Exception):
    """Raised for any validation failure inside a write-off / recovery
    transaction so get_db() rolls back instead of committing partial work."""
    pass


class DuplicateSubmission(BadDebtError):
    """The same idempotency key was already recorded — nothing new written."""
    pass


# ── Small helpers ────────────────────────────────────────────────────────────

def _require_business(business_id, owner_user_id):
    biz = get_business(business_id, owner_user_id)
    if biz is None:
        raise BadDebtError("This business was not found, or does not belong to you.")
    return biz


def _money(value, field_name):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise BadDebtError(f"{field_name} must be a valid number.")
    if not d.is_finite():
        raise BadDebtError(f"{field_name} must be a valid number.")
    return d.quantize(_CENT, rounding=ROUND_HALF_UP)


def _check_source(source_type):
    if source_type not in (SOURCE_SALE, SOURCE_TREATMENT):
        raise BadDebtError("Unknown transaction type.")
    return source_type


def _fk_column(source_type):
    # Whitelisted mapping — never interpolate user input into SQL.
    return "sale_id" if source_type == SOURCE_SALE else "treatment_id"


def _aware(dt):
    """Older tables (payments, treatment_payments) use naive TIMESTAMP columns
    that hold UTC (Supabase's server timezone); the 5A-4 tables use
    TIMESTAMPTZ. Normalise so both can be sorted together."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _clean_key(idempotency_key):
    key = (idempotency_key or "").strip()
    if not key or len(key) > 100:
        raise BadDebtError("Missing submission reference. Please reopen the form and try again.")
    return key


# ── SQL fragments (shared with customers.py so balances can never disagree) ─

def active_write_off_sql(source_type, alias):
    """Scalar subquery: SUM of this transaction's NON-reversed write-offs.
    `alias` is the sales/treatments table alias in the enclosing query."""
    col = _fk_column(source_type)
    return (
        "COALESCE((SELECT SUM(w.amount) FROM debt_write_offs w "
        f"WHERE w.business_id = {alias}.business_id AND w.{col} = {alias}.id "
        "AND NOT EXISTS (SELECT 1 FROM debt_write_off_reversals r "
        "WHERE r.write_off_id = w.id)), 0)"
    )


def _recovered_sql(source_type, alias):
    col = _fk_column(source_type)
    return (
        "COALESCE((SELECT SUM(rc.amount) FROM debt_recoveries rc "
        f"WHERE rc.business_id = {alias}.business_id AND rc.{col} = {alias}.id), 0)"
    )


def _treatment_total_sql(alias="t"):
    # Same bill computation as treatments.get_treatment_billing(): flat
    # service charge + every dispensing's own locked-in price. Scalar
    # subquery (not a JOIN) so nothing can multiply rows.
    return (
        f"{alias}.service_charge + COALESCE((SELECT SUM(d.quantity * d.unit_price) "
        "FROM treatment_items ti JOIN treatment_dispensing d ON d.treatment_item_id = ti.id "
        f"WHERE ti.treatment_id = {alias}.id AND ti.business_id = {alias}.business_id "
        "AND d.unit_price IS NOT NULL), 0)"
    )


def _base_rows_sql(source_type):
    """One row per transaction with every figure needed, as a derived table
    taking ONE parameter: business_id."""
    if source_type == SOURCE_SALE:
        return (
            "SELECT 'sale' AS source_type, s.id AS tx_id, s.customer_id, "
            "  ('Sale #' || s.id) AS label, s.created_at AS tx_created_at, "
            "  s.total_amount AS total, s.amount_paid AS paid, "
            f"  {active_write_off_sql(SOURCE_SALE, 's')} AS written_off, "
            f"  {_recovered_sql(SOURCE_SALE, 's')} AS recovered "
            "FROM sales s WHERE s.business_id = %s"
        )
    return (
        "SELECT 'treatment' AS source_type, t.id AS tx_id, t.customer_id, "
        "  ('Treatment: ' || t.patient_identifier) AS label, t.created_at AS tx_created_at, "
        f"  {_treatment_total_sql('t')} AS total, t.amount_paid AS paid, "
        f"  {active_write_off_sql(SOURCE_TREATMENT, 't')} AS written_off, "
        f"  {_recovered_sql(SOURCE_TREATMENT, 't')} AS recovered "
        "FROM treatments t WHERE t.business_id = %s"
    )


def _all_rows_sql(source_type=None):
    if source_type == SOURCE_SALE:
        return _base_rows_sql(SOURCE_SALE), 1
    if source_type == SOURCE_TREATMENT:
        return _base_rows_sql(SOURCE_TREATMENT), 1
    return _base_rows_sql(SOURCE_SALE) + " UNION ALL " + _base_rows_sql(SOURCE_TREATMENT), 2


# ── Locked / unlocked transaction snapshot ──────────────────────────────────

def _snapshot(cursor, source_type, tx_id, business_id, lock=False):
    """Current figures for one transaction, scoped to the business. With
    lock=True the parent row is locked FOR UPDATE until the surrounding
    transaction ends. Returns None if it doesn't exist in this business."""
    suffix = " FOR UPDATE" if lock else ""
    if source_type == SOURCE_SALE:
        cursor.execute(
            "SELECT id, customer_id, total_amount AS total, amount_paid AS paid, "
            "created_at FROM sales WHERE id=%s AND business_id=%s" + suffix,
            (tx_id, business_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        label = f"Sale #{row['id']}"
        total = row["total"]
    else:
        cursor.execute(
            "SELECT id, customer_id, service_charge, amount_paid AS paid, "
            "created_at, patient_identifier FROM treatments "
            "WHERE id=%s AND business_id=%s" + suffix,
            (tx_id, business_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cursor.execute(
            "SELECT COALESCE(SUM(d.quantity * d.unit_price) "
            "  FILTER (WHERE d.unit_price IS NOT NULL), 0) AS dispensed "
            "FROM treatment_items ti "
            "LEFT JOIN treatment_dispensing d ON d.treatment_item_id = ti.id "
            "WHERE ti.treatment_id=%s AND ti.business_id=%s",
            (tx_id, business_id),
        )
        total = row["service_charge"] + cursor.fetchone()["dispensed"]
        label = f"Treatment: {row['patient_identifier']}"

    col = _fk_column(source_type)
    cursor.execute(
        "SELECT COALESCE(SUM(w.amount), 0) AS wo FROM debt_write_offs w "
        f"WHERE w.business_id=%s AND w.{col}=%s AND NOT EXISTS "
        "(SELECT 1 FROM debt_write_off_reversals r WHERE r.write_off_id = w.id)",
        (business_id, tx_id),
    )
    written_off = cursor.fetchone()["wo"]
    cursor.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS rec FROM debt_recoveries "
        f"WHERE business_id=%s AND {col}=%s",
        (business_id, tx_id),
    )
    recovered = cursor.fetchone()["rec"]

    return {
        "source_type": source_type,
        "tx_id": row["id"],
        "label": label,
        "customer_id": row["customer_id"],
        "created_at": row["created_at"],
        "total": total,
        "paid": row["paid"],
        "written_off": written_off,
        "recovered": recovered,
        "collectible": total - row["paid"] - written_off,
        "unrecovered": written_off - recovered,
    }


def _customer(cursor, customer_id, business_id):
    cursor.execute(
        "SELECT id, name, phone FROM customers WHERE id=%s AND business_id=%s",
        (customer_id, business_id),
    )
    return cursor.fetchone()


def _locked_context(cursor, source_type, tx_id, business_id):
    snap = _snapshot(cursor, source_type, tx_id, business_id, lock=True)
    if snap is None:
        raise BadDebtError("Transaction not found in this business.")
    if snap["customer_id"] is None:
        raise BadDebtError(
            "This transaction has no customer linked to it, so it cannot be "
            "written off or recovered. Link it to a customer first."
        )
    if _customer(cursor, snap["customer_id"], business_id) is None:
        raise BadDebtError("The customer on this transaction was not found in this business.")
    return snap


def _fail(e):
    """Common outcome mapping for public functions."""
    if isinstance(e, DuplicateSubmission):
        return None, str(e)
    if isinstance(e, BadDebtError):
        return None, str(e)
    if isinstance(e, psycopg2.errors.UniqueViolation):
        return None, "This was already recorded — it has not been recorded twice."
    return None, str(e)


# ── Write-off ───────────────────────────────────────────────────────────────

def write_off_debt(source_type, transaction_id, business_id, owner_user_id,
                    created_by_user_id, amount, reason_category, reason_note,
                    idempotency_key):
    """Writes off all or part of one transaction's collectible balance.
    Returns (write_off_id, message) or (None, error_message); on failure
    nothing is written."""
    try:
        _require_business(business_id, owner_user_id)
        _check_source(source_type)
        key = _clean_key(idempotency_key)
        amount = _money(amount, "Write-off amount")
        if amount <= 0:
            raise BadDebtError("Write-off amount must be greater than zero.")

        if reason_category not in WRITE_OFF_REASONS:
            raise BadDebtError("Please choose a reason for the write-off.")
        note = (reason_note or "").strip()
        if reason_category == OTHER_REASON and not note:
            raise BadDebtError("Please explain the reason when choosing 'Other'.")

        with get_db() as (conn, cursor):
            snap = _locked_context(cursor, source_type, transaction_id, business_id)

            cursor.execute(
                "SELECT 1 FROM debt_write_offs WHERE business_id=%s AND idempotency_key=%s",
                (business_id, key),
            )
            if cursor.fetchone():
                raise DuplicateSubmission(
                    "This write-off was already recorded — it has not been recorded twice."
                )

            if snap["collectible"] <= 0:
                raise BadDebtError("There is no collectible balance left on this transaction.")
            if amount > snap["collectible"]:
                raise BadDebtError(
                    f"You can write off at most \u20A6{snap['collectible']:,.2f} "
                    f"on this transaction."
                )

            col = _fk_column(source_type)
            cursor.execute(
                f"INSERT INTO debt_write_offs (business_id, customer_id, source_type, "
                f"{col}, amount, reason_category, reason_note, idempotency_key, created_by) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (business_id, snap["customer_id"], source_type, transaction_id,
                 amount, reason_category, note or None, key, created_by_user_id),
            )
            wid = cursor.fetchone()["id"]
        return wid, f"\u20A6{amount:,.2f} written off."
    except Exception as e:
        return _fail(e)


def reverse_write_off(write_off_id, business_id, owner_user_id,
                       created_by_user_id, reason):
    """Auditable correction: records a reversal row (the write-off row stays
    forever) so the amount becomes collectible again. Not allowed if that
    would leave more recovered than written off on the transaction."""
    try:
        _require_business(business_id, owner_user_id)
        reason = (reason or "").strip()
        if not reason:
            raise BadDebtError("Please give a reason for reversing this write-off.")

        with get_db() as (conn, cursor):
            cursor.execute(
                "SELECT id, source_type, sale_id, treatment_id, amount FROM debt_write_offs "
                "WHERE id=%s AND business_id=%s",
                (write_off_id, business_id),
            )
            w = cursor.fetchone()
            if w is None:
                raise BadDebtError("Write-off not found.")
            tx_id = w["sale_id"] if w["source_type"] == SOURCE_SALE else w["treatment_id"]

            snap = _locked_context(cursor, w["source_type"], tx_id, business_id)

            cursor.execute(
                "SELECT 1 FROM debt_write_off_reversals WHERE write_off_id=%s", (write_off_id,),
            )
            if cursor.fetchone():
                raise DuplicateSubmission("This write-off has already been reversed.")

            if snap["recovered"] > snap["written_off"] - w["amount"]:
                raise BadDebtError(
                    f"This write-off can't be reversed because \u20A6{snap['recovered']:,.2f} "
                    f"has already been recovered against it."
                )

            cursor.execute(
                "INSERT INTO debt_write_off_reversals (write_off_id, business_id, reason, created_by) "
                "VALUES (%s, %s, %s, %s)",
                (write_off_id, business_id, reason, created_by_user_id),
            )
        return True, f"Write-off of \u20A6{w['amount']:,.2f} reversed. The amount is collectible again."
    except Exception as e:
        return _fail(e)


# ── Recovery ────────────────────────────────────────────────────────────────

def record_recovery(source_type, transaction_id, business_id, owner_user_id,
                     created_by_user_id, amount, payment_method, note,
                     idempotency_key):
    """Money received against a PREVIOUSLY WRITTEN-OFF amount. Reduces the
    unrecovered written-off balance only. Creates no sale, touches no
    inventory, never alters collectible debt or any payment row."""
    try:
        _require_business(business_id, owner_user_id)
        _check_source(source_type)
        key = _clean_key(idempotency_key)
        amount = _money(amount, "Recovery amount")
        if amount <= 0:
            raise BadDebtError("Recovery amount must be greater than zero.")
        if payment_method not in PAYMENT_METHODS:
            raise BadDebtError("Please choose a valid payment method.")

        with get_db() as (conn, cursor):
            snap = _locked_context(cursor, source_type, transaction_id, business_id)

            cursor.execute(
                "SELECT 1 FROM debt_recoveries WHERE business_id=%s AND idempotency_key=%s",
                (business_id, key),
            )
            if cursor.fetchone():
                raise DuplicateSubmission(
                    "This recovery was already recorded — it has not been recorded twice."
                )

            if snap["unrecovered"] <= 0:
                raise BadDebtError("There is no written-off balance left to recover on this transaction.")
            if amount > snap["unrecovered"]:
                raise BadDebtError(
                    f"You can record at most \u20A6{snap['unrecovered']:,.2f} "
                    f"as recovered on this transaction."
                )

            col = _fk_column(source_type)
            cursor.execute(
                f"INSERT INTO debt_recoveries (business_id, customer_id, source_type, {col}, "
                f"amount, payment_method, note, idempotency_key, created_by) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (business_id, snap["customer_id"], source_type, transaction_id, amount,
                 payment_method, (note or "").strip() or None, key, created_by_user_id),
            )
            rid = cursor.fetchone()["id"]
        return rid, f"Recovery of \u20A6{amount:,.2f} recorded."
    except Exception as e:
        return _fail(e)


# ── Reads (all scoped to business_id AND verified owner) ────────────────────

def get_transaction_snapshot(source_type, transaction_id, business_id, owner_user_id):
    """Figures for the confirmation screen: customer, original total, paid,
    previously written off, collectible, recovered. None if not found."""
    _require_business(business_id, owner_user_id)
    _check_source(source_type)
    with get_db() as (conn, cursor):
        snap = _snapshot(cursor, source_type, transaction_id, business_id)
        if snap is None:
            return None
        cust = _customer(cursor, snap["customer_id"], business_id) if snap["customer_id"] else None
        snap["customer_name"] = cust["name"] if cust else None
        snap["customer_phone"] = cust["phone"] if cust else None
        return snap


def _rows_with_customers(business_id, where_sql, source_type=None):
    base, n = _all_rows_sql(source_type)
    sql = (
        f"SELECT x.*, c.name AS customer_name, c.phone AS customer_phone "
        f"FROM ({base}) x JOIN customers c ON c.id = x.customer_id AND c.business_id = %s "
        f"WHERE {where_sql} ORDER BY x.tx_created_at DESC, x.tx_id DESC"
    )
    params = (business_id,) * n + (business_id,)
    with get_db() as (conn, cursor):
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
    for r in rows:
        r["collectible"] = r["total"] - r["paid"] - r["written_off"]
        r["unrecovered"] = r["written_off"] - r["recovered"]
    return rows


def get_collectible_debts(business_id, owner_user_id, source_type=None):
    """Transactions that still have a collectible balance (candidates for a
    write-off). Only transactions linked to a customer are listed."""
    _require_business(business_id, owner_user_id)
    return _rows_with_customers(
        business_id, "x.total - x.paid - x.written_off > 0", source_type)


def get_unrecovered_write_offs(business_id, owner_user_id, source_type=None):
    """Transactions with a written-off balance not yet recovered
    (candidates for recording a recovery)."""
    _require_business(business_id, owner_user_id)
    return _rows_with_customers(
        business_id, "x.written_off - x.recovered > 0", source_type)


def get_bad_debt_summary(business_id, owner_user_id):
    """Lifetime totals. 'Written off' counts ACTIVE (non-reversed)
    write-offs only; reversed ones are shown separately."""
    _require_business(business_id, owner_user_id)
    base, n = _all_rows_sql(None)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT COALESCE(SUM(written_off), 0) AS total_written_off, "
            "  COALESCE(SUM(recovered), 0) AS total_recovered, "
            "  COUNT(*) FILTER (WHERE written_off > 0) AS written_off_transactions, "
            "  COUNT(*) FILTER (WHERE recovered > 0) AS transactions_with_recovery "
            f"FROM ({base}) x",
            (business_id,) * n,
        )
        row = dict(cursor.fetchone())
        cursor.execute(
            "SELECT COALESCE(SUM(w.amount), 0) AS reversed_total "
            "FROM debt_write_offs w JOIN debt_write_off_reversals r ON r.write_off_id = w.id "
            "WHERE w.business_id=%s",
            (business_id,),
        )
        row["reversed_total"] = cursor.fetchone()["reversed_total"]
    row["unrecovered"] = row["total_written_off"] - row["total_recovered"]
    return row


def _date_filter(col, start_date, end_date):
    # Business-day filter in Africa/Lagos on the TIMESTAMPTZ event time.
    sql, params = "", []
    if start_date is not None and end_date is not None:
        sql = f" AND ({col} AT TIME ZONE '{BUSINESS_TZ}')::date BETWEEN %s AND %s"
        params = [start_date, end_date]
    return sql, params


def _paid_before(cursor, source_type, tx_id, business_id, at):
    if source_type == SOURCE_SALE:
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM payments "
            "WHERE sale_id=%s AND business_id=%s AND created_at <= %s",
            (tx_id, business_id, at),
        )
    else:
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM treatment_payments "
            "WHERE treatment_id=%s AND business_id=%s AND created_at <= %s",
            (tx_id, business_id, at),
        )
    return cursor.fetchone()["s"]


def get_write_off_events(business_id, owner_user_id, start_date=None, end_date=None,
                          source_type=None):
    """Every write-off (including reversed ones, flagged) dated by the day it
    was actually made — never by the original sale date. Newest first."""
    _require_business(business_id, owner_user_id)
    if source_type is not None:
        _check_source(source_type)
    fsql, fparams = _date_filter("w.created_at", start_date, end_date)
    sql = (
        "SELECT w.id, w.source_type, w.sale_id, w.treatment_id, w.customer_id, "
        "  c.name AS customer_name, c.phone AS customer_phone, w.amount, "
        "  w.reason_category, w.reason_note, w.created_at, u.username AS authorized_by, "
        "  (r.id IS NOT NULL) AS reversed, r.created_at AS reversed_at, "
        "  r.reason AS reversal_reason "
        "FROM debt_write_offs w "
        "JOIN customers c ON c.id = w.customer_id AND c.business_id = w.business_id "
        "LEFT JOIN users u ON u.id = w.created_by "
        "LEFT JOIN debt_write_off_reversals r ON r.write_off_id = w.id "
        "WHERE w.business_id = %s"
    )
    params = [business_id]
    if source_type is not None:
        sql += " AND w.source_type = %s"
        params.append(source_type)
    sql += fsql + " ORDER BY w.created_at DESC, w.id DESC"
    params += fparams

    with get_db() as (conn, cursor):
        cursor.execute(sql, params)
        events = [dict(e) for e in cursor.fetchall()]
        cache = {}
        for e in events:
            tx_id = e["sale_id"] if e["source_type"] == SOURCE_SALE else e["treatment_id"]
            key = (e["source_type"], tx_id)
            if key not in cache:
                cache[key] = _snapshot(cursor, e["source_type"], tx_id, business_id)
            snap = cache[key]
            e["tx_id"] = tx_id
            e["tx_label"] = snap["label"]
            e["original_total"] = snap["total"]
            e["paid_before_write_off"] = _paid_before(
                cursor, e["source_type"], tx_id, business_id, e["created_at"])
            e["recovered"] = snap["recovered"]
            e["unrecovered"] = snap["unrecovered"]
            e["status"] = (
                "Reversed" if e["reversed"]
                else ("Fully Recovered" if snap["unrecovered"] <= 0 and snap["recovered"] > 0
                      else ("Partly Recovered" if snap["recovered"] > 0 else "Written Off"))
            )
        return events


def get_recovery_events(business_id, owner_user_id, start_date=None, end_date=None,
                         source_type=None):
    """Every recovery, dated by the day the money was actually received."""
    _require_business(business_id, owner_user_id)
    if source_type is not None:
        _check_source(source_type)
    fsql, fparams = _date_filter("rc.created_at", start_date, end_date)
    sql = (
        "SELECT rc.id, rc.source_type, rc.sale_id, rc.treatment_id, rc.customer_id, "
        "  c.name AS customer_name, c.phone AS customer_phone, rc.amount, "
        "  rc.payment_method, rc.note, rc.created_at, u.username AS authorized_by "
        "FROM debt_recoveries rc "
        "JOIN customers c ON c.id = rc.customer_id AND c.business_id = rc.business_id "
        "LEFT JOIN users u ON u.id = rc.created_by "
        "WHERE rc.business_id = %s"
    )
    params = [business_id]
    if source_type is not None:
        sql += " AND rc.source_type = %s"
        params.append(source_type)
    sql += fsql + " ORDER BY rc.created_at DESC, rc.id DESC"
    params += fparams

    with get_db() as (conn, cursor):
        cursor.execute(sql, params)
        events = [dict(e) for e in cursor.fetchall()]
        cache = {}
        for e in events:
            tx_id = e["sale_id"] if e["source_type"] == SOURCE_SALE else e["treatment_id"]
            key = (e["source_type"], tx_id)
            if key not in cache:
                cache[key] = _snapshot(cursor, e["source_type"], tx_id, business_id)
            e["tx_id"] = tx_id
            e["tx_label"] = cache[key]["label"]
            e["remaining_recoverable"] = cache[key]["unrecovered"]
        return events


def get_transaction_history(source_type, transaction_id, business_id, owner_user_id):
    """Full chronological history of one transaction: ordinary payments,
    write-offs, reversals and recoveries — each kept distinct."""
    _require_business(business_id, owner_user_id)
    _check_source(source_type)
    col = _fk_column(source_type)
    pay_table = "payments" if source_type == SOURCE_SALE else "treatment_payments"
    pay_col = "sale_id" if source_type == SOURCE_SALE else "treatment_id"
    with get_db() as (conn, cursor):
        snap = _snapshot(cursor, source_type, transaction_id, business_id)
        if snap is None:
            return None, []
        events = []
        cursor.execute(
            f"SELECT p.amount, p.payment_method, p.note, p.created_at, u.username "
            f"FROM {pay_table} p LEFT JOIN users u ON u.id = p.created_by "
            f"WHERE p.{pay_col}=%s AND p.business_id=%s",
            (transaction_id, business_id),
        )
        for r in cursor.fetchall():
            events.append({"kind": "Payment", "amount": r["amount"], "at": _aware(r["created_at"]),
                           "detail": f"via {r['payment_method'] or 'unspecified'}"
                                     + (f" \u2014 {r['note']}" if r["note"] else ""),
                           "by": r["username"]})
        cursor.execute(
            f"SELECT w.id, w.amount, w.reason_category, w.reason_note, w.created_at, "
            f"  u.username, r.created_at AS rev_at, r.reason AS rev_reason, ru.username AS rev_by "
            f"FROM debt_write_offs w LEFT JOIN users u ON u.id = w.created_by "
            f"LEFT JOIN debt_write_off_reversals r ON r.write_off_id = w.id "
            f"LEFT JOIN users ru ON ru.id = r.created_by "
            f"WHERE w.{col}=%s AND w.business_id=%s",
            (transaction_id, business_id),
        )
        for r in cursor.fetchall():
            events.append({"kind": "Write-off", "amount": r["amount"], "at": r["created_at"],
                           "detail": r["reason_category"]
                                     + (f" \u2014 {r['reason_note']}" if r["reason_note"] else ""),
                           "by": r["username"]})
            if r["rev_at"] is not None:
                events.append({"kind": "Write-off reversed", "amount": r["amount"],
                               "at": r["rev_at"], "detail": r["rev_reason"], "by": r["rev_by"]})
        cursor.execute(
            f"SELECT rc.amount, rc.payment_method, rc.note, rc.created_at, u.username "
            f"FROM debt_recoveries rc LEFT JOIN users u ON u.id = rc.created_by "
            f"WHERE rc.{col}=%s AND rc.business_id=%s",
            (transaction_id, business_id),
        )
        for r in cursor.fetchall():
            events.append({"kind": "Recovery", "amount": r["amount"], "at": r["created_at"],
                           "detail": f"via {r['payment_method']}"
                                     + (f" \u2014 {r['note']}" if r["note"] else ""),
                           "by": r["username"]})
    events.sort(key=lambda e: e["at"], reverse=True)
    return snap, events
