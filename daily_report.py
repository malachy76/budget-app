# daily_report.py — Business Mode: cash-basis End-of-Day / period report
#
# ACCOUNTING RULES (cash basis — these override any accrual-style figure)
# ──────────────────────────────────────────────────────────────────────
#  * "Realised revenue" is money ACTUALLY RECEIVED, dated by the day it was
#    received (Africa/Lagos). An unpaid invoice is never realised revenue.
#  * A later repayment of an old debt becomes realised revenue on the day it
#    is received. It never creates a sale and the original invoice is never
#    counted again (invoice value is reported ONLY as "activity").
#  * STOCK SALES — realised gross profit for a payment is
#        payment x (1 - COGS / invoice total)
#    i.e. each payment is treated as paying for the sale proportionally
#    (the app does not record which items a payment covers). COGS comes from
#    the cost snapshotted on each sale item (Phase 5A-1), never from the
#    current product price. Once a sale is fully paid its whole COGS has been
#    recognised exactly once.
#  * TREATMENTS — a bill only ever contains the service charge plus medicines
#    ALREADY dispensed, so a payment can never "pay for" medicine not yet
#    dispensed. Cost is recognised proportionally with a CUMULATIVE method:
#        cumulative cost after payment k =
#            (total paid so far) x (cost of medicines dispensed up to the
#                                   moment of payment k / bill up to then)
#        cost recognised by payment k = that minus the same figure after
#                                       payment k-1
#    It only uses information known at the time of each payment (so a past
#    day's report never changes), and once the bill is fully paid exactly the
#    true total cost has been recognised.
#  * Unknown costs are NEVER treated as zero. Revenue whose cost is unknown
#    is reported separately ("revenue with unknown cost") and excluded from
#    gross profit; the report is flagged incomplete.
#  * Bad-debt RECOVERIES, write-offs and write-off reversals are reported
#    separately. They are never part of operating revenue or gross profit,
#    and a write-off/reversal is never "money received".
#  * Gross profit is NOT net profit: business operating expenses are not
#    recorded in this app yet, so net profit is not calculated.
#
# DEBT RECONCILIATION (as-of balances, never today's balance projected back)
#     Opening debt + new charges billed - payments received
#       - written off + write-offs reversed = Closing debt
#   where "new charges billed" = invoices created in the period + treatment
#   service charges created in the period + medicines dispensed (priced) in
#   the period. The check is computed from raw records and reported honestly
#   (reconciles: True/False) rather than forced to balance.
#
# TIME: business days are Africa/Lagos. Older tables (sales, payments,
# treatments, treatment_payments, treatment_dispensing) store naive
# timestamps holding UTC (Supabase default); the 5A-4 tables are TIMESTAMPTZ.
# Day boundaries are converted to UTC instants once, in Python.

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from db import get_db
from business import get_business

BUSINESS_TZ = ZoneInfo("Africa/Lagos")
_UTC = timezone.utc
_CENT = Decimal("0.01")
_ZERO = Decimal("0")


class ReportError(Exception):
    pass


def business_today():
    """Today's date in Nigeria (not the server's UTC date)."""
    return datetime.now(BUSINESS_TZ).date()


def _require_business(business_id, owner_user_id):
    if get_business(business_id, owner_user_id) is None:
        raise ReportError("This business was not found, or does not belong to you.")


def _q(v):
    return Decimal(v).quantize(_CENT, rounding=ROUND_HALF_UP)


def day_bounds(start_date, end_date):
    """[start, end) as (naive_utc_start, naive_utc_end, aware_start, aware_end)
    for the Africa/Lagos business days start_date .. end_date inclusive."""
    s = datetime.combine(start_date, time.min, tzinfo=BUSINESS_TZ).astimezone(_UTC)
    e = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ).astimezone(_UTC)
    return s.replace(tzinfo=None), e.replace(tzinfo=None), s, e


def _naive_utc(dt):
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(_UTC).replace(tzinfo=None)
    return dt


# ── Pure allocation logic (unit-tested directly) ────────────────────────────

