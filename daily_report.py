# daily_report.py — Business Mode: cash-basis End-of-Day / period report
#
# ACCOUNTING RULES (cash basis — these override any accrual-style figure)
# ──────────────────────────────────────────────────────────────────────
# * "Realised revenue" is money ACTUALLY RECEIVED, dated by the day it was
# received (Africa/Lagos). An unpaid invoice is never realised revenue.
# * A later repayment of an old debt becomes realised revenue on the day it
# is received. It never creates a sale and the original invoice is never
# counted again (invoice value is reported ONLY as "activity").
# * STOCK SALES — realised gross profit for a payment is
# payment x (1 - COGS / invoice total)
# i.e. each payment is treated as paying for the sale proportionally
# (the app does not record which items a payment covers). COGS comes from
# the cost snapshotted on each sale item (Phase 5A-1), never from the
# current product price. Once a sale is fully paid its whole COGS has been
# recognised exactly once.
# * TREATMENTS — a bill only ever contains the service charge plus medicines
# ALREADY dispensed, so a payment can never "pay for" medicine not yet
# dispensed. Cost is recognised proportionally with a CUMULATIVE method:
# cumulative cost after payment k =
# (total paid so far) x (cost of medicines dispensed up to the
# moment of payment k / bill up to then)
# cost recognised by payment k = that minus the same figure after
# payment k-1
# It only uses information known at the time of each payment (so a past
# day's report never changes), and once the bill is fully paid exactly the
# true total cost has been recognised.
# * Unknown costs are NEVER treated as zero. A cost is unknown when it is
# NULL, or a legacy 0 that was never confirmed (costing.known_cost_sql).
# Within a sale (or a treatment bill) only the part of the money that
# belongs to unknown-cost lines is set aside as "revenue with unknown
# cost" and excluded from gross profit — the known-cost lines still earn
# profit — and the report is flagged incomplete and lists the products.
# * Bad-debt RECOVERIES, write-offs and write-off reversals are reported
# separately. They are never part of operating revenue or gross profit,
# and a write-off/reversal is never "money received".
# * Gross profit is NOT net profit: business operating expenses are not
# recorded in this app yet, so net profit is not calculated.
#
# DEBT RECONCILIATION (as-of balances, never today's balance projected back)
# Opening debt + new charges billed - payments received
# - written off + write-offs reversed = Closing debt
# where "new charges billed" = invoices created in the period + treatment
# service charges created in the period + medicines dispensed (priced) in
# the period. The check is computed from raw records and reported honestly
# (reconciles: True/False) rather than forced to balance.
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
from costing import known_cost_sql

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
    """[start, end) as (naive_utc_start, naive_utc_end, aware_start, aware_end) for the Africa/Lagos business days start_date .. end_date inclusive."""
    s = datetime.combine(start_date, time.min, tzinfo=BUSINESS_TZ).astimezone(_UTC)
    e = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ).astimezone(_UTC)
    return s.replace(tzinfo=None), e.replace(tzinfo=None), s, e


def _naive_utc(dt):
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(_UTC).replace(tzinfo=None)
    return dt


# ── Pure allocation logic (unit-tested directly) ────────────────────────────

def allocate_treatment_payments(service_charge, payments, dispensing):
    """Cumulative proportional cost recognition for ONE treatment. payments: [{"id", "amount", "created_at"(naive UTC)}] (any order) dispensing:[{"at"(naive UTC), "qty", "price", "cost"(None = unknown)}] only PRICED dispensings (the ones that are on the bill). Returns a list (payment order) of dicts with: id, amount, initial (bool), cogs (cost of the KNOWN-cost medicines the payment covers), unknown_revenue (the part of the payment that belongs to unknown-cost medicines — excluded from profit) and cost_known (= no unknown part). Everything is computed cumulatively from information available at the moment of each payment, so a past day's figures never change."""
    service_charge = Decimal(service_charge)
    ordered = sorted(payments, key=lambda p: (p["created_at"], p["id"]))
    cum_paid = _ZERO
    prev_cum_cost = _ZERO
    prev_cum_unknown = _ZERO
    out = []
    for i, p in enumerate(ordered):
        billed = service_charge
        cost = _ZERO
        unknown_charges = _ZERO
        for d in dispensing:
            if d["at"] <= p["created_at"]:
                line = (d["qty"] * d["price"]).quantize(_CENT, rounding=ROUND_HALF_UP)
                billed += line
                if d["cost"] is None:
                    unknown_charges += line
                else:
                    cost += d["qty"] * d["cost"]
        cum_paid += p["amount"]
        cum_cost = (cum_paid * cost / billed) if billed > 0 else _ZERO
        cum_unknown = (cum_paid * unknown_charges / billed) if billed > 0 else _ZERO
        unknown_rev = cum_unknown - prev_cum_unknown
        out.append({
            "id": p["id"], "amount": p["amount"], "initial": i == 0,
            "cogs": cum_cost - prev_cum_cost, "unknown_revenue": unknown_rev,
            "cost_known": unknown_rev == 0,
        })
        prev_cum_cost = cum_cost
        prev_cum_unknown = cum_unknown
    return out


