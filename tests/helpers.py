import itertools
from datetime import date
from decimal import Decimal

from db import get_db

_n = itertools.count(1)


def q(sql, params=()):
    with get_db() as (conn, cur):
        cur.execute(sql, params)
        try:
            return cur.fetchall()
        except Exception:
            return []


def one(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


def make_user():
    n = next(_n)
    r = one(
        "INSERT INTO users (surname, other_names, email, username, password) "
        "VALUES ('T','User',%s,%s,%s) RETURNING id",
        (f"u{n}@t.test", f"user{n}", b"x"),
    )
    return r["id"]


def make_business(uid, name="Test Pharmacy"):
    from business import create_business
    bid, msg = create_business(uid, name, "Pharmacy")
    assert bid, msg
    return bid


def make_product(bid, uid, name="Paracetamol", price="1000", cost="600", stock="100"):
    from inventory import create_product
    pid, msg = create_product(bid, uid, uid, name, None, None, "piece",
                              cost, price, stock, 0, None)
    assert pid, msg
    return pid


def make_customer(bid, uid, name="Ada Obi", phone="08012345678"):
    from sales import get_or_create_customer
    return get_or_create_customer(bid, uid, name, phone)


def make_sale(bid, uid, cid, pid, qty, paid="0", method="Cash"):
    from sales import create_sale
    sid, msg = create_sale(bid, uid, uid, [{"product_id": pid, "quantity": qty}],
                           cid, paid, method)
    assert sid, msg
    return sid


class World:
    """One owner + one business + one customer + one product."""
    def __init__(self, price="1000", cost="600", stock="100", cust="Ada Obi", phone="08012345678"):
        self.uid = make_user()
        self.bid = make_business(self.uid)
        self.pid = make_product(self.bid, self.uid, price=price, cost=cost, stock=stock)
        self.cid = make_customer(self.bid, self.uid, cust, phone)

    def sale(self, qty, paid="0"):
        return make_sale(self.bid, self.uid, self.cid, self.pid, qty, paid)

    def treatment(self, service_charge="0", dispense=(), patient="Ada Obi", phone="08012345678"):
        """dispense: iterable of quantities, each recorded as its own dispensing event."""
        from treatments import create_treatment, get_treatment_items, record_dispensing
        tid, msg = create_treatment(
            self.bid, self.uid, self.uid, patient, phone, None, date.today(), 5, None,
            [{"product_id": self.pid, "quantity_per_administration": 1,
              "administrations_per_day": 1, "duration_days": 50}],
            service_charge,
        )
        assert tid, msg
        item = get_treatment_items(tid, self.bid, self.uid)[0]
        for qty in dispense:
            ok, m = record_dispensing(item["id"], self.bid, self.uid, self.uid, qty, None)
            assert ok, m
        return tid


def key():
    import uuid
    return uuid.uuid4().hex


D = Decimal
