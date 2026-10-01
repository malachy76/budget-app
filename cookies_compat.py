# cookies_compat.py
# -*- coding: utf-8 -*-
"""
Drop-in replacement for the unmaintained `streamlit_cookies_manager`
(EncryptedCookieManager), backed by the actively-maintained
`extra_streamlit_components.CookieManager`.

Exposes the same surface the rest of the app already uses:
    cookies.ready()
    cookies.get(key, default)
    cookies[key] = value
    cookies.save()

SECURITY NOTE: EncryptedCookieManager encrypted the cookie value at rest.
CookieManager does not. The only value ever stored through this wrapper is
the random session token minted in auth.create_session_token() (a 48-byte
secrets.token_urlsafe value) — it is already opaque and unguessable, and it
is already treated as a bearer credential sent over HTTPS, so dropping
client-side encryption does not expose anything new. Do not start storing
other values (emails, user IDs, etc.) through this wrapper without adding
encryption back.

TIMING NOTE: CookieManager writes cookies via a browser-side JS component,
so a value set with `cookies[key] = value` is not guaranteed to be readable
via `cookies.get()` on the very next rerun (there can be a one-cycle lag
while the component round-trips to the browser). app.py's session-restore
logic accounts for this by checking st.session_state.session_token first,
before falling back to the cookie — see the restore block in app.py.
"""

import time
import streamlit as st
import extra_streamlit_components as stx

# How many times to give the cookie component the benefit of the doubt
# when it reports "no cookies" before we trust that result. This matters
# right after a server reboot: the browser reconnects and the component
# can report an empty result for a run or two before it actually finishes
# reading the real cookies, which would otherwise look exactly like the
# user being logged out.
_MAX_EMPTY_RETRIES = 4
_RETRY_DELAY_SECONDS = 0.2


class CookieManagerCompat:
    def __init__(self, prefix="budget_right_"):
        self._prefix = prefix
        self._cm = stx.CookieManager(key="budget_right_cookie_manager")
        # get_all() can return None for one render cycle while the
        # component's JS is still loading in the browser. Streamlit
        # automatically triggers a rerun once it resolves.
        self._cookies = self._cm.get_all()

    def ready(self):
        if self._cookies:
            # Got real data back — definitely ready. Remember this for the
            # rest of the browser session so a later legitimate empty read
            # (e.g. the user genuinely has no session cookie) is trusted
            # immediately instead of re-running the retry loop below.
            st.session_state["_cookies_seen_data"] = True
            return True
        if self._cookies is None:
            # Component hasn't returned anything at all yet — definitely
            # not ready. Streamlit will auto-rerun once it does.
            return False
        # self._cookies == {}: ambiguous. Could be a genuinely new visitor
        # with no cookies, or the component reporting in before it has
        # actually finished syncing from the browser (common right after a
        # reboot). If we've already seen real data this session, trust it.
        if st.session_state.get("_cookies_seen_data"):
            return True
        tries = st.session_state.get("_cookies_ready_retries", 0)
        if tries < _MAX_EMPTY_RETRIES:
            st.session_state["_cookies_ready_retries"] = tries + 1
            time.sleep(_RETRY_DELAY_SECONDS)
            st.rerun()
        # Retries exhausted — trust the empty result and move on.
        return True

    def get(self, key, default=""):
        if not self._cookies:
            return default
        return self._cookies.get(self._prefix + key, default)

    def __setitem__(self, key, value):
        full_key = self._prefix + key
        if value:
            self._cm.set(full_key, value, key=f"set_{full_key}")
        else:
            try:
                self._cm.delete(full_key, key=f"del_{full_key}")
            except KeyError:
                # Cookie was already absent — nothing to clear.
                pass

    def save(self):
        # extra_streamlit_components writes through immediately on
        # set()/delete(), so there's nothing to flush. Kept only so the
        # existing `cookies.save()` calls in auth.py don't need to change.
        pass
