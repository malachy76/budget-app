# import_csv.py — CSV import page
import streamlit as st

from db import get_db, get_connection
from csv_import import csv_import_page


def render_import_csv(user_id, pages):
    st.title("📥 Import Bank Statement (CSV)")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT COUNT(*) AS n FROM banks WHERE user_id=%s", (user_id,))
        csv_bank_count = cursor.fetchone()["n"]

    if csv_bank_count == 0:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:12px;padding:24px;text-align:center;color:#6b7f8e;margin:12px 0;">
          <div style="font-size:2rem;">&#x1F4E5;</div>
          <div style="font-weight:700;margin:6px 0 4px;color:#1a2e3b;">Add a bank account before importing</div>
          <div style="font-size:0.92rem;">
            Your CSV transactions need to be linked to a bank account.<br>
            Add your bank on the <strong>Banks</strong> page first, then come back to import.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Banks page", key="csv_goto_banks"):
            st.session_state.nav_radio = pages.index("Banks")
            st.rerun()
    else:
        with st.expander("How does CSV import work?", expanded=False):
            st.markdown("""
            1. **Download your bank statement** as a CSV from your bank's app or internet banking portal.
            2. **Upload it here** using the file uploader below.
            3. **Map the columns** — Budget Right auto-detects your bank format.
            4. **Preview and import** — every row becomes an expense and debits your bank balance.

            **Supported:** GTB, Access, Zenith, UBA, First Bank, Opay, Kuda, Moniepoint, and more.
            """)
        conn_csv = get_connection()
        try:
            csv_import_page(conn_csv, user_id)
        finally:
            conn_csv.close()
