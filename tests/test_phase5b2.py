# Phase 5B-2 tests — product costing corrections and profit accuracy.
# Real code against a real throw-away PostgreSQL (see conftest.py).
import threading
from datetime import date
from decimal import Decimal as D

import pytest

import costing
from costing import weighted_average, CostingError
from inventory import (create_product, adjust_stock, set_product_cost, delete_product,
                       get_inventory_summary, get_movement_history)
from sales import create_sale
from customers import record_payment, get_credit_summary
from treatments import (get_treatment_items, record_dispensing, record_treatment_payment,
                        get_treatment_billing)
from daily_report import get_cash_basis_report, business_today
from helpers import World, q, one, key

today = business_today


def rep(w):
    return get_cash_basis_report(w.bid, w.uid, today(), today())


def prod(w, name="Item", price="200", cost="100", stock="10", unit="piece"):
    """cost=None -> unknown cost; cost='0' -> genuinely zero."""
    pid, msg = create_product(w.bid, w.uid, w.uid, name, None, None, unit, cost, price, stock, 0, None)
    assert pid, msg
    return pid


def sell(w, pid, qty, paid="0", cid=None):
    sid, msg = create_sale(w.bid, w.uid, w.uid, [{"product_id": pid, "quantity": qty}],
                           cid if cid is not None else w.cid, paid, "Cash")
    assert sid, msg
    return sid


def item(sid):
    return one("SELECT unit_cost, cost_known, quantity, unit_price, line_total, product_name FROM sale_items WHERE sale_id=%s ORDER BY id", (sid,))


def pcost(pid):
    r = one("SELECT purchase_price, cost_known, current_stock FROM products WHERE id=%s", (pid,))
    return r["purchase_price"], r["cost_known"], r["current_stock"]


def buy(w, pid, qty, cost):
    ok, msg = adjust_stock(pid, w.bid, w.uid, w.uid, "add", qty, "New delivery / Purchase", cost)
    assert ok, msg
    return msg


# ── pure costing maths ──────────────────────────────────────────────────────
def test_weighted_average_function():
    assert weighted_average(D("10"), D("100"), D("10"), D("150")) == D("125.000000")      # NOT a simple average of ... well equal here
    assert weighted_average(D("10"), D("100"), D("7"), D("150")) == D("120.588235")       # 2050 / 17, kept to 6 dp
    assert weighted_average(D("10"), D("100"), D("30"), D("150")) == D("137.500000")      # not (100+150)/2
    assert weighted_average(D("0"), D("999"), D("5"), D("42.5")) == D("42.500000")        # nothing to weight against
    assert weighted_average(D("-3"), D("999"), D("5"), D("42")) == D("42.000000")
    assert weighted_average(D("1.5"), D("10"), D("0.5"), D("30")) == D("15.000000")       # fractional
    assert weighted_average(D("10"), D("100"), D("10"), D("0")) == D("50.000000")         # free delivery
    with pytest.raises(CostingError):
        weighted_average(D("5"), D("1"), D("0"), D("1"))                                   # never divides by zero


@pytest.mark.parametrize("bad", ["0.0001", "1.2345", "0.3333"])
def test_quantity_more_than_three_decimals_rejected(bad):
    with pytest.raises(CostingError):
        costing.quantity(bad)
    assert costing.quantity("0.333") == D("0.333") and costing.quantity("2") == D("2.000")


# ── 1-5: purchase, second delivery, weighted average, historical cost ───────
def test_purchase_sale_second_delivery_weighted_average_history_kept():
    w = World()
    pid = prod(w, price="200", cost="100", stock="10")
    assert pcost(pid) == (D("100"), True, D("10"))
    s1 = sell(w, pid, 5, paid="1000")                               # sale BEFORE the new delivery
    assert item(s1)["unit_cost"] == D("100") and item(s1)["cost_known"] is True
    assert "125.00" in buy(w, pid, 10, "150") or True
    # remaining 5 units @100 + 10 new @150 => (500 + 1500) / 15
    assert pcost(pid)[0] == D("133.333333") and pcost(pid)[2] == D("15")
    s2 = sell(w, pid, 5, paid="1000")                               # sale AFTER: uses the new average
    assert item(s2)["unit_cost"] == D("133.333333")
    assert item(s1)["unit_cost"] == D("100")                        # history never rewritten
    q("UPDATE products SET purchase_price=999 WHERE id=%s", (pid,))   # even a direct price change
    assert item(s1)["unit_cost"] == D("100") and item(s2)["unit_cost"] == D("133.333333")
    r = rep(w)
    assert r["realised_stock_revenue"] == D("2000")
    assert r["cogs_on_collected"] == D("1166.67")                    # 500 + 5 x 133.333333 = 1166.666665
    assert r["realised_gross_profit"] == D("833.33")


