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
from contacts import normalize_phone, PHONE_REQUIRED_MSG
import costing
import integrity
from costing import CostingError, snapshot_cost, known_cost_sql

PAYMENT_METHODS = ["Cash", "Bank Transfer", "POS", "Other"]


class SaleError(Exception):
    """Raised for any validation failure inside the sale transaction, so get_db() rolls back instead of committing partial work."""
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

def get_today_sales_summary(business_id, owner_user_id):
    """Sales made today vs. payments actually received today — kept as two separate numbers on purpose. A payment received today might be against a sale made last week; a sale made today might still be sitting as outstanding credit. Conflating the two would misrepresent cash flow, which the project's own spec is explicit about avoiding."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT "
            " COALESCE((SELECT SUM(total_amount) FROM sales "
            " WHERE business_id=%s AND created_at::date = CURRENT_DATE), 0) AS sales_today, "
            " COALESCE((SELECT SUM(amount) FROM payments "
            " WHERE business_id=%s AND created_at::date = CURRENT_DATE), 0) AS payments_today, "
            # Phase 5C: value of goods returned today, and money actually refunded today
            " COALESCE((SELECT SUM(return_value) FROM sale_returns "
            " WHERE business_id=%s AND created_at::date = CURRENT_DATE), 0) AS returns_today, "
            " COALESCE((SELECT SUM(refund_amount) FROM sale_returns "
            " WHERE business_id=%s AND created_at::date = CURRENT_DATE), 0) AS refunds_today",
            (business_id, business_id, business_id, business_id),
        )
        return cursor.fetchone()


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

def _get_or_create_customer_tx(cursor, business_id, name, phone, require_phone=False):
    """The get-or-create logic, on the CALLER's cursor so it can run inside another transaction (create_sale) and roll back with it. Phase 5B-3: a transaction-scoped advisory lock on (business, name) makes two simultaneous submissions for the same new customer queue up instead of both inserting — there is no UNIQUE(business_id, name) index (existing data may already hold same-name rows), so the lock is what keeps the 'one customer, one row' promise under concurrency."""
    name = (name or "").strip()
    if not name:
        return None

    typed = (phone or "").strip()
    clean = None
    if typed:
        clean, err = normalize_phone(typed)
        if err:
            raise SaleError(err)          # a typed number must always be sane

    integrity.lock_name(cursor, business_id, "customer", name)
    cursor.execute(
        "SELECT id, phone FROM customers WHERE business_id=%s AND name=%s ORDER BY id LIMIT 1",
        (business_id, name),
    )
    existing = cursor.fetchone()
    if existing:
        on_file_ok = normalize_phone(existing["phone"])[0] is not None
        if clean and not on_file_ok:
            # Customer had no (valid) number: save the one just typed.
            cursor.execute(
                "UPDATE customers SET phone=%s WHERE id=%s AND business_id=%s",
                (clean, existing["id"], business_id),
            )
        elif require_phone and not on_file_ok:
            raise SaleError(PHONE_REQUIRED_MSG)
        return existing["id"]
    if require_phone and not clean:
        raise SaleError(PHONE_REQUIRED_MSG)
    cursor.execute(
        "INSERT INTO customers (business_id, name, phone) "
        "VALUES (%s, %s, %s) RETURNING id",
        (business_id, name, clean),
    )
    return cursor.fetchone()["id"]


