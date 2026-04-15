# db.py — database connection with connection pooling
# Uses a ThreadedConnectionPool so connections are reused across reruns
# instead of opening a new TCP handshake to Supabase on every get_db() call.
import streamlit as st
import psycopg2
import psycopg2.pool
import psycopg2.extras
from contextlib import contextmanager

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the singleton pool, creating it on first call."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=5,          # Supabase free tier: max 15 direct / 200 pooler
            dsn=st.secrets["SUPABASE_DB_URL"],
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _pool


def get_connection():
    """Get a raw connection from the pool (caller must return it)."""
    return _get_pool().getconn()


def _return_connection(conn, error: bool = False) -> None:
    try:
        _get_pool().putconn(conn, close=error)
    except Exception:
        pass


@contextmanager
def get_db():
    """
    Context manager that yields (conn, cursor).
    Commits on success, rolls back on exception.
    Connection is returned to the pool (not closed) when the block exits.
    """
    pool = _get_pool()
    conn = pool.getconn()
    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        _return_connection(conn, error=True)
        raise
    else:
        _return_connection(conn, error=False)
