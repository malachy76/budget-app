# returns.py — Phase 5C: sales returns, refunds and corrections for STOCK SALES.
#
# What a return does (and never does)
# * The original sale, its items and its payments are NEVER edited or deleted.
# A return is a NEW record (sale_returns + sale_return_items) that points at them.
# * Goods go back into stock through the normal inventory-movement ledger
# ('sale_return', +qty) only if the business says they are SALEABLE. Damaged goods
# are recorded ('return_damaged', qty 0 — stock unchanged) but not restocked.
# * Money: the value of the goods returned is settled in this order:
# 1. it first REDUCES what the customer still owes (debt_reduction)
# 2. only the rest is REFUNDED, and only money the customer actually paid
# so return_value = debt_reduction + refund_amount. A credit sale therefore
# never produces a cash refund, and a fully paid sale never changes a debt.
# * A customer's balance on a sale is
# total_amount - amount_paid - active write-offs - SUM(debt_reduction of its returns)
# (return_credit_sql() is the one shared SQL fragment for that last term).
# * Cost: each returned line copies the ORIGINAL sale line's unit_cost / cost_known
# (Phase 5B-2). Nothing is re-costed; an unknown cost stays unknown; products'
# weighted-average cost is NOT changed by a return (returned units re-enter stock
# at the current average — documented limitation).
# * Treatment Management is separate: this module only ever reads sales, sale_items,
# payments' parent sale and products. Treatment dispensing/payments are untouched.
# * Safety: one transaction; the sale row is locked (the same lock payments, payment
# reversals and write-offs take) so a return cannot interleave with them; products
# are locked in id order; ownership (business_id + owner) is part of every query;
# a submission reference (idempotency key) makes a repeat return the original
# result instead of a second return/refund.

from decimal import Decimal

import costing
import integrity
from costing import CostingError
from db import get_db
from business import get_business
from sales import PAYMENT_METHODS

CONDITIONS = ("saleable", "damaged")
CONDITION_LABELS = {
    "saleable": "Saleable \u2014 put back in stock",
    "damaged": "Damaged / unsaleable \u2014 do not restock",
}
_ZERO = Decimal("0")
_CENT = Decimal("0.01")


class ReturnError(Exception):
    pass


def return_credit_sql(alias="s"):
    """SQL fragment: the total debt reduction granted by returns on sale `alias`. Subtract it wherever a sale's outstanding balance is computed."""
    return ("COALESCE((SELECT SUM(sr.debt_reduction) FROM sale_returns sr "
            f"WHERE sr.business_id = {alias}.business_id AND sr.sale_id = {alias}.id), 0)")


def _require_business(business_id, owner_user_id):
    biz = get_business(business_id, owner_user_id)
    if biz is None:
        raise ReturnError("This business was not found, or does not belong to you.")
    return biz


def split_return(total, paid, prior_credit, value):
    """How a return of `value` is settled. Returns (debt_reduction, refund_amount). Pure function — the whole money rule in one place."""
    outstanding = total - paid - prior_credit
    if outstanding < 0:
        raise ReturnError("This sale's balance does not add up, so a return cannot be processed. "
                          "Run \u2018Check my records\u2019 on the End-of-Day page.")
    debt = min(value, outstanding)
    return debt, value - debt


def _active_write_off(cursor, business_id, sale_id):
    cursor.execute(
        "SELECT COALESCE(SUM(w.amount), 0) AS wo FROM debt_write_offs w "
        "WHERE w.business_id=%s AND w.sale_id=%s AND NOT EXISTS "
        "(SELECT 1 FROM debt_write_off_reversals r WHERE r.write_off_id = w.id)",
        (business_id, sale_id),
    )
    return cursor.fetchone()["wo"]


def _normalise_lines(lines):
    """Merge duplicate sale_item_ids; validate quantity (max 3 decimals, > 0) and condition."""
    if not lines:
        raise ReturnError("Select at least one item to return.")
    merged = {}
    for ln in lines:
        try:
            item_id = int(ln["sale_item_id"])
        except (KeyError, TypeError, ValueError):
            raise ReturnError("One of the selected items is not valid.")
        qty = costing.quantity(ln["quantity"], "Return quantity")
        if qty <= 0:
            raise ReturnError("Each returned quantity must be greater than zero.")
        cond = ln.get("condition", "saleable")
        if cond not in CONDITIONS:
            raise ReturnError("Choose whether each returned item is saleable or damaged.")
        if item_id in merged:
            if merged[item_id]["condition"] != cond:
                raise ReturnError("The same item cannot be returned in two different conditions at once. "
                                  "Record two separate returns.")
            merged[item_id]["quantity"] += qty
        else:
            merged[item_id] = {"sale_item_id": item_id, "quantity": qty, "condition": cond}
    return list(merged.values())


