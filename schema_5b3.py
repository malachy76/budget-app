# schema_5b3.py — Phase 5B-3 database changes, as plain SQL statements.
#
# Pure data: no streamlit, no database access, so it can be imported by
# models.py (which runs it at start-up), by the tests, and by
# tools to regenerate migrations/phase_5b3_financial_integrity.sql.
#
# EVERY statement is additive and safe to run any number of times:
#   * ADD COLUMN IF NOT EXISTS                     (nullable, no rewrite)
#   * CREATE [UNIQUE] INDEX IF NOT EXISTS          (partial unique indexes
#                                                   ignore the NULL keys that
#                                                   every existing row has)
#   * CHECK constraints are added NOT VALID and only if absent. NOT VALID
#     means: enforced for every NEW insert/update from now on, but existing
#     rows are NOT scanned or rewritten, so legacy data can never make the
#     migration fail or be altered. (Use integrity.reconcile_business() to
#     see whether any legacy row would violate a rule.)
# Nothing is dropped, renamed, deleted, reset or rewritten.

IDEMPOTENCY_TABLES = (
    "sales", "treatments", "payments", "treatment_payments",
    "inventory_movements", "treatment_dispensing", "transactions",
)

# (constraint name, table, boolean expression)
CHECKS = (
    # Stock can never be driven below zero, whatever code path writes it.
    ("chk_products_stock_nonneg", "products", "current_stock >= 0"),
    # The movement ledger never records a negative balance.
    ("chk_inv_movements_after_nonneg", "inventory_movements", "quantity_after >= 0"),
    # Every manual stock change must say why (sales/dispensing carry their
    # own reference note; these are the owner-initiated movement types).
    ("chk_inv_movements_adjust_reason", "inventory_movements",
     "movement_type NOT IN ('purchase','adjustment_in','adjustment_out','damaged','expired','cost_set') "
     "OR (note IS NOT NULL AND btrim(note) <> '')"),
    # A sale can never record more paid than it is worth, or a negative amount.
    ("chk_sales_paid_range", "sales",
     "total_amount >= 0 AND amount_paid >= 0 AND amount_paid <= total_amount"),
    ("chk_sale_items_qty_positive", "sale_items", "quantity > 0"),
    ("chk_treatments_paid_nonneg", "treatments", "amount_paid >= 0"),
    ("chk_treatment_dispensing_qty_positive", "treatment_dispensing", "quantity > 0"),
    # A payment row is either a real positive payment, or a NEGATIVE
    # compensating row that points at the payment it reverses. Nothing else.
    ("chk_payments_amount_shape", "payments",
     "(amount > 0 AND reverses_payment_id IS NULL) OR (amount < 0 AND reverses_payment_id IS NOT NULL)"),
    ("chk_treatment_payments_amount_shape", "treatment_payments",
     "(amount > 0 AND reverses_payment_id IS NULL) OR (amount < 0 AND reverses_payment_id IS NOT NULL)"),
)


def _add_check_sql(name, table, expr):
    return (
        "DO $$ BEGIN\n"
        f"  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}' "
        f"AND conrelid = '{table}'::regclass) THEN\n"
        f"    ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expr}) NOT VALID;\n"
        "  END IF;\n"
        "END $$"
    )


def statements():
    """Ordered list of SQL statements for the whole phase."""
    out = []
    # 1. Submission references (idempotency keys). Nullable: every existing
    #    row simply has NULL and is unaffected.
    for t in IDEMPOTENCY_TABLES:
        out.append(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS idempotency_key TEXT")
    # 2. Payment reversal links (a reversal is a NEW negative row; the
    #    original payment row is never edited or deleted).
    out.append("ALTER TABLE payments ADD COLUMN IF NOT EXISTS reverses_payment_id INTEGER REFERENCES payments(id)")
    out.append("ALTER TABLE treatment_payments ADD COLUMN IF NOT EXISTS reverses_payment_id INTEGER REFERENCES treatment_payments(id)")
    # 3. Database-level duplicate backstops.
    for t in ("sales", "treatments", "payments", "treatment_payments", "inventory_movements", "treatment_dispensing"):
        out.append(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{t}_idem ON {t}(business_id, idempotency_key) "
            "WHERE idempotency_key IS NOT NULL"
        )
    # Personal Mode: transactions belong to a bank account, not a business.
    out.append(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_idem ON transactions(bank_id, idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    )
    # A payment can be reversed at most once.
    out.append("CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_reverses ON payments(reverses_payment_id) "
               "WHERE reverses_payment_id IS NOT NULL")
    out.append("CREATE UNIQUE INDEX IF NOT EXISTS uq_treatment_payments_reverses ON treatment_payments(reverses_payment_id) "
               "WHERE reverses_payment_id IS NOT NULL")
    # 4. Lookup speed for get-or-create customer by name.
    out.append("CREATE INDEX IF NOT EXISTS idx_customers_business_name ON customers(business_id, name)")
    # 5. Integrity CHECK constraints (NOT VALID: new writes only).
    for name, table, expr in CHECKS:
        out.append(_add_check_sql(name, table, expr))
    return out


HEADER = """\
-- Phase 5B-3 — Financial integrity, transaction safety & data protection.
--
-- You do NOT need to run this by hand: the app runs exactly these statements
-- automatically (models.create_tables) every time it starts. It is provided so
-- you can read it, review it, or run it yourself in the Supabase SQL editor.
--
-- GENERATED from schema_5b3.py (a test checks the two never drift apart).
--
-- Safety
--   * Additive only. Nothing is dropped, renamed, deleted, reset or rewritten.
--   * Safe to run any number of times (IF NOT EXISTS everywhere).
--   * New columns are nullable; every existing row keeps NULL and is untouched.
--   * CHECK constraints are added NOT VALID: enforced for new writes only;
--     existing rows are not scanned, changed or rejected.
--   * Existing sales, payments, customers, balances, treatments, stock
--     movements and bad-debt records are NOT modified by this migration.
--
-- OPTIONAL PRE-FLIGHT (read-only). Every query below should return 0. A non-zero
-- count means an OLD row already breaks a rule; the migration still succeeds and
-- changes nothing, but later edits to THAT row would be refused until it is
-- looked at. (The app's own "Check my records for problems" button reports these.)
--
--   SELECT COUNT(*) FROM products WHERE current_stock < 0;
--   SELECT COUNT(*) FROM sales    WHERE amount_paid > total_amount OR amount_paid < 0;
--   SELECT COUNT(*) FROM payments WHERE amount <= 0;
--   SELECT COUNT(*) FROM treatment_payments WHERE amount <= 0;
--   SELECT COUNT(*) FROM treatments WHERE amount_paid < 0;
--   SELECT COUNT(*) FROM inventory_movements
--    WHERE quantity_after < 0
--       OR (movement_type IN ('purchase','adjustment_in','adjustment_out','damaged','expired','cost_set')
--           AND (note IS NULL OR btrim(note) = ''));
"""


def render_sql():
    body = ";\n\n".join(statements()) + ";\n"
    return HEADER + "\n" + body


if __name__ == "__main__":
    import sys
    sys.stdout.write(render_sql())