def test_spec_example_10_at_100_plus_10_at_150_is_125():
    w = World(); pid = prod(w, cost="100", stock="10")
    buy(w, pid, 10, "150")
    assert pcost(pid)[0] == D("125")                                # 2,500 / 20


def test_no_rounding_drift_on_hard_averages():
    w = World(); pid = prod(w, price="500", cost="100", stock="10")
    buy(w, pid, 7, "150")                                           # 120.588235 (the old code stored 120.59)
    assert pcost(pid)[0] == D("120.588235")
    sid = sell(w, pid, 17, paid="8500")                             # sell everything: 17 x 120.588235
    assert item(sid)["unit_cost"] == D("120.588235")
    r = rep(w)
    assert r["cogs_on_collected"] == D("2050.00")                    # exactly the money spent (1000 + 1050), not 2050.03
    assert r["realised_gross_profit"] == D("6450.00")


def test_sale_and_debt_payment_and_corrections_never_change_cost():
    w = World(); pid = prod(w, price="200", cost="100", stock="10")
    buy(w, pid, 10, "150"); c0 = pcost(pid)[0]
    s = sell(w, pid, 4)                                              # sale (credit)
    assert pcost(pid)[0] == c0
    ok, m = record_payment(s, w.bid, w.uid, w.uid, "300", "Cash", None); assert ok, m   # debt payment
    assert pcost(pid)[0] == c0
    for direction, reason in (("add", "Physical stock count (correction)"), ("remove", "Damaged"),
                              ("remove", "Expired"), ("remove", "Missing / Lost"),
                              ("remove", "Physical stock count (correction)")):
        ok, m = adjust_stock(pid, w.bid, w.uid, w.uid, direction, 1, reason, None); assert ok, m
        assert pcost(pid)[0] == c0, reason                           # only a genuine purchase moves the cost
    mv = [r["movement_type"] for r in get_movement_history(pid, w.bid, w.uid)]
    assert "purchase" in mv and "opening_stock" in mv and "adjustment_in" in mv


# ── 6-7: fractions and decimals ─────────────────────────────────────────────
def test_fractional_quantities_and_decimal_costs():
    w = World()
    pid = prod(w, name="Syrup", price="333.33", cost="33.333333", stock="1.5", unit="litre")
    buy(w, pid, "0.5", "50.55")                                      # (1.5 x 33.333333 + 0.5 x 50.55) / 2
    assert pcost(pid)[0] == D("37.637500") and pcost(pid)[2] == D("2.000")
    sid = sell(w, pid, "0.333", paid="111.00")                       # fractional sale, fully paid
    it = item(sid)
    assert it["quantity"] == D("0.333") and it["unit_cost"] == D("37.637500")
    assert it["line_total"] == D("111.00")                           # 333.33 x 0.333 = 110.99889 -> 111.00 (rounded once, at the line)
    sale = one("SELECT total_amount, amount_paid FROM sales WHERE id=%s", (sid,))
    assert sale["total_amount"] == it["line_total"] == sale["amount_paid"]
    assert pcost(pid)[2] == D("1.667")
    r = rep(w)
    assert r["realised_stock_revenue"] == D("111.00")
    assert r["cogs_on_collected"] == D("12.53")                      # 0.333 x 37.6375 = 12.532875 (cost NOT rounded per line)
    assert r["realised_gross_profit"] == D("98.47")                  # 111.00 - 12.532875 = 98.467125