def _load_sale_state(cursor, business_id, sale_id, for_update):
    cursor.execute(
        "SELECT s.id, s.customer_id, s.total_amount, s.amount_paid FROM sales s "
        "WHERE s.id=%s AND s.business_id=%s" + (" FOR UPDATE" if for_update else ""),
        (sale_id, business_id),
    )
    sale = cursor.fetchone()
    if sale is None:
        raise ReturnError("Sale not found.")
    cursor.execute(
        "SELECT id, product_id, product_name, quantity, unit_price, unit_cost, cost_known, line_total "
        "FROM sale_items WHERE sale_id=%s AND business_id=%s ORDER BY id",
        (sale_id, business_id),
    )
    items = {r["id"]: r for r in cursor.fetchall()}
    cursor.execute(
        "SELECT sri.sale_item_id, SUM(sri.quantity) AS q, SUM(sri.line_value) AS v "
        "FROM sale_return_items sri JOIN sale_returns sr ON sr.id = sri.return_id "
        "WHERE sri.business_id=%s AND sr.sale_id=%s GROUP BY sri.sale_item_id",
        (business_id, sale_id),
    )
    returned = {r["sale_item_id"]: (r["q"], r["v"]) for r in cursor.fetchall()}
    cursor.execute(
        "SELECT COALESCE(SUM(debt_reduction), 0) AS d, COALESCE(SUM(refund_amount), 0) AS r, "
        "COALESCE(SUM(return_value), 0) AS v FROM sale_returns WHERE business_id=%s AND sale_id=%s",
        (business_id, sale_id),
    )
    prior = cursor.fetchone()
    return sale, items, returned, prior


def _compute(cursor, business_id, sale_id, lines, for_update):
    """Validate a proposed return against the CURRENT state and work out what it would do. Writes nothing. Used by both the preview and the real thing (which calls it with the sale row locked)."""
    lines = _normalise_lines(lines)
    sale, items, returned, prior = _load_sale_state(cursor, business_id, sale_id, for_update)
    if _active_write_off(cursor, business_id, sale_id) > 0:
        raise ReturnError(
            "This sale has a written-off balance. Reverse the write-off in Bad Debts first, "
            "then record the return \u2014 otherwise the write-off and the return would overlap.")
    out_lines = []
    total_value = _ZERO
    for ln in lines:
        it = items.get(ln["sale_item_id"])
        if it is None:
            raise ReturnError("One of the selected items is not part of this sale.")
        ret_q, ret_v = returned.get(it["id"], (_ZERO, _ZERO))
        eligible = it["quantity"] - ret_q
        if ln["quantity"] > eligible:
            raise ReturnError(
                f"Only {eligible:g} of '{it['product_name']}' can still be returned "
                f"(sold {it['quantity']:g}, already returned {ret_q:g}).")
        # The line that completes the return takes the exact remainder, so the sum of all
        # returns of a line can never differ from its original line_total by a rounding cent.
        if ret_q + ln["quantity"] == it["quantity"]:
            value = it["line_total"] - ret_v
        else:
            value = (it["unit_price"] * ln["quantity"]).quantize(_CENT)
        total_value += value
        out_lines.append({
            "sale_item_id": it["id"], "product_id": it["product_id"], "product_name": it["product_name"],
            "quantity": ln["quantity"], "condition": ln["condition"], "unit_price": it["unit_price"],
            "unit_cost": it["unit_cost"], "cost_known": bool(it["cost_known"]), "line_value": value,
        })
    debt, refund = split_return(sale["total_amount"], sale["amount_paid"], prior["d"], total_value)
    return {
        "sale": sale, "lines": out_lines, "return_value": total_value,
        "debt_reduction": debt, "refund_amount": refund,
        "outstanding_before": sale["total_amount"] - sale["amount_paid"] - prior["d"],
        "outstanding_after": sale["total_amount"] - sale["amount_paid"] - prior["d"] - debt,
    }


def preview_return(business_id, owner_user_id, sale_id, lines):
    """What a return WOULD do, for the review screen. Writes nothing. Returns (preview_dict, None) or (None, message)."""
    _require_business(business_id, owner_user_id)
    try:
        with get_db() as (conn, cursor):
            return _compute(cursor, business_id, sale_id, lines, for_update=False), None
    except (ReturnError, CostingError) as e:
        return None, str(e)
    except Exception as e:
        return None, integrity.friendly_db_error(e)


