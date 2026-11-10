# Standalone UI smoke test (real Streamlit AppTest + throw-away PostgreSQL).
# Usage:  cd <repo> && python3 tests/ui_smoke_5b1.py
# Runs the REAL app.py (login cookie component faked) and the changed pages.
import os, sys, tempfile, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, ROOT + "/tests")
import pgserver
srv = pgserver.get_server(tempfile.mkdtemp(prefix="br_ui5b_"))
srv.psql("ALTER DATABASE postgres SET timezone TO 'UTC';")
wd = tempfile.mkdtemp(prefix="br_ui5b_wd_"); os.makedirs(wd + "/.streamlit")
open(wd + "/.streamlit/secrets.toml", "w").write('SUPABASE_DB_URL = "%s"\n' % srv.get_uri())
os.chdir(wd)

# The login-cookie browser component can't run headless: replace it with a stub.
fake = types.ModuleType("cookies_compat")
class CookieManagerCompat:
    def __init__(self, *a, **k): pass
    def ready(self): return True
    def get(self, *a, **k): return ""
    def set(self, *a, **k): pass
    def delete(self, *a, **k): pass
    def __getitem__(self, k): return ""
    def __contains__(self, k): return False
fake.CookieManagerCompat = CookieManagerCompat
sys.modules["cookies_compat"] = fake

from streamlit.testing.v1 import AppTest
import models; models.create_tables()
from helpers import q, one, make_user, make_product
from business import create_business, set_treatment_management
uid = make_user()
q("UPDATE users SET role='user' WHERE id=%s", (uid,))
pharm, _ = create_business(uid, "My Pharmacy", "Pharmacy")
shop, _ = create_business(uid, "My Shop", "Supermarket / Provision Store")
pid = make_product(pharm, uid, price="1000", cost="600", stock="100")
cust_no_phone = one("INSERT INTO customers (business_id, name, phone) VALUES (%s,'Old Debtor',NULL) RETURNING id", (pharm,))["id"]
one("INSERT INTO sales (business_id, customer_id, total_amount, amount_paid, payment_status) VALUES (%s,%s,3000,0,'unpaid') RETURNING id", (pharm, cust_no_phone))

def app_at(biz_id, page=None):
    at = AppTest.from_file(ROOT + "/app.py", default_timeout=60)
    at.session_state["user_id"] = uid
    at.session_state["app_mode"] = "business"
    at.session_state["active_business_id"] = biz_id
    if page: at.session_state["biz_nav_radio"] = page
    return at.run()

def nav(at): return list(at.radio(key="biz_nav_radio").options)
def ok(at, label):
    assert not at.exception, (label, [e.value for e in at.exception])
    print("  ok:", label)

print("1. app starts; pharmacy (feature ON) shows the menu entry")
at = app_at(pharm); ok(at, "app.py started for pharmacy"); assert "Treatment Management" in nav(at), nav(at)

print("2. supermarket (feature OFF): menu entry hidden")
at = app_at(shop); ok(at, "app.py started for supermarket"); assert "Treatment Management" not in nav(at), nav(at)
assert "Bad Debts" in nav(at) and "End-of-Day Summary" in nav(at)
home = " ".join(m.value for m in at.markdown)
assert "Treatments" not in [b.label for b in at.button], "treatment shortcut leaked"

print("3. stale selection of the hidden page falls back safely")
at = app_at(shop, page="Treatment Management"); ok(at, "no crash"); assert at.radio(key="biz_nav_radio").value == "Business Home"

print("4. pharmacy owner switches the feature OFF from Settings")
at = app_at(pharm)
assert any(b.label == "\U0001F48A Treatments" for b in at.button), "shortcut should show while ON"
cb = at.checkbox(key=f"tm_toggle_{pharm}"); cb.uncheck().run(); ok(at, "unchecked")
at.button(key=f"tm_save_{pharm}").click().run(); ok(at, "saved")
assert one("SELECT treatment_management_enabled v FROM businesses WHERE id=%s", (pharm,))["v"] is False
assert "Treatment Management" not in nav(at), nav(at)
assert not any(b.label == "\U0001F48A Treatments" for b in at.button), "shortcut should be hidden"
assert any("kept" in s.value for s in at.success), [s.value for s in at.success]
print("   ...and back ON")
at.checkbox(key=f"tm_toggle_{pharm}").check().run(); at.button(key=f"tm_save_{pharm}").click().run(); ok(at, "re-enabled")
assert "Treatment Management" in nav(at)

