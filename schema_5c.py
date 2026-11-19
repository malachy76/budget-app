# schema_5c.py — Phase 5C (Sales Returns & Refunds) database changes, as plain SQL.
#
# Pure data (no streamlit, no database access) so models.py, the tests and the
# migration-file generator can all import it.
#
# ADDITIVE and REPEATABLE only:
# * two NEW tables (CREATE TABLE IF NOT EXISTS) — nothing existing is altered
# * CREATE [UNIQUE] INDEX IF NOT EXISTS
# No existing table, column, constraint or row is dropped, renamed, rewritten or
# reset. The original sale, its items and its payments are never touched by a
# return; a return is a NEW record that points at them.
#
# sale_returns one row per return (value, how it was settled, reason, who, when)
# sale_return_items the goods in that return, with the ORIGINAL sale line's price and
# cost snapshot copied in (cost is never re-derived or rewritten)
#
# How a return is settled (all derived, nothing is stored on the sale):
# return_value = debt_reduction + refund_amount
# debt_reduction : the part that simply reduces what the customer still owes
# refund_amount : money actually paid back (only ever money the customer paid)
# A customer's balance on a sale is therefore
# total_amount - amount_paid - active write-offs - SUM(debt_reduction of its returns)

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS sale_returns ( id SERIAL PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE, customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL, return_value NUMERIC(14,2) NOT NULL, debt_reduction NUMERIC(14,2) NOT NULL DEFAULT 0, refund_amount NUMERIC(14,2) NOT NULL DEFAULT 0, refund_method TEXT, reason TEXT NOT NULL, note TEXT, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMP DEFAULT NOW(), idempotency_key TEXT, CONSTRAINT chk_sale_returns_value_nonneg CHECK (return_value >= 0), CONSTRAINT chk_sale_returns_split CHECK ( debt_reduction >= 0 AND refund_amount >= 0 AND return_value = debt_reduction + refund_amount), CONSTRAINT chk_sale_returns_refund_method CHECK ( refund_amount = 0 OR (refund_method IS NOT NULL AND btrim(refund_method) <> '')), CONSTRAINT chk_sale_returns_reason CHECK (btrim(reason) <> '') )""",
    """CREATE TABLE IF NOT EXISTS sale_return_items ( id SERIAL PRIMARY KEY, return_id INTEGER NOT NULL REFERENCES sale_returns(id) ON DELETE CASCADE, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, sale_item_id INTEGER NOT NULL REFERENCES sale_items(id) ON DELETE CASCADE, product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE, product_name TEXT NOT NULL, quantity NUMERIC(12,3) NOT NULL, unit_price NUMERIC(14,2) NOT NULL, unit_cost NUMERIC(14,6), cost_known BOOLEAN NOT NULL DEFAULT FALSE, line_value NUMERIC(14,2) NOT NULL, condition TEXT NOT NULL, CONSTRAINT chk_sale_return_items_qty CHECK (quantity > 0), CONSTRAINT chk_sale_return_items_value CHECK (line_value >= 0), CONSTRAINT chk_sale_return_items_condition CHECK (condition IN ('saleable', 'damaged')) )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_sale_returns_idem ON sale_returns(business_id, idempotency_key) "
    "WHERE idempotency_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_sale_returns_sale ON sale_returns(business_id, sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_sale_returns_created ON sale_returns(business_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sale_return_items_item ON sale_return_items(business_id, sale_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_sale_return_items_return ON sale_return_items(return_id)",
]


def statements():
    return list(STATEMENTS)


HEADER = """\ -- Phase 5C — Sales Returns & Refunds. -- -- You do NOT need to run this by hand: the app runs exactly these statements -- automatically (models.create_tables) every time it starts. It is provided so you -- can read it, review it, or run it yourself in the Supabase SQL editor. -- -- GENERATED from schema_5c.py (a test checks the two never drift apart). -- -- Safety -- * Additive only: two NEW tables and some indexes. Nothing existing is altered. -- * Safe to run any number of times (IF NOT EXISTS everywhere). -- * No existing sale, payment, customer, balance, stock figure or report is -- modified by this migration. Until a return is recorded, every figure in the -- app is exactly what it was before. """


def render_sql():
    return HEADER + "\n" + ";\n\n".join(statements()) + ";\n"


if __name__ == "__main__":
    import sys
    sys.stdout.write(render_sql())
