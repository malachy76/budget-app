# reconcile.py — Phase 5B-3: read-only financial integrity & reconciliation check
#
# Answers, with evidence, "do my records agree with each other?" for ONE
# business. It WRITES NOTHING and never "fixes" anything — a discrepancy is
# reported honestly so the owner (or support) can look at it, rather than
# being silently forced to balance. Where history genuinely cannot be
# verified (e.g. rows older than a safeguard) the check says so instead of
# inventing a figure.
#
# Every figure is computed straight from the raw tables, independently of the
# dashboards it is compared against, so a bug in a dashboard cannot hide
# itself by also being the reference.
#
# Each check returns {"key", "title", "ok", "count", "detail", "examples"}:
# ok=True -> verified consistent
# ok=False -> a real discrepancy (count rows / examples listed)
# plus a top-level "all_ok".

from datetime import datetime, timezone
from decimal import Decimal

from db import get_db
from business import get_business
from contacts import normalize_phone
from baddebt import active_write_off_sql, _treatment_total_sql, SOURCE_SALE, SOURCE_TREATMENT
import customers
import daily_report
from returns import return_credit_sql

_ZERO = Decimal("0")


class ReconcileError(Exception):
    pass


def _check(key, title, rows, detail_ok, detail_bad, limit=5):
    rows = list(rows)
    return {
        "key": key, "title": title, "ok": len(rows) == 0, "count": len(rows),
        "detail": detail_ok if not rows else detail_bad.format(n=len(rows)),
        "examples": [dict(r) for r in rows[:limit]],
    }


