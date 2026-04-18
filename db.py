# db.py — database connection with persistent connection pooling
# Uses st.cache_resource so the pool truly persists across Streamlit reruns
# (module-level globals can be reset by Streamlit's module reloader).
import streamlit as st
import psycopg2
import psycopg2.pool
import psycopg2.extras
from contextlib import contextmanager


@st.cache_resource
def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """
    Create the connection pool once per server process.
    st.cache_resource keeps it alive across all reruns and all users
    — far more reliable than a module-level global on Streamlit Cloud.
    """
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=8,           # Supabase free tier: 15 direct / 200 pooler
        dsn=st.secrets["SUPABASE_DB_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


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
    Yield (conn, cursor).  Commits on success, rolls back on exception.
    Returns the connection to the pool — never closes it.
    Multiple get_db() calls within one request reuse the same pool slot.
    """
    conn   = _get_pool().getconn()
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
