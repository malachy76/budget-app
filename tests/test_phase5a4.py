# Phase 5A-4 automated tests — real code, real PostgreSQL.
import threading
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

import baddebt
from baddebt import (
    write_off_debt, reverse_write_off, record_recovery, get_transaction_snapshot,
    get_bad_debt_summary, get_write_off_events, get_recovery_events,
    get_collectible_debts, get_unrecovered_write_offs, get_transaction_history,
    OTHER_REASON, SOURCE_SALE, SOURCE_TREATMENT,
)
from customers import (
    record_payment, get_customers_with_balance, get_credit_summary,
    get_customer_sales, get_customer_treatments, get_sale_payments,
)
from treatments import record_treatment_payment, get_treatment_billing, get_treatment_payments
from helpers import World, q, one, key, make_user, make_business, make_product, make_customer

REASON = "Customer is unable to repay"


def wo(w, tx, amount, src=SOURCE_SALE, k=None, reason=REASON, note=""):
    return write_off_debt(src, tx, w.bid, w.uid, w.uid, amount, reason, note, key() if k is None else k)


def rec(w, tx, amount, src=SOURCE_SALE, k=None, method="Cash", note=""):
    return record_recovery(src, tx, w.bid, w.uid, w.uid, amount, method, note, key() if k is None else k)


def snap(w, tx, src=SOURCE_SALE):
    return get_transaction_snapshot(src, tx, w.bid, w.uid)


def count(table, bid):
    return one(f"SELECT COUNT(*) AS n FROM {table} WHERE business_id=%s", (bid,))["n"]


# ── Tests 1-5: the accounting examples from the spec ────────────────────────

def test01_full_write_off():
    w = World(); s = w.sale(20)                       # 20 x 1000 = 20,000 on credit
    wid, msg = wo(w, s, "20000")
    assert wid, msg
    sn = snap(w, s)
    assert sn["total"] == D("20000") and sn["written_off"] == D("20000")
    assert sn["collectible"] == D("0")
    cust = [c for c in get_customers_with_balance(w.bid, w.uid) if c["id"] == w.cid][0]
    assert cust["total_outstanding"] == D("0") and cust["unpaid_sales_count"] == 0
    assert get_credit_summary(w.bid, w.uid)["total_outstanding"] == D("0")
    assert get_customer_sales(w.cid, w.bid, w.uid)[0]["outstanding"] == D("0")


def test02_partial_write_off():
    w = World(); s = w.sale(20)
    assert wo(w, s, "8000")[0]
    sn = snap(w, s)
    assert sn["written_off"] == D("8000") and sn["collectible"] == D("12000")
    cust = [c for c in get_customers_with_balance(w.bid, w.uid) if c["id"] == w.cid][0]
    assert cust["total_outstanding"] == D("12000") and cust["unpaid_sales_count"] == 1


def test03_partial_write_off_then_ordinary_payment():
    w = World(); s = w.sale(20)
    assert wo(w, s, "8000")[0]
    ok, msg = record_payment(s, w.bid, w.uid, w.uid, "5000", "Cash", None)
    assert ok, msg
    sn = snap(w, s)
    assert sn["collectible"] == D("7000") and sn["unrecovered"] == D("8000")
    assert sn["paid"] == D("5000") and sn["recovered"] == D("0")
    # an ordinary payment can't exceed what is still collectible (7,000)
    ok, msg = record_payment(s, w.bid, w.uid, w.uid, "7000.01", "Cash", None)
    assert not ok and "outstanding" in msg.lower()
    ok, msg = record_payment(s, w.bid, w.uid, w.uid, "7000", "Cash", None)
    assert ok, msg
    assert snap(w, s)["collectible"] == D("0")
    assert one("SELECT payment_status FROM sales WHERE id=%s", (s,))["payment_status"] == "partial"


def test04_full_write_off_then_partial_recovery():
    w = World(); s = w.sale(20)
    assert wo(w, s, "20000")[0]
    rid, msg = rec(w, s, "5000")
    assert rid, msg
    sn = snap(w, s)
    assert sn["collectible"] == D("0") and sn["recovered"] == D("5000")
    assert sn["unrecovered"] == D("15000") and sn["written_off"] == D("20000")
    summ = get_bad_debt_summary(w.bid, w.uid)
    assert (summ["total_written_off"], summ["total_recovered"], summ["unrecovered"]) == \
        (D("20000"), D("5000"), D("15000"))


