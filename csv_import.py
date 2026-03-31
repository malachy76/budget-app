# csv_import.py
import re
import pandas as pd
import streamlit as st
from datetime import datetime


# ── helpers ──────────────────────────────────────────────────────────────────

def _clean_amount(x):
    """Strip currency symbols / commas, return positive float or None."""
    if pd.isna(x):
        return None
    s = re.sub(r"[^0-9.\-]", "", str(x).replace(",", ""))
    if not s or s == "-":
        return None
    try:
        val = float(s)
        return abs(val) if val != 0 else None   # expenses are always positive
    except Exception:
        return None


def _clean_date(x):
    """Parse any date format -> 'YYYY-MM-DD' string, or today as fallback."""
    if pd.isna(x):
        return datetime.now().strftime("%Y-%m-%d")
    dt = pd.to_datetime(x, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return datetime.now().strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")


def _clean_text(x):
    if pd.isna(x):
        return "Imported expense"
    return str(x).strip() or "Imported expense"


# ── main page ─────────────────────────────────────────────────────────────────

def csv_import_page(conn, user_id: int):
    st.header("Import Bank Statement (CSV)")
    st.caption(
        "Upload your bank statement CSV, map the columns, pick the bank "
        "it belongs to, preview — then import. "
        "Each row becomes an expense + a debit transaction exactly "
        "like adding expenses manually."
    )

    # ── 1. Load user's banks ─────────────────────────────────────────────────
    cur = conn.cursor()
    cur.execute(
        "SELECT id, bank_name, account_number, balance FROM banks WHERE user_id = %s",
        (user_id,)
    )
    banks = cur.fetchall()

    if not banks:
        st.warning("You have no bank accounts yet. Add one on the Banks page first.")
        return

    bank_options = {
        f"{b['bank_name']} (****{b['account_number']}) - NGN {b['balance']:,}": b["id"]
        for b in banks
    }
    selected_bank_label = st.selectbox(
        "Which bank does this statement belong to?",
        list(bank_options.keys()),
        key="csv_bank_select"
    )
    bank_id = bank_options[selected_bank_label]

    st.divider()

    # ── 2. File upload ───────────────────────────────────────────────────────
    file = st.file_uploader("Upload CSV file", type=["csv"], key="csv_file")
    if not file:
        return

    try:
        df = pd.read_csv(file)
    except UnicodeDecodeError:
        file.seek(0)
        df = pd.read_csv(file, encoding="latin-1")
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
        return

    if df.empty:
        st.warning("The CSV file is empty.")
        return

    st.subheader("Preview (first 10 rows)")
    st.dataframe(df.head(10), use_container_width=True)

    # ── 3. Column mapping ────────────────────────────────────────────────────
    st.subheader("Map your columns")
    csv_cols = list(df.columns)

    def auto_pick(keywords):
        """Return index of first column whose name contains any keyword."""
        for i, c in enumerate(csv_cols):
            if any(k in c.lower() for k in keywords):
                return i + 1          # +1 because index 0 = "(none)"
        return 0

    amount_idx = auto_pick(["amount", "amt", "debit", "dr", "withdraw", "value"])
    date_idx   = auto_pick(["date", "time", "posted", "value date", "txn date"])
    desc_idx   = auto_pick(["description", "narration", "remark", "details",
                             "merchant", "particulars", "reference", "memo"])

    amount_col = st.selectbox(
        "Amount column *",
        ["(none)"] + csv_cols,
        index=amount_idx,
        key="csv_amount_col"
    )
    date_col = st.selectbox(
        "Date column (optional — today used if blank)",
        ["(none)"] + csv_cols,
        index=date_idx,
        key="csv_date_col"
    )
    desc_col = st.selectbox(
        "Description / Narration column *",
        ["(none)"] + csv_cols,
        index=desc_idx,
        key="csv_desc_col"
    )

    if amount_col == "(none)" or desc_col == "(none)":
        st.info("Please map at least the Amount and Description columns to continue.")
        return

    # ── 4. Build preview data ────────────────────────────────────────────────
    working = pd.DataFrame()
    working["amount"]      = df[amount_col].apply(_clean_amount)
    working["description"] = df[desc_col].apply(_clean_text)
    working["date"]        = (
        df[date_col].apply(_clean_date)
        if date_col != "(none)"
        else datetime.now().strftime("%Y-%m-%d")
    )

    # Drop rows with no valid amount
    before  = len(working)
    working = working[working["amount"].notna()].reset_index(drop=True)
    dropped = before - len(working)

    if working.empty:
        st.error("No rows with a valid amount found. Check your Amount column mapping.")
        return

    st.divider()
    st.subheader(f"Ready to import — {len(working)} rows")
    if dropped:
        st.caption(f"({dropped} rows skipped — no valid amount)")

    st.dataframe(
        working[["date", "description", "amount"]].rename(columns={
            "date": "Date", "description": "Description", "amount": "Amount (NGN)"
        }),
        use_container_width=True
    )

    total = working["amount"].sum()
    st.markdown(f"**Total debit: NGN {total:,.2f}**")

    # ── 5. Bank balance check ────────────────────────────────────────────────
    cur.execute("SELECT balance FROM banks WHERE id = %s", (bank_id,))
    row = cur.fetchone()
    current_balance = row["balance"] if row else 0

    if total > current_balance:
        st.warning(
            f"Total import (NGN {total:,.0f}) exceeds current bank balance "
            f"(NGN {current_balance:,.0f}). Import will still work but balance "
            f"will go negative."
        )

    # ── 6. Import button ─────────────────────────────────────────────────────
    if st.button("Import All into Expenses", use_container_width=True, key="csv_import_btn"):
        imported = 0
        errors   = 0
        try:
            for _, row in working.iterrows():
                amt  = int(round(row["amount"]))
                desc = row["description"]
                date = row["date"]

                # — Insert transaction FIRST, use RETURNING id (PostgreSQL syntax) —
                cur.execute("""
                    INSERT INTO transactions (bank_id, type, amount, description, created_at)
                    VALUES (%s, 'debit', %s, %s, %s)
                    RETURNING id
                """, (bank_id, amt, f"Expense: {desc}", date))
                tx_id = cur.fetchone()["id"]  # replaces SQLite's lastrowid

                # — Insert expense with tx_id linked —
                cur.execute("""
                    INSERT INTO expenses (user_id, bank_id, name, amount, created_at, tx_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, bank_id, desc, amt, date, tx_id))

                # — Debit the bank balance —
                cur.execute(
                    "UPDATE banks SET balance = balance - %s WHERE id = %s",
                    (amt, bank_id)
                )
                imported += 1

            conn.commit()
            st.success(f"Imported {imported} expenses successfully!")
            st.caption(
                "All rows are now visible on the Expenses page and the "
                "Dashboard charts. Your bank balance has been updated."
            )

        except Exception as e:
            conn.rollback()
            st.error(f"Import failed — no data was changed. Error: {e}")
