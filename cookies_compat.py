# cookies_compat.py
# -*- coding: utf-8 -*-
"""Compatibility wrapper for persistent browser cookies in Budget Right.

Keeps the small interface used by app.py, auth.py, and landing.py while
using a real Streamlit cookie component to read/write cookies in the browser.
Do not use st.components.v1.html() to write document.cookie: that script runs
in an embedded frame and may not update the cookies sent with the main page.
"""

import datetime
import extra_streamlit_components as stx

_COOKIE_LIFETIME_DAYS = 400


class CookieManagerCompat:
    """Small adapter preserving the existing cookies.get/set/save interface."""

    def __init__(self, prefix="budget_right_"):
        self._prefix = prefix
        # A stable key is important: changing it on each rerun would reset the
        # component and make browser cookie reads unreliable.
        self._manager = stx.CookieManager(key="budget_right_cookie_manager")
        try:
            values = self._manager.get_all()
            self._cookies = dict(values or {})
        except Exception:
            # Do not crash the whole app if the component has not returned its
            # initial value yet. The next Streamlit rerun can load it again.
            self._cookies = {}

    def ready(self):
        # CookieManager is a bidirectional Streamlit component. It returns its
        # current browser values through get_all(); no separate save phase is
        # needed for reads. Keep this method for app.py compatibility.
        return True

    def get(self, key, default=""):
        value = self._cookies.get(self._prefix + key, default)
        return default if value is None else value

    def __setitem__(self, key, value):
        full_key = self._prefix + key
        if value is None or value == "":
            self._cookies.pop(full_key, None)
            # Delete the browser cookie using the component's supported API.
            try:
                self._manager.delete(full_key)
            except Exception:
                # Fall back to an expired cookie if this component version
                # exposes set/delete differently. Do not fail authentication.
                self._manager.set(
                    full_key, "",
                    expires_at=datetime.datetime.now(datetime.timezone.utc)
                    - datetime.timedelta(days=1),
                )
            return

        value = str(value)
        self._cookies[full_key] = value
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            days=_COOKIE_LIFETIME_DAYS
        )
        self._manager.set(full_key, value, expires_at=expires_at)

    def save(self):
        # extra-streamlit-components persists changes as part of set/delete.
        # Retained because existing callers explicitly call cookies.save().
        return None