def test05_full_recovery():
    w = World(); s = w.sale(20)
    assert wo(w, s, "20000")[0]
    assert rec(w, s, "5000")[0] and rec(w, s, "15000")[0]
    sn = snap(w, s)
    assert sn["unrecovered"] == D("0") and sn["recovered"] == D("20000")
    rid, msg = rec(w, s, "1")
    assert rid is None
    hist = get_recovery_events(w.bid, w.uid)
    assert [e["amount"] for e in hist] == [D("15000"), D("5000")]
    assert get_unrecovered_write_offs(w.bid, w.uid) == []


def test_spec_example2_recovery_never_reduces_collectible_debt():
    w = World(); s = w.sale(20)
    wo(w, s, "8000")
    record_payment(s, w.bid, w.uid, w.uid, "5000", "Cash", None)
    assert rec(w, s, "3000")[0]
    sn = snap(w, s)
    assert sn["collectible"] == D("7000")          # unchanged by the recovery
    assert sn["recovered"] == D("3000") and sn["unrecovered"] == D("5000")
    assert sn["paid"] == D("5000")                 # recovery is not an ordinary payment


# ── Tests 6-9: validation ───────────────────────────────────────────────────

def test06_excessive_write_off_rejected_without_changes():
    w = World(); s = w.sale(10)
    before = count("debt_write_offs", w.bid)
    wid, msg = wo(w, s, "12000")
    assert wid is None and "at most" in msg
    assert count("debt_write_offs", w.bid) == before
    assert snap(w, s)["collectible"] == D("10000")


def test07_excessive_recovery_rejected():
    w = World(); s = w.sale(5)
    wo(w, s, "5000")
    rid, msg = rec(w, s, "6000")
    assert rid is None and "at most" in msg
    assert count("debt_recoveries", w.bid) == 0


def test08_paid_transaction_cannot_be_written_off():
    w = World(); s = w.sale(5, paid="5000")
    wid, msg = wo(w, s, "1")
    assert wid is None and "no collectible" in msg.lower()
    # fully written-off balance can't be written off twice either
    s2 = w.sale(5); wo(w, s2, "5000")
    assert wo(w, s2, "1")[0] is None
    # and an unwritten-off sale has nothing to recover
    assert rec(w, w.sale(1), "1")[0] is None


def test09_business_ownership():
    a = World(); b = World()
    sa = a.sale(10)
    # user B on business A
    wid, msg = write_off_debt(SOURCE_SALE, sa, a.bid, b.uid, b.uid, "100", REASON, "", key())
    assert wid is None and "not found" in msg.lower()
    # user B on own business, but A's sale id
    wid, msg = write_off_debt(SOURCE_SALE, sa, b.bid, b.uid, b.uid, "100", REASON, "", key())
    assert wid is None and "not found" in msg.lower()
    wo(a, sa, "1000")
    # same for recoveries, reads and reversal
    rid, msg = record_recovery(SOURCE_SALE, sa, b.bid, b.uid, b.uid, "100", "Cash", "", key())
    assert rid is None
    assert record_recovery(SOURCE_SALE, sa, a.bid, b.uid, b.uid, "100", "Cash", "", key())[0] is None
    wid_a = one("SELECT id FROM debt_write_offs WHERE business_id=%s", (a.bid,))["id"]
    ok, msg = reverse_write_off(wid_a, b.bid, b.uid, b.uid, "mistake")
    assert not ok
    assert get_write_off_events(b.bid, b.uid) == []
    with pytest.raises(baddebt.BadDebtError):
        get_bad_debt_summary(a.bid, b.uid)
    assert count("debt_write_offs", a.bid) == 1 and count("debt_recoveries", a.bid) == 0
    assert count("debt_write_offs", b.bid) == 0


