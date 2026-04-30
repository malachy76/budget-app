# csv_import.py
# -*- coding: utf-8 -*-
"""
Safe CSV bank-statement importer for Budget Right.
Fixes: fingerprint date mismatch, overdraft silent block, mobile UI.
"""

import re
import hashlib
import pandas as pd
import streamlit as st
from datetime import datetime, date

BANK_FORMATS = {
    "GTB (Guaranty Trust Bank)": {
        "amount_cols":   ["debit", "withdrawal", "dr"],
        "date_cols":     ["date", "value date", "transaction date"],
        "desc_cols":     ["description", "narration", "details", "remarks"],
        "credit_cols":   ["credit", "deposit", "cr"],
        "skip_keywords": ["opening balance", "closing balance", "brought forward"],
    },
    "Access Bank": {
        "amount_cols":   ["debit amount", "debit", "withdrawal", "amount"],
        "date_cols":     ["transaction date", "date", "value date"],
        "desc_cols":     ["transaction details", "description", "narration"],
        "credit_cols":   ["credit amount", "credit"],
        "skip_keywords": ["balance b/f", "opening", "total"],
    },
    "Zenith Bank": {
        "amount_cols":   ["dr amount", "debit", "dr"],
        "date_cols":     ["posting date", "date", "value date"],
        "desc_cols":     ["transaction description", "narration", "description"],
        "credit_cols":   ["cr amount", "credit", "cr"],
        "skip_keywords": ["balance", "total"],
    },
    "UBA (United Bank for Africa)": {
        "amount_cols":   ["debit", "withdrawal", "dr amount"],
        "date_cols":     ["transaction date", "date"],
        "desc_cols":     ["transaction description", "narration", "description"],
        "credit_cols":   ["credit", "deposit"],
        "skip_keywords": ["balance b/f", "total", "brought forward"],
    },
    "First Bank": {
        "amount_cols":   ["debit", "amount", "dr"],
        "date_cols":     ["date", "transaction date", "posting date"],
        "desc_cols":     ["description", "narration", "particulars"],
        "credit_cols":   ["credit", "cr"],
        "skip_keywords": ["opening", "closing", "b/f"],
    },
    "Opay": {
        "amount_cols":   ["amount", "debit amount", "transaction amount"],
        "date_cols":     ["date", "time", "created at", "transaction date"],
        "desc_cols":     ["description", "narration", "transaction type", "remark"],
        "credit_cols":   ["credit amount"],
        "skip_keywords": [],
    },
    "Kuda Bank": {
        "amount_cols":   ["amount", "debit"],
        "date_cols":     ["date", "transaction date", "created at"],
        "desc_cols":     ["description", "narration", "transaction description"],
        "credit_cols":   ["credit"],
        "skip_keywords": [],
    },
    "Moniepoint": {
        "amount_cols":   ["amount", "debit amount"],
        "date_cols":     ["date", "transaction date"],
        "desc_cols":     ["description", "narration", "transaction description"],
        "credit_cols":   ["credit amount"],
        "skip_keywords": [],
    },
    "Fidelity Bank": {
        "amount_cols":   ["debit", "dr", "amount"],
        "date_cols":     ["transaction date", "value date", "date"],
        "desc_cols":     ["narration", "description", "transaction details"],
        "credit_cols":   ["credit", "cr"],
        "skip_keywords": ["balance", "total"],
    },
    "FCMB": {
        "amount_cols":   ["debit", "amount", "withdrawal"],
        "date_cols":     ["date", "transaction date", "value date"],
        "desc_cols":     ["description", "narration", "details"],
        "credit_cols":   ["credit", "deposit"],
        "skip_keywords": ["balance"],
    },
    "Stanbic IBTC": {
        "amount_cols":   ["debit amount", "debit", "dr"],
        "date_cols":     ["date", "posting date", "transaction date"],
        "desc_cols":     ["transaction narrative", "description", "narration"],
        "credit_cols":   ["credit amount", "credit", "cr"],
        "skip_keywords": ["balance", "opening", "closing"],
    },
    "Polaris Bank": {
        "amount_cols":   ["debit", "dr amount", "withdrawal"],
        "date_cols":     ["date", "value date", "transaction date"],
        "desc_cols":     ["description", "narration", "particulars"],
        "credit_cols":   ["credit", "cr amount"],
        "skip_keywords": ["balance", "b/f"],
    },
    "Generic (any bank)": {
        "amount_cols":   ["amount", "debit", "dr", "withdrawal", "amt", "value"],
        "date_cols":     ["date", "time", "posted", "value date", "txn date", "transaction date"],
        "desc_cols":     ["description", "narration", "remark", "details",
                          "merchant", "particulars", "reference", "memo", "narrative"],
        "credit_cols":   ["credit", "cr", "deposit"],
        "skip_keywords": [],
    },
}

