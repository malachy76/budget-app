# Phase 5B-1 tests — optional Treatment Management + compulsory phone for credit.
# Real code against a real throw-away PostgreSQL (see conftest.py).
from datetime import date
from decimal import Decimal as D

import pytest

import models
from business import (
    create_business, get_business, get_user_businesses, is_treatment_management_enabled,
    set_treatment_management,
)
from contacts import normalize_phone
from sales import create_sale, get_or_create_customer, SaleError
from customers import (
    update_customer_phone, get_customers_with_balance, get_credit_summary, record_payment,
)
from treatments import (
    create_treatment, get_treatment_items, record_dispensing, update_treatment_status,
    record_treatment_payment, get_treatment_billing, get_treatments, TREATMENT_OFF_MSG,
)
from baddebt import write_off_debt
from daily_report import get_cash_basis_report, business_today
from helpers import World, q, one, key, make_user, make_product


def biz(uid, btype, **kw):
    bid, msg = create_business(uid, f"{btype} test", btype, **kw)
    assert bid, msg
    return bid


def count(table, bid):
    return one(f"SELECT COUNT(*) n FROM {table} WHERE business_id=%s", (bid,))["n"]


def mk_treatment(w, phone="08012345678", patient="Ada Obi", service="1000"):
    return create_treatment(
        w.bid, w.uid, w.uid, patient, phone, None, date.today(), 5, None,
        [{"product_id": w.pid, "quantity_per_administration": 1,
          "administrations_per_day": 1, "duration_days": 50}], service)


# ═══ A. Treatment Management is optional and enforced in the backend ═══════

def test_defaults_by_business_type():
    u = make_user()
    assert get_business(biz(u, "Pharmacy"), u)["treatment_management_enabled"] is True
    for t in ("Supermarket / Provision Store", "Mini Mart", "Beauty / Cosmetics", "Other Retail"):
        assert get_business(biz(u, t), u)["treatment_management_enabled"] is False, t


def test_explicit_setting_at_creation_and_in_listing():
    u = make_user()
    off_pharm = biz(u, "Pharmacy", treatment_management_enabled=False)
    on_other = biz(u, "Mini Mart", treatment_management_enabled=True)
    assert is_treatment_management_enabled(off_pharm, u) is False
    assert is_treatment_management_enabled(on_other, u) is True
    listing = {b["id"]: b["treatment_management_enabled"] for b in get_user_businesses(u)}
    assert listing[off_pharm] is False and listing[on_other] is True


def test_pharmacy_enabled_can_create_and_dispense():
    w = World(); w.pid  # World businesses are Pharmacy => enabled by default
    tid, msg = mk_treatment(w)
    assert tid, msg
    item = get_treatment_items(tid, w.bid, w.uid)[0]
    ok, msg = record_dispensing(item["id"], w.bid, w.uid, w.uid, 2, None)
    assert ok, msg
    assert update_treatment_status(tid, w.bid, w.uid, "in_progress")[0]


def test_pharmacy_disabled_blocks_every_treatment_write_path():
    w = World()
    tid, _ = mk_treatment(w)
    item = get_treatment_items(tid, w.bid, w.uid)[0]
    assert set_treatment_management(w.bid, w.uid, False)[0]
    stock = one("SELECT current_stock FROM products WHERE id=%s", (w.pid,))["current_stock"]
    n_tx, n_items, n_disp = count("treatments", w.bid), count("treatment_items", w.bid), count("treatment_dispensing", w.bid)
    assert mk_treatment(w, patient="New Patient") == (None, TREATMENT_OFF_MSG)
    assert record_dispensing(item["id"], w.bid, w.uid, w.uid, 1, None) == (None, TREATMENT_OFF_MSG)
    assert update_treatment_status(tid, w.bid, w.uid, "completed") == (None, TREATMENT_OFF_MSG)
    assert (count("treatments", w.bid), count("treatment_items", w.bid), count("treatment_dispensing", w.bid)) == (n_tx, n_items, n_disp)
    assert one("SELECT current_stock FROM products WHERE id=%s", (w.pid,))["current_stock"] == stock      # no stock moved
    assert one("SELECT status FROM treatments WHERE id=%s", (tid,))["status"] != "completed"


