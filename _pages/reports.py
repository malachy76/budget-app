# pages/reports.py — PDF report engine for Budget Right
#
# Produces 4 report types, each as a BytesIO PDF using reportlab Platypus:
#   1. monthly_statement  — full monthly summary + transaction list
#   2. goal_progress      — all active & completed goals with progress bars
#   3. category_budget    — category budgets vs actual spend with bar charts
#   4. bank_report        — per-bank balance, income, expenses, transactions
#
# All reports share a common header/footer template with the Budget Right
# brand colours (#1a2e3b navy, #0e7c5b green).  No external fonts needed —
# Helvetica works on every platform.

import io
import calendar
from datetime import datetime, timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics import renderPDF

from db import get_db

# ── Brand colours ─────────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#1a2e3b")
GREEN   = colors.HexColor("#0e7c5b")
LIGHT   = colors.HexColor("#f4f7f6")
BORDER  = colors.HexColor("#d8eae2")
RED_C   = colors.HexColor("#c0392b")
AMBER   = colors.HexColor("#f39c12")
GREY    = colors.HexColor("#95a5a6")
WHITE   = colors.white
BLACK   = colors.HexColor("#2c3e50")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


# ── Shared style sheet ────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    s    = {}
    def add(name, **kw):
        s[name] = ParagraphStyle(name, **kw)

    add("ReportTitle",  fontName="Helvetica-Bold", fontSize=22,
        textColor=WHITE, alignment=TA_CENTER, spaceAfter=4)
    add("ReportSubtitle", fontName="Helvetica", fontSize=11,
        textColor=colors.HexColor("#a8d8c8"), alignment=TA_CENTER, spaceAfter=2)
    add("ReportMeta",   fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#a8d8c8"), alignment=TA_CENTER, spaceAfter=0)
    add("H1",    fontName="Helvetica-Bold",  fontSize=14,
        textColor=NAVY, spaceBefore=14, spaceAfter=6)
    add("H2",    fontName="Helvetica-Bold",  fontSize=11,
        textColor=GREEN, spaceBefore=10, spaceAfter=4)
    add("Body",  fontName="Helvetica",       fontSize=9,
        textColor=BLACK, leading=14)
    add("BodyBold", fontName="Helvetica-Bold", fontSize=9, textColor=BLACK)
    add("Small", fontName="Helvetica",       fontSize=8,  textColor=GREY)
    add("RightBold", fontName="Helvetica-Bold", fontSize=9,
        textColor=BLACK, alignment=TA_RIGHT)
    add("GreenBold", fontName="Helvetica-Bold", fontSize=10, textColor=GREEN)
    add("RedBold",   fontName="Helvetica-Bold", fontSize=10, textColor=RED_C)
    add("NavyBold",  fontName="Helvetica-Bold", fontSize=10, textColor=NAVY)
    return s


# ── Header banner ─────────────────────────────────────────────────────────────
def _header_banner(title: str, subtitle: str, meta: str) -> list:
    """Gradient-like banner using a coloured table cell."""
    S = _styles()
    data = [[
        Paragraph(f"Budget Right", S["ReportTitle"]),
        Paragraph(title,    S["ReportSubtitle"]),
        Paragraph(subtitle, S["ReportMeta"]),
        Paragraph(meta,     S["ReportMeta"]),
    ]]
    t = Table([[Paragraph(f"<b>Budget Right</b>", S["ReportTitle"])],
               [Paragraph(title,    S["ReportSubtitle"])],
               [Paragraph(subtitle, S["ReportMeta"])],
               [Paragraph(meta,     S["ReportMeta"])]],
              colWidths=[PAGE_W - 2 * MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), NAVY),
        ("TOPPADDING",  (0,0), (-1,0),  14),
        ("BOTTOMPADDING",(0,-1),(-1,-1),14),
        ("LEFTPADDING", (0,0), (-1,-1), 20),
        ("RIGHTPADDING",(0,0), (-1,-1), 20),
        ("ROUNDEDCORNERS", [6]),
    ]))
    return [t, Spacer(1, 10)]