def test_validation_reason_amount_method_customer():
    w = World(); s = w.sale(10)
    assert wo(w, s, "100", reason=OTHER_REASON, note="")[0] is None        # Other needs explanation
    assert wo(w, s, "100", reason=OTHER_REASON, note="Moved abroad")[0]
    assert wo(w, s, "100", reason="made up")[0] is None
    assert wo(w, s, "0")[0] is None and wo(w, s, "-5")[0] is None and wo(w, s, "abc")[0] is None
    assert wo(w, s, "NaN")[0] is None
    assert wo(w, s, "100", k="")[0] is None                                # no submission reference
    assert wo(w, s, "100", src="bogus")[0] is None
    assert rec(w, s, "10", method="Bitcoin")[0] is None
    # transaction with no customer linked cannot be written off
    # (since Phase 5B-1 create_sale refuses a credit sale without a customer, so
    #  this simulates an OLDER record created before that rule existed)
    sid = one("INSERT INTO sales (business_id, customer_id, total_amount, amount_paid, payment_status, created_by) "
              "VALUES (%s, NULL, 1000, 0, 'unpaid', %s) RETURNING id", (w.bid, w.uid))["id"]
    wid, msg = wo(w, sid, "100")
    assert wid is None and "no customer" in msg.lower()


def test_decimal_precision():
    w = World(price="333.33"); s = w.sale(3)                 # 999.99
    assert snap(w, s)["total"] == D("999.99")
    assert wo(w, s, "333.33")[0] and wo(w, s, "333.33")[0] and wo(w, s, "333.33")[0]
    assert snap(w, s)["collectible"] == D("0.00")
    assert wo(w, s, "0.01")[0] is None


# ── Test 10: original records are never touched ─────────────────────────────

def _state(w, sale_id=None, treatment_id=None):
    s = {}
    s["product"] = one("SELECT current_stock, purchase_price, selling_price FROM products WHERE id=%s", (w.pid,))
    s["moves"] = q("SELECT movement_type, quantity, quantity_before, quantity_after, unit_cost FROM inventory_movements "
                   "WHERE business_id=%s ORDER BY id", (w.bid,))
    if sale_id:
        s["sale"] = one("SELECT total_amount, amount_paid, payment_status, customer_id, created_at FROM sales WHERE id=%s", (sale_id,))
        s["items"] = q("SELECT product_id, quantity, unit_price, unit_cost, line_total FROM sale_items WHERE sale_id=%s ORDER BY id", (sale_id,))
        s["payments"] = q("SELECT amount, payment_method, created_at FROM payments WHERE sale_id=%s ORDER BY id", (sale_id,))
    if treatment_id:
        s["tx"] = one("SELECT service_charge, amount_paid, customer_id, status FROM treatments WHERE id=%s", (treatment_id,))
        s["disp"] = q("SELECT d.quantity, d.unit_price, d.unit_cost FROM treatment_dispensing d "
                      "JOIN treatment_items i ON i.id=d.treatment_item_id WHERE i.treatment_id=%s ORDER BY d.id", (treatment_id,))
        s["tpay"] = q("SELECT amount FROM treatment_payments WHERE treatment_id=%s ORDER BY id", (treatment_id,))
    s["sales_n"] = count("sales", w.bid)
    s["profit_lines"] = q("SELECT SUM(quantity*unit_cost) AS cogs, SUM(line_total) AS rev FROM sale_items WHERE business_id=%s", (w.bid,))
    return s


def test10_original_sale_and_treatment_preserved():
    w = World()
    s = w.sale(20, paid="4000")
    t = w.treatment(service_charge="1500", dispense=(2, 3), patient="Ada Obi")   # 1500 + 5*1000 = 6500
    record_treatment_payment(t, w.bid, w.uid, w.uid, "500", "Cash", None)
    before = _state(w, s, t)

    assert wo(w, s, "16000")[0]                                   # write off ALL of the sale's debt
    assert wo(w, t, "6000", src=SOURCE_TREATMENT)[0]              # and ALL of the treatment's
    assert rec(w, s, "1000")[0] and rec(w, t, "250", src=SOURCE_TREATMENT)[0]

    assert _state(w, s, t) == before                              # byte-for-byte unchanged
    assert snap(w, t, SOURCE_TREATMENT)["collectible"] == D("0")
    bill = get_treatment_billing(t, w.bid, w.uid)
    assert bill["total_bill"] == D("6500") and bill["amount_paid"] == D("500")
    assert bill["written_off"] == D("6000") and bill["outstanding"] == D("0")
    assert bill["payment_status"] == "written_off"
    assert [p["amount"] for p in get_sale_payments(s, w.bid, w.uid)] == [D("4000")]
    assert [p["amount"] for p in get_treatment_payments(t, w.bid, w.uid)] == [D("500")]


