# Standalone upgrade check (not part of pytest — it needs TWO versions of the
# code). Usage:  python3 tests/migration_check_5b1.py <old_repo_dir> <new_repo_dir>
# Builds a throw-away PostgreSQL with the OLD (5A-5) schema + realistic data,
# then runs the NEW code's migration over it and proves nothing was lost.
import sys, types, tempfile
import pgserver

OLD, NEW = sys.argv[1], sys.argv[2]
srv = pgserver.get_server(tempfile.mkdtemp(prefix="br_mig5b_"))
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
import models, db
models.create_tables()
with db.get_db() as (c, cur):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='businesses'")
    assert "treatment_management_enabled" not in [r["column_name"] for r in cur.fetchall()]
    cur.execute("INSERT INTO users (surname, other_names, email, username, password) VALUES ('A','B','a@b.c','ab',%s) RETURNING id", (b"x",)); uid = cur.fetchone()["id"]
    ids = {}
    for key, name, typ in [("pharm", "City Pharmacy", "Pharmacy"), ("pharm2", "Clinic Pharmacy", "Pharmacy"),
                           ("shop", "Corner Shop", "Supermarket / Provision Store"),
                           ("oldtx", "Odd Mart", "Mini Mart")]:
        cur.execute("INSERT INTO businesses (owner_user_id, business_name, business_type) VALUES (%s,%s,%s) RETURNING id", (uid, name, typ)); ids[key] = cur.fetchone()["id"]
    cur.execute("INSERT INTO customers (business_id, name, phone) VALUES (%s,'Ada','0801') RETURNING id", (ids["oldtx"],)); cid = cur.fetchone()["id"]
    cur.execute("INSERT INTO treatments (business_id, patient_identifier, start_date, status, service_charge, customer_id) VALUES (%s,'Old Patient',CURRENT_DATE,'planned',500,%s)", (ids["oldtx"], cid))
    cur.execute("INSERT INTO sales (business_id, customer_id, total_amount, amount_paid, payment_status) VALUES (%s,%s,20000,5000,'partial')", (ids["shop"], None))
def snapshot():
    with db.get_db() as (c, cur):
        out = {}
        for t in ("users","businesses_core","customers","sales","treatments"):
            if t == "businesses_core":
                cur.execute("SELECT id, owner_user_id, business_name, business_type, created_at FROM businesses ORDER BY id")
            else:
                cur.execute(f"SELECT * FROM {t} ORDER BY 1")
            out[t] = [dict(r) for r in cur.fetchall()]
        return out
before = snapshot()

for m in [m for m in list(sys.modules) if m in ("models", "db", "business")]: del sys.modules[m]
sys.path.remove(OLD); sys.path.insert(0, NEW)
import models, db, business
models.create_tables()
after = snapshot()
assert before == after, "EXISTING DATA CHANGED"
vals = {}
with db.get_db() as (c, cur):
    cur.execute("SELECT id, treatment_management_enabled FROM businesses"); vals = {r["id"]: r["treatment_management_enabled"] for r in cur.fetchall()}
print({k: vals[v] for k, v in ids.items()})
assert vals[ids["pharm"]] is True and vals[ids["pharm2"]] is True        # pharmacies keep access
assert vals[ids["shop"]] is False                                         # a shop does not get pharmacy features
assert vals[ids["oldtx"]] is True                                         # a non-pharmacy that already used treatments keeps access
# owner turns one pharmacy off; re-running the migration (every app start) must keep it off
ok, msg = business.set_treatment_management(ids["pharm2"], uid, False); assert ok
models.create_tables.clear(); models.create_tables(); models.create_tables.clear(); models.create_tables()
assert business.is_treatment_management_enabled(ids["pharm2"], uid) is False
assert business.is_treatment_management_enabled(ids["pharm"], uid) is True
assert business.is_treatment_management_enabled(ids["shop"], uid) is False
print("existing rows identical before/after migration: OK")
print("MIGRATION CHECK PASSED")
srv.cleanup()