def create_sale_return(business_id, owner_user_id, created_by_user_id, sale_id, lines, reason, refund_method=None, note=None, idempotency_key=None):
    """Record a return. lines = [{"sale_item_id", "quantity", "condition"}]. Returns (return_id, message); on failure (None, message) and NOTHING is written."""
    _require_business(business_id, owner_user_id)
    try:
        key = integrity.clean_key(idempotency_key)
        reason = (reason or "").strip()
        if not reason:
            raise ReturnError("Please give a reason for the return.")
        wanted = _normalise_lines(lines)

        with get_db() as (conn, cursor):
            if key is not None:
                integrity.lock_key(cursor, business_id, "sale_return", key)
                cursor.execute(
                    "SELECT id, sale_id FROM sale_returns WHERE business_id=%s AND idempotency_key=%s",
                    (business_id, key))
                prior = cursor.fetchone()
                if prior:
                    cursor.execute(
                        "SELECT sale_item_id, SUM(quantity) AS q FROM sale_return_items "
                        "WHERE return_id=%s GROUP BY sale_item_id", (prior["id"],))
                    had = {r["sale_item_id"]: r["q"] for r in cursor.fetchall()}
                    asked = {w["sale_item_id"]: w["quantity"] for w in wanted}
                    if prior["sale_id"] != sale_id or had != asked:
                        raise ReturnError("This submission reference was already used for a different "
                                          "return. Please start the return again.")
                    return prior["id"], f"Return #{prior['id']} was {integrity.REPLAY_NOTE}."

            calc = _compute(cursor, business_id, sale_id, wanted, for_update=True)
            refund = calc["refund_amount"]
            method = None
            if refund > 0:
                if refund_method not in PAYMENT_METHODS:
                    raise ReturnError("Choose how the refund of \u20A6{:,.2f} is being paid.".format(refund))
                method = refund_method

            cursor.execute(
                "INSERT INTO sale_returns (business_id, sale_id, customer_id, return_value, debt_reduction, "
                "refund_amount, refund_method, reason, note, created_by, idempotency_key) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (business_id, sale_id, calc["sale"]["customer_id"], calc["return_value"],
                 calc["debt_reduction"], refund, method, reason, (note or "").strip() or None,
                 created_by_user_id, key),
            )
            return_id = cursor.fetchone()["id"]

            # Lock every product row (id order => no deadlocks), then write items + stock movements.
            stock = {}
            for pid in sorted({ln["product_id"] for ln in calc["lines"]}):
                cursor.execute(
                    "SELECT id, current_stock FROM products WHERE id=%s AND business_id=%s FOR UPDATE",
                    (pid, business_id))
                row = cursor.fetchone()
                if row is None:
                    raise ReturnError("A product on this sale no longer exists.")
                stock[pid] = row["current_stock"]

            for ln in calc["lines"]:
                cursor.execute(
                    "INSERT INTO sale_return_items (return_id, business_id, sale_item_id, product_id, "
                    "product_name, quantity, unit_price, unit_cost, cost_known, line_value, condition) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (return_id, business_id, ln["sale_item_id"], ln["product_id"], ln["product_name"],
                     ln["quantity"], ln["unit_price"], ln["unit_cost"], ln["cost_known"],
                     ln["line_value"], ln["condition"]),
                )
                before = stock[ln["product_id"]]
                if ln["condition"] == "saleable":
                    after = before + ln["quantity"]
                    mtype, mqty = "sale_return", ln["quantity"]
                    mnote = f"Return #{return_id} of Sale #{sale_id}"
                    cursor.execute(
                        "UPDATE products SET current_stock=%s, updated_at=NOW() WHERE id=%s AND business_id=%s",
                        (after, ln["product_id"], business_id))
                    stock[ln["product_id"]] = after
                else:
                    after = before
                    mtype, mqty = "return_damaged", _ZERO
                    mnote = (f"Return #{return_id} of Sale #{sale_id} \u2014 {ln['quantity']:g} damaged, "
                             "not restocked")
                cursor.execute(
                    "INSERT INTO inventory_movements (business_id, product_id, movement_type, quantity, "
                    "quantity_before, quantity_after, note, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (business_id, ln["product_id"], mtype, mqty, before, after, mnote, created_by_user_id),
                )

        parts = [f"Return #{return_id} recorded for Sale #{sale_id} (value \u20A6{calc['return_value']:,.2f})."]
        if calc["debt_reduction"] > 0:
            parts.append(f"Customer's balance reduced by \u20A6{calc['debt_reduction']:,.2f}.")
        if refund > 0:
            parts.append(f"Refund of \u20A6{refund:,.2f} paid by {method}.")
        return return_id, " ".join(parts)
    except (ReturnError, CostingError) as e:
        return None, str(e)
    except Exception as e:
        return None, integrity.friendly_db_error(e)