# ── Unified debt: both sources, no row multiplication ───────────────────────

def test_unified_debt_with_many_dispensing_rows_not_inflated():
    w = World()
    s = w.sale(10)                                                # 10,000 stock debt
    t = w.treatment(service_charge="0", dispense=(1, 1, 1, 1, 1), patient="Ada Obi")   # 5,000, 5 dispensing rows
    c = [c for c in get_customers_with_balance(w.bid, w.uid) if c["id"] == w.cid][0]
    assert c["stock_sale_outstanding"] == D("10000") and c["treatment_outstanding"] == D("5000")
    assert wo(w, t, "2000", src=SOURCE_TREATMENT)[0]              # one write-off vs 5 dispensing rows
    assert wo(w, s, "4000")[0]
    c = [c for c in get_customers_with_balance(w.bid, w.uid) if c["id"] == w.cid][0]
    assert c["treatment_outstanding"] == D("3000")                # NOT 5000 - 5*2000
    assert c["stock_sale_outstanding"] == D("6000")
    assert c["total_outstanding"] == D("9000")
    assert get_credit_summary(w.bid, w.uid)["total_outstanding"] == D("9000")
    assert get_customer_treatments(w.cid, w.bid, w.uid)[0]["outstanding"] == D("3000")
    # more medicine dispensed after a write-off creates NEW collectible debt
    from treatments import get_treatment_items, record_dispensing
    item = get_treatment_items(t, w.bid, w.uid)[0]
    assert record_dispensing(item["id"], w.bid, w.uid, w.uid, 1, None)[0]
    assert snap(w, t, SOURCE_TREATMENT)["collectible"] == D("4000")


def test_ordinary_treatment_payment_respects_write_off():
    w = World()
    t = w.treatment(service_charge="1000", dispense=(4,))         # 5,000
    wo(w, t, "3000", src=SOURCE_TREATMENT)
    ok, msg = record_treatment_payment(t, w.bid, w.uid, w.uid, "2000.01", "Cash", None)
    assert not ok and "outstanding" in msg.lower()
    ok, msg = record_treatment_payment(t, w.bid, w.uid, w.uid, "2000", "Cash", None)
    assert ok, msg
    ok, msg = record_treatment_payment(t, w.bid, w.uid, w.uid, "1", "Cash", None)
    assert not ok and "written off" in msg.lower()
    assert snap(w, t, SOURCE_TREATMENT)["unrecovered"] == D("3000")


# ── Test 11: duplicates ─────────────────────────────────────────────────────

def test11_duplicate_submissions():
    w = World(); s = w.sale(20)
    k = key()
    first = wo(w, s, "5000", k=k)
    again = wo(w, s, "5000", k=k)
    assert first[0] and again[0] is None and "already recorded" in again[1]
    assert count("debt_write_offs", w.bid) == 1 and snap(w, s)["written_off"] == D("5000")
    rk = key()
    assert rec(w, s, "1000", k=rk)[0]
    r2 = rec(w, s, "1000", k=rk)
    assert r2[0] is None and "already recorded" in r2[1]
    assert count("debt_recoveries", w.bid) == 1
    # DB-level backstop: even bypassing the Python check the UNIQUE constraint holds
    import psycopg2
    with pytest.raises(psycopg2.errors.UniqueViolation):
        q("INSERT INTO debt_write_offs (business_id,customer_id,source_type,sale_id,amount,reason_category,idempotency_key) "
          "VALUES (%s,%s,'sale',%s,1,'x',%s)", (w.bid, w.cid, s, k))


def test_concurrent_write_offs_only_one_wins():
    w = World(); s = w.sale(10)                                   # 10,000
    results = []
    barrier = threading.Barrier(2)

    def go():
        barrier.wait()
        results.append(wo(w, s, "10000"))
    ts = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(bool(r[0]) for r in results) == [False, True]
    assert snap(w, s)["written_off"] == D("10000") and count("debt_write_offs", w.bid) == 1