# ── Metric summary row ────────────────────────────────────────────────────────
def _metric_table(metrics: list) -> Table:
    """
    metrics: list of (label, value, colour) tuples — rendered as a 1-row grid.
    """
    S = _styles()
    n = len(metrics)
    col_w = (PAGE_W - 2 * MARGIN) / n
    cells = []
    for label, value, col in metrics:
        val_style = ParagraphStyle("mv", fontName="Helvetica-Bold", fontSize=14,
                                   textColor=col, alignment=TA_CENTER)
        lbl_style = ParagraphStyle("ml", fontName="Helvetica", fontSize=8,
                                   textColor=GREY, alignment=TA_CENTER)
        cells.append([Paragraph(value, val_style),
                      Paragraph(label, lbl_style)])
    t = Table([cells], colWidths=[col_w] * n)
    t.setStyle(TableStyle([
        ("BOX",           (0,0), (-1,-1), 0.5, BORDER),
        ("INNERGRID",     (0,0), (-1,-1), 0.5, BORDER),
        ("BACKGROUND",    (0,0), (-1,-1), LIGHT),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [LIGHT]),
    ]))
    return t


# ── Progress bar (drawn inline) ───────────────────────────────────────────────
def _progress_bar(pct: float, width_pts: float = 160,
                  height_pts: float = 10) -> Drawing:
    """Return a Drawing of a horizontal progress bar."""
    pct   = max(0.0, min(pct, 100.0))
    fill  = RED_C if pct >= 100 else (AMBER if pct >= 80 else GREEN)
    d     = Drawing(width_pts, height_pts)
    # Background
    d.add(Rect(0, 0, width_pts, height_pts,
               fillColor=BORDER, strokeColor=None, rx=3, ry=3))
    # Filled portion
    filled_w = width_pts * pct / 100
    if filled_w > 0:
        d.add(Rect(0, 0, filled_w, height_pts,
                   fillColor=fill, strokeColor=None, rx=3, ry=3))
    return d


# ── Styled data table ─────────────────────────────────────────────────────────
def _data_table(headers: list, rows: list, col_widths: list = None) -> Table:
    S   = _styles()
    available = PAGE_W - 2 * MARGIN
    if col_widths is None:
        col_widths = [available / len(headers)] * len(headers)
    header_row = [Paragraph(f"<b>{h}</b>", S["Small"]) for h in headers]
    body_rows  = []
    for row in rows:
        body_rows.append([
            Paragraph(str(cell) if cell is not None else "", S["Small"])
            for cell in row
        ])
    t = Table([header_row] + body_rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),   NAVY),
        ("TEXTCOLOR",     (0,0), (-1,0),   WHITE),
        ("FONTNAME",      (0,0), (-1,0),   "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1),  8),
        ("ROWBACKGROUNDS",(0,1), (-1,-1),  [WHITE, LIGHT]),
        ("INNERGRID",     (0,0), (-1,-1),  0.3, BORDER),
        ("BOX",           (0,0), (-1,-1),  0.5, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1),  4),
        ("BOTTOMPADDING", (0,0), (-1,-1),  4),
        ("LEFTPADDING",   (0,0), (-1,-1),  6),
        ("RIGHTPADDING",  (0,0), (-1,-1),  6),
        ("VALIGN",        (0,0), (-1,-1),  "MIDDLE"),
    ]))
    return t