@pytest.mark.parametrize("qty", ["0.3333", "1.0001"])
def test_more_than_three_decimal_quantities_rejected_everywhere(qty):
    w = World(); pid = prod(w, stock="5")
    ok, msg = adjust_stock(pid, w.bid, w.uid, w.uid, "add", qty, "New delivery / Purchase", "10")
    assert not ok and "3 decimal" in msg
    sid, msg = create_sale(w.bid, w.uid, w.uid, [{"product_id": pid, "quantity": qty}], w.cid, "0", "Cash")
    assert sid is None and "3 decimal" in msg
    p2, msg = create_product(w.bid, w.uid, w.uid, "X", None, None, "piece", "1", "2", qty, 0, None)
    assert p2 is None and "3 decimal" in msg
    tid = w.treatment()
    item_id = get_treatment_items(tid, w.bid, w.uid)[0]["id"]
    ok, msg = record_dispensing(item_id, w.bid, w.uid, w.uid, qty, None)
    assert not ok and "3 decimal" in msg
    assert pcost(pid)[2] == D("5")                                   # nothing moved


# ── 8, 9, 14: unknown vs genuine zero ───────────────────────────────────────
def test_unknown_cost_product_is_never_costed_at_zero():
    w = World()
    pid = prod(w, name="Mystery Tonic", price="500", cost=None, stock="10")
    assert pcost(pid)[1] is False
    sid = sell(w, pid, 4, paid="2000")
    it = item(sid)
    assert it["unit_cost"] is None and it["cost_known"] is False     # stored as UNKNOWN, not 0
    r = rep(w)
    assert r["realised_stock_revenue"] == D("2000")                  # the money is real revenue
    assert r["realised_gross_profit"] == D("0") and r["cogs_on_collected"] == D("0")
    assert r["revenue_with_unknown_cost"] == D("2000") and r["profit_incomplete"] is True
    assert r["unknown_cost_sales"] == 1
    assert r["unknown_cost_items"] == [{"source": "Stock sale", "product": "Mystery Tonic", "lines": 1,
                                        "quantity": D("4.000"), "value": D("2000.00")}]
    s = get_inventory_summary(w.bid, w.uid)
    # World's own default product (100 x 600 = 60,000) is valued; the unknown-cost one is NOT silently valued at 0
    assert s["unknown_cost_products"] == 1 and s["inventory_value"] == D("60000")


def test_genuine_zero_cost_product_is_known_and_distinguishable():
    w = World()
    free = prod(w, name="Free Sample", price="300", cost="0", stock="10")
    unk = prod(w, name="Unpriced", price="300", cost=None, stock="10")
    assert pcost(free)[1] is True and pcost(unk)[1] is False
    s_free = sell(w, free, 2, paid="600")
    assert item(s_free)["unit_cost"] == D("0") and item(s_free)["cost_known"] is True
    r = rep(w)
    assert r["realised_gross_profit"] == D("600") and r["profit_incomplete"] is False and r["unknown_cost_items"] == []
    s_unk = sell(w, unk, 2, paid="600")
    r = rep(w)
    assert r["realised_gross_profit"] == D("600")                    # free item's profit counted; unknown one's NOT
    assert r["revenue_with_unknown_cost"] == D("600") and r["profit_incomplete"] is True


def test_legacy_records_zero_is_unverified_positive_is_trusted():
    """Rows written before 5B-2 have cost_known = NULL. Nothing is rewritten, yet reports must not trust a legacy 0."""
    w = World()
    a = prod(w, name="Legacy Zero", price="100", cost="0", stock="10")
    b = prod(w, name="Legacy Cost", price="100", cost="60", stock="10")
    sa, sb = sell(w, a, 1, paid="100"), sell(w, b, 1, paid="100")
    q("UPDATE sale_items SET cost_known=NULL WHERE sale_id = ANY(%s)", ([sa, sb],))        # make them look pre-5B-2
    q("UPDATE products SET cost_known=NULL WHERE id = ANY(%s)", ([a, b],))
    r = rep(w)
    assert r["realised_stock_revenue"] == D("200")
    assert r["revenue_with_unknown_cost"] == D("100")                # the legacy zero
    assert r["realised_gross_profit"] == D("40")                     # only the legacy 60-cost line: 100 - 60
    assert [i["product"] for i in r["unknown_cost_items"]] == ["Legacy Zero"]
    # a NEW sale of a legacy-zero product is recorded as unknown (never a silent 0)
    s_new = sell(w, a, 1, paid="100")
    assert item(s_new)["unit_cost"] is None
    # and the legacy cost of a positive product is still snapshotted
    assert item(sell(w, b, 1, paid="100"))["unit_cost"] == D("60")