def test_non_pharmacy_has_no_treatment_features_unless_enabled():
    u = make_user(); b = biz(u, "Supermarket / Provision Store")
    pid = make_product(b, u)
    class X: pass
    w = X(); w.bid, w.uid, w.pid = b, u, pid
    assert is_treatment_management_enabled(b, u) is False
    assert mk_treatment(w) == (None, TREATMENT_OFF_MSG)
    assert count("treatments", b) == 0
    # explicit opt-in works, and nothing else changed
    assert set_treatment_management(b, u, True)[0]
    tid, msg = mk_treatment(w); assert tid, msg


def test_disabling_keeps_history_debts_payments_and_reports_intact():
    w = World()
    tid, _ = mk_treatment(w, service="2000")
    item = get_treatment_items(tid, w.bid, w.uid)[0]
    assert record_dispensing(item["id"], w.bid, w.uid, w.uid, 8, None)[0]          # 8,000 medicine + 2,000 service
    assert record_treatment_payment(tid, w.bid, w.uid, w.uid, "3000", "Cash", None)[0]
    today = business_today()
    before = {
        "bill": get_treatment_billing(tid, w.bid, w.uid),
        "report": get_cash_basis_report(w.bid, w.uid, today, today),
        "credit": get_credit_summary(w.bid, w.uid),
        "rows": [count(t, w.bid) for t in ("treatments", "treatment_items", "treatment_dispensing", "treatment_payments", "customers")],
    }
    assert set_treatment_management(w.bid, w.uid, False)[0]
    after = {
        "bill": get_treatment_billing(tid, w.bid, w.uid),
        "report": get_cash_basis_report(w.bid, w.uid, today, today),
        "credit": get_credit_summary(w.bid, w.uid),
        "rows": [count(t, w.bid) for t in ("treatments", "treatment_items", "treatment_dispensing", "treatment_payments", "customers")],
    }
    assert after == before                                         # nothing lost, nothing recalculated
    assert after["credit"]["treatment_outstanding"] == D("7000")
    assert len(get_treatments(w.bid, w.uid)) == 1                  # still readable
    # collecting existing treatment debt and writing it off still work while OFF
    ok, msg = record_treatment_payment(tid, w.bid, w.uid, w.uid, "2000", "Cash", None); assert ok, msg
    wid, msg = write_off_debt("treatment", tid, w.bid, w.uid, w.uid, "5000", "Customer is unable to repay", "", key()); assert wid, msg
    assert get_credit_summary(w.bid, w.uid)["treatment_outstanding"] == D("0")
    # switching back on restores full access
    assert set_treatment_management(w.bid, w.uid, True)[0]
    assert mk_treatment(w, patient="Second Patient")[0]


def test_setting_is_owner_scoped():
    a, b = World(), World()
    ok, msg = set_treatment_management(a.bid, b.uid, False)       # B tries to switch A's setting
    assert not ok and "not found" in msg.lower()
    assert is_treatment_management_enabled(a.bid, a.uid) is True
    assert is_treatment_management_enabled(a.bid, b.uid) is False  # fails closed for a non-owner
    assert is_treatment_management_enabled(999999, a.uid) is False
    assert get_business(a.bid, b.uid) is None
    # a non-owner can't create treatments in someone else's business either
    with pytest.raises(Exception):
        create_treatment(a.bid, b.uid, b.uid, "X", "08011112222", None, date.today(), 5, None,
                         [{"product_id": a.pid, "quantity_per_administration": 1}], "0")


# ═══ B. Migration (idempotent, never overrides an owner's choice) ═══════════

def test_migration_backfill_rules_idempotent_and_respects_owner_choice():
    u = make_user()
    pharm = biz(u, "Pharmacy")
    shop = biz(u, "Supermarket / Provision Store")
    shop_with_history = biz(u, "Mini Mart")
    w = type("X", (), {})(); w.bid, w.uid, w.pid = shop_with_history, u, make_product(shop_with_history, u)
    set_treatment_management(shop_with_history, u, True); assert mk_treatment(w)[0]
    # simulate rows written before the 5B-1 migration ran: setting is NULL
    q("UPDATE businesses SET treatment_management_enabled=NULL WHERE id = ANY(%s)", ([pharm, shop, shop_with_history],))
    # ...and until the migration runs, reads already apply the same rule (no access lost/gained)
    assert [is_treatment_management_enabled(b, u) for b in (pharm, shop, shop_with_history)] == [True, False, True]
    models.create_tables.clear(); models.create_tables()           # re-run migrations
    vals = {b: one("SELECT treatment_management_enabled v FROM businesses WHERE id=%s", (b,))["v"]
            for b in (pharm, shop, shop_with_history)}
    assert vals == {pharm: True, shop: False, shop_with_history: True}
    # owner switches a pharmacy OFF; later migration runs must not re-enable it
    set_treatment_management(pharm, u, False)
    models.create_tables.clear(); models.create_tables()
    models.create_tables.clear(); models.create_tables()
    assert is_treatment_management_enabled(pharm, u) is False
    assert count("treatments", shop_with_history) == 1             # data untouched