# ── Reading ──────────────────────────────────────────────────────────────────

def get_sale_for_return(business_id, owner_user_id, sale_id):
    """The original sale as the Returns screen needs it: header, each item with how many are still eligible, and the money position. None if the sale is not in this business."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT s.id, s.created_at, s.total_amount, s.amount_paid, s.payment_status, s.payment_method, "
            "s.customer_id, c.name AS customer_name, c.phone AS customer_phone, u.username AS sold_by "
            "FROM sales s LEFT JOIN customers c ON c.id = s.customer_id AND c.business_id = s.business_id "
            "LEFT JOIN users u ON u.id = s.created_by "
            "WHERE s.id=%s AND s.business_id=%s", (sale_id, business_id))
        sale = cursor.fetchone()
        if sale is None:
            return None
        _, items, returned, prior = _load_sale_state(cursor, business_id, sale_id, for_update=False)
        cursor.execute("SELECT id, unit FROM products WHERE business_id=%s AND id = ANY(%s)",
                       (business_id, [i["product_id"] for i in items.values()] or [0]))
        units = {r["id"]: r["unit"] for r in cursor.fetchall()}
        wo = _active_write_off(cursor, business_id, sale_id)
    out_items = []
    for it in items.values():
        rq, rv = returned.get(it["id"], (_ZERO, _ZERO))
        out_items.append({
            "sale_item_id": it["id"], "product_id": it["product_id"], "product_name": it["product_name"],
            "unit": units.get(it["product_id"]) or "", "sold": it["quantity"], "unit_price": it["unit_price"],
            "line_total": it["line_total"], "returned": rq, "eligible": it["quantity"] - rq,
        })
    outstanding = sale["total_amount"] - sale["amount_paid"] - prior["d"] - wo
    return {
        "sale": dict(sale), "items": out_items,
        "money": {
            "total": sale["total_amount"], "paid": sale["amount_paid"], "returned_value": prior["v"],
            "debt_reduced_by_returns": prior["d"], "refunded": prior["r"],
            "outstanding": max(outstanding, _ZERO), "written_off": wo,
        },
    }


def get_recent_sales(business_id, owner_user_id, limit=15):
    """Latest sales, for picking one without typing its number."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT s.id, s.created_at, s.total_amount, c.name AS customer_name, "
            "EXISTS (SELECT 1 FROM sale_returns sr WHERE sr.sale_id = s.id) AS has_returns "
            "FROM sales s LEFT JOIN customers c ON c.id = s.customer_id AND c.business_id = s.business_id "
            "WHERE s.business_id=%s ORDER BY s.id DESC LIMIT %s", (business_id, limit))
        return cursor.fetchall()


def get_returns(business_id, owner_user_id, sale_id=None, limit=30):
    """Return records (newest first), optionally for one sale."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT sr.id, sr.sale_id, sr.created_at, sr.return_value, sr.debt_reduction, sr.refund_amount, "
            "sr.refund_method, sr.reason, sr.note, c.name AS customer_name, u.username AS processed_by "
            "FROM sale_returns sr LEFT JOIN customers c ON c.id = sr.customer_id AND c.business_id = sr.business_id "
            "LEFT JOIN users u ON u.id = sr.created_by "
            "WHERE sr.business_id=%s" + (" AND sr.sale_id=%s" if sale_id is not None else "") +
            " ORDER BY sr.id DESC LIMIT %s",
            (business_id, sale_id, limit) if sale_id is not None else (business_id, limit))
        return cursor.fetchall()


def get_return(business_id, owner_user_id, return_id):
    """One return with its items, or None if it is not in this business."""
    _require_business(business_id, owner_user_id)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT sr.*, c.name AS customer_name, u.username AS processed_by "
            "FROM sale_returns sr LEFT JOIN customers c ON c.id = sr.customer_id AND c.business_id = sr.business_id "
            "LEFT JOIN users u ON u.id = sr.created_by WHERE sr.id=%s AND sr.business_id=%s",
            (return_id, business_id))
        header = cursor.fetchone()
        if header is None:
            return None
        cursor.execute(
            "SELECT product_name, quantity, unit_price, line_value, condition FROM sale_return_items "
            "WHERE return_id=%s AND business_id=%s ORDER BY id", (return_id, business_id))
        return {"return": dict(header), "items": cursor.fetchall()}