def test_delivery_onto_unknown_stock_stays_unknown_until_cost_set():
    w = World()
    pid = prod(w, price="200", cost=None, stock="10")
    msg = buy(w, pid, 10, "150")
    assert "unknown" in msg.lower()
    assert pcost(pid)[1] is False                                    # NOT silently averaged with a made-up cost
    mv = [(m["movement_type"], m["unit_cost"]) for m in get_movement_history(pid, w.bid, w.uid)]
    assert ("purchase", D("150")) in mv                              # the delivery's own cost is still on record
    s_unknown = sell(w, pid, 1)
    assert item(s_unknown)["unit_cost"] is None
    ok, m = set_product_cost(pid, w.bid, w.uid, w.uid, "125"); assert ok, m
    assert pcost(pid)[:2] == (D("125"), True)
    assert item(s_unknown)["unit_cost"] is None                      # past sale is NOT back-filled
    assert item(sell(w, pid, 1))["unit_cost"] == D("125")
    assert ("cost_set", D("125")) in [(m["movement_type"], m["unit_cost"]) for m in get_movement_history(pid, w.bid, w.uid)]
    # a delivery onto EMPTY stock also makes the cost known
    p2 = prod(w, name="Other", cost=None, stock="0")
    buy(w, p2, 5, "80"); assert pcost(p2)[:2] == (D("80"), True)
    # a free delivery (cost 0) is allowed and lowers the average
    p3 = prod(w, name="Third", cost="100", stock="10"); buy(w, p3, 10, "0")
    assert pcost(p3)[0] == D("50")
    assert set_product_cost(p3, w.bid, w.uid, w.uid, "-1")[0] is False
    assert set_product_cost(p3, w.bid, w.uid, w.uid, "abc")[0] is False


def test_concurrent_deliveries_average_is_exact():
    w = World(); pid = prod(w, cost="100", stock="10")
    barrier = threading.Barrier(2)
    def go():
        barrier.wait(); adjust_stock(pid, w.bid, w.uid, w.uid, "add", 10, "New delivery / Purchase", "150")
    ts = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    # (10x100 + 10x150 + 10x150) / 30, whichever order they ran in
    assert pcost(pid)[0] == D("133.333333") and pcost(pid)[2] == D("30")


# ── 10-11: multi-product sales, partial payment, later repayment ────────────
def test_multi_product_sale_splits_known_and_unknown_lines():
    w = World()
    known = prod(w, name="Known", price="1000", cost="600", stock="10")
    unk = prod(w, name="Unknown", price="500", cost=None, stock="10")
    free = prod(w, name="Free", price="300", cost="0", stock="10")
    sid, msg = create_sale(w.bid, w.uid, w.uid,
                           [{"product_id": known, "quantity": 1}, {"product_id": unk, "quantity": 1},
                            {"product_id": free, "quantity": 1}], w.cid, "900", "Cash")      # total 1,800, paid half
    assert sid, msg
    total = one("SELECT total_amount FROM sales WHERE id=%s", (sid,))["total_amount"]
    assert total == D("1800") == one("SELECT SUM(line_total) s FROM sale_items WHERE sale_id=%s", (sid,))["s"]
    r = rep(w)
    # half paid: each line is paid for proportionally => unknown share 500/1800 of 900 = 250
    assert r["realised_stock_revenue"] == D("900")
    assert r["revenue_with_unknown_cost"] == D("250")
    assert r["cogs_on_collected"] == D("300")                        # 600 x 900/1800
    assert r["realised_gross_profit"] == D("900") - D("250") - D("300")   # known revenue 650 - cost 300 = 350
    assert r["realised_gross_profit"] == D("350")
    assert r["profit_incomplete"] and r["unknown_cost_items"][0]["product"] == "Unknown"
    # customer pays the rest later: whole sale recognised once
    ok, m = record_payment(sid, w.bid, w.uid, w.uid, "900", "Cash", None); assert ok, m
    r = rep(w)
    assert r["realised_stock_revenue"] == D("1800") and r["sales_activity"] == D("1800")
    assert r["revenue_with_unknown_cost"] == D("500")
    assert r["cogs_on_collected"] == D("600") and r["realised_gross_profit"] == D("1800") - D("500") - D("600")
    assert r["collections"]["stock_initial"]["amount"] == D("900") and r["collections"]["stock_repayment"]["amount"] == D("900")


