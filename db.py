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
        maxconn=5,           # Conservative: prevents pool exhaustion on Streamlit Cloud
        dsn=st.secrets["SUPABASE_DB_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def get_connection():
    """Get a raw connection from the pool wrapped so .close() returns it safely."""
    pool = _get_pool()
    raw  = pool.getconn()

    class _PooledConn:
        """Routes .close() to putconn so the pool slot is never permanently lost."""
        def __getattr__(self, name):
            return getattr(raw, name)
        def close(self):
            try:
                pool.putconn(raw)
            except Exception:
                pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.close()

    return _PooledConn()


def _return_connection(conn, error: bool = False) -> None:
    try:
        _get_pool().putconn(conn, close=error)
    except Exception:
        pass


@contextmanager
def get_db():
    """
    Yield (conn, cursor). Commits on success, rolls back on exception.
    Returns the connection to the pool. Auto-resets pool on exhaustion.
    """
    from psycopg2.pool import PoolError
    try:
        conn = _get_pool().getconn()
    except PoolError:
        # Pool exhausted — clear the cache so a fresh pool is created next call
        _get_pool.clear()
        conn = _get_pool().getconn()
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
