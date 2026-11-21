# schema_5d.py — Phase 5D (Staff Accounts & Role-Based Permissions) database changes, as plain SQL.
#
# Pure data (no streamlit, no database access) so models.py, the tests and the
# migration-file generator can all import it.
#
# ADDITIVE and REPEATABLE only:
#   * two NEW columns on users (ADD COLUMN IF NOT EXISTS, with a constant default,
#     so every existing user — every existing business owner — becomes
#     account_type = 'user', must_change_password = FALSE and nothing else changes)
#   * three NEW tables (CREATE TABLE IF NOT EXISTS)
#   * CREATE [UNIQUE] INDEX IF NOT EXISTS
#   * one CHECK constraint on users, added NOT VALID and only if absent (enforced for
#     new writes only; no existing row is scanned or changed)
#   * NEW functions + triggers: audit log append-only, and account-type guards
# No existing table, column, constraint or row is dropped, renamed, rewritten or reset.
# Nothing is back-filled: business OWNERS are never copied into the staff tables.
# An owner is, and stays, whoever businesses.owner_user_id says it is.
#
# users.account_type          'user' (everyone today, incl. all owners) or 'staff'
# users.must_change_password  forced password change on a staff member's next login
#
# business_members            one row per STAFF member: which business, role, status.
#                             UNIQUE(user_id): a staff login belongs to exactly ONE
#                             business. (A person who works for two owners gets two
#                             logins — this keeps "which business?" unambiguous.)
#                             'owner' is deliberately NOT an allowed role here.
# business_member_permissions the explicit permissions granted to that member. A role is
#                             only a starting template that is COPIED into these rows,
#                             so editing a template later never silently changes access.
#                             The composite foreign key guarantees a permission row can
#                             never point at a member of a different business.
# business_audit_log          who did what, when. Append-only: a trigger rejects every
#                             UPDATE, DELETE and TRUNCATE. It deliberately has NO foreign
#                             keys, so the history survives even if a business or user
#                             row is ever removed, and it stores a username / name
#                             snapshot of the actor. Never store passwords, PINs or
#                             secrets in it.
#
# Account-type guards (added in Batch 2; three NEW functions + three NEW triggers, additive):
#   a staff account can never own a business; only a staff account can be a business member and
#   never someone who already owns a business; a staff account's type can never change, and an
#   account that already owns a business can never be turned into a staff account.

STAFF_ROLES = ("manager", "cashier", "employee")      # 'owner' is never a membership row
ACCOUNT_TYPES = ("user", "staff")
MEMBER_STATUSES = ("active", "inactive")

_ROLE_LIST = ", ".join(f"'{r}'" for r in STAFF_ROLES)
_STATUS_LIST = ", ".join(f"'{s}'" for s in MEMBER_STATUSES)
_ACCOUNT_LIST = ", ".join(f"'{a}'" for a in ACCOUNT_TYPES)

