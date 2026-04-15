# pdf_report.py — PDF statement generator for Budget Right
#
# Four report types, all returned as bytes for st.download_button:
#   build_monthly_statement(data)    — full monthly summary
#   build_goal_progress_report(data) — savings goal progress
#   build_category_budget_report(data) — category vs budget
#   build_bank_report(data)          — per-bank breakdown
#
# Each build_* function accepts a plain dict from the corresponding
# fetch_* function in this module. Keep DB logic here so dashboard.py
# stays thin.

import io
import calendar
from datetime import datetime, date, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)

from db import get_db

# ── Brand colours ─────────────────────────────────────────────────────────────
DARK_NAVY   = colors.HexColor("#1a3c5e")
TEAL        = colors.HexColor("#0e7c5b")
LIGHT_TEAL  = colors.HexColor("#e8f5f0")
MID_TEAL    = colors.HexColor("#a8d8c8")
RED         = colors.HexColor("#c0392b")
AMBER       = colors.HexColor("#f39c12")
LIGHT_AMBER = colors.HexColor("#fffbea")
LIGHT_GREY  = colors.HexColor("#f4f6f8")
MID_GREY    = colors.HexColor("#d0dde5")
DARK_GREY   = colors.HexColor("#4a6070")
WHITE       = colors.white

W, H = A4          # 210 × 297 mm
LM = RM = 18 * mm
TM = BM = 16 * mm

# ── Shared style helpers ──────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    def _p(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)
    return {
        "title":    _p("br_title",   "Title",   fontSize=22, textColor=WHITE,
                       alignment=TA_CENTER, spaceAfter=2),
        "subtitle": _p("br_sub",     "Normal",  fontSize=10, textColor=MID_TEAL,
                       alignment=TA_CENTER, spaceAfter=4),
        "h1":       _p("br_h1",      "Heading1",fontSize=13, textColor=DARK_NAVY,
                       spaceBefore=10, spaceAfter=4),
        "h2":       _p("br_h2",      "Heading2",fontSize=11, textColor=TEAL,
                       spaceBefore=8, spaceAfter=3),
        "body":     _p("br_body",    "Normal",  fontSize=9,  textColor=DARK_GREY,
                       leading=13, spaceAfter=3),
        "small":    _p("br_small",   "Normal",  fontSize=7.5,textColor=DARK_GREY,
                       leading=11),
        "label":    _p("br_label",   "Normal",  fontSize=8,  textColor=DARK_GREY,
                       textTransform="uppercase", spaceBefore=2),
        "metric_v": _p("br_metricv", "Normal",  fontSize=16, textColor=DARK_NAVY,
                       fontName="Helvetica-Bold", alignment=TA_CENTER),
        "metric_l": _p("br_metricl", "Normal",  fontSize=7.5,textColor=DARK_GREY,
                       alignment=TA_CENTER, textTransform="uppercase"),
        "green":    _p("br_green",   "Normal",  fontSize=9,  textColor=TEAL,
                       fontName="Helvetica-Bold"),
        "red":      _p("br_red",     "Normal",  fontSize=9,  textColor=RED,
                       fontName="Helvetica-Bold"),
        "right":    _p("br_right",   "Normal",  fontSize=9,  textColor=DARK_GREY,
                       alignment=TA_RIGHT),
        "footer":   _p("br_footer",  "Normal",  fontSize=7,  textColor=MID_GREY,
                       alignment=TA_CENTER),
        "tbl_hdr":  _p("br_tblhdr", "Normal",  fontSize=8,  textColor=WHITE,
                       fontName="Helvetica-Bold", alignment=TA_CENTER),
        "tbl_cell": _p("br_tblcell","Normal",  fontSize=8,  textColor=DARK_GREY),
        "tbl_amt":  _p("br_tblamt", "Normal",  fontSize=8,  textColor=DARK_GREY,
                       alignment=TA_RIGHT),
    }


def _ngn(amount: int) -> str:
    return f"NGN {amount:,}"