def allocate_treatment_payments(service_charge, payments, dispensing):
    """Cumulative proportional cost recognition for ONE treatment.

    payments:  [{"id", "amount", "created_at"(naive UTC)}]  (any order)
    dispensing:[{"at"(naive UTC), "qty", "price", "cost"(None = unknown)}]
               only PRICED dispensings (the ones that are on the bill).
    Returns a list (payment order) of dicts with: id, amount, initial (bool),
    cogs (Decimal, may be fractional), cost_known (bool).
    """
    service_charge = Decimal(service_charge)
    ordered = sorted(payments, key=lambda p: (p["created_at"], p["id"]))
    cum_paid = _ZERO
    prev_cum_cost = _ZERO
    out = []
    for i, p in enumerate(ordered):
        billed = service_charge
        cost = _ZERO
        missing = 0
        for d in dispensing:
            if d["at"] <= p["created_at"]:
                billed += d["qty"] * d["price"]
                if d["cost"] is None:
                    missing += 1
                else:
                    cost += d["qty"] * d["cost"]
        cum_paid += p["amount"]
        cum_cost = (cum_paid * cost / billed) if billed > 0 else _ZERO
        out.append({
            "id": p["id"], "amount": p["amount"], "initial": i == 0,
            "cogs": cum_cost - prev_cum_cost, "cost_known": missing == 0,
        })
        prev_cum_cost = cum_cost
    return out


# ── As-of debt (used for opening / closing balances) ────────────────────────

def _debt_as_of(cursor, business_id, cutoff_naive, cutoff_aware):
    """Collectible debt per customer using ONLY records that existed before
    the cutoff instant. Returns {customer_id|None: {"stock": D, "treatment": D}}."""
    result = {}

    cursor.execute(
        "SELECT s.customer_id, "
        "  COALESCE(SUM(s.total_amount - COALESCE(p.paid, 0) - COALESCE(w.wo, 0)), 0) AS debt "
        "FROM sales s "
        "LEFT JOIN (SELECT sale_id, SUM(amount) AS paid FROM payments "
        "           WHERE business_id=%s AND created_at < %s GROUP BY sale_id) p ON p.sale_id = s.id "
        "LEFT JOIN (SELECT w.sale_id, SUM(w.amount) AS wo FROM debt_write_offs w "
        "           WHERE w.business_id=%s AND w.sale_id IS NOT NULL AND w.created_at < %s "
        "           AND NOT EXISTS (SELECT 1 FROM debt_write_off_reversals r "
        "                           WHERE r.write_off_id = w.id AND r.created_at < %s) "
        "           GROUP BY w.sale_id) w ON w.sale_id = s.id "
        "WHERE s.business_id=%s AND s.created_at < %s "
        "GROUP BY s.customer_id",
        (business_id, cutoff_naive, business_id, cutoff_aware, cutoff_aware,
         business_id, cutoff_naive),
    )
    for r in cursor.fetchall():
        result.setdefault(r["customer_id"], {"stock": _ZERO, "treatment": _ZERO})["stock"] += r["debt"]

    cursor.execute(
        "SELECT t.customer_id, "
        "  COALESCE(SUM(t.service_charge + COALESCE(d.billed, 0) - COALESCE(p.paid, 0) "
        "               - COALESCE(w.wo, 0)), 0) AS debt "
        "FROM treatments t "
        "LEFT JOIN (SELECT ti.treatment_id, SUM(d.quantity * d.unit_price) AS billed "
        "           FROM treatment_dispensing d JOIN treatment_items ti ON ti.id = d.treatment_item_id "
        "           WHERE d.business_id=%s AND d.unit_price IS NOT NULL AND d.dispensed_at < %s "
        "           GROUP BY ti.treatment_id) d ON d.treatment_id = t.id "
        "LEFT JOIN (SELECT treatment_id, SUM(amount) AS paid FROM treatment_payments "
        "           WHERE business_id=%s AND created_at < %s GROUP BY treatment_id) p ON p.treatment_id = t.id "
        "LEFT JOIN (SELECT w.treatment_id, SUM(w.amount) AS wo FROM debt_write_offs w "
        "           WHERE w.business_id=%s AND w.treatment_id IS NOT NULL AND w.created_at < %s "
        "           AND NOT EXISTS (SELECT 1 FROM debt_write_off_reversals r "
        "                           WHERE r.write_off_id = w.id AND r.created_at < %s) "
        "           GROUP BY w.treatment_id) w ON w.treatment_id = t.id "
        "WHERE t.business_id=%s AND t.created_at < %s "
        "GROUP BY t.customer_id",
        (business_id, cutoff_naive, business_id, cutoff_naive,
         business_id, cutoff_aware, cutoff_aware, business_id, cutoff_naive),
    )
    for r in cursor.fetchall():
        result.setdefault(r["customer_id"], {"stock": _ZERO, "treatment": _ZERO})["treatment"] += r["debt"]
    return result