# (constraint name, table, boolean expression) — added NOT VALID, only if absent.
CHECKS = (
    ("chk_users_account_type", "users", f"account_type IN ({_ACCOUNT_LIST})"),
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


_APPEND_ONLY_FUNCTION = """CREATE OR REPLACE FUNCTION business_audit_log_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'business_audit_log is append-only: % is not allowed', TG_OP
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql"""


def _add_trigger_sql(name, table, event_clause, level, function="business_audit_log_append_only"):
    return (
        "DO $$ BEGIN\n"
        f"  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = '{name}' "
        f"AND tgrelid = '{table}'::regclass) THEN\n"
        f"    CREATE TRIGGER {name} BEFORE {event_clause} ON {table} "
        f"FOR EACH {level} EXECUTE FUNCTION {function}();\n"
        "  END IF;\n"
        "END $$"
    )


# ── Account-type guards (Batch 2) ────────────────────────────────────────────
# Hard database guarantees behind the application checks:
#   * a STAFF account can never own a business (so a staff member can never become an owner);
#   * only a STAFF account can be a business member, and never someone who already owns a business
#     (so an existing owner can never be turned into staff);
#   * a staff account can never be changed back into an ordinary account, and an account that
#     already owns a business can never be changed into a staff account.
_GUARD_BUSINESS_OWNER_FUNCTION = """CREATE OR REPLACE FUNCTION guard_business_owner_not_staff() RETURNS trigger AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM users WHERE id = NEW.owner_user_id AND account_type = 'staff') THEN
    RAISE EXCEPTION 'A staff account cannot own a business.'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql"""

_GUARD_MEMBER_FUNCTION = """CREATE OR REPLACE FUNCTION guard_member_is_staff_not_owner() RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.user_id AND account_type = 'staff') THEN
    RAISE EXCEPTION 'Only a staff account can be a business member.'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF EXISTS (SELECT 1 FROM businesses WHERE owner_user_id = NEW.user_id) THEN
    RAISE EXCEPTION 'A business owner cannot be a staff member.'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql"""

_GUARD_ACCOUNT_TYPE_FUNCTION = """CREATE OR REPLACE FUNCTION guard_account_type_change() RETURNS trigger AS $$
BEGIN
  IF NEW.account_type IS DISTINCT FROM OLD.account_type THEN
    IF OLD.account_type = 'staff' THEN
      RAISE EXCEPTION 'A staff account cannot be changed into another account type.'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.account_type = 'staff' AND EXISTS (SELECT 1 FROM businesses WHERE owner_user_id = OLD.id) THEN
      RAISE EXCEPTION 'A business owner cannot be changed into a staff account.'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql"""


STATEMENTS = [
    # ── users: two additive columns (constant defaults => existing rows become a plain user)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_type TEXT NOT NULL DEFAULT 'user'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE",
    _add_check_sql(*CHECKS[0]),

    # ── staff membership
    f"""CREATE TABLE IF NOT EXISTS business_members ( id SERIAL PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, role TEXT NOT NULL, full_name TEXT NOT NULL, phone TEXT, status TEXT NOT NULL DEFAULT 'active', created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), deactivated_at TIMESTAMPTZ, deactivated_by INTEGER REFERENCES users(id) ON DELETE SET NULL, last_access_at TIMESTAMPTZ, CONSTRAINT uq_business_members_user UNIQUE (user_id), CONSTRAINT uq_business_members_id_business UNIQUE (id, business_id), CONSTRAINT chk_business_members_role CHECK (role IN ({_ROLE_LIST})), CONSTRAINT chk_business_members_status CHECK (status IN ({_STATUS_LIST})), CONSTRAINT chk_business_members_name CHECK (btrim(full_name) <> '') )""",

    # ── explicit permissions per member (composite FK => same business, always)
    """CREATE TABLE IF NOT EXISTS business_member_permissions ( id SERIAL PRIMARY KEY, member_id INTEGER NOT NULL, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, permission TEXT NOT NULL, granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL, granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT uq_member_permission UNIQUE (member_id, permission), CONSTRAINT fk_member_permission_member FOREIGN KEY (member_id, business_id) REFERENCES business_members (id, business_id) ON DELETE CASCADE, CONSTRAINT chk_member_permission_name CHECK (btrim(permission) <> '') )""",

    # ── append-only audit log (no foreign keys on purpose — see header)
    """CREATE TABLE IF NOT EXISTS business_audit_log ( id BIGSERIAL PRIMARY KEY, business_id INTEGER NOT NULL, actor_user_id INTEGER, actor_member_id INTEGER, actor_username TEXT NOT NULL, actor_name TEXT, actor_role TEXT NOT NULL, action TEXT NOT NULL, entity_type TEXT, entity_id BIGINT, reference TEXT, detail JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT chk_audit_action CHECK (btrim(action) <> ''), CONSTRAINT chk_audit_actor_role CHECK (btrim(actor_role) <> '') )""",

    _APPEND_ONLY_FUNCTION,
    _add_trigger_sql("trg_business_audit_log_no_update_delete", "business_audit_log", "UPDATE OR DELETE", "ROW"),
    _add_trigger_sql("trg_business_audit_log_no_truncate", "business_audit_log", "TRUNCATE", "STATEMENT"),

    # ── account-type guards (Batch 2)
    _GUARD_BUSINESS_OWNER_FUNCTION,
    _add_trigger_sql("trg_businesses_owner_not_staff", "businesses", "INSERT OR UPDATE OF owner_user_id", "ROW",
                     "guard_business_owner_not_staff"),
    _GUARD_MEMBER_FUNCTION,
    _add_trigger_sql("trg_business_members_staff_only", "business_members", "INSERT OR UPDATE OF user_id", "ROW",
                     "guard_member_is_staff_not_owner"),
    _GUARD_ACCOUNT_TYPE_FUNCTION,
    _add_trigger_sql("trg_users_account_type_guard", "users", "UPDATE OF account_type", "ROW",
                     "guard_account_type_change"),

    # ── indexes
    "CREATE INDEX IF NOT EXISTS idx_business_members_business ON business_members(business_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_member_permissions_member ON business_member_permissions(member_id)",
    "CREATE INDEX IF NOT EXISTS idx_member_permissions_business ON business_member_permissions(business_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_business_created ON business_audit_log(business_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_audit_business_actor ON business_audit_log(business_id, actor_user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_audit_business_action ON business_audit_log(business_id, action, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_audit_business_entity ON business_audit_log(business_id, entity_type, entity_id)",
]


def statements():
    return list(STATEMENTS)


HEADER = """\
-- Phase 5D — Staff Accounts & Role-Based Permissions.
--
-- You do NOT need to run this by hand: the app runs exactly these statements
-- automatically (models.create_tables) every time it starts. It is provided so you
-- can read it, review it, or run it yourself in the Supabase SQL editor.
--
-- GENERATED from schema_5d.py (a test checks the two never drift apart).
--
-- Safety
--  * Additive only: two new columns on users (constant defaults), three NEW tables,
--    some indexes, one CHECK (NOT VALID), an append-only trigger on the NEW audit table,
--    and three account-type guard triggers (a staff account can never own a business; an
--    owner can never become staff). Nothing existing is dropped, renamed, deleted or rewritten.
--  * Safe to run any number of times.
--  * Every existing user — including every business owner — becomes
--    account_type = 'user' and keeps exactly the access they have today. No owner is
--    copied into the staff tables; ownership still comes from businesses.owner_user_id.
--  * Until a staff member is created, no figure or screen in the app changes.
"""


def render_sql():
    return HEADER + "\n" + ";\n\n".join(statements()) + ";\n"


if __name__ == "__main__":
    import sys
    sys.stdout.write(render_sql())