def _pct(num, denom) -> str:
    if not denom:
        return "—"
    return f"{round(num / denom * 100, 1):.1f}%"


def _doc(buf, title="Budget Right"):
    return SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=LM, rightMargin=RM,
        topMargin=TM, bottomMargin=BM,
        title=title, author="Budget Right",
    )


def _header_block(S, report_name: str, month_label: str, user_name: str) -> list:
    """Dark teal header banner with report name + period."""
    inner_w = W - LM - RM
    header_table = Table(
        [[
            Paragraph(f"<b>Budget Right</b>", S["title"]),
            Paragraph(report_name, S["title"]),
        ]],
        colWidths=[inner_w * 0.45, inner_w * 0.55],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), DARK_NAVY),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    sub = Paragraph(
        f"{month_label} &nbsp;&bull;&nbsp; {user_name} &nbsp;&bull;&nbsp; "
        f"Generated {datetime.now().strftime('%d %b %Y %H:%M')}",
        S["subtitle"],
    )
    return [header_table, Spacer(1, 3 * mm), sub, HRFlowable(width="100%", color=MID_TEAL, thickness=1)]


def _metric_row(S, metrics: list, inner_w: float) -> Table:
    """
    Horizontal row of metric boxes.
    metrics = [(label, value, color), ...]
    """
    n = len(metrics)
    col_w = inner_w / n
    header_row = [Paragraph(m[0], S["metric_l"]) for m in metrics]
    value_row  = [
        Paragraph(f"<font color='#{m[2].hexval()[2:] if hasattr(m[2],'hexval') else '1a3c5e'}'>{m[1]}</font>",
                  S["metric_v"])
        for m in metrics
    ]
    t = Table([header_row, value_row], colWidths=[col_w] * n)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_TEAL),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_TEAL),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def _section_heading(S, text: str) -> list:
    return [
        Spacer(1, 4 * mm),
        Paragraph(text, S["h1"]),
        HRFlowable(width="100%", color=MID_TEAL, thickness=0.75),
        Spacer(1, 2 * mm),
    ]


def _bar_html(pct: float, color_hex: str = "#0e7c5b", height_pt: int = 8) -> str:
    """Inline HTML progress bar using a single-cell table via Paragraph."""
    pct = min(max(pct, 0), 100)
    return (
        f'<font color="{color_hex}">{"█" * int(pct / 5)}'
        f'<font color="#d0dde5">{"░" * (20 - int(pct / 5))}</font></font> {pct:.0f}%'
    )


def _std_table(S, col_headers: list, rows: list, col_widths: list,
               alternating: bool = True) -> Table:
    """Standard data table with dark-navy header row."""
    header = [Paragraph(h, S["tbl_hdr"]) for h in col_headers]
    body   = []
    for r in rows:
        body.append([
            Paragraph(str(c), S["tbl_amt"] if i == len(r) - 1 else S["tbl_cell"])
            for i, c in enumerate(r)
        ])
    t = Table([header] + body, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0),  DARK_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("ALIGN",         (-1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",         (0, 0), (-2, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID_GREY),
    ]
    if alternating:
        for i in range(1, len(body) + 1):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GREY))
    t.setStyle(TableStyle(style))
    return t


def _footer_note(S, text: str) -> list:
    return [
        Spacer(1, 6 * mm),
        HRFlowable(width="100%", color=MID_GREY, thickness=0.5),
        Spacer(1, 2 * mm),
        Paragraph(text, S["footer"]),
    ]


# ── DATA FETCHERS ─────────────────────────────────────────────────────────────