CATEGORY_KEYWORDS = {
    "Transport":            ["bolt", "uber", "taxify", "okada", "danfo", "bus", "keke", "ride",
                             "transport", "brt", "taxi", "bike", "lasgidi", "gokada"],
    "Airtime/Data":         ["airtime", "data", "mtn", "airtel", "glo", "9mobile", "etisalat",
                             "recharge", "vtu", "bundle", "data sub"],
    "Foodstuff":            ["shoprite", "spar", "market", "grocery", "provision", "foodstuff",
                             "rice", "beans", "yam", "garri", "palm oil", "tomato", "pepper",
                             "chicken", "fish", "beef", "suya", "meat", "vegetable"],
    "Food & Eating Out":    ["restaurant", "eatery", "cafe", "pizza", "chicken republic",
                             "mr biggs", "tantalizers", "domino", "kfc", "fast food", "food court",
                             "canteen", "lunch", "dinner", "breakfast", "snack", "buka", "mama put"],
    "Fuel":                 ["fuel", "petrol", "diesel", "filling station", "nnpc", "total",
                             "mobil", "conoil", "oando", "gas station", "litre", "liter"],
    "Electricity (NEPA)":   ["nepa", "phcn", "eko electric", "ikeja electric", "abuja electric",
                             "disco", "prepaid meter", "token", "electricity", "power", "light bill"],
    "Rent":                 ["rent", "house", "apartment", "landlord", "caution fee", "agency fee",
                             "tenancy", "leasehold"],
    "School Fees":          ["school", "fees", "tuition", "university", "college", "academy",
                             "polytechnic", "exam", "waec", "jamb", "neco", "school levy"],
    "Hospital/Drugs":       ["hospital", "clinic", "pharmacy", "drug", "medicine", "health",
                             "doctor", "lab", "scan", "test", "surgery", "chemist"],
    "Internet":             ["internet", "isp", "spectranet", "smile", "swift", "ipnx", "wifi",
                             "broadband", "fiber", "starlink", "subscription"],
    "POS Charges":          ["pos charge", "pos fee", "withdrawal fee", "pos commission"],
    "Transfer Fees":        ["transfer fee", "transaction fee", "service charge", "maintenance fee",
                             "bank charge", "sms charge", "card maintenance"],
    "Church/Mosque Giving": ["tithe", "offering", "church", "mosque", "giving", "donation",
                             "crusade", "fellowship", "islamic", "juma"],
    "Business Stock":       ["stock", "inventory", "wholesale", "goods", "merchandise", "restock",
                             "supplier", "procurement", "raw material"],
    "Family Support":       ["family", "mum", "dad", "mother", "father", "brother", "sister",
                             "uncle", "aunt", "parents", "kin", "relative"],
    "Subscription":         ["netflix", "spotify", "apple", "google play", "dstv", "gotv",
                             "showmax", "prime video", "amazon", "canva", "chatgpt", "openai",
                             "monthly", "annual", "renewal"],
    "Hair/Beauty":          ["hair", "salon", "barber", "beauty", "makeup", "spa", "nail"],
    "Clothing":             ["clothing", "cloth", "fashion", "shoe", "bag", "boutique",
                             "tailoring", "sewing", "fabric", "ankara", "aso ebi"],
    "Generator/Fuel":       ["generator", "gen", "diesel gen", "fuel gen", "servicing gen"],
    "Water":                ["water", "borehole", "sachet water", "table water", "water board"],
    "Betting":              ["bet", "sporty", "nairabet", "betking", "melbet", "1xbet",
                             "betway", "bet9ja", "betting", "lottery"],
    "Savings Deposit":      ["savings", "piggy", "cowrywise", "kuda save", "stash"],
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _clean_amount(x):
    if pd.isna(x):
        return None
    s = re.sub(r"[^0-9.\-]", "", str(x).replace(",", ""))
    if not s or s == "-":
        return None
    try:
        val = float(s)
        return abs(val) if val != 0 else None
    except Exception:
        return None


def _clean_date(x):
    if pd.isna(x):
        return date.today()
    dt = pd.to_datetime(x, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return date.today()
    return dt.date()


def _clean_text(x, fallback="Imported expense"):
    if pd.isna(x):
        return fallback
    return str(x).strip() or fallback


def _to_date(val):
    """Normalize a DB value (datetime, date, str) to a plain date object."""
    if val is None:
        return date.today()
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return pd.to_datetime(val, dayfirst=True).date()
    except Exception:
        return date.today()


def _row_fingerprint(bank_id, txn_date, amount, description):
    """
    FIX: Always use ISO date string so datetime vs date type never causes mismatches.
    """
    date_str = txn_date.isoformat() if hasattr(txn_date, "isoformat") else str(txn_date)[:10]
    raw = f"{bank_id}|{date_str}|{amount}|{description.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _guess_category(description):
    desc_lower = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    return "Other"


def _detect_bank_format(columns):
    cols_lower = [c.lower().strip() for c in columns]
    best_name  = "Generic (any bank)"
    best_score = 0
    for bank_name, fmt in BANK_FORMATS.items():
        if bank_name == "Generic (any bank)":
            continue
        score = 0
        all_hints = fmt["amount_cols"] + fmt["date_cols"] + fmt["desc_cols"] + fmt["credit_cols"]
        for hint in all_hints:
            if any(hint in col for col in cols_lower):
                score += 1
        if score > best_score:
            best_score = score
            best_name  = bank_name
    return best_name, BANK_FORMATS[best_name]


def _auto_pick_col(columns, keywords):
    cols_lower = [c.lower().strip() for c in columns]
    for kw in keywords:
        for i, col_low in enumerate(cols_lower):
            if kw in col_low:
                return columns[i]
    return None


def _load_existing_fingerprints(cur, bank_id):
    """
    FIX: Normalize created_at to plain date before hashing so fingerprints
    always match regardless of whether the DB returns datetime or date.
    """
    cur.execute(
        "SELECT amount, description, created_at FROM transactions "
        "WHERE bank_id = %s AND type = 'debit'",
        (bank_id,)
    )
    rows = cur.fetchall()
    fps  = set()
    for r in rows:
        txn_date = _to_date(r["created_at"])          # ← FIX
        fp = _row_fingerprint(bank_id, txn_date, int(r["amount"]), r["description"] or "")
        fps.add(fp)
    return fps


def _ensure_import_tables(cur, conn):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS import_batches (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            bank_id INTEGER NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
            filename TEXT,
            row_count INTEGER DEFAULT 0,
            total_amount INTEGER DEFAULT 0,
            imported_at TIMESTAMP DEFAULT NOW(),
            undone INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS import_batch_items (
            id SERIAL PRIMARY KEY,
            batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
            expense_id INTEGER REFERENCES expenses(id) ON DELETE SET NULL,
            tx_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
            amount INTEGER NOT NULL,
            bank_id INTEGER NOT NULL REFERENCES banks(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_import_batches_user_id
            ON import_batches(user_id, imported_at DESC)
    """)
    conn.commit()


def _get_last_batch(cur, user_id):
    cur.execute("""
        SELECT id, filename, row_count, total_amount, imported_at, bank_id
        FROM import_batches
        WHERE user_id = %s AND undone = 0
        ORDER BY imported_at DESC LIMIT 1
    """, (user_id,))
    return cur.fetchone()


def _undo_batch(cur, conn, batch_id, user_id):
    cur.execute("""
        SELECT ibi.expense_id, ibi.tx_id, ibi.amount, ibi.bank_id
        FROM import_batch_items ibi WHERE ibi.batch_id = %s
    """, (batch_id,))
    items = cur.fetchall()
    rows_reversed  = 0
    total_reversed = 0
    for item in items:
        amt     = item["amount"]
        bank_id = item["bank_id"]
        cur.execute("UPDATE banks SET balance = balance + %s WHERE id = %s", (amt, bank_id))
        if item["expense_id"]:
            cur.execute("DELETE FROM expenses WHERE id = %s AND user_id = %s",
                        (item["expense_id"], user_id))
        if item["tx_id"]:
            cur.execute("DELETE FROM transactions WHERE id = %s", (item["tx_id"],))
        rows_reversed  += 1
        total_reversed += amt
    cur.execute("UPDATE import_batches SET undone = 1 WHERE id = %s", (batch_id,))
    conn.commit()
    return rows_reversed, total_reversed


# ── mobile-optimised styles ────────────────────────────────────────────────────

_IMPORT_CSS = """
<style>
.imp-badge      { display:inline-block; background:#e8f5f0; color:#0e7c5b;
                  border-radius:20px; padding:2px 10px; font-size:0.76rem;
                  font-weight:700; margin-left:4px; white-space:nowrap; }
.imp-badge-warn { background:#fff3e0; color:#e65100; }
.imp-badge-dup  { background:#f3e5f5; color:#6a1b9a; }
.imp-section    { background:#f0f7f4; border-radius:10px;
                  padding:12px 14px; margin-bottom:10px; }
.fmt-chip       { display:inline-block; background:#1a3c5e; color:#a8d8c8;
                  border-radius:8px; padding:3px 10px;
                  font-size:0.82rem; font-weight:600; }
.imp-stat-row   { display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; }
.imp-stat       { flex:1; min-width:110px; background:#fff;
                  border:1px solid #e0ebe7; border-radius:10px;
                  padding:10px 12px; text-align:center; }
.imp-stat-val   { font-size:1.2rem; font-weight:800; color:#0e7c5b; line-height:1.1; }
.imp-stat-lbl   { font-size:0.72rem; color:#6b7f8e; margin-top:2px; }
.imp-warn-box   { background:#fff8e1; border-left:4px solid #ffb300;
                  border-radius:8px; padding:10px 14px;
                  font-size:0.88rem; color:#5d4037; margin:8px 0; }
.imp-err-box    { background:#fdecea; border-left:4px solid #e53935;
                  border-radius:8px; padding:10px 14px;
                  font-size:0.88rem; color:#b71c1c; margin:8px 0; }
.imp-ok-box     { background:#e8f5e9; border-left:4px solid #43a047;
                  border-radius:8px; padding:10px 14px;
                  font-size:0.88rem; color:#1b5e20; margin:8px 0; }

/* Mobile tweaks */
@media screen and (max-width: 640px) {
  .imp-stat-val { font-size:1.05rem; }
  .imp-stat     { padding:8px 8px; min-width:90px; }
  .stSelectbox label { font-size:0.82rem !important; }
  .stButton > button { min-height:48px !important; font-size:1rem !important; }
  hr { margin:8px 0 !important; }
}
</style>
"""


# ── main page ─────────────────────────────────────────────────────────────────

def csv_import_page(conn, user_id: int):
    cur = conn.cursor()
    _ensure_import_tables(cur, conn)

    st.markdown(_IMPORT_CSS, unsafe_allow_html=True)

    # 1. Load banks
    cur.execute("SELECT id, bank_name, account_number, balance FROM banks WHERE user_id = %s", (user_id,))
    banks = cur.fetchall()
    if not banks:
        st.warning("You have no bank accounts yet. Add one on the Banks page first.")
        return

    bank_options = {
        f"{b['bank_name']} (****{b['account_number']}) — \u20a6{b['balance']:,}": b
        for b in banks
    }
    sel_label     = st.selectbox("Which bank does this statement belong to?",
                                 list(bank_options.keys()), key="csv_bank_select")
    selected_bank = bank_options[sel_label]
    bank_id       = selected_bank["id"]

    # 2. Undo last import
    last_batch = _get_last_batch(cur, user_id)
    if last_batch:
        with st.expander(
            f"\u21a9 Undo last import \u2014 {last_batch['row_count']} rows \u00b7 "
            f"\u20a6{last_batch['total_amount']:,} "
            f"({str(last_batch['imported_at'])[:16]})",
            expanded=False
        ):
            st.warning(
                f"This will reverse **{last_batch['row_count']} expenses** totalling "
                f"**\u20a6{last_batch['total_amount']:,}** and restore your bank balance."
            )
            if st.button("Undo this import", key="csv_undo_btn", type="primary"):
                rows_rev, total_rev = _undo_batch(cur, conn, last_batch["id"], user_id)
                st.success(f"Reversed {rows_rev} expenses — \u20a6{total_rev:,} restored.")
                st.rerun()

    st.divider()

    # 3. File upload
    file = st.file_uploader(
        "Upload CSV file", type=["csv"], key="csv_file",
        help="Download your bank statement as CSV from your bank's app or internet banking"
    )
    if not file:
        with st.expander("How does CSV import work?", expanded=False):
            st.markdown("""
            1. **Download your bank statement** as a CSV from your bank's app or internet banking.
            2. **Upload it here** using the file uploader above.
            3. **Map the columns** — Budget Right auto-detects your bank format.
            4. **Preview and confirm** — every debit row becomes an expense and updates your balance.

            **Supported:** GTB, Access, Zenith, UBA, First Bank, Opay, Kuda, Moniepoint, and more.
            """)
        return

    # Parse CSV — try UTF-8, fall back to latin-1
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

    filename = getattr(file, "name", "unknown.csv")
    csv_cols = list(df.columns)

    # 4. Bank format auto-detection
    detected_bank, fmt = _detect_bank_format(csv_cols)
    st.markdown(
        f'<div class="imp-section">\U0001f4cb <strong>Detected format:</strong> '
        f'<span class="fmt-chip">{detected_bank}</span></div>',
        unsafe_allow_html=True
    )

    with st.expander("Raw CSV preview (first 8 rows)", expanded=False):
        st.dataframe(df.head(8), use_container_width=True)

    # 5. Column mapping
    auto_amount = _auto_pick_col(csv_cols, fmt["amount_cols"])
    auto_date   = _auto_pick_col(csv_cols, fmt["date_cols"])
    auto_desc   = _auto_pick_col(csv_cols, fmt["desc_cols"])

    st.subheader("Column mapping")
    st.caption("Budget Right pre-selected the most likely columns. Adjust if anything looks off.")

    c1, c2, c3 = st.columns(3)
    with c1:
        amount_col = st.selectbox(
            "Amount column \u2605", ["(none)"] + csv_cols,
            index=(csv_cols.index(auto_amount) + 1) if auto_amount else 0,
            key="csv_amount_col",
            help="Column containing debit/expense amounts"
        )
    with c2:
        date_col = st.selectbox(
            "Date column", ["(none)"] + csv_cols,
            index=(csv_cols.index(auto_date) + 1) if auto_date else 0,
            key="csv_date_col",
            help="Transaction date — today used if blank"
        )
    with c3:
        desc_col = st.selectbox(
            "Description column \u2605", ["(none)"] + csv_cols,
            index=(csv_cols.index(auto_desc) + 1) if auto_desc else 0,
            key="csv_desc_col",
            help="Narration used as the expense name"
        )

    if amount_col == "(none)" or desc_col == "(none)":
        st.info("Please map at least the **Amount** and **Description** columns to continue.")
        return

    # 6. Build and clean working data
    skip_kws    = fmt.get("skip_keywords", [])
    rows_raw    = []
    broken_rows = []

    for idx, row in df.iterrows():
        try:
            raw_amount = row.get(amount_col)
            raw_desc   = row.get(desc_col)  if desc_col  != "(none)" else None
            raw_date   = row.get(date_col)  if date_col  != "(none)" else None

            desc = _clean_text(raw_desc)
            if skip_kws and any(kw in desc.lower() for kw in skip_kws):
                continue

            amt = _clean_amount(raw_amount)
            if amt is None or amt <= 0:
                continue

            txn_date = _clean_date(raw_date) if raw_date is not None else date.today()
            category = _guess_category(desc)

            rows_raw.append({
                "date": txn_date, "description": desc,
                "amount": int(round(amt)), "category": category,
                "_row_idx": idx,
            })
        except Exception as exc:
            broken_rows.append({"row": idx + 2, "error": str(exc)})

    if broken_rows:
        with st.expander(f"{len(broken_rows)} broken row(s) skipped", expanded=False):
            for br in broken_rows:
                st.caption(f"Row {br['row']}: {br['error']}")

    if not rows_raw:
        st.error("No valid rows found. Check your column mapping.")
        return

    # 7. Duplicate detection (uses normalized date fingerprints — FIX)
    existing_fps = _load_existing_fingerprints(cur, bank_id)
    new_rows, dup_rows = [], []
    for r in rows_raw:
        fp = _row_fingerprint(bank_id, r["date"], r["amount"], r["description"])
        (dup_rows if fp in existing_fps else new_rows).append(r)

    # 8. Preview
    st.divider()
    total_new = sum(r["amount"] for r in new_rows)
    total_dup = sum(r["amount"] for r in dup_rows)

    badge_new = f'<span class="imp-badge">{len(new_rows)} new</span>'
    badge_dup = (f'<span class="imp-badge imp-badge-dup">{len(dup_rows)} duplicates</span>'
                 if dup_rows else "")
    badge_brk = (f'<span class="imp-badge imp-badge-warn">{len(broken_rows)} broken</span>'
                 if broken_rows else "")
    st.markdown(f"### Import preview &nbsp; {badge_new} {badge_dup} {badge_brk}",
                unsafe_allow_html=True)

    if not new_rows:
        st.success(
            f"All {len(dup_rows)} rows in this file have already been imported. Nothing new to add."
        )
        return

    # Stat cards (responsive, wrap on mobile)
    st.markdown(
        f'<div class="imp-stat-row">'
        f'<div class="imp-stat"><div class="imp-stat-val">{len(new_rows)}</div>'
        f'<div class="imp-stat-lbl">Rows to import</div></div>'
        f'<div class="imp-stat"><div class="imp-stat-val">\u20a6{total_new:,}</div>'
        f'<div class="imp-stat-lbl">Total amount</div></div>'
        + (f'<div class="imp-stat"><div class="imp-stat-val">{len(dup_rows)}</div>'
           f'<div class="imp-stat-lbl">Skipped (dupes)</div></div>' if dup_rows else "")
        + '</div>',
        unsafe_allow_html=True
    )

    preview_df = pd.DataFrame(new_rows)[["date", "description", "category", "amount"]].copy()
    preview_df.columns = ["Date", "Description", "Category", "Amount (\u20a6)"]
    preview_df["Amount (\u20a6)"] = preview_df["Amount (\u20a6)"].apply(lambda v: f"{v:,}")
    st.dataframe(preview_df, use_container_width=True, height=min(300, 40 + len(new_rows) * 35))

    if dup_rows:
        st.markdown(
            f'<div class="imp-warn-box">\u2139\ufe0f {len(dup_rows)} duplicate row(s) \u2014 '
            f'\u20a6{total_dup:,} \u2014 already in your records and will be skipped.</div>',
            unsafe_allow_html=True
        )

    # 9. Balance / overdraft check
    cur.execute("SELECT balance FROM banks WHERE id = %s", (bank_id,))
    current_balance = (cur.fetchone() or {}).get("balance", 0)
    cur.execute("SELECT allow_overdraft FROM users WHERE id = %s", (user_id,))
    allow_overdraft = bool((cur.fetchone() or {}).get("allow_overdraft", 0))

    balance_ok = True
    if total_new > current_balance:
        shortfall = total_new - current_balance
        if not allow_overdraft:
            # FIX: was a silent return() — now shows a clear actionable error
            st.markdown(
                f'<div class="imp-err-box">\u26a0\ufe0f <strong>Insufficient balance.</strong> '
                f'Import total (\u20a6{total_new:,}) exceeds your {selected_bank["bank_name"]} '
                f'balance (\u20a6{current_balance:,}) by \u20a6{shortfall:,}.<br>'
                f'<strong>Fix:</strong> Go to <em>Settings \u2192 enable Overdraft</em>, '
                f'or increase your bank balance on the Banks page first.</div>',
                unsafe_allow_html=True
            )
            balance_ok = False
        else:
            st.markdown(
                f'<div class="imp-warn-box">\u26a0\ufe0f Import (\u20a6{total_new:,}) exceeds '
                f'balance (\u20a6{current_balance:,}). Overdraft is enabled \u2014 '
                f'balance will go negative.</div>',
                unsafe_allow_html=True
            )

    # 10. Import button — visible always, disabled when balance blocked
    btn_label = f"Import {len(new_rows)} expenses into Budget Right"
    if not balance_ok:
        st.button(btn_label, use_container_width=True, type="primary",
                  key="csv_import_btn", disabled=True)
        return

    if st.button(btn_label, use_container_width=True, type="primary", key="csv_import_btn"):
        imported      = 0
        import_errors = []
        total_to_do   = len(new_rows)
        progress      = st.progress(0, text="Importing\u2026")

        try:
            cur.execute("""
                INSERT INTO import_batches
                    (user_id, bank_id, filename, row_count, total_amount, imported_at)
                VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING id
            """, (user_id, bank_id, filename, len(new_rows), total_new))
            batch_id = cur.fetchone()["id"]

            for i, r in enumerate(new_rows):
                try:
                    amt      = r["amount"]
                    desc     = r["description"]
                    cat      = r["category"]
                    txn_date = r["date"]

                    cur.execute("""
                        INSERT INTO transactions (bank_id, type, amount, description, created_at)
                        VALUES (%s, 'debit', %s, %s, %s) RETURNING id
                    """, (bank_id, amt, f"Expense: {desc}", txn_date))
                    tx_id = cur.fetchone()["id"]

                    cur.execute("""
                        INSERT INTO expenses
                            (user_id, bank_id, name, category, amount, created_at, tx_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """, (user_id, bank_id, desc, cat, amt, txn_date, tx_id))
                    expense_id = cur.fetchone()["id"]

                    cur.execute("UPDATE banks SET balance = balance - %s WHERE id = %s",
                                (amt, bank_id))

                    cur.execute("""
                        INSERT INTO import_batch_items
                            (batch_id, expense_id, tx_id, amount, bank_id)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (batch_id, expense_id, tx_id, amt, bank_id))

                    imported += 1
                except Exception as row_exc:
                    import_errors.append(str(row_exc))

                # Update progress every 10 rows to avoid UI flooding
                if i % 10 == 0 or i == total_to_do - 1:
                    progress.progress(
                        (i + 1) / total_to_do,
                        text=f"Importing\u2026 {i + 1}/{total_to_do}"
                    )

            actual_total = sum(r["amount"] for r in new_rows[:imported])
            cur.execute(
                "UPDATE import_batches SET row_count=%s, total_amount=%s WHERE id=%s",
                (imported, actual_total, batch_id)
            )
            conn.commit()
            progress.empty()

            if imported > 0:
                st.markdown(
                    f'<div class="imp-ok-box">\u2705 <strong>Imported {imported} expenses</strong> '
                    f'from <strong>{selected_bank["bank_name"]}</strong> successfully! '
                    f'Your balance has been updated.<br>'
                    f'<em>To undo, reload this page and expand \u201cUndo last import\u201d above.</em></div>',
                    unsafe_allow_html=True
                )
                st.balloons()
            if import_errors:
                with st.expander(f"{len(import_errors)} row(s) failed during import"):
                    for err in import_errors:
                        st.caption(err)

        except Exception as e:
            conn.rollback()
            progress.empty()
            st.error(f"Import failed \u2014 no data was changed. Error: {e}")