# ── Footer callback ───────────────────────────────────────────────────────────
class _FooterCanvas:
    """Draws page number and generated-at footer on every page."""
    def __init__(self, generated_at: str):
        self.generated_at = generated_at

    def __call__(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        footer_text = (
            f"Budget Right  |  Generated {self.generated_at}  |  "
            f"Page {doc.page}"
        )
        canvas.drawCentredString(PAGE_W / 2, 10 * mm, footer_text)
        # Top accent line
        canvas.setStrokeColor(GREEN)
        canvas.setLineWidth(2)
        canvas.line(MARGIN, PAGE_H - 8 * mm, PAGE_W - MARGIN, PAGE_H - 8 * mm)
        canvas.restoreState()


# ── Helper: naira format ──────────────────────────────────────────────────────
def _ngn(amount: int) -> str:
    return f"NGN {int(amount):,}"


# ═════════════════════════════════════════════════════════════════════════════
# REPORT 1 — Monthly Statement
# ═════════════════════════════════════════════════════════════════════════════

def build_monthly_statement(user_id: int, year: int, month: int) -> bytes:
    """Full monthly statement: summary, category breakdown, transaction list."""
    import calendar as _cal
    from datetime import date

    month_start = date(year, month, 1)
    month_end   = date(year, month, _cal.monthrange(year, month)[1])
    month_label = month_start.strftime("%B %Y")
    generated   = datetime.now().strftime("%d %b %Y %H:%M")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT surname, other_names FROM users WHERE id=%s", (user_id,))
        user_row = cursor.fetchone()
        full_name = f"{user_row['surname']} {user_row['other_names']}" if user_row else "User"

        # Totals
        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
                COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
        """, (user_id, month_start, month_end))
        totals = cursor.fetchone()
        total_income = int(totals["income"] or 0)
        total_spent  = int(totals["spent"]  or 0)
        net_saved    = total_income - total_spent
        savings_rate = round(net_saved / total_income * 100, 1) if total_income > 0 else 0.0

        # Category breakdown
        cursor.execute("""
            SELECT COALESCE(e.category, e.name) AS cat,
                   COUNT(*) AS cnt, SUM(e.amount) AS total
            FROM expenses e JOIN banks b ON e.bank_id=b.id
            WHERE b.user_id=%s AND e.created_at>=%s AND e.created_at<=%s
            GROUP BY cat ORDER BY total DESC
        """, (user_id, month_start, month_end))
        cat_rows = cursor.fetchall()

        # Transaction list (debit)
        cursor.execute("""
            SELECT t.created_at, t.description, b.bank_name, t.type, t.amount
            FROM transactions t JOIN banks b ON t.bank_id=b.id
            WHERE b.user_id=%s AND t.created_at>=%s AND t.created_at<=%s
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT 200
        """, (user_id, month_start, month_end))
        txn_rows = cursor.fetchall()

        # Bank balances
        cursor.execute("""
            SELECT bank_name, account_number, balance
            FROM banks WHERE user_id=%s ORDER BY bank_name
        """, (user_id,))
        banks = cursor.fetchall()

    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 4*mm, bottomMargin=MARGIN,
        title=f"Budget Right — {month_label} Statement",
        author="Budget Right"
    )
    footer_cb = _FooterCanvas(generated)
    story = []

    # ── Cover banner ──────────────────────────────────────────────────────────
    story += _header_banner(
        f"Monthly Statement — {month_label}",
        full_name,
        f"Generated {generated}"
    )

    # ── Summary metrics ───────────────────────────────────────────────────────
    story.append(Paragraph("Financial Summary", S["H1"]))
    net_col = GREEN if net_saved >= 0 else RED_C
    story.append(_metric_table([
        ("Total Income",  _ngn(total_income), GREEN),
        ("Total Spent",   _ngn(total_spent),  RED_C),
        ("Net Saved",     _ngn(net_saved),    net_col),
        ("Savings Rate",  f"{savings_rate}%", GREEN if savings_rate >= 20 else
                                              (AMBER if savings_rate >= 0 else RED_C)),
    ]))
    story.append(Spacer(1, 8))

    # ── Bank balances ─────────────────────────────────────────────────────────
    if banks:
        story.append(Paragraph("Bank Account Balances", S["H2"]))
        bk_rows = [(b["bank_name"],
                    f"****{b['account_number']}",
                    _ngn(b["balance"])) for b in banks]
        story.append(_data_table(
            ["Bank", "Account", "Balance"],
            bk_rows,
            col_widths=[90*mm, 60*mm, 50*mm]
        ))
        story.append(Spacer(1, 8))

    # ── Category breakdown ────────────────────────────────────────────────────
    if cat_rows:
        story.append(Paragraph("Spending by Category", S["H1"]))
        total_all = sum(int(r["total"]) for r in cat_rows) or 1
        cat_table_rows = []
        for r in cat_rows:
            amt  = int(r["total"])
            pct  = round(amt / total_all * 100, 1)
            cat_table_rows.append((
                r["cat"] or "Uncategorised",
                str(int(r["cnt"])),
                _ngn(amt),
                f"{pct}%",
            ))
        story.append(_data_table(
            ["Category", "Transactions", "Amount (NGN)", "% of Total"],
            cat_table_rows,
            col_widths=[90*mm, 40*mm, 60*mm, 30*mm]
        ))
        story.append(Spacer(1, 8))

    # ── Transaction list ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("All Transactions", S["H1"]))
    story.append(Paragraph(
        f"Showing up to 200 transactions for {month_label}.",
        S["Small"]
    ))
    story.append(Spacer(1, 6))
    if txn_rows:
        txn_table_rows = []
        for r in txn_rows:
            sign = "+" if r["type"] == "credit" else "-"
            desc = (r["description"] or "")[:50]
            txn_table_rows.append((
                str(r["created_at"]),
                desc,
                r["bank_name"],
                f"{sign}NGN {int(r['amount']):,}",
            ))
        story.append(_data_table(
            ["Date", "Description", "Bank", "Amount"],
            txn_table_rows,
            col_widths=[28*mm, 90*mm, 42*mm, 40*mm]
        ))
    else:
        story.append(Paragraph("No transactions recorded for this period.", S["Body"]))

    doc.build(story, onLaterPages=footer_cb, onFirstPage=footer_cb)
    return buf.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
# REPORT 2 — Goal Progress Report
# ═════════════════════════════════════════════════════════════════════════════

def build_goal_progress_report(user_id: int) -> bytes:
    generated = datetime.now().strftime("%d %b %Y %H:%M")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT surname, other_names FROM users WHERE id=%s", (user_id,))
        user_row = cursor.fetchone()
        full_name = f"{user_row['surname']} {user_row['other_names']}" if user_row else "User"

        cursor.execute("""
            SELECT g.id, g.name, g.target_amount, g.current_amount, g.status, g.created_at
            FROM goals g WHERE g.user_id=%s ORDER BY g.status, g.created_at
        """, (user_id,))
        goals = cursor.fetchall()

        # Contribution history per goal
        cursor.execute("""
            SELECT gc.goal_id, gc.contributed_at, gc.amount, b.bank_name
            FROM goal_contributions gc JOIN banks b ON gc.bank_id=b.id
            WHERE gc.user_id=%s ORDER BY gc.contributed_at DESC
        """, (user_id,))
        contribs_all = cursor.fetchall()

    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 4*mm, bottomMargin=MARGIN,
        title="Budget Right — Goal Progress Report",
        author="Budget Right"
    )
    footer_cb = _FooterCanvas(generated)
    story = []

    story += _header_banner(
        "Savings Goal Progress Report",
        full_name,
        f"Generated {generated}"
    )

    active    = [g for g in goals if g["status"] == "active"]
    completed = [g for g in goals if g["status"] == "completed"]

    if not goals:
        story.append(Paragraph("No savings goals found.", S["Body"]))
    else:
        # Summary metrics
        total_target  = sum(int(g["target_amount"]) for g in active)
        total_saved   = sum(int(g["current_amount"]) for g in goals)
        story.append(_metric_table([
            ("Active Goals",     str(len(active)),           NAVY),
            ("Completed Goals",  str(len(completed)),        GREEN),
            ("Total Target",     _ngn(total_target),         NAVY),
            ("Total Saved",      _ngn(total_saved),          GREEN),
        ]))
        story.append(Spacer(1, 12))

        # Build a dict of contributions by goal_id
        contribs_by_goal = {}
        for c in contribs_all:
            contribs_by_goal.setdefault(c["goal_id"], []).append(c)

        for section_label, goal_list in [("Active Goals", active), ("Completed Goals", completed)]:
            if not goal_list:
                continue
            story.append(Paragraph(section_label, S["H1"]))

            for g in goal_list:
                target  = int(g["target_amount"])
                saved   = int(g["current_amount"])
                pct     = round(saved / target * 100, 1) if target > 0 else 0.0
                shortfall = max(target - saved, 0)
                bar_w   = 150  # pts

                # Goal name + progress bar block
                name_para = Paragraph(f"<b>{g['name']}</b>", S["H2"])
                pbar = _progress_bar(pct, width_pts=bar_w)

                pct_col = GREEN if pct >= 100 else (AMBER if pct >= 50 else RED_C)
                pct_para = Paragraph(f"<b>{pct:.0f}%</b>", ParagraphStyle(
                    "pct", fontName="Helvetica-Bold", fontSize=11,
                    textColor=pct_col, alignment=TA_LEFT))

                details = Paragraph(
                    f"Saved: {_ngn(saved)}  &nbsp;&nbsp;  "
                    f"Target: {_ngn(target)}  &nbsp;&nbsp;  "
                    f"{'Completed!' if g['status']=='completed' else f'Still needed: {_ngn(shortfall)}'}",
                    S["Small"]
                )
                started = Paragraph(f"Started: {g['created_at']}", S["Small"])

                block = Table([
                    [name_para],
                    [[pbar, Spacer(8, 1), pct_para]],
                    [details],
                    [started],
                ], colWidths=[PAGE_W - 2*MARGIN])
                block.setStyle(TableStyle([
                    ("BACKGROUND",    (0,0), (-1,-1), LIGHT),
                    ("BOX",           (0,0), (-1,-1), 0.5, BORDER),
                    ("TOPPADDING",    (0,0), (-1,-1), 5),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                    ("LEFTPADDING",   (0,0), (-1,-1), 10),
                    ("RIGHTPADDING",  (0,0), (-1,-1), 10),
                    ("ROUNDEDCORNERS", [4]),
                ]))

                # Contribution history for this goal
                goal_contribs = contribs_by_goal.get(g["id"], [])
                contrib_rows = [
                    (str(c["contributed_at"]), c["bank_name"], _ngn(c["amount"]))
                    for c in goal_contribs[:10]
                ]
                contrib_table = _data_table(
                    ["Date", "From Bank", "Amount"],
                    contrib_rows,
                    col_widths=[40*mm, 90*mm, 50*mm]
                ) if contrib_rows else Paragraph("No contributions yet.", S["Small"])

                story.append(KeepTogether([
                    block,
                    Spacer(1, 4),
                    Paragraph("Contribution History (last 10)", S["Small"]),
                    Spacer(1, 3),
                    contrib_table,
                    Spacer(1, 12),
                ]))

    doc.build(story, onLaterPages=footer_cb, onFirstPage=footer_cb)
    return buf.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
# REPORT 3 — Category Budget Report
# ═════════════════════════════════════════════════════════════════════════════

def build_category_budget_report(user_id: int, year: int, month: int) -> bytes:
    import calendar as _cal
    from datetime import date

    month_start = date(year, month, 1)
    month_end   = date(year, month, _cal.monthrange(year, month)[1])
    month_label = month_start.strftime("%B %Y")
    generated   = datetime.now().strftime("%d %b %Y %H:%M")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT surname, other_names FROM users WHERE id=%s", (user_id,))
        user_row  = cursor.fetchone()
        full_name = f"{user_row['surname']} {user_row['other_names']}" if user_row else "User"

        cursor.execute("""
            SELECT cb.category, cb.monthly_limit,
                   COALESCE(SUM(e.amount), 0) AS spent
            FROM category_budgets cb
            LEFT JOIN expenses e ON COALESCE(e.category, e.name) = cb.category
                AND e.user_id = cb.user_id
                AND e.created_at >= %s AND e.created_at <= %s
            WHERE cb.user_id=%s AND cb.monthly_limit > 0
            GROUP BY cb.category, cb.monthly_limit
            ORDER BY spent DESC
        """, (month_start, month_end, user_id))
        budgets = cursor.fetchall()

    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 4*mm, bottomMargin=MARGIN,
        title=f"Budget Right — Category Budget Report {month_label}",
        author="Budget Right"
    )
    footer_cb = _FooterCanvas(generated)
    story = []

    story += _header_banner(
        f"Category Budget Report — {month_label}",
        full_name,
        f"Generated {generated}"
    )

    if not budgets:
        story.append(Paragraph(
            "No category budgets have been set. Go to Settings to add them.",
            S["Body"]
        ))
    else:
        total_budget = sum(int(b["monthly_limit"]) for b in budgets)
        total_spent  = sum(int(b["spent"]) for b in budgets)
        total_remain = max(total_budget - total_spent, 0)
        over_count   = sum(1 for b in budgets if int(b["spent"]) > int(b["monthly_limit"]))

        story.append(_metric_table([
            ("Categories Tracked", str(len(budgets)),     NAVY),
            ("Total Budgeted",     _ngn(total_budget),    NAVY),
            ("Total Spent",        _ngn(total_spent),     RED_C if total_spent > total_budget else GREEN),
            ("Remaining",          _ngn(total_remain),    GREEN),
            ("Over Budget",        str(over_count),       RED_C if over_count else GREEN),
        ]))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Category Detail", S["H1"]))

        bar_col_w = 100  # pts for progress bar column

        for b in budgets:
            limit = int(b["monthly_limit"])
            spent = int(b["spent"])
            remaining = max(limit - spent, 0)
            pct   = round(spent / limit * 100, 1) if limit > 0 else 0.0
            over  = spent > limit
            overspend = spent - limit if over else 0

            status_text = (
                f"OVER by {_ngn(overspend)}" if over
                else f"{pct:.0f}% used — {_ngn(remaining)} remaining"
            )
            status_col = RED_C if over else (AMBER if pct >= 80 else GREEN)
            status_para = Paragraph(
                f"<b>{status_text}</b>",
                ParagraphStyle("st", fontName="Helvetica-Bold", fontSize=8,
                               textColor=status_col)
            )

            pbar = _progress_bar(pct, width_pts=bar_col_w, height_pts=9)

            row_block = Table([
                [
                    Paragraph(f"<b>{b['category']}</b>", S["BodyBold"]),
                    Paragraph(f"Budget: {_ngn(limit)}", S["Small"]),
                    Paragraph(f"Spent: {_ngn(spent)}", S["Small"]),
                    status_para,
                ],
                [pbar, "", "", ""],
            ], colWidths=[70*mm, 45*mm, 45*mm, 40*mm])
            row_block.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), LIGHT if not over else colors.HexColor("#fff5f5")),
                ("BOX",           (0,0), (-1,-1), 0.5, RED_C if over else BORDER),
                ("SPAN",          (0,1), (-1,1)),
                ("TOPPADDING",    (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                ("LEFTPADDING",   (0,0), (-1,-1), 8),
                ("RIGHTPADDING",  (0,0), (-1,-1), 8),
                ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ]))
            story.append(row_block)
            story.append(Spacer(1, 5))

    doc.build(story, onLaterPages=footer_cb, onFirstPage=footer_cb)
    return buf.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
# REPORT 4 — Bank-by-Bank Report
# ═════════════════════════════════════════════════════════════════════════════

def build_bank_report(user_id: int, year: int, month: int) -> bytes:
    import calendar as _cal
    from datetime import date

    month_start = date(year, month, 1)
    month_end   = date(year, month, _cal.monthrange(year, month)[1])
    month_label = month_start.strftime("%B %Y")
    generated   = datetime.now().strftime("%d %b %Y %H:%M")

    with get_db() as (conn, cursor):
        cursor.execute("SELECT surname, other_names FROM users WHERE id=%s", (user_id,))
        user_row  = cursor.fetchone()
        full_name = f"{user_row['surname']} {user_row['other_names']}" if user_row else "User"

        cursor.execute("""
            SELECT id, bank_name, account_name, account_number, balance, min_balance_alert
            FROM banks WHERE user_id=%s ORDER BY bank_name
        """, (user_id,))
        banks = cursor.fetchall()

        # Per-bank monthly totals
        cursor.execute("""
            SELECT t.bank_id,
                   COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
                   COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent,
                   COUNT(*) AS txn_count
            FROM transactions t
            WHERE t.bank_id IN (SELECT id FROM banks WHERE user_id=%s)
              AND t.created_at >= %s AND t.created_at <= %s
            GROUP BY t.bank_id
        """, (user_id, month_start, month_end))
        bank_totals = {r["bank_id"]: r for r in cursor.fetchall()}

        # Per-bank transactions
        cursor.execute("""
            SELECT t.bank_id, t.created_at, t.type, t.description, t.amount
            FROM transactions t
            WHERE t.bank_id IN (SELECT id FROM banks WHERE user_id=%s)
              AND t.created_at >= %s AND t.created_at <= %s
            ORDER BY t.bank_id, t.created_at DESC
            LIMIT 300
        """, (user_id, month_start, month_end))
        all_txns = cursor.fetchall()

    # Group transactions by bank_id
    txns_by_bank = {}
    for t in all_txns:
        txns_by_bank.setdefault(t["bank_id"], []).append(t)

    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 4*mm, bottomMargin=MARGIN,
        title=f"Budget Right — Bank Report {month_label}",
        author="Budget Right"
    )
    footer_cb = _FooterCanvas(generated)
    story = []

    story += _header_banner(
        f"Bank-by-Bank Report — {month_label}",
        full_name,
        f"Generated {generated}"
    )

    if not banks:
        story.append(Paragraph("No bank accounts found.", S["Body"]))
    else:
        total_balance = sum(int(b["balance"]) for b in banks)
        story.append(_metric_table([
            ("Banks Linked",   str(len(banks)),          NAVY),
            ("Total Balance",  _ngn(total_balance),      GREEN),
        ]))
        story.append(Spacer(1, 12))

        for bank in banks:
            bid = bank["id"]
            bt  = bank_totals.get(bid, {"income": 0, "spent": 0, "txn_count": 0})
            b_income = int(bt["income"] or 0)
            b_spent  = int(bt["spent"]  or 0)
            b_net    = b_income - b_spent
            b_txns   = txns_by_bank.get(bid, [])
            alert    = int(bank["min_balance_alert"] or 0)
            balance  = int(bank["balance"])
            below_alert = alert > 0 and balance <= alert

            # Bank header card
            header_text = (
                f"<b>{bank['bank_name']}</b>  ·  "
                f"{bank['account_name']}  ·  ****{bank['account_number']}"
            )
            header_para = Paragraph(header_text, ParagraphStyle(
                "bh", fontName="Helvetica-Bold", fontSize=10,
                textColor=WHITE))
            balance_para = Paragraph(
                f"Balance: {_ngn(balance)}"
                + (f"  ⚠ Below alert ({_ngn(alert)})" if below_alert else ""),
                ParagraphStyle("bal", fontName="Helvetica-Bold", fontSize=10,
                               textColor=colors.HexColor("#f1c40f") if below_alert else
                               colors.HexColor("#a8d8c8"),
                               alignment=TA_RIGHT)
            )
            bank_hdr = Table([[header_para, balance_para]],
                             colWidths=[(PAGE_W-2*MARGIN)*0.65, (PAGE_W-2*MARGIN)*0.35])
            bank_hdr.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), NAVY),
                ("TOPPADDING",    (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ("LEFTPADDING",   (0,0), (-1,-1), 10),
                ("RIGHTPADDING",  (0,0), (-1,-1), 10),
                ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ]))
            story.append(bank_hdr)

            # Monthly metrics for this bank
            net_col = GREEN if b_net >= 0 else RED_C
            metrics_tbl = _metric_table([
                (f"{month_label} Income",  _ngn(b_income),      GREEN),
                (f"{month_label} Spent",   _ngn(b_spent),       RED_C),
                (f"{month_label} Net",     _ngn(b_net),         net_col),
                ("Transactions",           str(int(bt["txn_count"] or 0)), NAVY),
            ])
            story.append(metrics_tbl)
            story.append(Spacer(1, 6))

            # Transaction list for this bank
            if b_txns:
                story.append(Paragraph(
                    f"Transactions — {month_label} (up to 50 shown)", S["Small"]
                ))
                txn_rows = []
                for t in b_txns[:50]:
                    sign = "+" if t["type"] == "credit" else "-"
                    desc = (t["description"] or "")[:55]
                    txn_rows.append((
                        str(t["created_at"]),
                        desc,
                        "Credit" if t["type"] == "credit" else "Debit",
                        f"{sign}NGN {int(t['amount']):,}",
                    ))
                story.append(_data_table(
                    ["Date", "Description", "Type", "Amount"],
                    txn_rows,
                    col_widths=[28*mm, 100*mm, 22*mm, 40*mm]
                ))
            else:
                story.append(Paragraph(
                    f"No transactions recorded for {month_label}.", S["Small"]
                ))

            story.append(Spacer(1, 14))

    doc.build(story, onLaterPages=footer_cb, onFirstPage=footer_cb)
    return buf.getvalue()
