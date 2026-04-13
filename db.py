# db.py — database connection and context manager
import streamlit as st
import psycopg2
import psycopg2.extras
from contextlib import contextmanager


def get_connection():
    return psycopg2.connect(
        st.secrets["SUPABASE_DB_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor
    )


@contextmanager
def get_db():
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