# ── As-of debt (used for opening / closing balances) ────────────────────────

def _debt_as_of(cursor, business_id, cutoff_naive, cutoff_aware):
    """Collectible debt per customer using ONLY records that existed before the cutoff instant. Returns {customer_id|None: {"stock": D, "treatment": D}}."""
    result = {}

    cursor.execute(
        "SELECT s.customer_id, "
        " COALESCE(SUM(s.total_amount - COALESCE(p.paid, 0) - COALESCE(w.wo, 0) - COALESCE(rc.d, 0)), 0) AS debt "
        "FROM sales s "
        "LEFT JOIN (SELECT sale_id, SUM(amount) AS paid FROM payments "
        " WHERE business_id=%s AND created_at < %s GROUP BY sale_id) p ON p.sale_id = s.id "
        "LEFT JOIN (SELECT w.sale_id, SUM(w.amount) AS wo FROM debt_write_offs w "
        " WHERE w.business_id=%s AND w.sale_id IS NOT NULL AND w.created_at < %s "
        " AND NOT EXISTS (SELECT 1 FROM debt_write_off_reversals r "
        " WHERE r.write_off_id = w.id AND r.created_at < %s) "
        " GROUP BY w.sale_id) w ON w.sale_id = s.id "
        "LEFT JOIN (SELECT sr.sale_id, SUM(sr.debt_reduction) AS d FROM sale_returns sr "
        " WHERE sr.business_id=%s AND sr.created_at < %s GROUP BY sr.sale_id) rc ON rc.sale_id = s.id "
        "WHERE s.business_id=%s AND s.created_at < %s "
        "GROUP BY s.customer_id",
        (business_id, cutoff_naive, business_id, cutoff_aware, cutoff_aware,
         business_id, cutoff_naive, business_id, cutoff_naive),
    )
    for r in cursor.fetchall():
        result.setdefault(r["customer_id"], {"stock": _ZERO, "treatment": _ZERO})["stock"] += r["debt"]

    cursor.execute(
        "SELECT t.customer_id, "
        " COALESCE(SUM(t.service_charge + COALESCE(d.billed, 0) - COALESCE(p.paid, 0) "
        " - COALESCE(w.wo, 0)), 0) AS debt "
        "FROM treatments t "
        "LEFT JOIN (SELECT ti.treatment_id, SUM(ROUND(d.quantity * d.unit_price, 2)) AS billed "
        " FROM treatment_dispensing d JOIN treatment_items ti ON ti.id = d.treatment_item_id "
        " WHERE d.business_id=%s AND d.unit_price IS NOT NULL AND d.dispensed_at < %s "
        " GROUP BY ti.treatment_id) d ON d.treatment_id = t.id "
        "LEFT JOIN (SELECT treatment_id, SUM(amount) AS paid FROM treatment_payments "
        " WHERE business_id=%s AND created_at < %s GROUP BY treatment_id) p ON p.treatment_id = t.id "
        "LEFT JOIN (SELECT w.treatment_id, SUM(w.amount) AS wo FROM debt_write_offs w "
        " WHERE w.business_id=%s AND w.treatment_id IS NOT NULL AND w.created_at < %s "
        " AND NOT EXISTS (SELECT 1 FROM debt_write_off_reversals r "
        " WHERE r.write_off_id = w.id AND r.created_at < %s) "
        " GROUP BY w.treatment_id) w ON w.treatment_id = t.id "
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


def allocate_sale_events(sale, payments, returns):
    """Cash-basis profit for a stock sale that HAS RETURNS (Phase 5C). Without returns, every payment earns revenue and cost in proportion to the sale (the Phase 5A/5B rule). A return changes the sale itself: its value, its known cost and its unknown-cost value all shrink, and a refund takes money back. So the sale is replayed event by event (payments and returns in time order): after each event the realised cost is net_paid x known_cost / value and the realised unknown-cost revenue is net_paid x unknown_value / value (net_paid = payments - refunds). The CHANGE at each event is what that event contributes on its own date. sale {"total", "known_cogs", "unknown_total"} payments [{"id", "amount", "at"}] (negative amounts are payment reversals) returns [{"id", "at", "value", "known_cost", "unknown_value", "refund"}] Returns one dict per event: {"kind", "id", "at", "d_paid", "d_cogs", "d_unknown_rev", "d_known_rev"} (d_paid is money in (+) or refunded out (-)). Pure function; no database access."""
    evs = ([(p["at"], 0, p["id"], "payment", p) for p in payments]
           + [(r["at"], 1, r["id"], "return", r) for r in returns])
    evs.sort(key=lambda e: (e[0], e[1], e[2]))
    total, cogs, unk = sale["total"], sale["known_cogs"], sale["unknown_total"]
    net_paid = rc = ru = _ZERO
    out = []
    for at, _o, eid, kind, e in evs:
        if kind == "payment":
            d_paid = e["amount"]
        else:
            total -= e["value"]
            cogs -= e["known_cost"]
            unk -= e["unknown_value"]
            d_paid = -e["refund"]
        net_paid += d_paid
        if total > 0:
            new_rc = net_paid * cogs / total
            new_ru = net_paid * unk / total
        else:
            new_rc = new_ru = _ZERO
        out.append({"kind": kind, "id": eid, "at": at, "d_paid": d_paid,
                    "d_cogs": new_rc - rc, "d_unknown_rev": new_ru - ru,
                    "d_known_rev": d_paid - (new_ru - ru)})
        rc, ru = new_rc, new_ru
    return out


# ── The report ──────────────────────────────────────────────────────────────

def get_cash_basis_report(business_id, owner_user_id, start_date, end_date):
    """Everything for the End-of-Day / period summary, cash basis. start_date/end_date are Africa/Lagos business dates, inclusive."""
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
            "SELECT COALESCE(SUM(ROUND(quantity * unit_price, 2)), 0) AS v FROM treatment_dispensing "
            "WHERE business_id=%s AND unit_price IS NOT NULL "
            "AND dispensed_at >= %s AND dispensed_at < %s",
            (business_id, s_n, e_n))
        medicine_billed = cursor.fetchone()["v"]
        treatment_activity = service_charges_billed + medicine_billed

        # 2. Stock-sale collections with cost info per sale
        cursor.execute(
            "SELECT p.id, p.sale_id, p.amount, p.payment_method, p.created_at, "
            " (p.created_at = s.created_at) AS is_initial, s.total_amount, "
            " COALESCE(c.known_cogs, 0) AS known_cogs, COALESCE(c.unknown_total, 0) AS unknown_total, "
            " COALESCE(c.lines, 0) AS lines "
            "FROM payments p "
            "JOIN sales s ON s.id = p.sale_id AND s.business_id = p.business_id "
            "LEFT JOIN (SELECT si.sale_id, COUNT(*) AS lines, "
            f" SUM(si.quantity * si.unit_cost) FILTER (WHERE {known_cost_sql('si')}) AS known_cogs, "
            f" SUM(si.line_total) FILTER (WHERE NOT {known_cost_sql('si')}) AS unknown_total "
            " FROM sale_items si WHERE si.business_id=%s GROUP BY si.sale_id) c ON c.sale_id = s.id "
            "WHERE p.business_id=%s AND p.created_at >= %s AND p.created_at < %s "
            # Phase 5C: a sale that has returns is handled by allocate_sale_events() below
            " AND NOT EXISTS (SELECT 1 FROM sale_returns sr WHERE sr.business_id = p.business_id "
            " AND sr.sale_id = p.sale_id AND sr.created_at < %s) "
            "ORDER BY p.created_at, p.id",
            (business_id, business_id, s_n, e_n, e_n))
        stock_pay_rows = cursor.fetchall()

        # 2b. Phase 5C — sales returns in the period, and the sales that need an event replay
        cursor.execute(
            "SELECT sr.id, sr.sale_id, sr.return_value, sr.debt_reduction, sr.refund_amount, sr.refund_method "
            "FROM sale_returns sr WHERE sr.business_id=%s AND sr.created_at >= %s AND sr.created_at < %s",
            (business_id, s_n, e_n))
        returns_rows = cursor.fetchall()
        cursor.execute(
            "SELECT DISTINCT sr.sale_id FROM sale_returns sr WHERE sr.business_id=%s AND sr.created_at < %s "
            "AND (sr.created_at >= %s OR EXISTS (SELECT 1 FROM payments p WHERE p.business_id = sr.business_id "
            " AND p.sale_id = sr.sale_id AND p.created_at >= %s AND p.created_at < %s))",
            (business_id, e_n, s_n, s_n, e_n))
        replay_ids = sorted(r["sale_id"] for r in cursor.fetchall())
        replay_events = []
        if replay_ids:
            cursor.execute(
                "SELECT s.id, s.created_at, s.total_amount, COALESCE(c.known_cogs, 0) AS known_cogs, "
                " COALESCE(c.unknown_total, 0) AS unknown_total FROM sales s "
                "LEFT JOIN (SELECT si.sale_id, "
                f" SUM(si.quantity * si.unit_cost) FILTER (WHERE {known_cost_sql('si')}) AS known_cogs, "
                f" SUM(si.line_total) FILTER (WHERE NOT {known_cost_sql('si')}) AS unknown_total "
                " FROM sale_items si WHERE si.business_id=%s GROUP BY si.sale_id) c ON c.sale_id = s.id "
                "WHERE s.business_id=%s AND s.id = ANY(%s)", (business_id, business_id, replay_ids))
            sale_info = {r["id"]: r for r in cursor.fetchall()}
            cursor.execute(
                "SELECT id, sale_id, amount, payment_method, created_at FROM payments "
                "WHERE business_id=%s AND sale_id = ANY(%s) AND created_at < %s",
                (business_id, replay_ids, e_n))
            pays_by_sale = {}
            for r in cursor.fetchall():
                pays_by_sale.setdefault(r["sale_id"], []).append(r)
            cursor.execute(
                "SELECT sr.id, sr.sale_id, sr.created_at, sr.return_value, sr.refund_amount, sr.refund_method, "
                " COALESCE((SELECT SUM(sri.quantity * sri.unit_cost) FROM sale_return_items sri "
                f" WHERE sri.return_id = sr.id AND {known_cost_sql('sri')}), 0) AS known_cost, "
                " COALESCE((SELECT SUM(sri.line_value) FROM sale_return_items sri "
                f" WHERE sri.return_id = sr.id AND NOT {known_cost_sql('sri')}), 0) AS unknown_value "
                "FROM sale_returns sr WHERE sr.business_id=%s AND sr.sale_id = ANY(%s) AND sr.created_at < %s",
                (business_id, replay_ids, e_n))
            rets_by_sale = {}
            for r in cursor.fetchall():
                rets_by_sale.setdefault(r["sale_id"], []).append(r)
            for sid in replay_ids:
                si = sale_info[sid]
                pay_meta = {p["id"]: p for p in pays_by_sale.get(sid, [])}
                ret_meta = {r["id"]: r for r in rets_by_sale.get(sid, [])}
                evs = allocate_sale_events(
                    {"total": si["total_amount"], "known_cogs": si["known_cogs"], "unknown_total": si["unknown_total"]},
                    [{"id": p["id"], "amount": p["amount"], "at": p["created_at"]} for p in pays_by_sale.get(sid, [])],
                    [{"id": r["id"], "at": r["created_at"], "value": r["return_value"], "known_cost": r["known_cost"],
                      "unknown_value": r["unknown_value"], "refund": r["refund_amount"]}
                     for r in rets_by_sale.get(sid, [])])
                for ev in evs:
                    if not (s_n <= ev["at"] < e_n):
                        continue
                    ev["sale_id"] = sid
                    ev["is_initial"] = (ev["kind"] == "payment" and ev["at"] == si["created_at"])
                    ev["method"] = (pay_meta[ev["id"]]["payment_method"] if ev["kind"] == "payment"
                                    else ret_meta[ev["id"]]["refund_method"])
                    replay_events.append(ev)

        # 3. Treatment collections (cumulative cost allocation needs each
        # affected treatment's full payment + dispensing history)
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
                " d.unit_price AS price, "
                f" CASE WHEN {known_cost_sql('d')} THEN d.unit_cost END AS cost "
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

        # 7. Which products have no reliable cost, among the sales/treatments
        # that collected money in this period (these are what make profit
        # incomplete). Listed so the owner knows exactly what to fix.
        unknown_items = []
        unknown_sales = unknown_treatments = 0
        stock_ids = sorted({r["sale_id"] for r in stock_pay_rows} | {e["sale_id"] for e in replay_events if e["kind"] == "payment"})
        if stock_ids:
            cursor.execute(
                "SELECT si.product_name AS product, COUNT(*) AS lines, SUM(si.quantity) AS qty, "
                " COALESCE(SUM(si.line_total), 0) AS value "
                "FROM sale_items si WHERE si.business_id=%s AND si.sale_id = ANY(%s) "
                f" AND NOT {known_cost_sql('si')} GROUP BY si.product_name ORDER BY value DESC, product",
                (business_id, stock_ids))
            unknown_items += [{"source": "Stock sale", "product": r["product"], "lines": r["lines"],
                               "quantity": r["qty"], "value": r["value"]} for r in cursor.fetchall()]
            cursor.execute(
                "SELECT COUNT(DISTINCT si.sale_id) AS n FROM sale_items si "
                f"WHERE si.business_id=%s AND si.sale_id = ANY(%s) AND NOT {known_cost_sql('si')}",
                (business_id, stock_ids))
            unknown_sales = cursor.fetchone()["n"]
        if treat_ids:
            cursor.execute(
                "SELECT pr.name AS product, COUNT(*) AS lines, SUM(d.quantity) AS qty, "
                " COALESCE(SUM(ROUND(d.quantity * d.unit_price, 2)), 0) AS value "
                "FROM treatment_dispensing d "
                "JOIN treatment_items ti ON ti.id = d.treatment_item_id "
                "JOIN products pr ON pr.id = ti.product_id "
                "WHERE d.business_id=%s AND ti.treatment_id = ANY(%s) AND d.unit_price IS NOT NULL "
                f" AND NOT {known_cost_sql('d')} GROUP BY pr.name ORDER BY value DESC, product",
                (business_id, treat_ids))
            unknown_items += [{"source": "Treatment", "product": r["product"], "lines": r["lines"],
                               "quantity": r["qty"], "value": r["value"]} for r in cursor.fetchall()]
            cursor.execute(
                "SELECT COUNT(DISTINCT ti.treatment_id) AS n FROM treatment_dispensing d "
                "JOIN treatment_items ti ON ti.id = d.treatment_item_id "
                "WHERE d.business_id=%s AND ti.treatment_id = ANY(%s) AND d.unit_price IS NOT NULL "
                f" AND NOT {known_cost_sql('d')}",
                (business_id, treat_ids))
            unknown_treatments = cursor.fetchone()["n"]

    # ── Aggregate (Decimal throughout; rounded once, at the end) ──
    def bucket():
        return {"amount": _ZERO, "count": 0}
    # Phase 5B-3: "*_reversal" buckets hold NEGATIVE compensating payment rows
    # (a mistaken payment that was reversed). They are kept in their own line
    # so a repayment is never silently reduced, yet every bucket still adds up
    # to the money-collected total.
    coll = {k: bucket() for k in ("stock_initial", "stock_repayment", "stock_reversal",
                                   "treatment_initial", "treatment_repayment",
                                   "treatment_reversal", "recovery")}
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
        key = ("stock_reversal" if amt < 0
               else "stock_initial" if r["is_initial"] else "stock_repayment")
        coll[key]["amount"] += amt
        coll[key]["count"] += 1
        add_method(r["payment_method"], "operating", amt)
        if r["lines"] == 0 or r["total_amount"] <= 0:
            unknown_cost_revenue += amt                      # no item records: cost unknowable
        else:
            # Each payment pays for the sale proportionally; the part that
            # belongs to unknown-cost lines is set aside (never costed at 0),
            # the rest earns profit against its recorded cost.
            unknown_part = amt * r["unknown_total"] / r["total_amount"]
            unknown_cost_revenue += unknown_part
            known_revenue += amt - unknown_part
            cogs += amt * r["known_cogs"] / r["total_amount"]

    # Phase 5C: sales that have returns (replayed event by event)
    refunds_paid = _ZERO
    refunds_by_method = {}
    for ev in replay_events:
        known_revenue += ev["d_known_rev"]
        unknown_cost_revenue += ev["d_unknown_rev"]
        cogs += ev["d_cogs"]
        if ev["kind"] == "payment":
            amt = ev["d_paid"]
            stock_revenue += amt
            key = ("stock_reversal" if amt < 0
                   else "stock_initial" if ev["is_initial"] else "stock_repayment")
            coll[key]["amount"] += amt
            coll[key]["count"] += 1
            add_method(ev["method"], "operating", amt)
        elif ev["d_paid"] != 0:
            refunds_paid += -ev["d_paid"]
            refunds_by_method[ev["method"] or "Unspecified"] = (
                refunds_by_method.get(ev["method"] or "Unspecified", _ZERO) + -ev["d_paid"])
    returns_value = sum((r["return_value"] for r in returns_rows), _ZERO)
    debt_reduced_by_returns = sum((r["debt_reduction"] for r in returns_rows), _ZERO)

    for r in treat_pay_rows:
        amt = r["amount"]
        a = treat_alloc[r["id"]]
        treat_revenue += amt
        key = ("treatment_reversal" if amt < 0
               else "treatment_initial" if a["initial"] else "treatment_repayment")
        coll[key]["amount"] += amt
        coll[key]["count"] += 1
        add_method(r["payment_method"], "operating", amt)
        known_revenue += amt - a["unknown_revenue"]
        unknown_cost_revenue += a["unknown_revenue"]
        cogs += a["cogs"]

    for r in recovery_rows:
        coll["recovery"]["amount"] += r["amount"]
        coll["recovery"]["count"] += 1
        add_method(r["payment_method"], "recovery", r["amount"])

    operating_revenue = stock_revenue + treat_revenue          # money RECEIVED (gross of refunds)
    net_operating_revenue = operating_revenue - refunds_paid   # after refunds (Phase 5C)
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
    expected_closing = (opening_total + new_charges - operating_collected - written_off
                        + reversed_amount - debt_reduced_by_returns)

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
        # complement of the known part so the two figures always add up exactly
        "revenue_with_unknown_cost": _q(net_operating_revenue) - _q(known_revenue),
        "profit_incomplete": unknown_cost_revenue > 0,
        "unknown_cost_items": unknown_items,
        "unknown_cost_sales": unknown_sales, "unknown_cost_treatments": unknown_treatments,
        # 9-10 bad debt (separate)
        "recoveries": _q(recoveries),
        "written_off": _q(written_off), "written_off_count": written_off_count,
        "write_offs_reversed": _q(reversed_amount), "write_offs_reversed_count": reversed_count,
        # reconciliation
        "opening_debt": _q(opening_total), "new_charges": _q(new_charges),
        "payments_received": _q(operating_collected),
        "debt_reduced_by_returns": _q(debt_reduced_by_returns),
        # Phase 5C — sales returns & refunds (a debt reduction is NOT a cash refund)
        "gross_sales": _q(sales_activity),
        "sales_returns_value": _q(returns_value), "sales_returns_count": len(returns_rows),
        "net_sales": _q(sales_activity) - _q(returns_value),
        "refunds_paid": _q(refunds_paid),
        "refunds_by_method": {m: _q(v) for m, v in sorted(refunds_by_method.items())},
        "net_realised_operating_revenue": _q(net_operating_revenue),
        "net_cash_after_refunds": _q(operating_collected + recoveries - refunds_paid),
        "expected_closing_debt": _q(expected_closing),
        "reconciles": _q(expected_closing) == _q(closing_total),
        "payment_history_mismatches": mismatched,
    }
