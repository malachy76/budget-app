# Phase 5A-5 cash-basis report tests — real code, real PostgreSQL.
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

import daily_report
from daily_report import get_cash_basis_report, allocate_treatment_payments, business_today, ReportError
from baddebt import write_off_debt, reverse_write_off, record_recovery, SOURCE_SALE, SOURCE_TREATMENT
from customers import record_payment, get_credit_summary
from treatments import (record_treatment_payment, get_treatment_items, record_dispensing)
from helpers import World, q, one, key, make_user

REASON = "Customer is unable to repay"
UTC = timezone.utc


def W(**kw):
    kw.setdefault("price", "1000"); kw.setdefault("cost", "600"); kw.setdefault("stock", "5000")
    return World(**kw)


def rep(w, d1=None, d2=None):
    d1 = d1 or business_today(); d2 = d2 or d1
    return get_cash_basis_report(w.bid, w.uid, d1, d2)


# ── time-travel helpers: move records to a chosen business day ──────────────
def ts(day, hour=12):                       # naive UTC (older tables)
    return datetime(2026, 3, day, hour, 0, 0)


def tsz(day, hour=12):                      # aware UTC (5A-4 tables)
    return datetime(2026, 3, day, hour, 0, 0, tzinfo=UTC)


def D3(day):
    return date(2026, 3, day)


def back_sale(sid, day, hour=12):
    q("UPDATE sales SET created_at=%s WHERE id=%s", (ts(day, hour), sid))
    q("UPDATE payments SET created_at=%s WHERE sale_id=%s AND note='Initial payment at sale'", (ts(day, hour), sid))


def back_last(table, col, bid, when, extra=""):
    q(f"UPDATE {table} SET {col}=%s WHERE id=(SELECT MAX(id) FROM {table} WHERE business_id=%s {extra})", (when, bid))


def pay_sale(w, sid, amount, day, hour=12, method="Cash"):
    ok, m = record_payment(sid, w.bid, w.uid, w.uid, amount, method, None); assert ok, m
    back_last("payments", "created_at", w.bid, ts(day, hour))


def new_treatment(w, service, day, hour=9):
    tid = w.treatment(service_charge=service)
    q("UPDATE treatments SET created_at=%s WHERE id=%s", (ts(day, hour), tid))
    return tid


def dispense(w, tid, qty, day, hour=10):
    item = get_treatment_items(tid, w.bid, w.uid)[0]
    ok, m = record_dispensing(item["id"], w.bid, w.uid, w.uid, qty, None); assert ok, m
    back_last("treatment_dispensing", "dispensed_at", w.bid, ts(day, hour))


def pay_treatment(w, tid, amount, day, hour=12, method="Cash"):
    ok, m = record_treatment_payment(tid, w.bid, w.uid, w.uid, amount, method, None); assert ok, m
    back_last("treatment_payments", "created_at", w.bid, ts(day, hour))


# ── spec scenario 1 & 2: ₦100,000 sale, ₦65,000 paid, ₦35,000 later ─────────
def test_100k_sale_65k_paid_only_65k_is_realised():
    w = W(); s = w.sale(100, paid="65000")
    r = rep(w)
    assert r["sales_activity"] == D("100000") and r["sales_count"] == 1
    assert r["realised_stock_revenue"] == D("65000")
    assert r["realised_operating_revenue"] == D("65000")
    assert r["money_collected_total"] == D("65000")
    assert r["closing_debt"] == D("35000")
    assert r["cogs_on_collected"] == D("39000")            # 65% of 60,000
    assert r["realised_gross_profit"] == D("26000")
    assert r["collections"]["stock_initial"]["amount"] == D("65000")
    assert r["collections"]["stock_repayment"]["amount"] == D("0")


def test_later_35k_collection_adds_35k_not_100k():
    w = W(); s = w.sale(100, paid="65000")
    back_sale(s, 1)
    pay_sale(w, s, "35000", 4)
    day4 = rep(w, D3(4))
    assert day4["sales_activity"] == D("0") and day4["sales_count"] == 0     # no new sale
    assert day4["realised_stock_revenue"] == D("35000")                      # not 100,000
    assert day4["collections"]["stock_repayment"]["amount"] == D("35000")
    assert day4["collections"]["stock_initial"]["amount"] == D("0")
    assert day4["cogs_on_collected"] == D("21000") and day4["realised_gross_profit"] == D("14000")
    assert day4["opening_debt"] == D("35000") and day4["closing_debt"] == D("0")
    whole = rep(w, D3(1), D3(4))
    assert whole["sales_activity"] == D("100000")                            # invoice counted once
    assert whole["realised_stock_revenue"] == D("100000")                    # = cash received
    assert whole["realised_gross_profit"] == D("40000")                      # 100,000 - 60,000 COGS
    assert whole["reconciles"]


