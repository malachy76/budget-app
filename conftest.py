# tests/conftest.py — runs the REAL application modules (db.py, models.py,
# sales.py, customers.py, treatments.py, baddebt.py ...) against a REAL
# throw-away PostgreSQL server started by `pgserver` (pip install pgserver).
# Only the `streamlit` import is stubbed (st.secrets + st.cache_resource),
# because these tests don't render any UI.
import os
import sys
import tempfile
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_server = None


def _install_streamlit_stub(uri):
    st = types.ModuleType("streamlit")

    def cache_resource(*args, **kwargs):
        def deco(fn):
            cache = {}

            def wrapper(*a, **k):
                if "v" not in cache:
                    cache["v"] = fn(*a, **k)
                return cache["v"]
            wrapper.clear = lambda: cache.clear()
            return wrapper
        if args and callable(args[0]):
            return deco(args[0])
        return deco

    st.cache_resource = cache_resource
    st.secrets = {"SUPABASE_DB_URL": uri}
    st.session_state = {}
    sys.modules["streamlit"] = st


def _start():
    global _server
    import pgserver
    d = tempfile.mkdtemp(prefix="br_pg_")
    _server = pgserver.get_server(d)
    _server.psql("ALTER DATABASE postgres SET timezone TO 'UTC';")
    _install_streamlit_stub(_server.get_uri())


# Must happen at import time: test modules import the app (which imports
# streamlit and db) during collection, before any fixture runs.
_start()


@pytest.fixture(scope="session", autouse=True)
def database():
    import models
    models.create_tables()          # exercises every migration on an EMPTY db
    models.create_tables.clear()
    models.create_tables()          # ...and again: all migrations are idempotent
    yield
    _server.cleanup()
