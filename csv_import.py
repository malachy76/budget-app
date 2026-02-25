# csv_import.py
import re
import pandas as pd
import streamlit as st

def _guess_expense_table(conn):
    """Try to find an expenses-like table without crashing."""
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]

    # Common names
    candidates = ["expenses", "expense", "transactions", "expense_list", "spending"]
    for c in candidates:
        if c in tables:
            return c

    # Fallback: find any table that has amount + description-ish columns
    for t in tables:
        try:
            cols = [r[1].lower() for r in cur.execute(f"PRAGMA table_info({t})").fetchall()]
            if any(x in cols for x in ["amount", "amt", "value"]) and any(x in cols for x in ["description", "narration", "remark", "details"]):
                return t
        except Exception:
            continue

    return None

def _get_table_columns(conn, table):
    cur = conn.cursor()
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    # rows: cid, name, type, notnull, dflt_value, pk
    return [r[1] for r in rows]

def _clean_amount(x):
    if pd.isna(x):
        return None
    s = str(x)
    s = s.replace(",", "")
    # keep digits, dot, minus
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
    try:
        dt = pd.to_datetime(x, errors="coerce", dayfirst=True)
        if pd.isna(dt):
            return None
        # store as ISO date string (safe for SQLite)
        return dt.date().isoformat()
    except Exception:
        return None

def csv_import_page(conn, user_id: int):
    """
    Safe CSV import page:
    - Lets user upload a CSV
    - Shows preview
    - Lets user map CSV columns to DB columns
    - Inserts into your expenses-like table if compatible
    """
    st.header("📥 Import Bank Statement (CSV)")
    st.caption("Upload a CSV bank statement, map the columns, preview, then import into your expenses list.")

    table = _guess_expense_table(conn)
    if not table:
        st.error("I couldn't find an expenses/transactions table in your database. "
                 "Common names: expenses, expense, transactions.")
        st.stop()

    cols = _get_table_columns(conn, table)
    cols_lower = [c.lower() for c in cols]

  st.info(f"Import target: **{table}**")

# Show a cleaner, user-friendly table instead of raw list
friendly = []
for c in cols:
    cl = c.lower()
    if cl == "id":
        purpose = "Auto ID (internal)"
    elif cl == "user_id":
        purpose = "User owner (internal)"
    elif cl == "bank_id":
        purpose = "Linked bank (optional)"
    elif cl in ["name", "expense_name"]:
        purpose = "Expense name"
    elif cl in ["amount", "amt", "value"]:
        purpose = "Amount spent"
    elif cl in ["created_at", "date", "expense_date", "transaction_date"]:
        purpose = "Date"
    else:
        purpose = "Other"
    friendly.append({"Column": c, "Meaning": purpose})

st.markdown("**Detected fields (user-relevant):**")
user_fields = [x for x in friendly if x["Column"].lower() not in ["id", "user_id", "bank_id"]]
st.dataframe(pd.DataFrame(user_fields), use_container_width=True, hide_index=True)

    file = st.file_uploader("Upload CSV", type=["csv"])
    if not file:
        st.stop()

    # Read CSV safely
    try:
        df = pd.read_csv(file)
    except UnicodeDecodeError:
        file.seek(0)
        df = pd.read_csv(file, encoding="latin-1")
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
        st.stop()

    if df.empty:
        st.warning("CSV is empty.")
        st.stop()

    st.subheader("Preview")
    st.dataframe(df.head(20), use_container_width=True)

    st.subheader("Map columns")
    csv_cols = list(df.columns)

    def pick(label, default_keywords):
        default = None
        for c in csv_cols:
            cl = c.lower()
            if any(k in cl for k in default_keywords):
                default = c
                break
        return st.selectbox(label, ["(none)"] + csv_cols, index=(0 if default is None else (1 + csv_cols.index(default))))

    amount_col = pick("Amount column", ["amount", "amt", "value", "debit", "withdraw", "dr"])
    date_col = pick("Date column", ["date", "time", "transaction date", "posted", "value date"])
    desc_col = pick("Description / Narration / Remark column", ["description", "narration", "remark", "details", "merchant", "info"])
    category_col = pick("Category column (optional)", ["category", "cat", "type"])

    st.markdown("---")
    st.subheader("Import options")

    # Detect likely DB column names (we will insert only into columns that exist)
    db_amount = next((c for c in cols if c.lower() in ["amount", "amt", "value"]), None)
    db_date = next((c for c in cols if c.lower() in ["date", "expense_date", "created_at", "transaction_date", "trans_date"]), None)
    db_desc = next((c for c in cols if c.lower() in ["description", "narration", "remark", "details", "note", "merchant"]), None)
    db_cat = next((c for c in cols if c.lower() in ["category", "cat"]), None)
    db_user = next((c for c in cols if c.lower() in ["user_id", "userid", "owner_id"]), None)

    # Show what we will target
    st.write("**Database target mapping (auto-detected):**")
    st.write({
        "table": table,
        "amount_column": db_amount,
        "date_column": db_date,
        "description_column": db_desc,
        "category_column": db_cat,
        "user_id_column": db_user
    })

    # Hard safety checks: must have amount + user_id at least
    if not db_amount or not db_user:
        st.error("Your expenses table must have at least **amount** and **user_id** columns for safe import.")
        st.stop()

    if amount_col == "(none)" or desc_col == "(none)":
        st.warning("Please map at least **Amount** and **Description** columns.")
        st.stop()

    # Build import dataframe
    working = pd.DataFrame()
    working["amount"] = df[amount_col].apply(_clean_amount)
    working["description"] = df[desc_col].apply(_clean_text)

    if date_col != "(none)" and db_date:
        working["date"] = df[date_col].apply(_clean_date)
    else:
        working["date"] = None

    if category_col != "(none)" and db_cat:
        working["category"] = df[category_col].apply(_clean_text)
    else:
        working["category"] = None

    # Remove invalid rows (no amount)
    before = len(working)
    working = working[working["amount"].notna()]
    dropped = before - len(working)

    st.write(f"Rows ready to import: **{len(working)}** (dropped **{dropped}** rows with invalid amount)")

    st.subheader("Preview import rows")
    st.dataframe(working.head(20), use_container_width=True)

    # Prepare insert statement for only columns that exist
    insert_cols = [db_user, db_amount]
    insert_vals = ["user_id", "amount"]

    if db_desc:
        insert_cols.append(db_desc)
        insert_vals.append("description")

    if db_date:
        insert_cols.append(db_date)
        insert_vals.append("date")

    if db_cat:
        insert_cols.append(db_cat)
        insert_vals.append("category")

    placeholders = ",".join(["?"] * len(insert_cols))
    col_sql = ",".join(insert_cols)
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"

    # Build rows
    rows = []
    for _, r in working.iterrows():
        row = []
        for key in insert_vals:
            if key == "user_id":
                row.append(int(user_id))
            else:
                row.append(r.get(key))
        rows.append(tuple(row))

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        do_import = st.button("✅ Import into Expenses", use_container_width=True)
    with col2:
        st.caption("Tip: Try with a small CSV first.")

    if do_import:
        try:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            conn.commit()
            st.success(f"Imported **{len(rows)}** rows into **{table}** successfully.")
        except Exception as e:
            st.error("Import failed safely (no crash).")
            st.exception(e)
            st.stop()