def test_concurrent_payment_and_write_off_never_exceed_balance():
    w = World(); s = w.sale(10)
    results = {}
    barrier = threading.Barrier(2)

    def pay():
        barrier.wait(); results["pay"] = record_payment(s, w.bid, w.uid, w.uid, "10000", "Cash", None)

    def off():
        barrier.wait(); results["wo"] = wo(w, s, "10000")
    ts = [threading.Thread(target=pay), threading.Thread(target=off)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert [bool(results["pay"][0]), bool(results["wo"][0])].count(True) == 1
    assert snap(w, s)["collectible"] == D("0")


# ── Test 12: failure rolls everything back ──────────────────────────────────

@contextmanager
def _failing_get_db(real_get_db, fail_after_sql_prefix):
    with real_get_db() as (conn, cur):
        class Proxy:
            def __init__(self): self._last = ""
            def execute(self, sql, params=None):
                self._last = sql
                return cur.execute(sql, params)
            def fetchone(self):
                row = cur.fetchone()
                if self._last.lstrip().startswith(fail_after_sql_prefix):
                    raise RuntimeError("simulated database failure after INSERT")
                return row
            def fetchall(self): return cur.fetchall()
            def __getattr__(self, n): return getattr(cur, n)
        yield conn, Proxy()


def test12_failure_rolls_back_write_off_and_recovery(monkeypatch):
    w = World(); s = w.sale(10)
    real = baddebt.get_db
    monkeypatch.setattr(baddebt, "get_db", lambda: _failing_get_db(real, "INSERT INTO debt_write_offs"))
    wid, msg = wo(w, s, "4000")
    assert wid is None and "simulated" in msg
    monkeypatch.setattr(baddebt, "get_db", real)
    assert count("debt_write_offs", w.bid) == 0 and snap(w, s)["collectible"] == D("10000")

    assert wo(w, s, "4000")[0]
    monkeypatch.setattr(baddebt, "get_db", lambda: _failing_get_db(real, "INSERT INTO debt_recoveries"))
    rid, msg = rec(w, s, "1000")
    assert rid is None and "simulated" in msg
    monkeypatch.setattr(baddebt, "get_db", real)
    assert count("debt_recoveries", w.bid) == 0 and snap(w, s)["unrecovered"] == D("4000")


# ── Test 13: dated by the actual event day (Africa/Lagos) ───────────────────

def test13_events_dated_by_event_not_original_sale():
    w = World(); s = w.sale(10)
    q("UPDATE sales SET created_at = NOW() - interval '40 days' WHERE id=%s", (s,))
    wid, _ = wo(w, s, "6000"); rid, _ = rec(w, s, "1000")
    today_lagos = one("SELECT (NOW() AT TIME ZONE 'Africa/Lagos')::date AS d")["d"]
    sale_day = today_lagos - timedelta(days=40)
    assert [e["id"] for e in get_write_off_events(w.bid, w.uid, today_lagos, today_lagos)] == [wid]
    assert get_write_off_events(w.bid, w.uid, sale_day, sale_day) == []
    assert [e["id"] for e in get_recovery_events(w.bid, w.uid, today_lagos, today_lagos)] == [rid]
    assert get_recovery_events(w.bid, w.uid, sale_day, sale_day) == []

    # Lagos is UTC+1: 23:30 UTC on 10 Mar is 00:30 on 11 Mar in Lagos.
    q("UPDATE debt_write_offs SET created_at = '2026-03-10 23:30:00+00' WHERE id=%s", (wid,))
    d10, d11 = date(2026, 3, 10), date(2026, 3, 11)
    assert get_write_off_events(w.bid, w.uid, d10, d10) == []
    assert [e["id"] for e in get_write_off_events(w.bid, w.uid, d11, d11)] == [wid]
    # amount "paid before write-off" counts only payments made before the write-off moment
    ev = get_write_off_events(w.bid, w.uid)[0]
    assert ev["paid_before_write_off"] == D("0") and ev["original_total"] == D("10000")


def test_paid_before_write_off_and_type_filter():
    w = World(); s = w.sale(10, paid="3000")
    t = w.treatment(service_charge="2000", patient="Ada Obi")
    wo(w, s, "7000"); wo(w, t, "2000", src=SOURCE_TREATMENT)
    ev = {e["source_type"]: e for e in get_write_off_events(w.bid, w.uid)}
    assert ev["sale"]["paid_before_write_off"] == D("3000")
    assert len(get_write_off_events(w.bid, w.uid, source_type=SOURCE_TREATMENT)) == 1
    assert len(get_collectible_debts(w.bid, w.uid)) == 0


# ── Reversal (audit-friendly correction) ────────────────────────────────────

def test_reversal_is_auditable_and_guarded():
    w = World(); s = w.sale(10)
    wid, _ = wo(w, s, "10000")
    assert reverse_write_off(wid, w.bid, w.uid, w.uid, "")[0] is None           # reason required
    ok, msg = reverse_write_off(wid, w.bid, w.uid, w.uid, "Entered on wrong customer")
    assert ok, msg
    sn = snap(w, s)
    assert sn["written_off"] == D("0") and sn["collectible"] == D("10000")
    assert count("debt_write_offs", w.bid) == 1                                  # row kept forever
    assert get_write_off_events(w.bid, w.uid)[0]["status"] == "Reversed"
    assert reverse_write_off(wid, w.bid, w.uid, w.uid, "again")[0] is None       # only once
    assert get_bad_debt_summary(w.bid, w.uid)["reversed_total"] == D("10000")
    # can write off again afterwards; cannot reverse once money was recovered against it
    wid2, _ = wo(w, s, "10000")
    rec(w, s, "100")
    ok, msg = reverse_write_off(wid2, w.bid, w.uid, w.uid, "oops")
    assert not ok and "recovered" in msg
    snap_h, events = get_transaction_history(SOURCE_SALE, s, w.bid, w.uid)
    kinds = [e["kind"] for e in events]
    assert kinds.count("Write-off") == 2 and kinds.count("Write-off reversed") == 1 and kinds.count("Recovery") == 1


def test_write_off_rows_cannot_be_nonsense():
    w = World(); s = w.sale(1)
    import psycopg2
    with pytest.raises(psycopg2.errors.CheckViolation):
        q("INSERT INTO debt_write_offs (business_id,customer_id,source_type,sale_id,amount,reason_category,idempotency_key) "
          "VALUES (%s,%s,'sale',%s,0,'x',%s)", (w.bid, w.cid, s, key()))
    with pytest.raises(psycopg2.errors.CheckViolation):
        q("INSERT INTO debt_write_offs (business_id,customer_id,source_type,amount,reason_category,idempotency_key) "
          "VALUES (%s,%s,'sale',5,'x',%s)", (w.bid, w.cid, key()))


# ── Test 14: regression on existing behaviour ───────────────────────────────

def test14_existing_flows_unchanged_when_no_write_offs():
    w = World()
    s = w.sale(10, paid="2500")
    assert one("SELECT payment_status FROM sales WHERE id=%s", (s,))["payment_status"] == "partial"
    ok, msg = record_payment(s, w.bid, w.uid, w.uid, "7500", "POS", "x")
    assert ok, msg
    assert one("SELECT payment_status, amount_paid FROM sales WHERE id=%s", (s,)) == \
        {"payment_status": "paid", "amount_paid": D("10000.00")}
    ok, msg = record_payment(s, w.bid, w.uid, w.uid, "1", "Cash", None)
    assert not ok and "fully paid" in msg.lower()
    t = w.treatment(service_charge="500", dispense=(2,))
    bill = get_treatment_billing(t, w.bid, w.uid)
    assert bill["total_bill"] == D("2500") and bill["outstanding"] == D("2500") and bill["payment_status"] == "unpaid"
    assert bill["written_off"] == D("0")
    assert record_treatment_payment(t, w.bid, w.uid, w.uid, "2500", "Cash", None)[0]
    assert get_treatment_billing(t, w.bid, w.uid)["payment_status"] == "paid"
    c = [c for c in get_customers_with_balance(w.bid, w.uid) if c["id"] == w.cid][0]
    assert c["total_outstanding"] == D("0")
    assert one("SELECT current_stock FROM products WHERE id=%s", (w.pid,))["current_stock"] == D("88.000")
    from inventory import adjust_stock
    ok, msg = adjust_stock(w.pid, w.bid, w.uid, w.uid, "add", 10, "New delivery / Purchase", 700)
    assert ok, msg
    s2 = get_bad_debt_summary(w.bid, w.uid)
    assert s2["total_written_off"] == D("0") and s2["total_recovered"] == D("0")