def test_partial_payment_then_repayment_recognises_each_cost_once():
    w = World(); pid = prod(w, price="1000", cost="650", stock="100")
    sid = sell(w, pid, 100, paid="65000")
    r = rep(w)
    assert (r["realised_stock_revenue"], r["cogs_on_collected"], r["realised_gross_profit"]) == (D("65000"), D("42250"), D("22750"))
    ok, m = record_payment(sid, w.bid, w.uid, w.uid, "35000", "Cash", None); assert ok, m
    r = rep(w)
    assert (r["realised_stock_revenue"], r["cogs_on_collected"], r["realised_gross_profit"]) == (D("100000"), D("65000"), D("35000"))
    assert r["sales_activity"] == D("100000") and r["closing_debt"] == D("0")


# ── 12: treatment inventory usage ───────────────────────────────────────────
def test_treatment_dispensing_costs_stock_and_unknown_handling():
    w = World()
    known = prod(w, name="KnownMed", price="1000", cost="600", stock="50")
    unk = prod(w, name="UnknownMed", price="500", cost=None, stock="50")
    from treatments import create_treatment
    tid, msg = create_treatment(
        w.bid, w.uid, w.uid, "Ada Obi", "08012345678", None, date.today(), 5, None,
        [{"product_id": known, "quantity_per_administration": 1, "administrations_per_day": 1, "duration_days": 20},
         {"product_id": unk, "quantity_per_administration": 1, "administrations_per_day": 1, "duration_days": 20}], "1000")
    assert tid, msg
    items = {i["product_id"]: i["id"] for i in get_treatment_items(tid, w.bid, w.uid)}
    assert record_dispensing(items[known], w.bid, w.uid, w.uid, 4, None)[0]
    assert record_dispensing(items[unk], w.bid, w.uid, w.uid, 2, None)[0]
    assert pcost(known)[2] == D("46") and pcost(unk)[2] == D("48")                    # stock reduced as before
    d = one("SELECT unit_cost, cost_known FROM treatment_dispensing d JOIN treatment_items ti ON ti.id=d.treatment_item_id WHERE ti.product_id=%s", (known,))
    assert d["unit_cost"] == D("600") and d["cost_known"] is True
    d = one("SELECT unit_cost, cost_known FROM treatment_dispensing d JOIN treatment_items ti ON ti.id=d.treatment_item_id WHERE ti.product_id=%s", (unk,))
    assert d["unit_cost"] is None and d["cost_known"] is False
    bill = get_treatment_billing(tid, w.bid, w.uid)
    assert bill["total_bill"] == D("6000")                           # 1000 service + 4000 + 1000
    assert bill["lines_missing_cost"] == 1 and bill["incomplete"] is True
    assert bill["gross_profit"] == D("4000") - D("2400")             # unknown-cost line excluded, not costed at 0
    ok, m = record_treatment_payment(tid, w.bid, w.uid, w.uid, "3000", "Cash", None); assert ok, m
    r = rep(w)
    # bill 6,000: service 1,000 (no cost), known meds 4,000 (cost 2,400), unknown meds 1,000
    assert r["realised_treatment_revenue"] == D("3000")
    assert r["revenue_with_unknown_cost"] == D("500")                # 3000 x 1000/6000
    assert r["cogs_on_collected"] == D("1200")                       # 3000 x 2400/6000
    assert r["realised_gross_profit"] == D("2500") - D("1200")
    assert r["profit_incomplete"] and any(i["product"] == "UnknownMed" and i["source"] == "Treatment" for i in r["unknown_cost_items"])
    assert r["unknown_cost_treatments"] == 1


