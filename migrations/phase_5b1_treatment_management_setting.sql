-- Phase 5B-1 — Treatment Management becomes a per-business setting.
--
-- You do NOT need to run this by hand: the app runs exactly this logic
-- automatically (models.create_tables) every time it starts. It is provided
-- so you can read it, review it, or run it yourself in the Supabase SQL editor.
--
-- What it does
--   1. Adds ONE new nullable column: businesses.treatment_management_enabled.
--      Nothing is dropped, renamed or deleted. Existing columns, rows,
--      IDs, sales, customers, treatments, payments and debts are untouched.
--   2. Fills the column ONLY for businesses that have no decision recorded yet
--      (NULL):
--        * ON  if the business is a Pharmacy, OR it already has treatment
--              records (so nobody loses access to their existing history);
--        * OFF for every other business.
--
-- Safe to run any number of times
--   * ADD COLUMN IF NOT EXISTS does nothing the second time.
--   * The UPDATE only touches rows that are still NULL, so it never
--     re-enables a feature an owner switched off and never overwrites an
--     owner's choice.
--
-- Backward compatible
--   * Old code that does not know the column keeps working (it is nullable).
--   * Reads treat NULL with the same rule as the backfill above.

BEGIN;

ALTER TABLE businesses
    ADD COLUMN IF NOT EXISTS treatment_management_enabled BOOLEAN;

UPDATE businesses b
SET treatment_management_enabled = (
    b.business_type = 'Pharmacy'
    OR EXISTS (SELECT 1 FROM treatments t WHERE t.business_id = b.id)
)
WHERE b.treatment_management_enabled IS NULL;

COMMIT;