# ═══ C. Phone number is compulsory for credit ══════════════════════════════

@pytest.mark.parametrize("raw,expected", [
    ("08012345678", "08012345678"), ("0801 234 5678", "08012345678"),
    ("+234 801-234-5678", "+2348012345678"), ("(0801) 234.5678", "08012345678"),
])
def test_phone_normalisation(raw, expected):
    assert normalize_phone(raw) == (expected, None)


@pytest.mark.parametrize("bad", ["", "   ", "\t\n", None, "abc", "12345", "0801-ABC-5678", "1" * 16, "++2348012345678"])
def test_phone_rejects_blank_and_invalid(bad):
    clean, err = normalize_phone(bad)
    assert clean is None and err


def _credit_world():
    u = make_user(); b = biz(u, "Pharmacy"); pid = make_product(b, u, price="1000", cost="600", stock="100")
    return u, b, pid


def test_credit_sale_with_valid_phone_succeeds():
    u, b, pid = _credit_world()
    cid = get_or_create_customer(b, u, "Ada Obi", "0801 234 5678", require_phone=True)
    assert one("SELECT phone FROM customers WHERE id=%s", (cid,))["phone"] == "08012345678"
    sid, msg = create_sale(b, u, u, [{"product_id": pid, "quantity": 5}], cid, "0", "Cash")
    assert sid, msg
    row = [c for c in get_customers_with_balance(b, u) if c["id"] == cid][0]
    assert row["phone"] == "08012345678" and row["total_outstanding"] == D("5000")   # dashboard shows phone + debt


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_credit_sale_with_blank_or_whitespace_phone_is_rejected_without_side_effects(blank):
    u, b, pid = _credit_world()
    with pytest.raises(SaleError):
        get_or_create_customer(b, u, "Blank Phone", blank, require_phone=True)
    assert count("customers", b) == 0                              # no half-created customer
    # same protection if the customer row already exists without a phone (e.g. older data)
    cid = one("INSERT INTO customers (business_id, name, phone) VALUES (%s,'Old Customer',NULL) RETURNING id", (b,))["id"]
    stock = one("SELECT current_stock s FROM products WHERE id=%s", (pid,))["s"]
    sid, msg = create_sale(b, u, u, [{"product_id": pid, "quantity": 3}], cid, "0", "Cash")
    assert sid is None and "phone" in msg.lower()
    sid, msg = create_sale(b, u, u, [{"product_id": pid, "quantity": 3}], cid, "1000", "Cash")   # part-payment is credit too
    assert sid is None and "phone" in msg.lower()
    assert count("sales", b) == 0 and count("sale_items", b) == 0
    assert one("SELECT current_stock s FROM products WHERE id=%s", (pid,))["s"] == stock          # stock untouched
    with pytest.raises(SaleError):
        get_or_create_customer(b, u, "Old Customer", blank, require_phone=True)


def test_credit_sale_invalid_phone_rejected_and_credit_needs_a_customer():
    u, b, pid = _credit_world()
    with pytest.raises(SaleError):
        get_or_create_customer(b, u, "Bad Number", "abc123", require_phone=True)
    sid, msg = create_sale(b, u, u, [{"product_id": pid, "quantity": 1}], None, "0", "Cash")
    assert sid is None and "customer" in msg.lower()
    assert count("sales", b) == 0


def test_existing_customer_without_phone_gets_it_from_the_credit_form():
    u, b, pid = _credit_world()
    cid = one("INSERT INTO customers (business_id, name, phone) VALUES (%s,'Chi Eze',NULL) RETURNING id", (b,))["id"]
    same = get_or_create_customer(b, u, "Chi Eze", "07011112222", require_phone=True)
    assert same == cid and one("SELECT phone FROM customers WHERE id=%s", (cid,))["phone"] == "07011112222"
    sid, msg = create_sale(b, u, u, [{"product_id": pid, "quantity": 2}], cid, "0", "Cash"); assert sid, msg
    assert count("customers", b) == 1                              # reused, not duplicated