# ── spec scenario 3 & 4: ₦20,000 treatment, ₦8,000 paid ─────────────────────
def test_20k_treatment_8k_paid_only_8k_realised_then_balance():
    w = W()
    t = new_treatment(w, "2000", 1)
    dispense(w, t, 18, 1)                                   # 18 x 1,000 = 18,000 (cost 10,800)
    pay_treatment(w, t, "8000", 1)
    d1 = rep(w, D3(1))
    assert d1["treatment_activity"] == D("20000")
    assert d1["realised_treatment_revenue"] == D("8000")
    assert d1["realised_stock_revenue"] == D("0")
    assert d1["closing_debt"] == D("12000") and d1["closing_treatment_debt"] == D("12000")
    assert d1["cogs_on_collected"] == D("4320") and d1["realised_gross_profit"] == D("3680")
    assert d1["collections"]["treatment_initial"]["amount"] == D("8000")
    pay_treatment(w, t, "12000", 3)
    d3 = rep(w, D3(3))
    assert d3["treatment_activity"] == D("0")                                # bill not counted twice
    assert d3["realised_treatment_revenue"] == D("12000")                    # only the extra
    assert d3["collections"]["treatment_repayment"]["amount"] == D("12000")
    assert d3["collections"]["treatment_initial"]["amount"] == D("0")
    assert d3["closing_debt"] == D("0")
    whole = rep(w, D3(1), D3(3))
    assert whole["cogs_on_collected"] == D("10800")                          # whole cost recognised exactly once
    assert whole["realised_gross_profit"] == D("9200") and whole["reconciles"]


def test_fully_unpaid_stock_and_treatment_have_no_revenue_or_profit():
    w = W(); s = w.sale(10)
    t = new_treatment(w, "1500", 1); dispense(w, t, 4, 1)
    # leave the sale where it was created today and the treatment on day 1
    today = rep(w)
    assert today["sales_activity"] == D("10000")
    assert today["realised_stock_revenue"] == D("0") and today["realised_gross_profit"] == D("0")
    assert today["money_collected_total"] == D("0") and today["cogs_on_collected"] == D("0")
    d1 = rep(w, D3(1))
    assert d1["treatment_activity"] == D("5500")
    assert d1["realised_treatment_revenue"] == D("0") and d1["realised_gross_profit"] == D("0")
    assert d1["closing_treatment_debt"] == D("5500")


def test_partial_payment_profit_uses_proportional_cost():
    w = W(); s = w.sale(10, paid="2500")                       # 25% paid
    r = rep(w)
    assert r["realised_operating_revenue"] == D("2500")
    assert r["cogs_on_collected"] == D("1500")                 # 25% of 6,000
    assert r["realised_gross_profit"] == D("1000")
    assert r["gross_margin_pct"] == D("40")


def test_historic_cost_not_current_price():
    w = W(); s = w.sale(10, paid="10000")                      # cost snapshot 600
    q("UPDATE products SET purchase_price=900 WHERE id=%s", (w.pid,))
    assert rep(w)["realised_gross_profit"] == D("4000")


# ── bad debt kept out of operating figures ──────────────────────────────────
def test_recovery_excluded_from_operating_revenue_and_profit():
    w = W(); s = w.sale(20)                                    # 20,000 unpaid
    back_sale(s, 1)
    wid, _ = write_off_debt(SOURCE_SALE, s, w.bid, w.uid, w.uid, "20000", REASON, "", key())
    back_last("debt_write_offs", "created_at", w.bid, tsz(2))
    rid, msg = record_recovery(SOURCE_SALE, s, w.bid, w.uid, w.uid, "5000", "Bank Transfer", "", key())
    assert rid, msg
    back_last("debt_recoveries", "created_at", w.bid, tsz(3))
    r = rep(w, D3(3))
    assert r["recoveries"] == D("5000") and r["money_collected_total"] == D("5000")
    assert r["operating_collected"] == D("0")
    assert r["realised_operating_revenue"] == D("0") and r["realised_gross_profit"] == D("0")
    assert r["collections"]["recovery"]["amount"] == D("5000")
    assert r["by_method"]["Bank Transfer"] == {"operating": D("0"), "recovery": D("5000"), "total": D("5000")}
    assert r["sales_activity"] == D("0")                       # recovery is not a sale
    r2 = rep(w, D3(2))
    assert r2["written_off"] == D("20000") and r2["realised_operating_revenue"] == D("0")
    assert r2["closing_debt"] == D("0")
    assert rep(w, D3(1), D3(3))["reconciles"]


