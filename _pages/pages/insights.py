# _pages/insights.py
# Smart Insights page — renders all AI-style financial insights for the user
import streamlit as st
from datetime import datetime
from smart_insights import generate_all_insights


# ── category colours & order ──────────────────────────────────────────────────
_CAT_META = {
    "warning":  {"label": "⚠️ Warnings",       "bg": "#fff0f0", "border": "#c0392b", "badge_bg": "#c0392b"},
    "spending": {"label": "📊 Spending Patterns","bg": "#fffbea", "border": "#f39c12", "badge_bg": "#e67e22"},
    "goal":     {"label": "🎯 Goal Suggestions", "bg": "#f0f7ff", "border": "#2980b9", "badge_bg": "#2980b9"},
    "saving":   {"label": "💚 Saving Wins",      "bg": "#f0faf4", "border": "#0e7c5b", "badge_bg": "#0e7c5b"},
    "habit":    {"label": "🏅 Habits",           "bg": "#f8f4ff", "border": "#8e44ad", "badge_bg": "#8e44ad"},
}
_CAT_ORDER = ["warning", "spending", "goal", "saving", "habit"]


def render_insights(user_id: int):
    st.title("💡 Smart Insights")
    st.caption("Personalised financial observations updated every time you visit this page.")

    # ── Generate ──────────────────────────────────────────────────────────────
    with st.spinner("Analysing your financial data…"):
        insights = generate_all_insights(user_id)

    if not insights:
        st.info(
            "Not enough data to generate insights yet. "
            "Log some income, expenses, and savings goals — then come back here."
        )
        return

    # ── Summary bar ───────────────────────────────────────────────────────────
    counts = {}
    for i in insights:
        counts[i["category"]] = counts.get(i["category"], 0) + 1

    warn_count = counts.get("warning", 0)
    if warn_count:
        st.error(
            f"🚨 **{warn_count} warning{'s' if warn_count > 1 else ''}** need your attention — "
            f"see the Warnings section below.",
            icon=None,
        )

    total = len(insights)
    mc = st.columns(len(_CAT_ORDER))
    for col, cat in zip(mc, _CAT_ORDER):
        meta = _CAT_META[cat]
        n = counts.get(cat, 0)
        col.markdown(
            f"<div style='background:{meta['badge_bg']};color:#fff;border-radius:8px;"
            f"padding:8px 4px;text-align:center'>"
            f"<div style='font-size:1.1rem'>{meta['label'].split()[0]}</div>"
            f"<div style='font-size:1.4rem;font-weight:800'>{n}</div>"
            f"<div style='font-size:0.72rem;opacity:0.85'>{meta['label'].split(' ',1)[1]}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Filter controls ───────────────────────────────────────────────────────
    available_cats = [c for c in _CAT_ORDER if counts.get(c, 0) > 0]
    all_labels     = ["All"] + [_CAT_META[c]["label"] for c in available_cats]
    selected_label = st.radio(
        "Filter by type", all_labels, horizontal=True, key="insights_filter"
    )
    label_to_cat = {_CAT_META[c]["label"]: c for c in available_cats}
    selected_cat = label_to_cat.get(selected_label)  # None means "All"

    # ── Render insight cards ──────────────────────────────────────────────────
    shown = [i for i in insights if selected_cat is None or i["category"] == selected_cat]

    if selected_cat is None:
        # Group by category in order
        for cat in _CAT_ORDER:
            cat_insights = [i for i in shown if i["category"] == cat]
            if not cat_insights:
                continue
            meta = _CAT_META[cat]
            st.markdown(f"### {meta['label']}")
            for ins in cat_insights:
                _render_card(ins, meta)
    else:
        meta = _CAT_META[selected_cat]
        for ins in shown:
            _render_card(ins, meta)

    st.divider()
    st.caption(
        f"💡 {total} insight{'s' if total > 1 else ''} generated · "
        f"Based on your transactions, goals, and budget settings · "
        f"Refreshed {datetime.now().strftime('%d %b %Y %H:%M')}"
    )


def _render_card(ins: dict, meta: dict):
    action_html = (
        f"<div style='margin-top:6px'>"
        f"<span style='background:{meta['badge_bg']};color:#fff;border-radius:20px;"
        f"padding:3px 12px;font-size:0.78rem;font-weight:700'>"
        f"→ {ins['action']}</span></div>"
        if ins.get("action") else ""
    )
    st.markdown(
        f"""<div style='background:{meta['bg']};border-left:5px solid {meta['border']};
        border-radius:10px;padding:14px 18px;margin-bottom:10px;
        box-shadow:0 1px 4px rgba(0,0,0,0.06)'>
        <div style='display:flex;align-items:flex-start;gap:12px'>
          <span style='font-size:1.6rem;line-height:1'>{ins['icon']}</span>
          <div style='flex:1'>
            <div style='font-weight:700;font-size:0.97rem;color:#1a3c5e;margin-bottom:4px'>
              {ins['title']}</div>
            <div style='font-size:0.91rem;line-height:1.55;color:#333'>{ins['body']}</div>
            {action_html}
          </div>
        </div></div>""",
        unsafe_allow_html=True,
    )