def get_or_create_customer(business_id, owner_user_id, name, phone, require_phone=False):
    """Exact-name match against existing customers for this business, to avoid duplicate rows for a repeat customer typed the same way. Not fuzzy matching — a proper customer picker is Phase 4C. Returns None for a blank name (walk-in customer, not tracked). Phase 5B-1 phone rules: * require_phone=True (used whenever money will be owed): the customer MUST end up with a valid phone number — either the one typed now, or one already on file. Blank/whitespace/invalid -> SaleError, and no customer row is created or changed. * require_phone=False (ordinary cash sale): a phone is optional, but if one is typed it must still be valid. * A phone typed for an existing customer who has none on file is saved onto that customer (previously it was silently dropped). Phase 5B-3: create_sale() can now do this inside the sale's own transaction (pass customer_name / customer_phone to it), so a sale that fails leaves no stray customer behind. This stand-alone form remains for treatments and older callers."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        return _get_or_create_customer_tx(cursor, business_id, name, phone, require_phone)


# ── Sale creation ────────────────────────────────────────────────────────────

def create_sale(business_id, owner_user_id, created_by_user_id, items, customer_id, amount_paid, payment_method, idempotency_key=None, customer_name=None, customer_phone=None):
    """ items: list of {"product_id": int, "quantity": <number-like>} Returns (sale_id, message). On failure, sale_id is None and message explains why — nothing is written to the database in that case. Phase 5B-3 * idempotency_key: a per-form submission reference. The same key sent again (double-click, rerun, retry after a timeout) returns the ORIGINAL sale (sale_id of the first attempt, message saying it was already recorded) and writes nothing. Checked first, inside the transaction and under an advisory lock, so even two simultaneous submissions can't both succeed. * Same product on several cart lines is handled correctly: quantities are totalled per product BEFORE the stock check (previously each line was checked against the full stock on its own, so two lines could together oversell and leave a wrong stock figure), and the stock movement chain is computed line by line. * Product rows are locked in product-id order, so two carts that contain the same products in different orders can't deadlock. * customer_name / customer_phone (optional, used when customer_id is None): the customer is found or created INSIDE this transaction. * Money typed by a person must have at most 2 decimals (never rounded). """
    _require_business(business_id, owner_user_id)

    try:
        key = integrity.clean_key(idempotency_key)
    except ValueError as e:
        return None, str(e)

    if not items:
        return None, "Add at least one product to the sale."

    try:
        amount_paid = costing.money_amount(amount_paid, "Amount paid")
    except CostingError as e:
        return None, str(e)
    if amount_paid < 0:
        return None, "Amount paid cannot be negative."
    if amount_paid > 0 and payment_method not in PAYMENT_METHODS:
        return None, "Please choose a valid payment method."

    clean_items = []
    for it in items:
        try:
            qty = costing.quantity(it["quantity"], "Quantity")   # max 3 decimals, never silently rounded
        except CostingError as e:
            return None, str(e)
        if qty <= 0:
            return None, "Each item's quantity must be greater than zero."
        clean_items.append({"product_id": it["product_id"], "quantity": qty})

    try:
        with get_db() as (conn, cursor):
            # 0. Replay check FIRST — before any validation that depends on
            # current stock/balances, which a successful first attempt has
            # already changed.
            if key is not None:
                integrity.lock_key(cursor, business_id, "sale", key)
                cursor.execute(
                    "SELECT id FROM sales WHERE business_id=%s AND idempotency_key=%s",
                    (business_id, key),
                )
                prior = cursor.fetchone()
                if prior:
                    # A reference may only replay the SAME sale. If it is being
                    # reused for different goods, refuse loudly rather than
                    # silently dropping the new sale.
                    cursor.execute(
                        "SELECT product_id, SUM(quantity) AS qty FROM sale_items "
                        "WHERE sale_id=%s AND business_id=%s GROUP BY product_id",
                        (prior["id"], business_id),
                    )
                    prior_items = {r["product_id"]: r["qty"] for r in cursor.fetchall()}
                    req_items = {}
                    for it in clean_items:
                        req_items[it["product_id"]] = req_items.get(it["product_id"], Decimal("0")) + it["quantity"]
                    if prior_items != req_items:
                        raise SaleError(
                            "This submission reference was already used for a different sale. "
                            "Please start the sale again.")
                    return prior["id"], f"Sale #{prior['id']} was {integrity.REPLAY_NOTE}."

            # 1. Total the quantity per product, then lock every product row
            # in a fixed (id) order for this whole transaction.
            needed = {}
            for it in clean_items:
                needed[it["product_id"]] = needed.get(it["product_id"], Decimal("0")) + it["quantity"]

            products = {}
            for pid in sorted(needed):
                cursor.execute(
                    "SELECT id, name, unit, selling_price, current_stock, purchase_price, cost_known, is_active "
                    "FROM products WHERE id=%s AND business_id=%s FOR UPDATE",
                    (pid, business_id),
                )
                product = cursor.fetchone()
                if product is None:
                    raise SaleError("One of the selected products was not found.")
                if product["is_active"] == 0:
                    raise SaleError(f"'{product['name']}' is no longer available for sale.")
                if needed[pid] > product["current_stock"]:
                    raise SaleError(
                        f"Not enough stock for '{product['name']}' — "
                        f"only {product['current_stock']:g} {product['unit']} available."
                    )
                products[pid] = product

            total_amount = Decimal("0")
            line_rows = []  # (product_row, qty, unit_price, unit_cost, line_total)
            for it in clean_items:
                product = products[it["product_id"]]
                unit_price = product["selling_price"]
                # Historical cost snapshot — Phase 5A-1. Whatever
                # products.purchase_price is RIGHT NOW (the running
                # weighted-average cost — see inventory.adjust_stock())
                # is locked onto this line permanently. A later price or
                # cost change must never rewrite this sale's profit.
                # Phase 5B-2: the cost is locked on ONLY if it is KNOWN. An
                # unknown cost is stored as NULL (never as a silent 0) and
                # reports exclude it from profit with a warning. A genuine
                # zero-cost product has cost_known=TRUE and keeps its 0.
                unit_cost = snapshot_cost(product)
                line_total = (unit_price * it["quantity"]).quantize(Decimal("0.01"))
                total_amount += line_total
                line_rows.append((product, it["quantity"], unit_price, unit_cost, line_total))

            if amount_paid > total_amount:
                raise SaleError("Amount paid cannot be more than the total amount due.")

            # Phase 5B-1: customer checks, enforced here in the backend (not
            # just in the form) inside the same transaction as the sale.
            # * Any customer_id must belong to THIS business.
            # * Anything that leaves money owing (credit or part-payment)
            # needs a named customer WITH a valid phone number. A fully
            # paid walk-in cash sale needs neither.
            will_owe = amount_paid < total_amount
            if customer_id is None and (customer_name or "").strip():
                customer_id = _get_or_create_customer_tx(
                    cursor, business_id, customer_name, customer_phone, require_phone=will_owe)
            customer_row = None
            if customer_id is not None:
                cursor.execute(
                    "SELECT id, phone FROM customers WHERE id=%s AND business_id=%s",
                    (customer_id, business_id),
                )
                customer_row = cursor.fetchone()
                if customer_row is None:
                    raise SaleError("The selected customer was not found in this business.")
            if will_owe:
                if customer_row is None:
                    raise SaleError(
                        "A credit sale needs a customer. Enter the customer's name and phone number."
                    )
                _, phone_err = normalize_phone(customer_row["phone"])
                if phone_err:
                    raise SaleError(
                        "This customer has no valid phone number on file. " + phone_err
                    )

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
                "amount_paid, payment_status, payment_method, created_by, idempotency_key) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (business_id, customer_id, total_amount, amount_paid,
                 payment_status, payment_method, created_by_user_id, key),
            )
            sale_id = cursor.fetchone()["id"]

            running = {pid: p["current_stock"] for pid, p in products.items()}
            for product, qty, unit_price, unit_cost, line_total in line_rows:
                cursor.execute(
                    "INSERT INTO sale_items (sale_id, business_id, product_id, "
                    "product_name, quantity, unit_price, unit_cost, cost_known, line_total) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (sale_id, business_id, product["id"], product["name"],
                     qty, unit_price, unit_cost, unit_cost is not None, line_total),
                )

                before = running[product["id"]]
                after = before - qty
                running[product["id"]] = after
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

        return sale_id, f"Sale recorded (Sale #{sale_id})"
    except SaleError as e:
        return None, str(e)
    except Exception as e:
        return None, integrity.friendly_db_error(e)


# ── Stock-sale profit reporting (Phase 5A-1) ────────────────────────────────

def get_stock_sales_profit_summary(business_id, owner_user_id, start_date, end_date):
    """ Net revenue, COGS, and gross profit for completed stock sales whose sale.created_at falls within [start_date, end_date] (inclusive, business-local dates). Scoped at the sale_items line level, not the sales-row level, since COGS is a per-line figure (unit_cost × qty). Lines with unit_cost IS NULL are sale_items written before the Phase 5A-1 migration — they're excluded from the COGS sum (never treated as zero cost, which would overstate profit) and counted separately so the caller can show an honest "incomplete" caveat instead of a falsely precise number. """
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT "
            " COUNT(DISTINCT s.id) AS sales_count, "
            " COALESCE(SUM(si.line_total), 0) AS net_revenue, "
            f" COALESCE(SUM(si.line_total) FILTER (WHERE {known_cost_sql('si')}), 0) "
            " AS revenue_with_known_cost, "
            f" COALESCE(SUM(si.quantity * si.unit_cost) FILTER (WHERE {known_cost_sql('si')}), 0) "
            " AS cogs, "
            f" COUNT(*) FILTER (WHERE NOT {known_cost_sql('si')}) AS lines_missing_cost "
            "FROM sales s "
            "JOIN sale_items si ON si.sale_id = s.id "
            "WHERE s.business_id=%s AND s.created_at::date BETWEEN %s AND %s",
            (business_id, start_date, end_date),
        )
        row = cursor.fetchone()

        # Phase 5C: goods RETURNED in the period (by return date) come off revenue and cost.
        # Each returned line carries the original sale line's cost snapshot, so the cost
        # reversed is exactly the cost that was charged; unknown cost stays unknown.
        cursor.execute(
            "SELECT COALESCE(SUM(sri.line_value), 0) AS returned_value, "
            f" COALESCE(SUM(sri.line_value) FILTER (WHERE {known_cost_sql('sri')}), 0) AS returned_known_value, "
            f" COALESCE(SUM(sri.quantity * sri.unit_cost) FILTER (WHERE {known_cost_sql('sri')}), 0) AS returned_cogs, "
            f" COUNT(*) FILTER (WHERE NOT {known_cost_sql('sri')}) AS returned_lines_missing_cost "
            "FROM sale_return_items sri JOIN sale_returns sr ON sr.id = sri.return_id "
            "WHERE sr.business_id=%s AND sr.created_at::date BETWEEN %s AND %s",
            (business_id, start_date, end_date),
        )
        ret = cursor.fetchone()

        gross_sales = row["net_revenue"]
        net_revenue = gross_sales - ret["returned_value"]
        cogs = row["cogs"] - ret["returned_cogs"]
        # Gross profit/margin computed only from the portion of revenue
        # whose cost is actually known — mixing in unknown-cost revenue
        # at an assumed cost of zero would inflate profit.
        known_revenue = row["revenue_with_known_cost"] - ret["returned_known_value"]
        gross_profit = known_revenue - cogs
        gross_margin_pct = (
            (gross_profit / known_revenue * 100) if known_revenue > 0 else None
        )

        return {
            "sales_count": row["sales_count"],
            "gross_sales": gross_sales,
            "returns_value": ret["returned_value"],
            "net_revenue": net_revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "gross_margin_pct": gross_margin_pct,
            "lines_missing_cost": row["lines_missing_cost"],
            "incomplete": row["lines_missing_cost"] > 0,
        }
