# styles.py — all CSS, injected once at app startup
import streamlit as st


CSS = """<style>
/* ── BASE ── */
html, body { overflow-x: hidden !important; }
.main .block-container { max-width: 100% !important; padding-top: 1rem !important; }

/* ── INSIGHT CARDS ── */
.insight-card {
    border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
    display: flex; align-items: flex-start; gap: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.insight-icon { font-size: 1.4rem; flex-shrink: 0; margin-top: 1px; }
.insight-body { flex: 1; }
.insight-title { font-weight: 700; font-size: 0.88rem; text-transform: uppercase;
    letter-spacing: 0.04em; margin-bottom: 3px; opacity: 0.7; }
.insight-text  { font-size: 0.93rem; line-height: 1.5; }

/* ── WEEKLY SUMMARY CARD ── */
.week-card {
    background: linear-gradient(135deg,#1a3c5e 0%,#0e7c5b 100%);
    border-radius: 14px; padding: 20px 22px; color: #fff; margin-bottom: 12px;
}
.week-title  { font-size: 1rem; font-weight: 700; margin-bottom: 14px; color: #a8d8c8; }
.week-grid   { display: flex; flex-wrap: wrap; gap: 10px; }
.week-stat   { background: rgba(255,255,255,0.12); border-radius: 10px;
    padding: 10px 14px; flex: 1 1 120px; min-width: 110px; }
.week-stat-label { font-size: 0.75rem; color: #a8d8c8; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em; }
.week-stat-value { font-size: 1.15rem; font-weight: 800; color: #fff; margin-top: 2px; }

/* ── GOAL PRESET CHIPS ── */
.goal-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.goal-chip  {
    background: #e8f5f0; color: #0e7c5b; border: 1.5px solid #0e7c5b;
    border-radius: 20px; padding: 5px 14px; font-size: 0.85rem; font-weight: 600;
    cursor: pointer; white-space: nowrap;
}
.goal-chip:hover { background: #0e7c5b; color: #fff; }
.goal-chip.selected { background: #0e7c5b; color: #fff; }

/* ── EXP CARDS ── */
.exp-card {
    background: #ffffff; border: 1px solid #d0e8df;
    border-left: 4px solid #0e7c5b; border-radius: 10px;
    padding: 12px 14px; margin-bottom: 8px;
    display: flex; justify-content: space-between;
    align-items: flex-start; flex-wrap: wrap; gap: 6px;
}
.exp-card-left { flex: 1 1 60%; min-width: 0; }
.exp-card-right { flex: 0 0 auto; text-align: right; }
.exp-card-name { font-weight: 700; color: #1a3c5e; font-size: 0.97rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.exp-card-bank  { font-size: 0.78rem; color: #7a9aaa; margin-top: 2px; }
.exp-card-date  { font-size: 0.75rem; color: #95a5a6; margin-top: 2px; }
.exp-card-amount { font-size: 1.05rem; font-weight: 800; color: #c0392b; }

/* ── MOBILE ── */
@media screen and (max-width: 640px) {
    .main .block-container { padding: 0.5rem 0.6rem 1rem 0.6rem !important; }
    h1 { font-size: 1.3rem !important; line-height: 1.3 !important; }
    h2 { font-size: 1.15rem !important; }
    h3 { font-size: 1rem !important; }

    /* Stack all columns on mobile */
    div[data-testid="stHorizontalBlock"] { flex-direction: column !important; gap: 0.35rem !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] {
        width: 100% !important; min-width: 100% !important; flex: 1 1 100% !important;
    }

    /* Metrics — dark themed cards on mobile */
    div[data-testid="stMetric"] {
        background: #1a3c5e !important; border: 1px solid #0e7c5b !important;
        border-radius: 10px !important; padding: 0.65rem 0.8rem !important; margin-bottom: 0.4rem !important;
    }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricLabel"],
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] p,
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] div {
        color: #a8d8c8 !important; font-size: 0.78rem !important; font-weight: 600 !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricValue"] div,
    div[data-testid="stMetric"] [data-testid="stMetricValue"] p {
        color: #ffffff !important; font-size: 1.2rem !important; font-weight: 800 !important;
    }

    /* Buttons — full width, tall enough for thumbs */
    .stButton > button {
        width: 100% !important; min-height: 3rem !important;
        font-size: 1rem !important; border-radius: 8px !important; margin-bottom: 0.3rem !important;
    }

    /* Inputs — large enough to tap */
    input, textarea,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    div[data-baseweb="select"] {
        font-size: 1rem !important; min-height: 2.8rem !important;
        width: 100% !important; box-sizing: border-box !important;
    }

    /* Select dropdowns */
    div[data-baseweb="select"] > div { min-height: 2.8rem !important; }

    /* Tabs — horizontal scroll */
    div[data-testid="stTabs"] > div:first-child {
        overflow-x: auto !important; -webkit-overflow-scrolling: touch !important;
        white-space: nowrap !important; scrollbar-width: none !important;
    }
    div[data-testid="stTabs"] > div:first-child::-webkit-scrollbar { display: none !important; }

    /* Sidebar */
    section[data-testid="stSidebar"] { min-width: 200px !important; max-width: 220px !important; }
    section[data-testid="stSidebar"] label { font-size: 0.9rem !important; }

    /* Charts */
    div[data-testid="stArrowVegaLiteChart"],
    div[data-testid="stVegaLiteChart"],
    .stPlotlyChart { overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; }

    /* Tables */
    div[data-testid="stDataFrame"],
    div[data-testid="stTable"] { overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; }

    details, div[data-testid="stExpander"] { width: 100% !important; }
    div[data-testid="stProgress"] { width: 100% !important; }

    /* Landing page */
    .landing-hero { padding: 20px 12px 16px 12px !important; border-radius: 12px !important; }
    .landing-title   { font-size: 1.5rem !important; }
    .landing-tagline { font-size: 0.88rem !important; }
    .landing-desc    { font-size: 0.86rem !important; }
    .demo-card  { padding: 10px !important; }
    .demo-row   { font-size: 0.8rem !important; flex-wrap: wrap !important; }
    .feature-card { margin-bottom: 0.5rem !important; padding: 12px 14px !important; }
    .stAlert { font-size: 0.88rem !important; }

    /* Exp cards */
    .exp-card { padding: 10px 10px !important; }
    .exp-card-name { font-size: 0.9rem !important; }
    .exp-card-amount { font-size: 0.98rem !important; }

    /* Weekly card */
    .week-card { padding: 14px 14px !important; }
    .week-stat { flex: 1 1 90px !important; padding: 8px 10px !important; }
    .week-stat-value { font-size: 1rem !important; }

    /* Insight cards */
    .insight-card { padding: 11px 12px !important; }
    .insight-text  { font-size: 0.88rem !important; }

    /* Quick-add buttons — 2 per row on mobile */
    div[data-testid="stHorizontalBlock"].qa-row > div { flex: 1 1 48% !important; max-width: 50% !important; }

    hr { margin: 0.5rem 0 !important; }
}

/* ── TABLET ── */
@media screen and (min-width: 641px) and (max-width: 900px) {
    .main .block-container { padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100% !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] { min-width: 44% !important; flex-wrap: wrap !important; }
    .stButton > button { min-height: 2.5rem !important; font-size: 0.95rem !important; }
    .week-stat { flex: 1 1 130px !important; }
}
</style>"""


def inject_styles():
    """Call once at startup before any page renders."""
    st.markdown(CSS, unsafe_allow_html=True)
