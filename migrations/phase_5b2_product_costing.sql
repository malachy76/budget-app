# Standalone upgrade check (not part of pytest — it needs TWO versions of the code).
# Usage:  python3 tests/migration_check_5b2.py <old_repo_dir> <new_repo_dir>
# Builds a throw-away PostgreSQL with the OLD (5B-1) schema + realistic data, runs the
# NEW migration over it, and proves: no value changed, columns widened, no cost
# back-filled, safe to run again, and legacy zero costs are reported as unverified.
import sys, types, tempfile
from datetime import date
from decimal import Decimal as D
import pgserver

OLD, NEW = sys.argv[1], sys.argv[2]
srv = pgserver.get_server(tempfile.mkdtemp(prefix="br_mig5b2_"))
srv.psql("ALTER DATABASE postgres SET timezone TO 'UTC';")
st = types.ModuleType("streamlit")
def cache_resource(*a, **k):
    def deco(fn):
        c = {}
        def w(*x, **y):
            if "v" not in c: c["v"] = fn(*x, **y)
            return c["v"]
        w.clear = lambda: c.clear(); return w
    return deco(a[0]) if a and callable(a[0]) else deco
st.cache_resource = cache_resource; st.secrets = {"SUPABASE_DB_URL": srv.get_uri()}
sys.modules["streamlit"] = st

sys.path.insert(0, OLD)
import models, db, business, inventory, sales, treatments
models.create_tables()
with db.get_db() as (c, cur):
    cur.execute("SELECT numeric_scale FROM information_schema.columns WHERE table_name='sale_items' AND column_name='unit_cost'")
    assert cur.fetchone()["numeric_scale"] == 2                         # old schema really is 2-decimal
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='products'")
    assert "cost_known" not in [r["column_name"] for r in cur.fetchall()]
    cur.execute("INSERT INTO users (surname, other_names, email, username, password) VALUES ('A','B','a@b.c','ab',%s) RETURNING id", (b"x",)); uid = cur.fetchone()["id"]
bid, _ = business.create_business(uid, "Old Pharmacy", "Pharmacy")
p_avg, _ = inventory.create_product(bid, uid, uid, "Averaged", None, None, "piece", "100", "200", "10", 0, None)
assert inventory.adjust_stock(p_avg, bid, uid, uid, "add", 7, "New delivery / Purchase", "150")[0]      # OLD code stores 120.59
p_zero, _ = inventory.create_product(bid, uid, uid, "Zero Priced", None, None, "piece", "0", "50", "10", 0, None)
cid = sales.get_or_create_customer(bid, uid, "Ada Obi", "08012345678")
s1, m = sales.create_sale(bid, uid, uid, [{"product_id": p_avg, "quantity": 3}, {"product_id": p_zero, "quantity": 2}], cid, "100", "Cash"); assert s1, m
tid, m = treatments.create_treatment(bid, uid, uid, "Ada Obi", "08012345678", None, date.today(), 5, None,
    [{"product_id": p_avg, "quantity_per_administration": 1, "administrations_per_day": 1, "duration_days": 10}], "500"); assert tid, m
iid = treatments.get_treatment_items(tid, bid, uid)[0]["id"]
assert treatments.record_dispensing(iid, bid, uid, uid, 2, None)[0]

COLS = {"products": "id, name, purchase_price, selling_price, current_stock",
        "inventory_movements": "id, movement_type, quantity, unit_cost",
        "sale_items": "id, sale_id, product_id, product_name, quantity, unit_price, unit_cost, line_total",
        "treatment_dispensing": "id, quantity, unit_price, unit_cost",
        "sales": "id, total_amount, amount_paid", "payments": "id, amount"}
def snapshot():
    out = {}
    with db.get_db() as (c, cur):
        for t, cols in COLS.items():
            cur.execute(f"SELECT {cols} FROM {t} ORDER BY id"); out[t] = [dict(r) for r in cur.fetchall()]
    return out
before = snapshot()
print("old averaged cost stored as:", [r["purchase_price"] for r in before["products"] if r["name"] == "Averaged"])

for m in [m for m in list(sys.modules) if m in ("models","db","business","inventory","sales","treatments","contacts","costing","daily_report","customers","baddebt")]: del sys.modules[m]
sys.path.remove(OLD); sys.path.insert(0, NEW)
import models, db, daily_report
for i in range(3):                                       # three app restarts
    models.create_tables.clear(); models.create_tables()
after = snapshot()
assert set(before) == set(after)
for t in before:
    assert len(before[t]) == len(after[t]), t
    for b, a in zip(before[t], after[t]):
        assert b == a, (t, b, a)                          # Decimal equality: 120.59 == 120.590000
print("every existing value identical after migration (all 6 tables): OK")
with db.get_db() as (c, cur):
    for t, col in (("products","purchase_price"),("inventory_movements","unit_cost"),("sale_items","unit_cost"),("treatment_dispensing","unit_cost")):
        cur.execute("SELECT numeric_precision, numeric_scale FROM information_schema.columns WHERE table_name=%s AND column_name=%s", (t, col))
        r = cur.fetchone(); assert (r["numeric_precision"], r["numeric_scale"]) == (18, 6), (t, r)
    for t in ("products","sale_items","treatment_dispensing"):
        cur.execute(f"SELECT COUNT(*) n FROM {t} WHERE cost_known IS NOT NULL"); assert cur.fetchone()["n"] == 0, t   # nothing back-filled
print("cost columns are NUMERIC(18,6); cost_known left NULL on every existing row: OK")

# New code over legacy data: the legacy zero-cost line is unverified, the positive cost is trusted
today = daily_report.business_today()
r = daily_report.get_cash_basis_report(bid, uid, today, today)
print({k: r[k] for k in ("realised_stock_revenue", "revenue_with_unknown_cost", "cogs_on_collected", "realised_gross_profit", "profit_incomplete")})
assert r["profit_incomplete"] and [i["product"] for i in r["unknown_cost_items"]] == ["Zero Priced"]
assert r["revenue_with_unknown_cost"] > 0 and r["realised_gross_profit"] > 0
# and new sales of an upgraded product are fine
import inventory, sales
assert inventory.adjust_stock(p_avg, bid, uid, uid, "add", 5, "New delivery / Purchase", "130")[0]
sid, m = sales.create_sale(bid, uid, uid, [{"product_id": p_avg, "quantity": 1}], cid, "0", "Cash"); assert sid, m
with db.get_db() as (c, cur):
    cur.execute("SELECT unit_cost, cost_known FROM sale_items WHERE sale_id=%s", (sid,)); row = cur.fetchone()
    assert row["cost_known"] is True and row["unit_cost"] > 0
    cur.execute("SELECT unit_cost, cost_known FROM sale_items WHERE sale_id=%s ORDER BY id", (s1,)); legacy = cur.fetchall()
    assert [x["unit_cost"] for x in legacy] == [before["sale_items"][0]["unit_cost"], D("0")] and all(x["cost_known"] is None for x in legacy)
print("MIGRATION CHECK (5B-2) PASSED")
srv.cleanup()