def _sum_debt(by_customer):
    stock = sum((v["stock"] for v in by_customer.values()), _ZERO)
    treat = sum((v["treatment"] for v in by_customer.values()), _ZERO)
    return stock, treat


# ── The report ──────────────────────────────────────────────────────────────

def get_cash_basis_report(business_id, owner_user_id, start_date, end_date):
    """Everything for the End-of-Day / period summary, cash basis.
    start_date/end_date are Africa/Lagos business dates, inclusive."""
    _require_business(business_id, owner_user_id)
    if start_date > end_date:
        raise ReportError("The start date must not be after the end date.")
    s_n, e_n, s_a, e_a = day_bounds(start_date, end_date)

    with get_db() as (conn, cursor):
        # 1. Activity (invoice / bill value — NOT revenue)
        cursor.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_amount), 0) AS v FROM sales "
            "WHERE business_id=%s AND created_at >= %s AND created_at < %s",
            (business_id, s_n, e_n))
        r = cursor.fetchone()
        sales_count, sales_activity = r["n"], r["v"]

        cursor.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(service_charge), 0) AS v FROM treatments "
            "WHERE business_id=%s AND created_at >= %s AND created_at < %s",
            (business_id, s_n, e_n))
        r = cursor.fetchone()
        treatments_started, service_charges_billed = r["n"], r["v"]
        cursor.execute(
            "SELECT COALESCE(SUM(quantity * unit_price), 0) AS v FROM treatment_dispensing "
            "WHERE business_id=%s AND unit_price IS NOT NULL "
            "AND dispensed_at >= %s AND dispensed_at < %s",
            (business_id, s_n, e_n))
        medicine_billed = cursor.fetchone()["v"]
        treatment_activity = service_charges_billed + medicine_billed

        # 2. Stock-sale collections with cost info per sale
        cursor.execute(
            "SELECT p.id, p.sale_id, p.amount, p.payment_method, p.created_at, "
            "  (p.created_at = s.created_at) AS is_initial, s.total_amount, "
            "  COALESCE(c.cogs, 0) AS sale_cogs, COALESCE(c.missing, 0) AS missing "
            "FROM payments p "
            "JOIN sales s ON s.id = p.sale_id AND s.business_id = p.business_id "
            "LEFT JOIN (SELECT sale_id, "
            "    SUM(quantity * unit_cost) FILTER (WHERE unit_cost IS NOT NULL) AS cogs, "
            "    COUNT(*) FILTER (WHERE unit_cost IS NULL) AS missing "
            "  FROM sale_items WHERE business_id=%s GROUP BY sale_id) c ON c.sale_id = s.id "
            "WHERE p.business_id=%s AND p.created_at >= %s AND p.created_at < %s "
            "ORDER BY p.created_at, p.id",
            (business_id, business_id, s_n, e_n))
        stock_pay_rows = cursor.fetchall()

        # 3. Treatment collections (cumulative cost allocation needs each
        #    affected treatment's full payment + dispensing history)
        cursor.execute(
            "SELECT id, treatment_id, amount, payment_method, created_at FROM treatment_payments "
            "WHERE business_id=%s AND created_at >= %s AND created_at < %s "
            "ORDER BY created_at, id", (business_id, s_n, e_n))
        treat_pay_rows = cursor.fetchall()
        treat_ids = sorted({r["treatment_id"] for r in treat_pay_rows})
        treat_alloc = {}      # payment id -> allocation dict
        if treat_ids:
            cursor.execute(
                "SELECT id, service_charge FROM treatments WHERE business_id=%s AND id = ANY(%s)",
                (business_id, treat_ids))
            service = {r["id"]: r["service_charge"] for r in cursor.fetchall()}
            cursor.execute(
                "SELECT id, treatment_id, amount, created_at FROM treatment_payments "
                "WHERE business_id=%s AND treatment_id = ANY(%s)", (business_id, treat_ids))
            pays = {}
            for r in cursor.fetchall():
                pays.setdefault(r["treatment_id"], []).append(
                    {"id": r["id"], "amount": r["amount"], "created_at": r["created_at"]})
            cursor.execute(
                "SELECT ti.treatment_id, d.dispensed_at AS at, d.quantity AS qty, "
                "  d.unit_price AS price, d.unit_cost AS cost "
                "FROM treatment_dispensing d JOIN treatment_items ti ON ti.id = d.treatment_item_id "
                "WHERE d.business_id=%s AND ti.treatment_id = ANY(%s) AND d.unit_price IS NOT NULL",
                (business_id, treat_ids))
            disp = {}
            for r in cursor.fetchall():
                disp.setdefault(r["treatment_id"], []).append(
                    {"at": r["at"], "qty": r["qty"], "price": r["price"], "cost": r["cost"]})
            for tid in treat_ids:
                for a in allocate_treatment_payments(service[tid], pays.get(tid, []), disp.get(tid, [])):
                    treat_alloc[a["id"]] = a

        # 4. Bad-debt events (kept entirely separate from operating figures)
        cursor.execute(
            "SELECT payment_method, amount FROM debt_recoveries "
            "WHERE business_id=%s AND created_at >= %s AND created_at < %s",
            (business_id, s_a, e_a))
        recovery_rows = cursor.fetchall()
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) AS v, COUNT(*) AS n FROM debt_write_offs "
            "WHERE business_id=%s AND created_at >= %s AND created_at < %s",
            (business_id, s_a, e_a))
        r = cursor.fetchone()
        written_off, written_off_count = r["v"], r["n"]
        cursor.execute(
            "SELECT COALESCE(SUM(w.amount), 0) AS v, COUNT(*) AS n "
            "FROM debt_write_off_reversals r JOIN debt_write_offs w ON w.id = r.write_off_id "
            "WHERE r.business_id=%s AND r.created_at >= %s AND r.created_at < %s",
            (business_id, s_a, e_a))
        r = cursor.fetchone()
        reversed_amount, reversed_count = r["v"], r["n"]

        # 5. As-of debts (opening = start of first day, closing = end of last day)
        opening = _debt_as_of(cursor, business_id, s_n, s_a)
        closing = _debt_as_of(cursor, business_id, e_n, e_a)
        cursor.execute(
            "SELECT id, name, phone FROM customers WHERE business_id=%s", (business_id,))
        customers = {c["id"]: c for c in cursor.fetchall()}

        # 6. Data-integrity check: payment history must add up to amount_paid
        cursor.execute(
            "SELECT COUNT(*) AS n FROM sales s WHERE s.business_id=%s AND s.amount_paid <> "
            "COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.sale_id = s.id), 0)",
            (business_id,))
        mismatched = cursor.fetchone()["n"]
        cursor.execute(
            "SELECT COUNT(*) AS n FROM treatments t WHERE t.business_id=%s AND t.amount_paid <> "
            "COALESCE((SELECT SUM(p.amount) FROM treatment_payments p WHERE p.treatment_id = t.id), 0)",
            (business_id,))
        mismatched += cursor.fetchone()["n"]

    # ── Aggregate (Decimal throughout; rounded once, at the end) ──
    def bucket():
        return {"amount": _ZERO, "count": 0}
    coll = {k: bucket() for k in ("stock_initial", "stock_repayment",
                                   "treatment_initial", "treatment_repayment", "recovery")}
    methods = {}

    def add_method(method, kind, amount):
        m = methods.setdefault(method or "Unspecified",
                               {"operating": _ZERO, "recovery": _ZERO, "total": _ZERO})
        m[kind] += amount
        m["total"] += amount

    stock_revenue = _ZERO
    treat_revenue = _ZERO
    known_revenue = _ZERO        # revenue whose cost is known
    cogs = _ZERO
    unknown_cost_revenue = _ZERO

    for r in stock_pay_rows:
        amt = r["amount"]
        stock_revenue += amt
        key = "stock_initial" if r["is_initial"] else "stock_repayment"
        coll[key]["amount"] += amt
        coll[key]["count"] += 1
        add_method(r["payment_method"], "operating", amt)
        if r["missing"] == 0 and r["total_amount"] > 0:
            known_revenue += amt
            cogs += amt * r["sale_cogs"] / r["total_amount"]
        else:
            unknown_cost_revenue += amt

    for r in treat_pay_rows:
        amt = r["amount"]
        a = treat_alloc[r["id"]]
        treat_revenue += amt
        key = "treatment_initial" if a["initial"] else "treatment_repayment"
        coll[key]["amount"] += amt
        coll[key]["count"] += 1
        add_method(r["payment_method"], "operating", amt)
        if a["cost_known"]:
            known_revenue += amt
            cogs += a["cogs"]
        else:
            unknown_cost_revenue += amt

    for r in recovery_rows:
        coll["recovery"]["amount"] += r["amount"]
        coll["recovery"]["count"] += 1
        add_method(r["payment_method"], "recovery", r["amount"])

    operating_revenue = stock_revenue + treat_revenue
    gross_profit = known_revenue - cogs
    margin = (gross_profit / known_revenue * 100) if known_revenue > 0 else None
    operating_collected = operating_revenue
    recoveries = coll["recovery"]["amount"]

    # ── Debt reconciliation ──
    open_stock, open_treat = _sum_debt(opening)
    close_stock, close_treat = _sum_debt(closing)
    opening_total = open_stock + open_treat
    closing_total = close_stock + close_treat
    new_charges = sales_activity + treatment_activity
    expected_closing = opening_total + new_charges - operating_collected - written_off + reversed_amount

    debtors = []
    for cid, v in closing.items():
        total = v["stock"] + v["treatment"]
        if total > 0:
            c = customers.get(cid)
            debtors.append({
                "customer_id": cid,
                "name": c["name"] if c else "No customer linked",
                "phone": c["phone"] if c else None,
                "stock": _q(v["stock"]), "treatment": _q(v["treatment"]), "total": _q(total),
            })
    debtors.sort(key=lambda d: d["total"], reverse=True)

    return {
        "start_date": start_date, "end_date": end_date,
        # 1-2 activity (NOT revenue)
        "sales_activity": _q(sales_activity), "sales_count": sales_count,
        "treatment_activity": _q(treatment_activity), "treatments_started": treatments_started,
        "service_charges_billed": _q(service_charges_billed), "medicine_billed": _q(medicine_billed),
        # 3-5 realised revenue
        "realised_stock_revenue": _q(stock_revenue),
        "realised_treatment_revenue": _q(treat_revenue),
        "realised_operating_revenue": _q(operating_revenue),
        # 6 money collected
        "money_collected_total": _q(operating_collected + recoveries),
        "operating_collected": _q(operating_collected),
        "collections": {k: {"amount": _q(v["amount"]), "count": v["count"]} for k, v in coll.items()},
        "by_method": {m: {k: _q(x) for k, x in v.items()} for m, v in sorted(methods.items())},
        # 7 outstanding debt
        "closing_debt": _q(closing_total), "closing_stock_debt": _q(close_stock),
        "closing_treatment_debt": _q(close_treat), "debtors": debtors,
        # 8 realised gross profit
        "cogs_on_collected": _q(cogs), "realised_gross_profit": _q(gross_profit),
        "gross_margin_pct": margin,
        "revenue_with_unknown_cost": _q(unknown_cost_revenue),
        "profit_incomplete": unknown_cost_revenue > 0,
        # 9-10 bad debt (separate)
        "recoveries": _q(recoveries),
        "written_off": _q(written_off), "written_off_count": written_off_count,
        "write_offs_reversed": _q(reversed_amount), "write_offs_reversed_count": reversed_count,
        # reconciliation
        "opening_debt": _q(opening_total), "new_charges": _q(new_charges),
        "payments_received": _q(operating_collected),
        "expected_closing_debt": _q(expected_closing),
        "reconciles": _q(expected_closing) == _q(closing_total),
        "payment_history_mismatches": mismatched,
    }