def fetch_monthly_data(user_id: int, year: int, month: int) -> dict:
    """Fetch everything needed for the monthly statement PDF."""
    m_start = date(year, month, 1)
    m_end   = date(year, month, calendar.monthrange(year, month)[1])
    prev_end   = m_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)

    with get_db() as (conn, cursor):
        # User name
        cursor.execute("SELECT surname, other_names FROM users WHERE id=%s", (user_id,))
        u = cursor.fetchone()
        user_name = f"{u['surname']} {u['other_names']}"

        # Summary totals
        cursor.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
              COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
        """, (user_id, m_start, m_end))
        totals = cursor.fetchone()
        income = int(totals["income"] or 0)
        spent  = int(totals["spent"]  or 0)

        # Previous month totals
        cursor.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
              COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
        """, (user_id, prev_start, prev_end))
        prev = cursor.fetchone()
        prev_income = int(prev["income"] or 0)
        prev_spent  = int(prev["spent"]  or 0)

        # Category breakdown
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat,
                   SUM(e.amount) AS total, COUNT(*) AS cnt
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
            GROUP BY cat ORDER BY total DESC
        """, (user_id, m_start, m_end))
        categories = cursor.fetchall()

        # All expenses
        cursor.execute("""
            SELECT e.created_at, e.name, COALESCE(e.category, e.name) AS cat,
                   e.amount, b.bank_name
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
            ORDER BY e.created_at DESC
        """, (user_id, m_start, m_end))
        expenses = cursor.fetchall()

        # All income
        cursor.execute("""
            SELECT t.created_at, t.description, t.amount, b.bank_name
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.type='credit'
              AND t.created_at>=%s AND t.created_at<=%s
            ORDER BY t.created_at DESC
        """, (user_id, m_start, m_end))
        income_rows = cursor.fetchall()

        # Days with spending
        cursor.execute("""
            SELECT COUNT(DISTINCT e.created_at) AS n
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
        """, (user_id, m_start, m_end))
        spend_days = int(cursor.fetchone()["n"] or 0)

        # Monthly spending limit
        cursor.execute("SELECT monthly_spending_limit FROM users WHERE id=%s", (user_id,))
        limit = int(cursor.fetchone()["monthly_spending_limit"] or 0)

    days_in_month = calendar.monthrange(year, month)[1]
    return dict(
        user_name=user_name,
        year=year, month=month,
        m_start=m_start, m_end=m_end,
        income=income, spent=spent,
        net=income - spent,
        prev_income=prev_income, prev_spent=prev_spent,
        savings_rate=round((income - spent) / income * 100, 1) if income else None,
        categories=categories,
        expenses=expenses,
        income_rows=income_rows,
        spend_days=spend_days,
        no_spend_days=days_in_month - spend_days,
        days_in_month=days_in_month,
        limit=limit,
    )


def fetch_goal_data(user_id: int) -> dict:
    cursor_data = {}
    with get_db() as (conn, cursor):
        cursor.execute("SELECT surname, other_names FROM users WHERE id=%s", (user_id,))
        u = cursor.fetchone()
        cursor_data["user_name"] = f"{u['surname']} {u['other_names']}"

        cursor.execute("""
            SELECT g.id, g.name, g.target_amount, g.current_amount, g.status, g.created_at,
                   (g.target_amount - g.current_amount) AS shortfall
            FROM goals g WHERE g.user_id=%s ORDER BY g.status, g.created_at
        """, (user_id,))
        goals = cursor.fetchall()

        # Recent contributions per goal
        contributions = {}
        for g in goals:
            cursor.execute("""
                SELECT gc.contributed_at, gc.amount, b.bank_name
                FROM goal_contributions gc JOIN banks b ON gc.bank_id=b.id
                WHERE gc.goal_id=%s ORDER BY gc.contributed_at DESC LIMIT 5
            """, (g["id"],))
            contributions[g["id"]] = cursor.fetchall()

        cursor.execute("""
            SELECT COALESCE(SUM(current_amount),0) AS saved,
                   COALESCE(SUM(target_amount),0)  AS target
            FROM goals WHERE user_id=%s AND status='active'
        """, (user_id,))
        totals = cursor.fetchone()

    cursor_data["goals"]         = goals
    cursor_data["contributions"] = contributions
    cursor_data["total_saved"]   = int(totals["saved"] or 0)
    cursor_data["total_target"]  = int(totals["target"] or 0)
    return cursor_data


def fetch_category_budget_data(user_id: int, year: int, month: int) -> dict:
    m_start = date(year, month, 1)
    m_end   = date(year, month, calendar.monthrange(year, month)[1])

    with get_db() as (conn, cursor):
        cursor.execute("SELECT surname, other_names FROM users WHERE id=%s", (user_id,))
        u = cursor.fetchone()
        user_name = f"{u['surname']} {u['other_names']}"

        cursor.execute("""
            SELECT cb.category, cb.monthly_limit,
                   COALESCE(SUM(e.amount), 0) AS spent
            FROM category_budgets cb
            LEFT JOIN expenses e
                ON COALESCE(e.category, e.name) = cb.category
               AND e.user_id = cb.user_id
               AND e.created_at >= %s AND e.created_at <= %s
            WHERE cb.user_id = %s AND cb.monthly_limit > 0
            GROUP BY cb.category, cb.monthly_limit
            ORDER BY cb.monthly_limit DESC
        """, (m_start, m_end, user_id))
        cats = cursor.fetchall()

    return dict(user_name=user_name, year=year, month=month,
                m_start=m_start, m_end=m_end, categories=cats)


def fetch_bank_data(user_id: int, year: int, month: int) -> dict:
    m_start = date(year, month, 1)
    m_end   = date(year, month, calendar.monthrange(year, month)[1])

    with get_db() as (conn, cursor):
        cursor.execute("SELECT surname, other_names FROM users WHERE id=%s", (user_id,))
        u = cursor.fetchone()
        user_name = f"{u['surname']} {u['other_names']}"

        cursor.execute("""
            SELECT id, bank_name, account_name, account_number, balance
            FROM banks WHERE user_id=%s ORDER BY bank_name
        """, (user_id,))
        banks = cursor.fetchall()

        bank_details = []
        for b in banks:
            cursor.execute("""
                SELECT type,
                       COALESCE(SUM(CASE WHEN type='credit' THEN amount ELSE 0 END),0) AS credit,
                       COALESCE(SUM(CASE WHEN type='debit'  THEN amount ELSE 0 END),0) AS debit,
                       COUNT(*) AS txn_count
                FROM transactions
                WHERE bank_id=%s AND created_at>=%s AND created_at<=%s
                GROUP BY type
            """, (b["id"], m_start, m_end))
            rows = cursor.fetchall()
            credit = sum(int(r["credit"]) for r in rows)
            debit  = sum(int(r["debit"])  for r in rows)
            count  = sum(int(r["txn_count"]) for r in rows)

            cursor.execute("""
                SELECT created_at, type, description, amount
                FROM transactions
                WHERE bank_id=%s AND created_at>=%s AND created_at<=%s
                ORDER BY created_at DESC LIMIT 15
            """, (b["id"], m_start, m_end))
            txns = cursor.fetchall()

            bank_details.append(dict(
                name=b["bank_name"],
                account_name=b["account_name"],
                account_number=b["account_number"],
                balance=int(b["balance"]),
                credit=credit, debit=debit, net=credit-debit,
                txn_count=count,
                transactions=txns,
            ))

    return dict(user_name=user_name, year=year, month=month,
                m_start=m_start, m_end=m_end, banks=bank_details)


# ── PDF BUILDERS ──────────────────────────────────────────────────────────────

def build_monthly_statement(data: dict) -> bytes:
    """Full monthly statement: summary, income, expenses by category, transaction log."""
    buf  = io.BytesIO()
    doc  = _doc(buf, f"Budget Right — {data['m_start'].strftime('%B %Y')} Statement")
    S    = _styles()
    story = []
    inner_w = W - LM - RM
    month_label = data["m_start"].strftime("%B %Y")

    # ── Cover header ──────────────────────────────────────────────────────────
    story += _header_block(S, "Monthly Statement", month_label, data["user_name"])
    story.append(Spacer(1, 4 * mm))

    # ── Key metrics row ───────────────────────────────────────────────────────
    sr_str = f"{data['savings_rate']:.1f}%" if data["savings_rate"] is not None else "—"
    sr_color = TEAL if (data["savings_rate"] or 0) >= 10 else RED
    metrics = [
        ("Total Income",    _ngn(data["income"]),  TEAL),
        ("Total Spent",     _ngn(data["spent"]),   RED),
        ("Net Saved",       _ngn(data["net"]),      TEAL if data["net"] >= 0 else RED),
        ("Savings Rate",    sr_str,                 sr_color),
        ("No-Spend Days",   str(data["no_spend_days"]), TEAL),
    ]
    story.append(_metric_row(S, metrics, inner_w))
    story.append(Spacer(1, 4 * mm))

    # ── vs Previous month ─────────────────────────────────────────────────────
    if data["prev_spent"] > 0:
        diff = data["spent"] - data["prev_spent"]
        direction = "more" if diff > 0 else "less"
        story.append(Paragraph(
            f"Spending vs last month: <b>NGN {abs(diff):,} {direction}</b> "
            f"(last month: NGN {data['prev_spent']:,})",
            S["body"]
        ))

    # ── Monthly budget bar ────────────────────────────────────────────────────
    if data["limit"] > 0:
        pct_used = min(data["spent"] / data["limit"] * 100, 100)
        bar_color = "#c0392b" if pct_used >= 100 else ("#f39c12" if pct_used >= 80 else "#0e7c5b")
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"Monthly budget: {_bar_html(pct_used, bar_color)} of NGN {data['limit']:,}",
            S["body"]
        ))

    # ── Category breakdown ────────────────────────────────────────────────────
    story += _section_heading(S, "Spending by Category")
    if data["categories"]:
        cat_rows = []
        for c in data["categories"]:
            pct = round(int(c["total"]) / max(data["spent"], 1) * 100, 1)
            cat_rows.append([
                str(c["cat"] or "Uncategorised"),
                str(int(c["cnt"])),
                _ngn(int(c["total"])),
                f"{pct:.1f}%",
            ])
        story.append(_std_table(
            S,
            ["Category", "Transactions", "Amount", "% of Spend"],
            cat_rows,
            [inner_w * 0.45, inner_w * 0.15, inner_w * 0.22, inner_w * 0.18],
        ))
    else:
        story.append(Paragraph("No expenses recorded this month.", S["body"]))

    # ── Income detail ─────────────────────────────────────────────────────────
    story += _section_heading(S, "Income Received")
    if data["income_rows"]:
        inc_rows = [
            [str(r["created_at"]),
             str(r["description"] or "").replace("Income: ", "")[:40],
             str(r["bank_name"]),
             _ngn(int(r["amount"]))]
            for r in data["income_rows"]
        ]
        story.append(_std_table(
            S,
            ["Date", "Source", "Bank", "Amount"],
            inc_rows,
            [inner_w * 0.18, inner_w * 0.40, inner_w * 0.22, inner_w * 0.20],
        ))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"<b>Total income: {_ngn(data['income'])}</b>",
            S["green"]
        ))
    else:
        story.append(Paragraph("No income recorded this month.", S["body"]))

    # ── Expense log ───────────────────────────────────────────────────────────
    story += _section_heading(S, "Expense Log")
    if data["expenses"]:
        exp_rows = [
            [str(r["created_at"]),
             str(r["name"] or "")[:30],
             str(r["cat"] or "")[:20],
             str(r["bank_name"]),
             _ngn(int(r["amount"]))]
            for r in data["expenses"]
        ]
        story.append(_std_table(
            S,
            ["Date", "Description", "Category", "Bank", "Amount"],
            exp_rows,
            [inner_w*0.14, inner_w*0.28, inner_w*0.20, inner_w*0.20, inner_w*0.18],
        ))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"<b>Total expenses: {_ngn(data['spent'])}</b>",
            S["red"]
        ))
    else:
        story.append(Paragraph("No expenses recorded this month.", S["body"]))

    story += _footer_note(
        S,
        f"Budget Right — {data['user_name']} — {month_label} Statement — "
        f"Generated {datetime.now().strftime('%d %b %Y %H:%M')} — Confidential"
    )

    doc.build(story)
    return buf.getvalue()


def build_goal_progress_report(data: dict) -> bytes:
    """Savings goal progress report with per-goal progress bars and contribution history."""
    buf   = io.BytesIO()
    doc   = _doc(buf, "Budget Right — Goal Progress Report")
    S     = _styles()
    story = []
    inner_w = W - LM - RM
    today = date.today()

    story += _header_block(S, "Goal Progress Report",
                           f"As of {today.strftime('%d %B %Y')}", data["user_name"])
    story.append(Spacer(1, 4 * mm))

    # Overall summary metrics
    if data["goals"]:
        active_count    = sum(1 for g in data["goals"] if g["status"] == "active")
        completed_count = sum(1 for g in data["goals"] if g["status"] == "completed")
        overall_pct     = (data["total_saved"] / data["total_target"] * 100
                           if data["total_target"] else 0)
        metrics = [
            ("Active Goals",     str(active_count),               DARK_NAVY),
            ("Completed Goals",  str(completed_count),             TEAL),
            ("Total Saved",      _ngn(data["total_saved"]),        TEAL),
            ("Total Target",     _ngn(data["total_target"]),       DARK_NAVY),
            ("Overall Progress", f"{overall_pct:.1f}%",            TEAL),
        ]
        story.append(_metric_row(S, metrics, inner_w))
        story.append(Spacer(1, 4 * mm))
    else:
        story.append(Paragraph("No savings goals have been created yet.", S["body"]))
        doc.build(story)
        return buf.getvalue()

    # Per-goal sections
    active_goals    = [g for g in data["goals"] if g["status"] == "active"]
    completed_goals = [g for g in data["goals"] if g["status"] == "completed"]

    for section_label, goal_list in [("Active Goals", active_goals),
                                      ("Completed Goals", completed_goals)]:
        if not goal_list:
            continue
        story += _section_heading(S, section_label)

        for g in goal_list:
            target   = int(g["target_amount"])
            saved    = int(g["current_amount"])
            shortfall = max(target - saved, 0)
            pct       = min(saved / target * 100, 100) if target else 0
            is_done   = g["status"] == "completed"
            bar_color = "#0e7c5b" if is_done else ("#f39c12" if pct >= 50 else "#3498db")

            # Goal name + bar
            goal_block = [
                Paragraph(f"<b>{g['name']}</b>", S["h2"]),
                Paragraph(
                    f"Saved: {_ngn(saved)} of {_ngn(target)} &nbsp;|&nbsp; "
                    f"{'Completed!' if is_done else f'NGN {shortfall:,} remaining'}",
                    S["body"]
                ),
                Paragraph(_bar_html(pct, bar_color), S["body"]),
            ]

            # Weekly save suggestion for active goals
            if not is_done and shortfall > 0:
                weekly_12 = int(shortfall / 12)
                weekly_26 = int(shortfall / 26)
                goal_block.append(Paragraph(
                    f"Save <b>NGN {weekly_12:,}/week</b> to reach this in 3 months, "
                    f"or <b>NGN {weekly_26:,}/week</b> for 6 months.",
                    S["small"]
                ))

            # Contribution history
            contribs = data["contributions"].get(g["id"], [])
            if contribs:
                goal_block.append(Spacer(1, 2 * mm))
                goal_block.append(Paragraph("Recent contributions:", S["label"]))
                contrib_rows = [
                    [str(c["contributed_at"]), str(c["bank_name"]), _ngn(int(c["amount"]))]
                    for c in contribs
                ]
                goal_block.append(_std_table(
                    S,
                    ["Date", "From Bank", "Amount"],
                    contrib_rows,
                    [inner_w * 0.30, inner_w * 0.42, inner_w * 0.28],
                ))

            story.append(KeepTogether(goal_block + [Spacer(1, 4 * mm)]))

    story += _footer_note(
        S,
        f"Budget Right — {data['user_name']} — Goal Progress Report — "
        f"Generated {datetime.now().strftime('%d %b %Y %H:%M')} — Confidential"
    )

    doc.build(story)
    return buf.getvalue()


def build_category_budget_report(data: dict) -> bytes:
    """Category budget vs actual spend report."""
    buf   = io.BytesIO()
    month_label = date(data["year"], data["month"], 1).strftime("%B %Y")
    doc   = _doc(buf, f"Budget Right — Category Budget Report {month_label}")
    S     = _styles()
    story = []
    inner_w = W - LM - RM

    story += _header_block(S, "Category Budget Report", month_label, data["user_name"])
    story.append(Spacer(1, 4 * mm))

    cats = data["categories"]
    if not cats:
        story.append(Paragraph(
            "No category budgets have been set. Go to Settings to configure monthly category limits.",
            S["body"]
        ))
        doc.build(story)
        return buf.getvalue()

    # Summary metrics
    total_budget = sum(int(c["monthly_limit"]) for c in cats)
    total_spent  = sum(int(c["spent"]) for c in cats)
    total_remain = max(total_budget - total_spent, 0)
    over_count   = sum(1 for c in cats if int(c["spent"]) > int(c["monthly_limit"]))
    metrics = [
        ("Total Budgeted",     _ngn(total_budget),  DARK_NAVY),
        ("Total Spent",        _ngn(total_spent),   RED if total_spent > total_budget else TEAL),
        ("Remaining",          _ngn(total_remain),  TEAL),
        ("Categories Over",    str(over_count),     RED if over_count else TEAL),
    ]
    story.append(_metric_row(S, metrics, inner_w))
    story.append(Spacer(1, 4 * mm))

    # Per-category table
    story += _section_heading(S, "Budget vs Actual by Category")

    table_rows = []
    for c in sorted(cats, key=lambda x: int(x["spent"]), reverse=True):
        limit    = int(c["monthly_limit"])
        spent    = int(c["spent"])
        remain   = max(limit - spent, 0)
        pct      = min(spent / limit * 100, 100) if limit else 0
        over     = spent > limit
        bar_color = "#c0392b" if pct >= 100 else ("#f39c12" if pct >= 80 else "#0e7c5b")
        table_rows.append([
            c["category"],
            _ngn(limit),
            _ngn(spent),
            f"-{_ngn(abs(spent - limit))}" if over else _ngn(remain),
            _bar_html(pct, bar_color),
        ])

    story.append(_std_table(
        S,
        ["Category", "Budget", "Spent", "Remaining / Over", "Usage"],
        table_rows,
        [inner_w*0.24, inner_w*0.18, inner_w*0.18, inner_w*0.18, inner_w*0.22],
    ))

    # Overspent alert box
    overspent = [c for c in cats if int(c["spent"]) > int(c["monthly_limit"])]
    if overspent:
        story.append(Spacer(1, 4 * mm))
        story += _section_heading(S, "Over-Budget Categories")
        for c in overspent:
            excess = int(c["spent"]) - int(c["monthly_limit"])
            story.append(Paragraph(
                f"<b>{c['category']}</b>: spent {_ngn(int(c['spent']))} "
                f"vs {_ngn(int(c['monthly_limit']))} budget — "
                f"<b>over by {_ngn(excess)}</b> "
                f"({round(excess / int(c['monthly_limit']) * 100):.0f}% above limit).",
                S["body"]
            ))

    story += _footer_note(
        S,
        f"Budget Right — {data['user_name']} — Category Budget Report — {month_label} — "
        f"Generated {datetime.now().strftime('%d %b %Y %H:%M')} — Confidential"
    )

    doc.build(story)
    return buf.getvalue()


def build_bank_report(data: dict) -> bytes:
    """Bank-by-bank statement with per-bank totals and recent transactions."""
    buf   = io.BytesIO()
    month_label = date(data["year"], data["month"], 1).strftime("%B %Y")
    doc   = _doc(buf, f"Budget Right — Bank Report {month_label}")
    S     = _styles()
    story = []
    inner_w = W - LM - RM

    story += _header_block(S, "Bank-by-Bank Report", month_label, data["user_name"])
    story.append(Spacer(1, 4 * mm))

    banks = data["banks"]
    if not banks:
        story.append(Paragraph("No bank accounts found.", S["body"]))
        doc.build(story)
        return buf.getvalue()

    # Portfolio summary
    total_balance = sum(b["balance"] for b in banks)
    total_in      = sum(b["credit"]  for b in banks)
    total_out     = sum(b["debit"]   for b in banks)
    total_txns    = sum(b["txn_count"] for b in banks)
    metrics = [
        ("Total Balance",     _ngn(total_balance), TEAL),
        ("Money In",          _ngn(total_in),      TEAL),
        ("Money Out",         _ngn(total_out),      RED),
        ("Transactions",      str(total_txns),      DARK_NAVY),
        ("Bank Accounts",     str(len(banks)),       DARK_NAVY),
    ]
    story.append(_metric_row(S, metrics, inner_w))
    story.append(Spacer(1, 4 * mm))

    # Bank comparison table
    story += _section_heading(S, "Bank Summary")
    summary_rows = []
    for b in sorted(banks, key=lambda x: x["balance"], reverse=True):
        net_color = "green" if b["net"] >= 0 else "red"
        summary_rows.append([
            b["name"],
            f"****{b['account_number']}",
            _ngn(b["credit"]),
            _ngn(b["debit"]),
            f"+{_ngn(b['net'])}" if b["net"] >= 0 else f"-{_ngn(abs(b['net']))}",
            _ngn(b["balance"]),
        ])
    story.append(_std_table(
        S,
        ["Bank", "Account", "Money In", "Money Out", "Net", "Balance"],
        summary_rows,
        [inner_w*0.24, inner_w*0.14, inner_w*0.16, inner_w*0.16, inner_w*0.14, inner_w*0.16],
    ))
    story.append(Spacer(1, 4 * mm))

    # Per-bank detailed sections
    story += _section_heading(S, "Transaction Detail by Bank")
    for b in banks:
        bank_block = [
            Paragraph(f"<b>{b['name']}</b> — {b['account_name']} (****{b['account_number']})",
                      S["h2"]),
            Paragraph(
                f"Current balance: <b>{_ngn(b['balance'])}</b> &nbsp;|&nbsp; "
                f"Money in: {_ngn(b['credit'])} &nbsp;|&nbsp; "
                f"Money out: {_ngn(b['debit'])} &nbsp;|&nbsp; "
                f"{b['txn_count']} transaction{'s' if b['txn_count'] != 1 else ''} this month",
                S["body"]
            ),
        ]
        if b["transactions"]:
            txn_rows = []
            for t in b["transactions"]:
                is_credit = t["type"] == "credit"
                amt_str   = f"+{_ngn(int(t['amount']))}" if is_credit else f"-{_ngn(int(t['amount']))}"
                txn_rows.append([
                    str(t["created_at"]),
                    "Credit" if is_credit else "Debit",
                    str(t["description"] or "")[:45],
                    amt_str,
                ])
            bank_block.append(_std_table(
                S,
                ["Date", "Type", "Description", "Amount"],
                txn_rows,
                [inner_w*0.18, inner_w*0.12, inner_w*0.52, inner_w*0.18],
            ))
        else:
            bank_block.append(Paragraph("No transactions this month.", S["small"]))

        bank_block.append(Spacer(1, 4 * mm))
        story.append(KeepTogether(bank_block[:3]))  # header + stats always together
        story.extend(bank_block[3:])               # table can flow across pages

    story += _footer_note(
        S,
        f"Budget Right — {data['user_name']} — Bank Report — {month_label} — "
        f"Generated {datetime.now().strftime('%d %b %Y %H:%M')} — Confidential"
    )

    doc.build(story)
    return buf.getvalue()