def test_cash_sales_do_not_need_a_phone():
    u, b, pid = _credit_world()
    sid, msg = create_sale(b, u, u, [{"product_id": pid, "quantity": 2}], None, "2000", "Cash")
    assert sid, msg                                                # anonymous walk-in, fully paid
    cid = get_or_create_customer(b, u, "Walk In Named", "", require_phone=False)
    assert cid and one("SELECT phone FROM customers WHERE id=%s", (cid,))["phone"] is None
    sid, msg = create_sale(b, u, u, [{"product_id": pid, "quantity": 1}], cid, "1000", "Cash")
    assert sid, msg                                                # named, fully paid, no debt => no phone needed
    with pytest.raises(SaleError):
        get_or_create_customer(b, u, "Typo Phone", "xx", require_phone=False)   # but a typed number must be sane


def test_update_existing_customer_phone():
    u, b, pid = _credit_world()
    cid = one("INSERT INTO customers (business_id, name, phone) VALUES (%s,'Update Me',NULL) RETURNING id", (b,))["id"]
    for bad in ("", "   ", "nope"):
        ok, msg = update_customer_phone(cid, b, u, bad)
        assert ok is None and msg
        assert one("SELECT phone FROM customers WHERE id=%s", (cid,))["phone"] is None
    ok, msg = update_customer_phone(cid, b, u, " 0802 333 4444 "); assert ok, msg
    assert one("SELECT phone FROM customers WHERE id=%s", (cid,))["phone"] == "08023334444"
    # existing history untouched by the update
    sid, _ = create_sale(b, u, u, [{"product_id": pid, "quantity": 1}], cid, "0", "Cash"); assert sid
    assert update_customer_phone(cid, b, u, "08099998888")[0]
    assert one("SELECT customer_id FROM sales WHERE id=%s", (sid,))["customer_id"] == cid


def test_customer_and_phone_isolation_between_businesses():
    a, c = World(), World()
    cust_a = a.cid
    # owner C can't edit A's customer, even with A's business id or their own
    assert update_customer_phone(cust_a, a.bid, c.uid, "08011112222")[0] is None
    assert update_customer_phone(cust_a, c.bid, c.uid, "08011112222")[0] is None
    assert one("SELECT phone FROM customers WHERE id=%s", (cust_a,))["phone"] == "08012345678"
    # can't attach another business's customer to a sale
    sid, msg = create_sale(c.bid, c.uid, c.uid, [{"product_id": c.pid, "quantity": 1}], cust_a, "1000", "Cash")
    assert sid is None and "not found" in msg.lower()
    assert count("sales", c.bid) == 0
    # same name in two businesses stays two customers
    assert get_or_create_customer(a.bid, a.uid, "Shared Name", "08011110001", True) != \
           get_or_create_customer(c.bid, c.uid, "Shared Name", "08011110002", True)


def test_treatment_requires_patient_phone_and_links_customer_with_it():
    w = World()
    for bad in ("", "   ", "abc"):
        tid, msg = mk_treatment(w, phone=bad, patient="No Phone Patient")
        assert tid is None and "phone" in msg.lower()
    assert count("treatments", w.bid) == 0 and one("SELECT COUNT(*) n FROM customers WHERE business_id=%s AND name='No Phone Patient'", (w.bid,))["n"] == 0
    tid, msg = mk_treatment(w, phone="0803 111 2222", patient="Phone Patient"); assert tid, msg
    r = one("SELECT t.patient_phone, c.phone FROM treatments t JOIN customers c ON c.id=t.customer_id WHERE t.id=%s", (tid,))
    assert r["patient_phone"] == "08031112222" and r["phone"] == "08031112222"
    # a patient already known WITHOUT a phone gets it saved from the new treatment
    one("INSERT INTO customers (business_id, name, phone) VALUES (%s,'Known Patient',NULL) RETURNING id", (w.bid,))
    tid, msg = mk_treatment(w, phone="08034445555", patient="Known Patient"); assert tid, msg
    assert one("SELECT phone FROM customers WHERE business_id=%s AND name='Known Patient'", (w.bid,))["phone"] == "08034445555"
