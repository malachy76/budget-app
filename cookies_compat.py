# cookies_compat.py — v3
# -*- coding: utf-8 -*-
"""
Same public interface as before (ready / get / __setitem__ / save), so
nothing else in the app needs to change. The INTERNALS are a full rewrite.

WHY: v1 and v2 of this file used extra_streamlit_components.CookieManager
for both reading and writing cookies. That library requires every read to
round-trip through an async custom component in the browser, and we hit a
different race condition in that round-trip on every round of real-world
testing — a 1-day default expiry, a retry loop that caused
ERR_TOO_MANY_REDIRECTS on slow connections, and finally a case where the
cookie still wasn't reliably surviving a phone screen-lock/reboot cycle.
Four fixes, four new failure modes — the architecture itself was the
problem, not any one bug in it.

v3 instead:
  - READS use st.context.cookies — a native, read-only Streamlit API
    (available since 1.39) that returns exactly the cookies the browser
    sent with the CURRENT page request. It's just part of the HTTP
    request Streamlit already received — synchronous, always available
    from the first script run, nothing to wait for, nothing that can be
    "not ready yet".
  - WRITES still need to run JS in the browser, since Streamlit has no
    server-side way to send a Set-Cookie header. Instead of a stateful
    component that Python has to wait on and synchronize with, we fire
    a tiny one-shot `document.cookie = ...` snippet via
    st.components.v1.html(). There's no return value and nothing to
    synchronize, so there's nothing left to race against.

This also drops the `extra-streamlit-components` dependency entirely —
remove it from requirements.txt.
"""

import datetime
import json
import streamlit as st
import streamlit.components.v1 as components

# Keep in sync with auth.SESSION_EXPIRY_DAYS (currently 90) — this should
# stay at or above it so the cookie is never what logs someone out early.
# 400 days is also the hard cap modern browsers enforce on any cookie.
_COOKIE_LIFETIME_DAYS = 400


class CookieManagerCompat:
    def __init__(self, prefix="budget_right_"):
        self._prefix = prefix
        # Cookies the browser sent with THIS request. Already resolved —
        # no loading state, no async wait.
        self._cookies = dict(st.context.cookies)

    def ready(self):
        # st.context.cookies is synchronous from the very first run.
        return True

    def get(self, key, default=""):
        return self._cookies.get(self._prefix + key, default)

    def __setitem__(self, key, value):
        full_key = self._prefix + key
        # Keep our in-memory view consistent for any .get() calls later
        # in THIS SAME script run (e.g. right after login, before the
        # next real page load).
        if value:
            self._cookies[full_key] = value
        else:
            self._cookies.pop(full_key, None)
        self._write_cookie_js(full_key, value)

    def save(self):
        # Writes fire immediately in __setitem__ — nothing to flush.
        # Kept only so existing `cookies.save()` calls don't need to change.
        pass

    def _write_cookie_js(self, full_key, value):
        if value:
            expires = (
                datetime.datetime.utcnow() + datetime.timedelta(days=_COOKIE_LIFETIME_DAYS)
            ).strftime("%a, %d %b %Y %H:%M:%S GMT")
            cookie_str = f"{full_key}={value}; path=/; expires={expires}; SameSite=Lax; Secure"
        else:
            cookie_str = f"{full_key}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT"
        # json.dumps safely escapes the string for embedding in JS.
        # height=0 keeps this invisible — it's a fire-and-forget script,
        # not a visible widget.
        components.html(
            f"<script>document.cookie = {json.dumps(cookie_str)};</script>",
            height=0,
            width=0,
        )
