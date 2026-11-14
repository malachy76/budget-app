# integrity.py — Phase 5B-3: shared helpers for financial integrity
#
# Three small, dependency-light tools used by sales / customers / treatments /
# inventory (and the Personal Mode expense saver):
#
#   1. IDEMPOTENCY. A "submission reference" (idempotency key) is generated
#      once per form and sent with every attempt. The database remembers it
#      (a nullable column + partial UNIQUE index on the money-moving row), so
#      sending the same reference twice — double-click, Streamlit rerun, a
#      retry after a timeout whose COMMIT actually succeeded — returns the
#      ORIGINAL result instead of recording a second sale / payment / delivery.
#      Nothing here relies on button state or st.session_state.
#
#   2. SAME-KEY SERIALISATION. lock_key() takes a transaction-scoped Postgres
#      advisory lock on (business, scope, key) so two *simultaneous* attempts
#      with the same reference queue up: the second one waits for the first to
#      commit and then sees its row (=> replay) instead of racing it.
#
#   3. FRIENDLY ERRORS. Database constraint violations are translated into
#      sentences a shop owner can act on, instead of raw psycopg2 text.
#
# This module never opens its own connection; every helper works on the cursor
# of the caller's transaction so it commits / rolls back with the real work.

import psycopg2.errors

MAX_KEY_LEN = 100

REPLAY_NOTE = "already recorded \u2014 it was not recorded a second time"


class IdempotencyConflict(Exception):
    """The same submission reference was reused for a DIFFERENT operation."""
    pass


def clean_key(key):
    """Normalise an optional submission reference. Returns None when no
    reference was supplied (legacy callers keep working, unprotected by key
    but still protected by every other check). Raises ValueError if absurd."""
    key = (key or "").strip()
    if not key:
        return None
    if len(key) > MAX_KEY_LEN:
        raise ValueError("Submission reference is too long. Please reopen the form and try again.")
    return key


def lock_key(cursor, business_id, scope, key):
    """Serialise concurrent submissions that share (business, scope, key).
    Transaction-scoped: released automatically at COMMIT / ROLLBACK."""
    if key is None:
        return
    cursor.execute(
        "SELECT pg_advisory_xact_lock(%s, hashtext(%s))",
        (int(business_id), f"{scope}:{key}"),
    )


def lock_name(cursor, business_id, scope, name):
    """Advisory lock for get-or-create style operations (e.g. customer by
    name) where no unique index exists on legacy data to arbitrate a race."""
    cursor.execute(
        "SELECT pg_advisory_xact_lock(%s, hashtext(%s))",
        (int(business_id), f"{scope}:{name}"),
    )


def friendly_db_error(e):
    """Turn a database exception into a message a user can act on."""
    if isinstance(e, psycopg2.errors.UniqueViolation):
        return "This was already recorded \u2014 it has not been recorded twice."
    if isinstance(e, psycopg2.errors.CheckViolation):
        name = getattr(getattr(e, "diag", None), "constraint_name", "") or ""
        if "stock" in name:
            return "Not enough stock \u2014 this would make the quantity negative."
        return "The database rejected these figures as invalid. Nothing was recorded."
    if isinstance(e, psycopg2.errors.ForeignKeyViolation):
        return "A record this depends on no longer exists. Nothing was recorded."
    if isinstance(e, (psycopg2.errors.SerializationFailure, psycopg2.errors.DeadlockDetected)):
        return "The system was busy with another update. Nothing was recorded \u2014 please try again."
    return str(e)