def test_write_off_and_reversal_create_no_revenue():
    w = W(); s = w.sale(10); back_sale(s, 1)
    wid, _ = write_off_debt(SOURCE_SALE, s, w.bid, w.uid, w.uid, "10000", REASON, "", key())
    back_last("debt_write_offs", "created_at", w.bid, tsz(2))
    ok, msg = reverse_write_off(wid, w.bid, w.uid, w.uid, "entered by mistake"); assert ok, msg
    back_last("debt_write_off_reversals", "created_at", w.bid, tsz(3))
    for day in (2, 3):
        r = rep(w, D3(day))
        assert r["money_collected_total"] == D("0")
        assert r["realised_operating_revenue"] == D("0") and r["realised_gross_profit"] == D("0")
    assert rep(w, D3(2))["written_off"] == D("10000") and rep(w, D3(2))["closing_debt"] == D("0")
    r3 = rep(w, D3(3))
    assert r3["write_offs_reversed"] == D("10000") and r3["closing_debt"] == D("10000")
    assert r3["reconciles"] and rep(w, D3(1), D3(3))["reconciles"]


def test_no_double_counting_between_initial_and_later_payments():
    w = W(); s = w.sale(10, paid="4000")                       # real create_sale: untouched timestamps
    ok, m = record_payment(s, w.bid, w.uid, w.uid, "6000", "Cash", None); assert ok, m
    r = rep(w)
    assert r["sales_activity"] == D("10000") and r["sales_count"] == 1
    assert r["collections"]["stock_initial"]["amount"] == D("4000")      # real timestamps => classified initial
    assert r["collections"]["stock_repayment"]["amount"] == D("6000")
    assert r["realised_stock_revenue"] == D("10000") == one("SELECT amount_paid FROM sales WHERE id=%s", (s,))["amount_paid"]
    assert r["realised_gross_profit"] == D("4000") and r["cogs_on_collected"] == D("6000")
    assert r["closing_debt"] == D("0")


# ── treatment timing rules ──────────────────────────────────────────────────
def test_medicine_not_recognised_before_dispensing():
    w = W()
    t = new_treatment(w, "1000", 1)
    pay_treatment(w, t, "1000", 1)                             # only the service fee exists yet
    dispense(w, t, 5, 2)                                       # 5,000 of medicine dispensed LATER
    d1, d2 = rep(w, D3(1)), rep(w, D3(2))
    assert d1["treatment_activity"] == D("1000") and d1["realised_treatment_revenue"] == D("1000")
    assert d1["cogs_on_collected"] == D("0")                   # service charge has no medicine cost
    assert d2["treatment_activity"] == D("5000") and d2["medicine_billed"] == D("5000")
    assert d2["realised_treatment_revenue"] == D("0")          # nothing new collected for it
    assert d2["closing_debt"] == D("5000")


def test_treatment_cumulative_cost_converges_to_true_cost():
    # pure function: ratio changes between payments, total must still equal true cost
    pays = [{"id": 1, "amount": D("1000"), "created_at": ts(1, 12)},
            {"id": 2, "amount": D("2000"), "created_at": ts(3, 12)}]
    disp = [{"at": ts(1, 10), "qty": D("1"), "price": D("1000"), "cost": D("600")},
            {"at": ts(3, 10), "qty": D("1"), "price": D("1000"), "cost": D("600")}]
    out = allocate_treatment_payments(D("1000"), pays, disp)
    assert out[0]["initial"] and not out[1]["initial"]
    assert out[0]["cogs"] == D("300")                          # 1000 paid x 600/2000
    assert out[1]["cogs"] == D("900")                          # 3000 x 1200/3000 - 300
    assert sum(o["cogs"] for o in out) == D("1200")            # = true total cost
    # a dispensing AFTER a payment never changes that payment's cost
    assert allocate_treatment_payments(D("1000"), pays[:1], disp)[0]["cogs"] == D("300")


def test_unknown_cost_is_not_treated_as_zero():
    w = W(); s = w.sale(10, paid="10000")
    q("UPDATE sale_items SET unit_cost=NULL WHERE sale_id=%s", (s,))      # legacy line without cost
    r = rep(w)
    assert r["realised_operating_revenue"] == D("10000")       # still real money
    assert r["realised_gross_profit"] == D("0") and r["cogs_on_collected"] == D("0")
    assert r["revenue_with_unknown_cost"] == D("10000") and r["profit_incomplete"]
    s2 = w.sale(4, paid="4000")                                # a known-cost sale alongside
    r = rep(w)
    assert r["realised_gross_profit"] == D("1600") and r["revenue_with_unknown_cost"] == D("10000")


# ── dates, history, ownership ───────────────────────────────────────────────
def test_lagos_business_day_boundaries():
    w = W(); s = w.sale(10, paid="10000")
    back_sale(s, 10)
    q("UPDATE payments SET created_at=%s WHERE sale_id=%s", (datetime(2026, 3, 10, 22, 59), s))   # 23:59 Lagos
    assert rep(w, D3(10))["realised_stock_revenue"] == D("10000") and rep(w, D3(11))["realised_stock_revenue"] == D("0")
    q("UPDATE payments SET created_at=%s WHERE sale_id=%s", (datetime(2026, 3, 10, 23, 0), s))    # 00:00 Lagos next day
    assert rep(w, D3(10))["realised_stock_revenue"] == D("0") and rep(w, D3(11))["realised_stock_revenue"] == D("10000")