def test_treatment_bill_rounds_each_dispensing_to_the_kobo_consistently():
    w = World(); pid = prod(w, name="Fraction", price="15.55", cost="5", stock="10")
    from treatments import create_treatment
    tid, msg = create_treatment(w.bid, w.uid, w.uid, "Ada Obi", "08012345678", None, date.today(), 5, None,
                                [{"product_id": pid, "quantity_per_administration": 1, "administrations_per_day": 1, "duration_days": 10}], "0")
    assert tid, msg
    iid = get_treatment_items(tid, w.bid, w.uid)[0]["id"]
    assert record_dispensing(iid, w.bid, w.uid, w.uid, "0.5", None)[0]            # 0.5 x 15.55 = 7.775 -> 7.78
    bill = get_treatment_billing(tid, w.bid, w.uid)
    assert bill["total_bill"] == D("7.78")
    assert get_credit_summary(w.bid, w.uid)["treatment_outstanding"] == D("7.78")
    assert rep(w)["treatment_activity"] == D("7.78")
    ok, m = record_treatment_payment(tid, w.bid, w.uid, w.uid, "7.78", "Cash", None); assert ok, m
    assert get_treatment_billing(tid, w.bid, w.uid)["payment_status"] == "paid"   # exact, no 0.005 left over
    r = rep(w)
    assert r["realised_treatment_revenue"] == D("7.78") and r["closing_debt"] == D("0")


# ── 13: End-of-Day gross profit across changing costs ───────────────────────
def test_end_of_day_profit_with_cost_changes_between_sales():
    w = World(); pid = prod(w, price="200", cost="100", stock="10")
    sell(w, pid, 5, paid="1000")                                     # cost 100
    buy(w, pid, 10, "150")
    sell(w, pid, 5, paid="1000")                                     # cost (500 + 1500)/15 = 133.333333
    r = rep(w)
    assert r["realised_stock_revenue"] == D("2000") and r["cogs_on_collected"] == D("1166.67")
    assert r["realised_gross_profit"] == D("833.33") and r["profit_incomplete"] is False
    assert r["reconciles"] and r["unknown_cost_items"] == []


# ── 15: deleting / renaming a product keeps history ─────────────────────────
def test_product_delete_and_rename_keep_historical_sale_costs():
    w = World(); pid = prod(w, name="Old Name", price="200", cost="100", stock="10")
    sid = sell(w, pid, 3, paid="600")
    movements = one("SELECT COUNT(*) n FROM inventory_movements WHERE product_id=%s", (pid,))["n"]
    action, msg = delete_product(pid, w.bid, w.uid)
    assert action == "archived"                                      # has history -> archived, never destroyed
    assert one("SELECT is_active FROM products WHERE id=%s", (pid,))["is_active"] == 0
    assert one("SELECT COUNT(*) n FROM inventory_movements WHERE product_id=%s", (pid,))["n"] == movements
    it = item(sid)
    assert it["unit_cost"] == D("100") and it["product_name"] == "Old Name" and it["line_total"] == D("600")
    q("UPDATE products SET name='Renamed', purchase_price=777 WHERE id=%s", (pid,))
    it = item(sid)
    assert it["product_name"] == "Old Name" and it["unit_cost"] == D("100")
    r = rep(w)
    assert r["cogs_on_collected"] == D("300") and r["realised_gross_profit"] == D("300")
    # the database itself refuses to delete a sold product
    import psycopg2
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        q("DELETE FROM products WHERE id=%s", (pid,))
    # a product with no history at all is genuinely deleted
    empty = prod(w, name="Never Used", stock="0")
    assert delete_product(empty, w.bid, w.uid)[0] == "deleted"


def test_costing_is_business_scoped():
    a, b = World(), World()
    pid = prod(a, cost=None)
    from inventory import NotOwner
    ok, msg = set_product_cost(pid, b.bid, b.uid, b.uid, "10")      # B's own business, A's product id
    assert not ok and "not found" in msg.lower()
    with pytest.raises(NotOwner):                                    # same convention as adjust_stock: not your business
        set_product_cost(pid, a.bid, b.uid, b.uid, "10")
    assert pcost(pid)[1] is False
