# db.py — rock-solid connection pool that never logs users out on transient errors
import streamlit as st
import psycopg2
import psycopg2.pool
import psycopg2.extras
from contextlib import contextmanager


# ── Pool factory ──────────────────────────────────────────────────────────────

def _make_pool():
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,          # Supabase free tier handles this comfortably
        dsn=st.secrets["SUPABASE_DB_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=10,  # fail fast on dead connections instead of hanging
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


@st.cache_resource
def _pool_container():
    """
    Single mutable dict kept alive across ALL reruns and ALL users by
    st.cache_resource. We mutate the dict in-place to swap pools without
    losing the cache handle. Never call _pool_container.clear() — that
    would destroy the dict reference and force a cold restart.
    """
    return {"pool": _make_pool()}


def _get_pool():
    c = _pool_container()
    if c["pool"] is None:
        c["pool"] = _make_pool()
    return c["pool"]


def _reset_pool():
    """
    Replace the broken pool with a fresh one.
    Safe to call from any thread — worst case we create two pools briefly.
    """
    container = _pool_container()
    old = container.get("pool")
    if old is not None:
        try:
            old.closeall()
        except Exception:
            pass
    try:
        container["pool"] = _make_pool()
    except Exception:
        container["pool"] = None  # will retry on next _get_pool call
        raise


# ── Public API ────────────────────────────────────────────────────────────────

def get_connection():
    """
    Borrow a raw connection from the pool.
    The returned object's .close() safely returns it to the pool (never destroys it).
    Retries once on pool exhaustion by resetting the pool.
    """
    for attempt in range(2):
        try:
            pool = _get_pool()
            raw  = pool.getconn()

            class _PooledConn:
                """Thin proxy: .close() → putconn so the slot is always returned."""
                def __getattr__(self, name):
                    return getattr(raw, name)
                def close(self):
                    try:
                        _get_pool().putconn(raw)
                    except Exception:
                        pass
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    self.close()

            return _PooledConn()

        except psycopg2.pool.PoolError:
            if attempt == 0:
                _reset_pool()
            else:
                raise
        except Exception:
            if attempt == 0:
                _reset_pool()
            else:
                raise


def _return_connection(conn, error: bool = False) -> None:
    try:
        _get_pool().putconn(conn, close=error)
    except Exception:
        pass


@contextmanager
def get_db():
    """
    Yield (conn, cursor). Commits on clean exit, rolls back on exception.
    Always returns the connection to the pool — never closes/destroys it.
    Retries once on pool exhaustion or stale connection by resetting the pool.

    IMPORTANT: exceptions are always re-raised so callers can handle them.
    We never silently swallow errors here.
    """
    conn = None
    for attempt in range(2):
        try:
            conn = _get_pool().getconn()
            # Test if connection is still alive (catches stale Supabase connections)
            conn.reset()
            break
        except psycopg2.pool.PoolError:
            if attempt == 0:
                _reset_pool()
            else:
                raise
        except Exception:
            # Stale / broken connection — return it and reset the pool
            if conn is not None:
                try:
                    _return_connection(conn, error=True)
                except Exception:
                    pass
                conn = None
            if attempt == 0:
                _reset_pool()
            else:
                raise

    if conn is None:
        raise RuntimeError("Could not obtain a database connection after reset.")

    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        _return_connection(conn, error=True)
        raise
    else:
        _return_connection(conn, error=False)
