# styles.py — all CSS, injected once at app startup
import streamlit as st

CSS = """<style>
/* ── RESET & BASE ── */
html, body { overflow-x: hidden !important; }
.main .block-container {
    max-width: 1100px !important;
    padding: 1.25rem 1.5rem 2rem 1.5rem !important;
    margin: 0 auto !important;
}

/* ── TYPOGRAPHY ── */
h1 { font-size: 1.6rem !important; font-weight: 800 !important; color: #1a2e3b !important; letter-spacing: -0.02em !important; margin-bottom: 0.25rem !important; }
h2 { font-size: 1.2rem !important; font-weight: 700 !important; color: #1a2e3b !important; }
h3 { font-size: 1rem !important; font-weight: 700 !important; color: #1a2e3b !important; }

/* ── SIDEBAR — dark & clean ── */
section[data-testid="stSidebar"] {
    background: #1a2e3b !important;
    border-right: none !important;
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown h3,
section[data-testid="stSidebar"] label { color: #c8dae2 !important; }
section[data-testid="stSidebar"] .stRadio label {
    border-radius: 8px !important; padding: 6px 12px !important;
    font-size: 0.9rem !important; font-weight: 500 !important;
    color: #c8dae2 !important; cursor: pointer !important;
    transition: background 0.15s !important;
}
section[data-testid="stSidebar"] .stRadio label:hover { background: rgba(255,255,255,0.08) !important; color: #fff !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.12) !important; margin: 8px 0 !important; }
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.1) !important; color: #c8dae2 !important;
    border: 1px solid rgba(255,255,255,0.15) !important; border-radius: 8px !important;
    font-size: 0.88rem !important; width: 100% !important;
}
section[data-testid="stSidebar"] .stButton > button:hover { background: rgba(255,255,255,0.18) !important; color: #fff !important; }

/* ── METRIC CARDS — premium ── */
div[data-testid="stMetric"] {
    background: #ffffff !important; border: 1px solid #d8eae2 !important;
    border-radius: 14px !important; padding: 1rem 1.1rem !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.05) !important; transition: box-shadow 0.2s !important;
}
div[data-testid="stMetric"]:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.09) !important; }
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricLabel"] p,
div[data-testid="stMetric"] [data-testid="stMetricLabel"] div {
    color: #6b7f8e !important; font-size: 0.74rem !important;
    font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.05em !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricValue"] div {
    color: #1a2e3b !important; font-size: 1.35rem !important; font-weight: 800 !important;
}

/* ── BUTTONS — bold, tappable ── */
.stButton > button {
    border-radius: 10px !important; font-weight: 700 !important; font-size: 0.92rem !important;
    min-height: 2.6rem !important; padding: 0.45rem 1rem !important; border: none !important;
    background: #0e7c5b !important; color: #fff !important;
    transition: background 0.15s, box-shadow 0.15s !important; cursor: pointer !important;
}
.stButton > button:hover { background: #0a5c44 !important; box-shadow: 0 3px 10px rgba(14,124,91,0.3) !important; }
.stButton > button:active { background: #084d3a !important; }

/* ── FORMS & INPUTS ── */
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
    border-radius: 9px !important; border: 1.5px solid #d8eae2 !important;
    font-size: 0.95rem !important; background: #fafcfb !important; transition: border-color 0.15s !important;
}
div[data-baseweb="input"] input:focus, div[data-baseweb="textarea"] textarea:focus {
    border-color: #0e7c5b !important; box-shadow: 0 0 0 3px rgba(14,124,91,0.12) !important;
}
div[data-baseweb="select"] > div {
    border-radius: 9px !important; border: 1.5px solid #d8eae2 !important;
    background: #fafcfb !important; min-height: 2.4rem !important;
}

/* ── EXPANDERS ── */
div[data-testid="stExpander"] {
    border: 1px solid #d8eae2 !important; border-radius: 12px !important;
    background: #ffffff !important; margin-bottom: 10px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
div[data-testid="stExpander"] summary {
    font-weight: 700 !important; font-size: 0.95rem !important;
    color: #1a2e3b !important; padding: 0.7rem 1rem !important;
}

/* ── TABS ── */
div[data-testid="stTabs"] [role="tab"] {
    font-weight: 600 !important; font-size: 0.88rem !important;
    border-radius: 8px 8px 0 0 !important; padding: 0.4rem 1rem !important;
}
div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #0e7c5b !important; border-bottom: 3px solid #0e7c5b !important; font-weight: 800 !important;
}

/* ── PROGRESS BARS ── */
div[data-testid="stProgress"] > div { background: #e8f5f0 !important; border-radius: 99px !important; height: 8px !important; }
div[data-testid="stProgress"] > div > div { background: linear-gradient(90deg, #0e7c5b, #16a085) !important; border-radius: 99px !important; }

/* ── DIVIDERS ── */
hr { border-color: #e8f0ed !important; margin: 0.7rem 0 !important; }

/* ── INSIGHT CARDS ── */
.insight-card {
    border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
    display: flex; align-items: flex-start; gap: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.04);
}
.insight-icon { font-size: 1.4rem; flex-shrink: 0; margin-top: 1px; }
.insight-body { flex: 1; }
.insight-title { font-weight: 700; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; opacity: 0.75; }
.insight-text  { font-size: 0.92rem; line-height: 1.55; }

/* ── WEEK SUMMARY CARD ── */
.week-card {
    background: linear-gradient(135deg, #1a2e3b 0%, #0e7c5b 100%);
    border-radius: 16px; padding: 20px 22px; color: #fff; margin-bottom: 14px;
    box-shadow: 0 4px 16px rgba(14,124,91,0.2);
}
.week-title  { font-size: 0.8rem; font-weight: 700; margin-bottom: 14px; color: #a8d8c8; text-transform: uppercase; letter-spacing: 0.06em; }
.week-grid   { display: flex; flex-wrap: wrap; gap: 10px; }
.week-stat   { background: rgba(255,255,255,0.12); border-radius: 10px; padding: 10px 14px; flex: 1 1 120px; min-width: 110px; }
.week-stat-label { font-size: 0.72rem; color: #a8d8c8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.week-stat-value { font-size: 1.15rem; font-weight: 800; color: #fff; margin-top: 3px; }

/* ── GOAL CHIPS ── */
.goal-chip { background: #e8f5f0; color: #0e7c5b; border: 1.5px solid #0e7c5b; border-radius: 20px; padding: 5px 14px; font-size: 0.85rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
.goal-chip:hover { background: #0e7c5b; color: #fff; }

/* ── EXP CARDS ── */
.exp-card {
    background: #ffffff; border: 1px solid #d8eae2; border-left: 4px solid #0e7c5b;
    border-radius: 10px; padding: 12px 14px; margin-bottom: 8px;
    display: flex; justify-content: space-between; align-items: flex-start;
    flex-wrap: wrap; gap: 6px; transition: box-shadow 0.15s;
}
.exp-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.07); }
.exp-card-left  { flex: 1 1 60%; min-width: 0; }
.exp-card-right { flex: 0 0 auto; text-align: right; }
.exp-card-name   { font-weight: 700; color: #1a2e3b; font-size: 0.97rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.exp-card-bank   { font-size: 0.78rem; color: #6b7f8e; margin-top: 2px; }
.exp-card-date   { font-size: 0.75rem; color: #95a5a6; margin-top: 2px; }
.exp-card-amount { font-size: 1.05rem; font-weight: 800; color: #c0392b; }

/* ── STAT CARDS (dashboard) ── */
.sc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin: 4px 0 18px 0; }
.sc-card { background: #ffffff; border: 1px solid #d8eae2; border-radius: 14px; padding: 15px 17px 13px; display: flex; flex-direction: column; gap: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); transition: box-shadow 0.15s; }
.sc-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.08); }
.sc-label { font-size: 0.7rem; font-weight: 700; color: #6b7f8e; text-transform: uppercase; letter-spacing: 0.06em; }
.sc-value { font-size: 1.3rem; font-weight: 800; color: #1a2e3b; line-height: 1.2; word-break: break-word; }
.sc-sub   { font-size: 0.74rem; color: #95a5a6; margin-top: 1px; }
.sc-accent-green { color: #0e7c5b !important; }
.sc-accent-red   { color: #c0392b !important; }
.sc-accent-amber { color: #d4850a !important; }

/* ── REPORT CARDS ── */
.rpt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; margin: 8px 0 16px 0; }
.rpt-card { background: #f4f7f6; border: 1px solid #d8eae2; border-radius: 12px; padding: 15px 17px; }
.rpt-title { font-weight: 700; color: #1a2e3b; font-size: 0.93rem; margin-bottom: 4px; }
.rpt-desc  { color: #6b7f8e; font-size: 0.82rem; line-height: 1.5; }

/* ── ONBOARDING ── */
.ob-step { display: flex; align-items: center; gap: 10px; background: #f4f7f6; border-radius: 10px; padding: 10px 14px; margin-bottom: 6px; font-size: 0.91rem; }
.ob-done { border-left: 4px solid #0e7c5b; color: #2c7a5a; }
.ob-todo { border-left: 4px solid #d0d8d4; color: #555; }
.ob-icon { font-size: 1.2rem; }

/* ── LANDING PAGE ── */
.landing-hero { background: linear-gradient(135deg, #1a2e3b 0%, #0e7c5b 100%); border-radius: 18px; padding: 36px 28px 28px; text-align: center; margin-bottom: 24px; box-shadow: 0 6px 24px rgba(14,124,91,0.25); }
.landing-title   { font-size: 2.1rem; font-weight: 900; color: #fff; margin-bottom: 6px; }
.landing-tagline { font-size: 1.05rem; color: #a8d8c8; }
.landing-desc    { font-size: 0.95rem; color: #e0f0ec; margin-top: 10px; }
.feature-card    { background: #f4f7f6; border-left: 4px solid #0e7c5b; border-radius: 10px; padding: 14px 16px; margin-bottom: 10px; }
.demo-card  { background: #fff; border: 1px solid #d8eae2; border-radius: 10px; padding: 14px 16px; margin-bottom: 8px; }
.demo-row   { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; font-size: 0.88rem; }

/* ── MOBILE ── */
@media screen and (max-width: 640px) {
    .main .block-container { padding: 0.6rem 0.75rem 1rem !important; }
    h1 { font-size: 1.25rem !important; }
    h2 { font-size: 1.08rem !important; }
    div[data-testid="stHorizontalBlock"] { flex-direction: column !important; gap: 0.35rem !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] { width: 100% !important; min-width: 100% !important; flex: 1 1 100% !important; }
    div[data-testid="stMetric"] { padding: 0.7rem 0.85rem !important; }
    .stButton > button { width: 100% !important; min-height: 3rem !important; }
    input, textarea, div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea, div[data-baseweb="select"] { font-size: 1rem !important; min-height: 2.8rem !important; width: 100% !important; }
    div[data-baseweb="select"] > div { min-height: 2.8rem !important; }
    div[data-testid="stTabs"] > div:first-child { overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; white-space: nowrap !important; scrollbar-width: none !important; }
    div[data-testid="stTabs"] > div:first-child::-webkit-scrollbar { display: none !important; }
    section[data-testid="stSidebar"] { min-width: 200px !important; max-width: 220px !important; }
    .sc-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
    .sc-value { font-size: 1.05rem; }
    .week-card { padding: 14px !important; }
    .week-stat { flex: 1 1 90px !important; }
    .week-stat-value { font-size: 1rem !important; }
    .rpt-grid { grid-template-columns: 1fr; }
    .landing-hero { padding: 20px 14px 16px !important; border-radius: 12px !important; }
    .landing-title { font-size: 1.5rem !important; }
    hr { margin: 0.4rem 0 !important; }
}

/* ── TABLET ── */
@media screen and (min-width: 641px) and (max-width: 900px) {
    .main .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] { min-width: 44% !important; }
    .stButton > button { min-height: 2.5rem !important; }
    .week-stat { flex: 1 1 130px !important; }
}
</style>"""


def inject_styles():
    """Call once at startup before any page renders."""
    st.markdown(CSS, unsafe_allow_html=True)
