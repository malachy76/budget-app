# ui_idempotency.py — Phase 5B-3: one submission reference per form
#
# A form asks for its reference with get_key("scope"). The reference stays the
# same for every attempt of that form (double-click, rerun, retry after a
# timeout) and is dropped with clear_key("scope") only after the operation
# succeeded, so the NEXT submission gets a fresh one. The reference is sent to
# the backend, whose DATABASE remembers it — this module only keeps the string;
# it is not what prevents the duplicate.
import uuid

import streamlit as st


def get_key(scope):
    name = f"_idem_{scope}"
    if name not in st.session_state:
        st.session_state[name] = uuid.uuid4().hex
    return st.session_state[name]


def clear_key(scope):
    st.session_state.pop(f"_idem_{scope}", None)