def test_past_reports_never_change_after_later_activity():
    w = W(); s = w.sale(10, paid="3000"); back_sale(s, 1)
    before = {d: rep(w, D3(d)) for d in (1, 2, 3)}
    pay_sale(w, s, "7000", 5)
    write_off_debt(SOURCE_SALE, w.sale(2), w.bid, w.uid, w.uid, "100", REASON, "", key())   # a write-off "today"
    for d in (1, 2, 3):
        assert rep(w, D3(d)) == before[d]
    assert before[2]["closing_debt"] == D("7000") and before[1]["opening_debt"] == D("0")


def test_report_is_business_scoped_and_owner_checked():
    a, b = W(), W()
    a.sale(10, paid="1000")
    assert rep(b)["realised_operating_revenue"] == D("0") and rep(b)["sales_activity"] == D("0")
    with pytest.raises(ReportError):
        get_cash_basis_report(a.bid, b.uid, business_today(), business_today())
    with pytest.raises(ReportError):
        get_cash_basis_report(a.bid, a.uid, date(2026, 3, 5), date(2026, 3, 4))


# ── reconciliation over a realistic multi-day story ─────────────────────────
def test_reconciliation_every_window_and_matches_live_balances():
    w = W()
    s = w.sale(10, paid="3000"); back_sale(s, 1)                         # day1: sale 10,000, paid 3,000
    t = new_treatment(w, "2000", 1); dispense(w, t, 5, 2)                # day1 service, day2 5,000 medicine
    pay_sale(w, s, "2000", 2); pay_treatment(w, t, "1500", 2)
    wid, m = write_off_debt(SOURCE_SALE, s, w.bid, w.uid, w.uid, "3000", REASON, "", key()); assert wid, m
    back_last("debt_write_offs", "created_at", w.bid, tsz(3))
    dispense(w, t, 3, 3, hour=11); pay_treatment(w, t, "2000", 3)        # +3,000 medicine, pay 2,000
    ok, m = reverse_write_off(wid, w.bid, w.uid, w.uid, "wrong customer"); assert ok, m
    back_last("debt_write_off_reversals", "created_at", w.bid, tsz(4))
    wid2, m = write_off_debt(SOURCE_TREATMENT, t, w.bid, w.uid, w.uid, "1000", REASON, "", key()); assert wid2, m
    back_last("debt_write_offs", "created_at", w.bid, tsz(5))
    rid, m = record_recovery(SOURCE_TREATMENT, t, w.bid, w.uid, w.uid, "400", "Cash", "", key()); assert rid, m
    back_last("debt_recoveries", "created_at", w.bid, tsz(6))
    pay_sale(w, s, "1500", 6)

    days = range(1, 8)
    for i in days:
        for j in range(i, 8):
            r = rep(w, D3(i), D3(j))
            assert r["reconciles"], (i, j, r["opening_debt"], r["new_charges"], r["payments_received"],
                                     r["written_off"], r["write_offs_reversed"], r["expected_closing_debt"], r["closing_debt"])
    # windows chain: closing of day d == opening of day d+1
    for d in range(1, 7):
        assert rep(w, D3(d))["closing_debt"] == rep(w, D3(d + 1))["opening_debt"]
    # whole-history totals agree with the ledger
    whole = rep(w, D3(1), D3(7))
    paid_sales = one("SELECT SUM(amount) a FROM payments WHERE business_id=%s", (w.bid,))["a"]
    paid_tx = one("SELECT SUM(amount) a FROM treatment_payments WHERE business_id=%s", (w.bid,))["a"]
    assert whole["realised_stock_revenue"] == paid_sales and whole["realised_treatment_revenue"] == paid_tx
    assert whole["realised_operating_revenue"] == paid_sales + paid_tx
    assert whole["recoveries"] == D("400") and whole["written_off"] == D("4000") and whole["write_offs_reversed"] == D("3000")
    assert whole["sales_activity"] == D("10000") and whole["treatment_activity"] == D("10000")
    # the report's closing debt equals what the live Customers/Credit screens show
    live = get_credit_summary(w.bid, w.uid)
    assert whole["closing_debt"] == live["total_outstanding"]
    assert whole["closing_stock_debt"] == live["stock_sale_outstanding"]
    assert whole["closing_treatment_debt"] == live["treatment_outstanding"]
    assert whole["payment_history_mismatches"] == 0
    # debtor list adds up
    assert sum(d["total"] for d in whole["debtors"]) == whole["closing_debt"]
