# csv_import.py
import re
import pandas as pd
import streamlit as st


def _guess_expense_table(conn):
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]

    for name in ["expenses", "expense", "transactions", "expense_list", "spending"]:
        if name in tables:
            return name

    # fallback: find any table that has amount + description-ish columns
    for t in tables:
        try:
            cols = [r[1].lower() for r in cur.execute(f"PRAGMA table_info({t})").fetchall()]
            has_amount = any(x in cols for x in ["amount", "amt", "value"])
            has_desc = any(x in cols for x in ["description", "narration", "remark", "details", "name"])
            if has_amount and has_desc:
                return t
        except Exception:
            continue

    return None


def _get_table_columns(conn, table):
    cur = conn.cursor()
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _clean_amount(x):
    if pd.isna(x):
        return None
    s = str(x).replace(",", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s.strip() == "":
        return None
    try:
        return float(s)
    except Exception:
        return None


def _clean_text(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def _clean_date(x):
    if pd.isna(x):
        return None
    dt = pd.to_datetime(x, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return None
    return dt.date().isoformat()


def csv_import_page(conn, user_id: int):
    st.header("📥 Import Bank Statement (CSV)")
    st.caption("Upload a CSV statement, map columns, preview, then import safely.")

    table = _guess_expense_table(conn)
    if not table:
        st.error("I couldn't find an expenses-like table (e.g. 'expenses' or 'transactions').")
        return

    cols = _get_table_columns(conn, table)

    # Clean UI display (no raw list)
    st.info(f"Import target: **{table}**")
    friendly = []
    for c in cols:
        cl = c.lower()
        if cl == "id":
            meaning = "Auto ID (internal)"
        elif cl == "user_id":
            meaning = "User owner (internal)"
        elif cl == "bank_id":
            meaning = "Linked bank (optional)"
        elif cl in ["name", "expense_name", "description", "narration", "remark", "details"]:
            meaning = "Expense name / description"
        elif cl in ["amount", "amt", "value"]:
            meaning = "Amount spent"
        elif cl in ["created_at", "date", "expense_date", "transaction_date"]:
            meaning = "Date"
        else:
            meaning = "Other"
        friendly.append({"Column": c, "Meaning": meaning})

    st.markdown("**Detected fields:**")
    st.dataframe(pd.DataFrame(friendly), use_container_width=True, hide_index=True)

    file = st.file_uploader("Upload CSV", type=["csv"])
    if not file:
        return

    # Read CSV safely
    try:
        df = pd.read_csv(file)
    except UnicodeDecodeError:
        file.seek(0)
        df = pd.read_csv(file, encoding="latin-1")
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
        return

    if df.empty:
        st.warning("CSV is empty.")
        return

    st.subheader("Preview")
    st.dataframe(df.head(20), use_container_width=True)

    st.subheader("Map columns")
    csv_cols = list(df.columns)

    def pick(label, keywords):
        default = None
        for c in csv_cols:
            cl = c.lower()
            if any(k in cl for k in keywords):
                default = c
                break
        idx = 0 if default is None else 1 + csv_cols.index(default)
        return st.selectbox(label, ["(none)"] + csv_cols, index=idx)

    amount_col = pick("Amount column", ["amount", "amt", "value", "debit", "withdraw", "dr"])
    date_col = pick("Date column (optional)", ["date", "time", "transaction date", "value date", "posted"])
    desc_col = pick("Description/Remark column", ["description", "narration", "remark", "details", "merchant", "name"])

    # DB column detection
    cols_lower = [c.lower() for c in cols]
    db_amount = next((c for c in cols if c.lower() in ["amount", "amt", "value"]), None)
    db_desc = next((c for c in cols if c.lower() in ["name", "description", "narration", "remark", "details"]), None)
    db_date = next((c for c in cols if c.lower() in ["created_at", "date", "expense_date", "transaction_date"]), None)
    db_user = next((c for c in cols if c.lower() in ["user_id", "userid", "owner_id"]), None)

    if not db_amount or not db_user:
        st.error("Import needs the target table to have at least: user_id and amount.")
        return

    if amount_col == "(none)" or desc_col == "(none)":
        st.warning("Please map at least Amount and Description.")
        return

    # Build working import data
    working = pd.DataFrame()
    working["amount"] = df[amount_col].apply(_clean_amount)
    working["description"] = df[desc_col].apply(_clean_text)
    working["date"] = df[date_col].apply(_clean_date) if (date_col != "(none)" and db_date) else None

    before = len(working)
    working = working[working["amount"].notna()]
    dropped = before - len(working)

    st.write(f"Rows ready: **{len(working)}** (dropped **{dropped}** invalid amounts)")
    st.dataframe(working.head(20), use_container_width=True)

    # Prepare insert statement
    insert_cols = [db_user, db_amount]
    insert_vals = ["user_id", "amount"]

    if db_desc:
        insert_cols.append(db_desc)
        insert_vals.append("description")

    if db_date:
        insert_cols.append(db_date)
        insert_vals.append("date")

    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO {table} ({','.join(insert_cols)}) VALUES ({placeholders})"

    rows = []
    for _, r in working.iterrows():
        row = []
        for key in insert_vals:
            if key == "user_id":
                row.append(int(user_id))
            else:
                row.append(r.get(key))
        rows.append(tuple(row))

    if st.button("✅ Import into Expenses", use_container_width=True):
        try:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            conn.commit()
            st.success(f"Imported **{len(rows)}** rows into **{table}**.")
        except Exception as e:
            st.error("Import failed safely (no crash).")
            st.exception(e)
