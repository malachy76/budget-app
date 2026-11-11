# Standalone UI smoke test for Phase 5B-2 (real Streamlit AppTest + throw-away PostgreSQL).
# Usage:  cd <repo> && python3 tests/ui_smoke_5b2.py
import os, sys, tempfile, types
from decimal import Decimal
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, ROOT + "/tests")
import pgserver
srv = pgserver.get_server(tempfile.mkdtemp(prefix="br_ui5b2_"))
srv.psql("ALTER DATABASE postgres SET timezone TO 'UTC';")
wd = tempfile.mkdtemp(prefix="br_ui5b2_wd_"); os.makedirs(wd + "/.streamlit")
open(wd + "/.streamlit/secrets.toml", "w").write('SUPABASE_DB_URL = "%s"\n' % srv.get_uri())
os.chdir(wd)
from streamlit.testing.v1 import AppTest
import models; models.create_tables()
from helpers import q, one, make_user
from business import create_business
uid = make_user(); bid, _ = create_business(uid, "My Pharmacy", "Pharmacy")
cid = one("INSERT INTO customers (business_id, name, phone) VALUES (%s,'Ada','08012345678') RETURNING id", (bid,))["id"]

def page(fn_name, mod):
    src = (f"import sys\nsys.path.insert(0, {ROOT!r})\nimport streamlit as st\n"
           f"from {mod} import {fn_name}\n{fn_name}(st.session_state['uid'])\n")
    at = AppTest.from_string(src, default_timeout=30)
    at.session_state["uid"] = uid; at.session_state["active_business_id"] = bid
    return at
def ok(at, label):
    assert not at.exception, (label, [e.value for e in at.exception]); print("  ok:", label)

print("1. add a product WITHOUT a purchase price (cost unknown)")
inv = page("render_business_inventory", "_pages.business_inventory").run(); ok(inv, "inventory page")
inv.text_input(key="add_product_name").set_value("Mystery Tonic")
inv.number_input(key="add_product_selling_price").set_value(500.0)
inv.number_input(key="add_product_opening_stock").set_value(10.0)
inv.button(key="create_product_btn").click().run(); ok(inv, "created")
assert not inv.error, [e.value for e in inv.error]
p = one("SELECT id, purchase_price, cost_known FROM products WHERE business_id=%s AND name='Mystery Tonic'", (bid,))
assert p["cost_known"] is False; pid = p["id"]
txt = " ".join(m.value for m in inv.markdown) + " ".join(w.value for w in inv.warning)
assert "not set" in txt and any("no cost set" in w.value for w in inv.warning), (txt, [w.value for w in inv.warning])
print("   card shows 'not set' + summary warning")

print("2. add a product with an explicit 0 cost (genuinely free)")
inv.text_input(key="add_product_name").set_value("Free Sample")
inv.number_input(key="add_product_purchase_price").set_value(0.0)
inv.number_input(key="add_product_selling_price").set_value(300.0)
inv.number_input(key="add_product_opening_stock").set_value(5.0)
inv.button(key="create_product_btn").click().run(); ok(inv, "created free product")
f = one("SELECT purchase_price, cost_known FROM products WHERE business_id=%s AND name='Free Sample'", (bid,))
assert f["cost_known"] is True and f["purchase_price"] == 0

print("3. a sale of the unknown-cost product -> End-of-Day shows incomplete profit and names the product")
from sales import create_sale
sid, m = create_sale(bid, uid, uid, [{"product_id": pid, "quantity": 2}], cid, "1000", "Cash"); assert sid, m
eod = page("render_business_daily_report", "_pages.business_daily_report").run(); ok(eod, "end-of-day page")
w = " ".join(x.value for x in eod.warning); c = " ".join(x.value for x in eod.caption)
print("   warnings:", [x.value[:70] for x in eod.warning])
assert "Profit is incomplete" in w and "Mystery Tonic" in c
mm = {x.label: x.value for x in eod.metric}
assert mm["Realised Gross Profit"] == "₦0.00" and mm["Realised Stock Sales Revenue"] == "₦1,000.00"

print("4. detail page: Set Cost fixes FUTURE sales only; zero-cost delivery allowed")
inv2 = page("render_business_inventory", "_pages.business_inventory"); inv2.session_state["_inv_detail_product_id"] = pid; inv2.run(); ok(inv2, "detail page")
assert any("not set" in m.value for m in inv2.markdown)
inv2.number_input(key="set_cost_value").set_value(250.0).run()
inv2.button(key="set_cost_btn").click().run(); ok(inv2, "set cost")
assert not inv2.error, [e.value for e in inv2.error]
p = one("SELECT purchase_price, cost_known FROM products WHERE id=%s", (pid,))
assert p["cost_known"] is True and p["purchase_price"] == Decimal("250")
assert one("SELECT unit_cost FROM sale_items WHERE sale_id=%s", (sid,))["unit_cost"] is None      # history untouched
inv2.radio(key="adj_direction").set_value("Add stock").run()
inv2.selectbox(key="adj_reason").set_value("New delivery / Purchase").run()
inv2.number_input(key="adj_qty").set_value(10.0).run()
inv2.number_input(key="adj_unit_cost").set_value(0.0).run()
inv2.button(key="adj_confirm_btn").click().run(); ok(inv2, "zero-cost delivery")
assert not inv2.error, [e.value for e in inv2.error]                    # used to be rejected as "enter the unit cost"
p = one("SELECT purchase_price, current_stock FROM products WHERE id=%s", (pid,))
print("   after free delivery: stock", p["current_stock"], "avg cost", p["purchase_price"])
assert p["current_stock"] == Decimal("18")          # 8 left after the sale + 10 free units; (8 x 250 + 10 x 0) / 18
assert abs(p["purchase_price"] - Decimal("111.111111")) < Decimal("0.000002")

print("5. the other pages still render")
for fn, mod in (("render_business_home", "_pages.business_home"), ("render_business_sales", "_pages.business_sales"),
                ("render_business_customers", "_pages.business_customers"), ("render_business_treatments", "_pages.business_treatments")):
    ok(page(fn, mod).run(), fn)
print("UI SMOKE TEST (5B-2) PASSED")
srv.cleanup()