def reconcile_business(business_id, owner_user_id):
    if get_business(business_id, owner_user_id) is None:
        raise ReconcileError("This business was not found, or does not belong to you.")

    checks = []
    with get_db() as (conn, cur):
        b = (business_id,)

        # ── Stock ──────────────────────────────────────────────────────────
        cur.execute("SELECT id, name, current_stock FROM products "
                    "WHERE business_id=%s AND current_stock < 0", b)
        checks.append(_check("negative_stock", "No product has negative stock", cur.fetchall(),
                             "No product has negative stock.",
                             "{n} product(s) have NEGATIVE stock."))

        cur.execute(
            "SELECT p.id, p.name, p.current_stock, COALESCE(m.total, 0) AS ledger_total "
            "FROM products p LEFT JOIN (SELECT product_id, SUM(quantity) AS total "
            " FROM inventory_movements WHERE business_id=%s GROUP BY product_id) m "
            " ON m.product_id = p.id "
            "WHERE p.business_id=%s AND p.current_stock <> COALESCE(m.total, 0)", (business_id, business_id))
        checks.append(_check("stock_vs_ledger", "Stock on hand equals the sum of its movements", cur.fetchall(),
                             "Every product's stock equals the sum of its recorded movements.",
                             "{n} product(s) have a stock figure that does not match their movement history."))

        # ── Sales & payments ───────────────────────────────────────────────
        cur.execute(
            "SELECT s.id, s.amount_paid, COALESCE(p.paid, 0) AS payments_total FROM sales s "
            "LEFT JOIN (SELECT sale_id, SUM(amount) AS paid FROM payments WHERE business_id=%s GROUP BY sale_id) p "
            " ON p.sale_id = s.id "
            "WHERE s.business_id=%s AND s.amount_paid <> COALESCE(p.paid, 0)", (business_id, business_id))
        checks.append(_check("sale_paid_vs_payments", "Each sale's amount paid equals its payment records",
                             cur.fetchall(), "Every sale's amount paid equals the sum of its payment records.",
                             "{n} sale(s) have an amount paid that does not match their payment records."))

        cur.execute("SELECT id, total_amount, amount_paid FROM sales "
                    "WHERE business_id=%s AND (amount_paid > total_amount OR amount_paid < 0)", b)
        checks.append(_check("sale_overpaid", "No sale is overpaid", cur.fetchall(),
                             "No sale has more paid than it is worth.",
                             "{n} sale(s) are overpaid or have a negative amount paid."))

        cur.execute(
            "SELECT s.id, s.total_amount, COALESCE(i.items_total, 0) AS items_total FROM sales s "
            "LEFT JOIN (SELECT sale_id, SUM(line_total) AS items_total FROM sale_items "
            " WHERE business_id=%s GROUP BY sale_id) i ON i.sale_id = s.id "
            "WHERE s.business_id=%s AND s.total_amount <> COALESCE(i.items_total, 0)", (business_id, business_id))
        checks.append(_check("sale_total_vs_items", "Each sale's total equals its items", cur.fetchall(),
                             "Every sale's total equals the sum of its item lines.",
                             "{n} sale(s) have a total that does not match their items."))

        cur.execute(
            "SELECT id, payment_status, total_amount, amount_paid FROM sales WHERE business_id=%s AND NOT ("
            " (payment_status='paid' AND amount_paid >= total_amount) OR "
            " (payment_status='partial' AND amount_paid > 0 AND amount_paid < total_amount) OR "
            " (payment_status='unpaid' AND amount_paid = 0 AND total_amount > 0))", b)
        checks.append(_check("sale_status", "Each sale's paid/partial/unpaid status is correct", cur.fetchall(),
                             "Every sale's status matches its amounts.",
                             "{n} sale(s) show a status that does not match their amounts."))

        # ── Sales returns (Phase 5C) ───────────────────────────────────────
        cur.execute(
            "SELECT sr.id, sr.return_value, COALESCE(i.items_value, 0) AS items_value FROM sale_returns sr "
            "LEFT JOIN (SELECT return_id, SUM(line_value) AS items_value FROM sale_return_items "
            " WHERE business_id=%s GROUP BY return_id) i ON i.return_id = sr.id "
            "WHERE sr.business_id=%s AND sr.return_value <> COALESCE(i.items_value, 0)", (business_id, business_id))
        checks.append(_check("return_value_vs_items", "Each return's value equals its items", cur.fetchall(),
                             "Every return's value equals the sum of its returned items.",
                             "{n} return(s) have a value that does not match their items."))

        cur.execute(
            "SELECT si.id AS sale_item_id, si.quantity AS sold, r.returned FROM sale_items si "
            "JOIN (SELECT sale_item_id, SUM(quantity) AS returned FROM sale_return_items "
            " WHERE business_id=%s GROUP BY sale_item_id) r ON r.sale_item_id = si.id "
            "WHERE si.business_id=%s AND r.returned > si.quantity", (business_id, business_id))
        checks.append(_check("over_returned", "Nothing has been returned more than once over", cur.fetchall(),
                             "No sale line has more returned than was sold.",
                             "{n} sale line(s) have more returned than was sold."))

        cur.execute(
            "SELECT s.id, s.amount_paid, r.refunded FROM sales s "
            "JOIN (SELECT sale_id, SUM(refund_amount) AS refunded FROM sale_returns "
            " WHERE business_id=%s GROUP BY sale_id) r ON r.sale_id = s.id "
            "WHERE s.business_id=%s AND r.refunded > s.amount_paid", (business_id, business_id))
        checks.append(_check("refund_exceeds_paid", "No sale has been refunded more than was paid", cur.fetchall(),
                             "No refund exceeds the money actually paid on its sale.",
                             "{n} sale(s) were refunded more than the customer paid."))

        cur.execute(
            "SELECT s.id FROM sales s WHERE s.business_id=%s AND "
            f"s.total_amount - s.amount_paid - {active_write_off_sql(SOURCE_SALE, 's')} - {return_credit_sql('s')} < 0",
            b)
        checks.append(_check("negative_balance", "No sale shows a negative amount owed", cur.fetchall(),
                             "No sale has a negative balance after payments, returns and write-offs.",
                             "{n} sale(s) show a negative balance."))

        # ── Treatments ─────────────────────────────────────────────────────
        cur.execute(
            "SELECT t.id, t.amount_paid, COALESCE(p.paid, 0) AS payments_total FROM treatments t "
            "LEFT JOIN (SELECT treatment_id, SUM(amount) AS paid FROM treatment_payments "
            " WHERE business_id=%s GROUP BY treatment_id) p ON p.treatment_id = t.id "
            "WHERE t.business_id=%s AND t.amount_paid <> COALESCE(p.paid, 0)", (business_id, business_id))
        checks.append(_check("treatment_paid_vs_payments", "Each treatment's amount paid equals its payment records",
                             cur.fetchall(), "Every treatment's amount paid equals its payment records.",
                             "{n} treatment(s) have an amount paid that does not match their payment records."))

        cur.execute(
            "SELECT t.id, t.amount_paid, bill FROM (SELECT t.id, t.amount_paid, "
            f" {_treatment_total_sql('t')} AS bill FROM treatments t WHERE t.business_id=%s) t "
            "WHERE t.amount_paid > t.bill", b)
        checks.append(_check("treatment_overpaid", "No treatment bill is overpaid", cur.fetchall(),
                             "No treatment has more paid than its bill.",
                             "{n} treatment(s) are overpaid."))

        # ── Cross-business references (must never exist) ──────────────────
        cur.execute(
            "SELECT 'sale.customer' AS what, s.id FROM sales s JOIN customers c ON c.id = s.customer_id "
            " WHERE s.business_id=%s AND c.business_id <> s.business_id "
            "UNION ALL SELECT 'sale_item.product', si.id FROM sale_items si JOIN products p ON p.id = si.product_id "
            " WHERE si.business_id=%s AND p.business_id <> si.business_id "
            "UNION ALL SELECT 'treatment.customer', t.id FROM treatments t JOIN customers c ON c.id = t.customer_id "
            " WHERE t.business_id=%s AND c.business_id <> t.business_id "
            "UNION ALL SELECT 'treatment_item.product', ti.id FROM treatment_items ti JOIN products p ON p.id = ti.product_id "
            " WHERE ti.business_id=%s AND p.business_id <> ti.business_id "
            "UNION ALL SELECT 'sale_return.sale', sr.id FROM sale_returns sr JOIN sales s ON s.id = sr.sale_id "
            " WHERE sr.business_id=%s AND s.business_id <> sr.business_id "
            "UNION ALL SELECT 'sale_return_item.product', i.id FROM sale_return_items i JOIN products p ON p.id = i.product_id "
            " WHERE i.business_id=%s AND p.business_id <> i.business_id",
            (business_id,) * 6)
        checks.append(_check("cross_business", "No record points at another business's data", cur.fetchall(),
                             "No sale, treatment or item refers to another business's customer or product.",
                             "{n} record(s) refer to another business's customer or product."))

        # ── Debt ───────────────────────────────────────────────────────────
        cur.execute(
            "SELECT COALESCE(SUM(GREATEST(x.c, 0)), 0) AS v, "
            " COALESCE(SUM(GREATEST(x.c, 0)) FILTER (WHERE x.customer_id IS NULL), 0) AS unlinked, "
            " COALESCE(SUM(GREATEST(x.c, 0)) FILTER (WHERE x.customer_id IS NOT NULL), 0) AS linked "
            "FROM (SELECT s.customer_id, "
            f" s.total_amount - s.amount_paid - {active_write_off_sql(SOURCE_SALE, 's')} "
            f" - {return_credit_sql('s')} AS c "
            " FROM sales s WHERE s.business_id=%s) x", b)
        raw_sale = cur.fetchone()
        cur.execute(
            "SELECT COALESCE(SUM(GREATEST(x.c, 0)), 0) AS v, "
            " COALESCE(SUM(GREATEST(x.c, 0)) FILTER (WHERE x.customer_id IS NULL), 0) AS unlinked, "
            " COALESCE(SUM(GREATEST(x.c, 0)) FILTER (WHERE x.customer_id IS NOT NULL), 0) AS linked "
            "FROM (SELECT t.customer_id, "
            f" {_treatment_total_sql('t')} - t.amount_paid - {active_write_off_sql(SOURCE_TREATMENT, 't')} AS c "
            " FROM treatments t WHERE t.business_id=%s) x", b)
        raw_treat = cur.fetchone()

    summary = customers.get_credit_summary(business_id, owner_user_id)
    diffs = []
    if summary["stock_sale_outstanding"] != raw_sale["linked"]:
        diffs.append({"what": "stock-sale debt", "dashboard": summary["stock_sale_outstanding"],
                      "records": raw_sale["linked"]})
    if summary["treatment_outstanding"] != raw_treat["linked"]:
        diffs.append({"what": "treatment debt", "dashboard": summary["treatment_outstanding"],
                      "records": raw_treat["linked"]})
    checks.append(_check("dashboard_vs_records", "Customer debt dashboard equals the underlying records", diffs,
                         "The customer debt dashboard equals the debt computed directly from sales, "
                         "treatments, payments and write-offs.",
                         "The customer debt dashboard disagrees with the underlying records on {n} line(s)."))

    unlinked = raw_sale["unlinked"] + raw_treat["unlinked"]
    checks.append(_check(
        "debt_without_customer", "All money owed belongs to a customer",
        [{"unlinked_amount": unlinked}] if unlinked > 0 else [],
        "Every amount owed is linked to a customer.",
        "Money is owed on records with NO customer linked (\u20A6" + f"{unlinked:,.2f}" + "). "
        "It does not appear in the customer debt dashboard."))

    # Customers who owe money must have a valid phone number.
    rows = []
    for c in customers.get_customers_with_balance(business_id, owner_user_id):
        if c["total_outstanding"] > 0 and normalize_phone(c["phone"])[0] is None:
            rows.append({"customer_id": c["id"], "name": c["name"], "owes": c["total_outstanding"]})
    checks.append(_check("owing_customer_phone", "Every customer who owes money has a phone number", rows,
                         "Every customer who owes money has a valid phone number.",
                         "{n} customer(s) owe money but have no valid phone number (older records)."))

    # ── Bad debt ───────────────────────────────────────────────────────────
    with get_db() as (conn, cur):
        cur.execute(
            "SELECT x.* FROM (SELECT 'sale' AS source, s.id, "
            f" {active_write_off_sql(SOURCE_SALE, 's')} AS written_off, "
            " COALESCE((SELECT SUM(rc.amount) FROM debt_recoveries rc WHERE rc.business_id=s.business_id "
            " AND rc.sale_id=s.id), 0) AS recovered FROM sales s WHERE s.business_id=%s "
            " UNION ALL SELECT 'treatment', t.id, "
            f" {active_write_off_sql(SOURCE_TREATMENT, 't')}, "
            " COALESCE((SELECT SUM(rc.amount) FROM debt_recoveries rc WHERE rc.business_id=t.business_id "
            " AND rc.treatment_id=t.id), 0) FROM treatments t WHERE t.business_id=%s) x "
            "WHERE x.recovered > x.written_off", (business_id, business_id))
        checks.append(_check("recovered_vs_written_off", "Recoveries never exceed what was written off",
                             cur.fetchall(), "No transaction has recovered more than was written off.",
                             "{n} transaction(s) show more recovered than written off."))

        cur.execute("SELECT MIN(d) AS first_day FROM ("
                    " SELECT MIN(created_at) AS d FROM sales WHERE business_id=%s "
                    " UNION ALL SELECT MIN(created_at) FROM treatments WHERE business_id=%s "
                    " UNION ALL SELECT MIN(created_at) FROM payments WHERE business_id=%s "
                    " UNION ALL SELECT MIN(created_at) FROM treatment_payments WHERE business_id=%s) z",
                    (business_id,) * 4)
        first = cur.fetchone()["first_day"]

    # ── End-of-Day report over the whole history ───────────────────────────
    if first is None:
        checks.append({"key": "end_of_day", "title": "End-of-Day report reconciles", "ok": True, "count": 0,
                       "detail": "No sales or treatments yet \u2014 nothing to reconcile.", "examples": []})
    else:
        first_day = first.replace(tzinfo=timezone.utc).astimezone(daily_report.BUSINESS_TZ).date() \
            if first.tzinfo is None else first.astimezone(daily_report.BUSINESS_TZ).date()
        rep = daily_report.get_cash_basis_report(
            business_id, owner_user_id, first_day, daily_report.business_today())
        problems = []
        if not rep["reconciles"]:
            problems.append({"what": "debt roll-forward", "expected_closing": rep["expected_closing_debt"],
                             "actual_closing": rep["closing_debt"]})
        if rep["payment_history_mismatches"]:
            problems.append({"what": "payment history mismatches", "count": rep["payment_history_mismatches"]})
        checks.append(_check("end_of_day", "End-of-Day report reconciles over the whole history", problems,
                             "Opening debt + new charges \u2212 payments \u2212 write-offs + reversals = "
                             "closing debt, over the business's whole history.",
                             "The End-of-Day report does not reconcile ({n} problem(s))."))

    return {
        "business_id": business_id,
        "checked_at": datetime.now(timezone.utc),
        "checks": checks,
        "all_ok": all(c["ok"] for c in checks),
        "failed": [c["key"] for c in checks if not c["ok"]],
        "limitations": [
            "Records written before Phase 5A-1 have no cost snapshot; their profit is reported as unknown, never invented.",
            "Rows older than the Phase 5B-3 database rules were not re-validated or changed; this check reports any that disagree.",
            "A recorded return cannot be undone; record a new sale if goods are taken back. Returned goods re-enter stock at the current average cost.",
        ],
}