print("5. treatments page refuses access when OFF (direct page call)")
set_treatment_management(pharm, uid, False)
def tpage():
    import streamlit as st
    from _pages.business_treatments import render_business_treatments
    render_business_treatments(st.session_state["uid"])
t = AppTest.from_function(tpage, default_timeout=30); t.session_state["uid"] = uid; t.session_state["active_business_id"] = pharm; t.run()
ok(t, "treatments page renders"); assert "turned off" in " ".join(i.value for i in t.info), [i.value for i in t.info]
assert not t.button and not t.text_input, "no treatment forms/buttons may show while OFF"
set_treatment_management(pharm, uid, True)

print("6. sales page: credit sale needs phone")
def spage():
    import streamlit as st
    from _pages.business_sales import render_business_sales
    render_business_sales(st.session_state["uid"])
s = AppTest.from_function(spage, default_timeout=30); s.session_state["uid"] = uid; s.session_state["active_business_id"] = pharm
s.session_state["_sale_cart"] = [{"product_id": pid, "name": "Item", "unit": "piece", "unit_price": __import__("decimal").Decimal("1000"), "quantity": __import__("decimal").Decimal("2")}]
s.run(); ok(s, "sales page")
s.text_input(key="sale_customer_name").set_value("New Debtor").run()
s.button(key="record_sale_btn").click().run()
errs = [e.value for e in s.error]; print("   no phone ->", errs)
assert errs and "phone" in errs[0].lower() and one("SELECT COUNT(*) n FROM sales WHERE business_id=%s", (pharm,))["n"] == 1
s.text_input(key="sale_customer_phone").set_value("   ").run(); s.button(key="record_sale_btn").click().run()
errs = [e.value for e in s.error]; print("   whitespace ->", errs); assert errs and "phone" in errs[0].lower()
assert one("SELECT COUNT(*) n FROM customers WHERE business_id=%s AND name='New Debtor'", (pharm,))["n"] == 0, "rejected sale must not leave a customer behind"
s.text_input(key="sale_customer_phone").set_value("0803 555 1212").run(); s.button(key="record_sale_btn").click().run()
ok(s, "credit sale with phone"); assert not s.error, [e.value for e in s.error]
r = one("SELECT c.phone, sa.amount_paid FROM sales sa JOIN customers c ON c.id=sa.customer_id WHERE sa.business_id=%s AND c.name='New Debtor'", (pharm,))
assert r["phone"] == "08035551212"; print("   saved:", dict(r))

print("7. customers page: missing phone flagged, can be added")
def cpage():
    import streamlit as st
    from _pages.business_customers import render_business_customers
    render_business_customers(st.session_state["uid"])
c = AppTest.from_function(cpage, default_timeout=30); c.session_state["uid"] = uid; c.session_state["active_business_id"] = pharm; c.run()
ok(c, "customers page"); assert any("no phone number" in w.value for w in c.warning), [w.value for w in c.warning]
assert any("No phone number" in m.value for m in c.markdown)
assert any("08035551212" in x.value for x in c.caption), "phone must show on the debt dashboard"
c.session_state["_credit_detail_customer_id"] = cust_no_phone; c.run(); ok(c, "customer detail")
c.text_input(key=f"add_phone_{cust_no_phone}").set_value("   ").run(); c.button(key=f"add_save_phone_{cust_no_phone}").click().run()
print("   blank ->", [e.value for e in c.error]); assert c.error
assert one("SELECT phone FROM customers WHERE id=%s", (cust_no_phone,))["phone"] is None
c.text_input(key=f"add_phone_{cust_no_phone}").set_value("0701 222 3333").run(); c.button(key=f"add_save_phone_{cust_no_phone}").click().run()
ok(c, "phone saved"); assert one("SELECT phone FROM customers WHERE id=%s", (cust_no_phone,))["phone"] == "07012223333"

print("8. End-of-Day Summary and Bad Debts still render")
for page in ("End-of-Day Summary", "Bad Debts", "Customers / Credit", "Sales / Point of Sale", "Products / Inventory"):
    at = app_at(pharm, page=page); ok(at, page)
print("9. Personal Mode still starts")
p = AppTest.from_file(ROOT + "/app.py", default_timeout=60); p.session_state["user_id"] = uid; p.session_state["app_mode"] = "personal"; p.run(); ok(p, "personal mode")
print("UI SMOKE TEST (5B-1) PASSED")
srv.cleanup()
