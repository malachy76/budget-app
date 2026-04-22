# styles.py — all CSS, injected once at app startup
# OPTIMIZED: consolidated, premium modern design, better mobile experience
import streamlit as st


CSS = """<style>
/* ══════════════════════════════════════════════
   BASE & LAYOUT
══════════════════════════════════════════════ */
html, body { overflow-x: hidden !important; }
.main .block-container {
    max-width: 100% !important;
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
}

/* ══════════════════════════════════════════════
   TYPOGRAPHY — cleaner hierarchy
══════════════════════════════════════════════ */
h1 { font-size: 1.6rem !important; font-weight: 800 !important;
     color: #1a3c5e !important; letter-spacing: -0.3px !important;
     margin-bottom: 0.1rem !important; }
h2 { font-size: 1.25rem !important; font-weight: 700 !important;
     color: #1a3c5e !important; margin-bottom: 0.1rem !important; }
h3 { font-size: 1.05rem !important; font-weight: 600 !important;
     color: #1a3c5e !important; }

/* ══════════════════════════════════════════════
   SIDEBAR — cleaner, more premium
══════════════════════════════════════════════ */
section[data-testid="stSidebar"] {
    background: #0f2540 !important;
}
section[data-testid="stSidebar"] * { color: #c8dff0 !important; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] strong { color: #ffffff !important; }
section[data-testid="stSidebar"] .stRadio label { 
    font-size: 0.92rem !important; font-weight: 500 !important;
    padding: 6px 0 !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] { display: none !important; }
div[data-testid="stSidebarNavItems"] { display: none !important; }

/* ══════════════════════════════════════════════
   BUTTONS — bigger, clearer, more tappable
══════════════════════════════════════════════ */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    min-height: 2.4rem !important;
    padding: 0.4rem 1rem !important;
    transition: all 0.15s ease !important;
    border: none !important;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid*="primary"] {
    background: linear-gradient(135deg, #0e7c5b 0%, #1a3c5e 100%) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 8px rgba(14,124,91,0.25) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 14px rgba(14,124,91,0.35) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:not([kind="primary"]) {
    background: #f0f7f4 !important;
    color: #1a3c5e !important;
    border: 1.5px solid #c5ddd6 !important;
}
.stButton > button:not([kind="primary"]):hover {
    background: #e0f0ea !important;
    border-color: #0e7c5b !important;
}

/* Download buttons */
.stDownloadButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    background: linear-gradient(135deg, #1a3c5e 0%, #0e7c5b 100%) !important;
    color: #fff !important;
    border: none !important;
    min-height: 2.4rem !important;
    box-shadow: 0 2px 8px rgba(26,60,94,0.2) !important;
}

/* ══════════════════════════════════════════════
   INPUTS — cleaner, more polished
══════════════════════════════════════════════ */
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div:first-child {
    border-radius: 8px !important;
    border-color: #c5ddd6 !important;
    background: #fafcfb !important;
    transition: border-color 0.15s !important;
}
div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="textarea"] > div:focus-within,
div[data-baseweb="select"] > div:first-child:focus-within {
    border-color: #0e7c5b !important;
    box-shadow: 0 0 0 2px rgba(14,124,91,0.12) !important;
}
/* Force dark text inside every input so typed text is always visible */
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea,
div[data-baseweb="select"] [data-testid="stSelectboxValue"],
div[data-baseweb="select"] span,
input[type="text"],
input[type="number"],
input[type="email"],
input[type="password"],
textarea,
.stTextInput input,
.stNumberInput input,
.stTextArea textarea,
.stDateInput input,
.stTimeInput input {
    color: #1a2e3b !important;
    -webkit-text-fill-color: #1a2e3b !important;
    caret-color: #1a2e3b !important;
    opacity: 1 !important;
}
/* Placeholder — muted but readable */
div[data-baseweb="input"] input::placeholder,
div[data-baseweb="textarea"] textarea::placeholder,
.stTextInput input::placeholder,
.stNumberInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #8aa5b0 !important;
    -webkit-text-fill-color: #8aa5b0 !important;
    opacity: 1 !important;
}
/* Select dropdown value */
div[data-baseweb="select"] [data-testid="stSelectboxValue"],
div[data-baseweb="select"] > div > div > div {
    color: #1a2e3b !important;
}
/* Number input spinner buttons */
div[data-testid="stNumberInput"] button {
    color: #1a2e3b !important;
    background: #eef5f2 !important;
}

/* ══════════════════════════════════════════════
   METRICS — premium card style
══════════════════════════════════════════════ */
div[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #e2ede9 !important;
    border-radius: 12px !important;
    padding: 1rem 1.1rem !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.05) !important;
    transition: box-shadow 0.15s !important;
}
div[data-testid="stMetric"]:hover {
    box-shadow: 0 3px 12px rgba(0,0,0,0.09) !important;
}
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricLabel"] p,
div[data-testid="stMetric"] [data-testid="stMetricLabel"] div {
    font-size: 0.75rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    color: #7a9aaa !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricValue"] div {
    font-size: 1.4rem !important;
    font-weight: 800 !important;
    color: #1a3c5e !important;
    line-height: 1.2 !important;
}
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-size: 0.8rem !important;
    font-weight: 600 !important;
}

/* ══════════════════════════════════════════════
   TABS — cleaner
══════════════════════════════════════════════ */
div[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 0.5rem 1rem !important;
    border-radius: 6px 6px 0 0 !important;
}

/* ══════════════════════════════════════════════
   EXPANDERS — cleaner
══════════════════════════════════════════════ */
div[data-testid="stExpander"] {
    border: 1px solid #e2ede9 !important;
    border-radius: 10px !important;
    background: #fafcfb !important;
}
div[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: #1a3c5e !important;
    font-size: 0.92rem !important;
}

/* ══════════════════════════════════════════════
   ALERTS — refined
══════════════════════════════════════════════ */
div[data-testid="stAlert"] {
    border-radius: 10px !important;
    font-size: 0.9rem !important;
    border-left-width: 4px !important;
}

/* ══════════════════════════════════════════════
   DIVIDERS — subtler
══════════════════════════════════════════════ */
hr { border-color: #e8f0ec !important; margin: 1rem 0 !important; }

/* ══════════════════════════════════════════════
   STAT CARDS (dashboard At-a-Glance)
══════════════════════════════════════════════ */
.sc-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(195px, 1fr));
    gap: 12px;
    margin: 4px 0 18px 0;
}
.sc-card {
    background: #ffffff;
    border: 1px solid #e2ede9;
    border-radius: 14px;
    padding: 16px 18px 14px 18px;
    display: flex; flex-direction: column; gap: 4px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.05);
    transition: box-shadow 0.15s, transform 0.15s;
}
.sc-card:hover {
    box-shadow: 0 4px 14px rgba(0,0,0,0.09);
    transform: translateY(-1px);
}
.sc-label {
    font-size: 0.71rem; font-weight: 700; color: #7a9aaa;
    text-transform: uppercase; letter-spacing: 0.06em;
}
.sc-value {
    font-size: 1.3rem; font-weight: 800; color: #1a3c5e;
    line-height: 1.2; word-break: break-word;
}
.sc-sub { font-size: 0.75rem; color: #95a5a6; margin-top: 1px; }
.sc-accent-green { color: #0e7c5b !important; }
.sc-accent-red   { color: #c0392b !important; }
.sc-accent-amber { color: #d4850a !important; }

/* ══════════════════════════════════════════════
   INSIGHT / SUGGESTION CARDS
══════════════════════════════════════════════ */
.insight-card {
    border-radius: 12px; padding: 13px 15px; margin-bottom: 9px;
    display: flex; align-items: flex-start; gap: 12px;
    box-shadow: 0 1px 5px rgba(0,0,0,0.06);
    transition: box-shadow 0.15s;
}
.insight-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.09); }
.insight-icon { font-size: 1.35rem; flex-shrink: 0; margin-top: 1px; }
.insight-body { flex: 1; }
.insight-title {
    font-weight: 700; font-size: 0.86rem;
    text-transform: uppercase; letter-spacing: 0.04em;
    margin-bottom: 3px; opacity: 0.75;
}
.insight-text { font-size: 0.92rem; line-height: 1.5; }

/* ══════════════════════════════════════════════
   WEEKLY SUMMARY CARD
══════════════════════════════════════════════ */
.week-card {
    background: linear-gradient(135deg, #1a3c5e 0%, #0e7c5b 100%);
    border-radius: 16px; padding: 18px 20px; color: #fff;
    margin-bottom: 14px; box-shadow: 0 4px 16px rgba(14,124,91,0.18);
}
.week-title { font-size: 0.92rem; font-weight: 700; margin-bottom: 12px; color: #a8d8c8; }
.week-grid  { display: flex; flex-wrap: wrap; gap: 8px; }
.week-stat  {
    background: rgba(255,255,255,0.13); border-radius: 10px;
    padding: 10px 13px; flex: 1 1 110px; min-width: 100px;
}
.week-stat-label {
    font-size: 0.72rem; color: #a8d8c8; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em;
}
.week-stat-value { font-size: 1.1rem; font-weight: 800; color: #fff; margin-top: 2px; }

/* ══════════════════════════════════════════════
   GOAL PRESET CHIPS
══════════════════════════════════════════════ */
.goal-chips { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 10px; }
.goal-chip {
    background: #e8f5f0; color: #0e7c5b;
    border: 1.5px solid #0e7c5b; border-radius: 20px;
    padding: 4px 13px; font-size: 0.83rem; font-weight: 600;
    cursor: pointer; white-space: nowrap;
    transition: all 0.12s;
}
.goal-chip:hover   { background: #0e7c5b; color: #fff; }
.goal-chip.selected { background: #0e7c5b; color: #fff; }

/* ══════════════════════════════════════════════
   TRANSACTION / EXPENSE CARDS
══════════════════════════════════════════════ */
.exp-card {
    background: #ffffff;
    border: 1px solid #e2ede9;
    border-left: 4px solid #0e7c5b;
    border-radius: 11px;
    padding: 11px 13px;
    margin-bottom: 7px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 5px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    transition: box-shadow 0.12s;
}
.exp-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.08); }
.exp-card-left  { flex: 1 1 60%; min-width: 0; }
.exp-card-right { flex: 0 0 auto; text-align: right; }
.exp-card-name  {
    font-weight: 700; color: #1a3c5e; font-size: 0.95rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.exp-card-bank   { font-size: 0.77rem; color: #7a9aaa; margin-top: 2px; }
.exp-card-date   { font-size: 0.73rem; color: #95a5a6; margin-top: 2px; }
.exp-card-amount { font-size: 1.05rem; font-weight: 800; color: #c0392b; }

/* ══════════════════════════════════════════════
   NOTIFICATION CARDS (notifications page)
══════════════════════════════════════════════ */
.notif-card {
    border-radius: 12px; padding: 13px 15px; margin-bottom: 9px;
    display: flex; align-items: flex-start; gap: 11px;
    border-left: 4px solid #0e7c5b;
    box-shadow: 0 1px 5px rgba(0,0,0,0.05);
    transition: opacity 0.2s;
}
.notif-card.read   { opacity: 0.52; }
.notif-card.unread { opacity: 1; }
.notif-icon  { font-size: 1.35rem; flex-shrink: 0; margin-top: 1px; }
.notif-body  { flex: 1; }
.notif-title {
    font-weight: 700; font-size: 0.92rem; color: #1a3c5e;
    margin-bottom: 3px; display: flex; align-items: center;
    gap: 7px; flex-wrap: wrap;
}
.notif-badge {
    font-size: 0.67rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.05em; border-radius: 20px;
    padding: 2px 8px; color: #fff;
}
.notif-text { font-size: 0.88rem; color: #4a6070; line-height: 1.5; }
.notif-time { font-size: 0.71rem; color: #95a5a6; margin-top: 3px; }

/* ══════════════════════════════════════════════
   STREAK BANNER (notifications page)
══════════════════════════════════════════════ */
.streak-banner {
    background: linear-gradient(90deg, #1a3c5e 0%, #0e7c5b 100%);
    border-radius: 14px; padding: 16px 20px; margin-bottom: 16px;
    display: flex; justify-content: space-between;
    align-items: center; flex-wrap: wrap; gap: 10px; color: #fff;
    box-shadow: 0 4px 14px rgba(14,124,91,0.18);
}
.streak-left {}
.streak-num  {
    font-size: 2.2rem; font-weight: 900; color: #fff;
    line-height: 1; display: inline-block; margin-right: 6px;
}
.streak-label { font-size: 0.84rem; color: #a8d8c8; font-weight: 600; margin-top: 2px; }
.streak-sub   { font-size: 0.76rem; color: #a8d8c8; margin-top: 3px; }
.streak-right { text-align: right; }
.streak-best  { font-size: 0.76rem; color: #a8d8c8; }
.streak-best-num { font-size: 1.15rem; font-weight: 800; color: #fff; }

/* ══════════════════════════════════════════════
   LANDING PAGE
══════════════════════════════════════════════ */
.landing-hero {
    background: linear-gradient(135deg, #1a3c5e 0%, #0e7c5b 100%);
    border-radius: 18px; padding: 44px 38px 36px 38px;
    text-align: center; margin-bottom: 8px;
    box-shadow: 0 8px 32px rgba(14,124,91,0.15);
}
.landing-logo    { font-size: 52px; margin-bottom: 4px; display: block; }
.landing-title   { font-size: 2.5rem; font-weight: 800; color: #fff;
                   margin: 0 0 6px 0; letter-spacing: -0.5px; }
.landing-tagline { font-size: 1.05rem; color: #a8d8c8; margin: 0 0 24px 0;
                   font-weight: 400; }
.landing-desc    { font-size: 1rem; color: #d4eee6; max-width: 520px;
                   margin: 0 auto; line-height: 1.7; }
.feature-card    {
    background: #f0f7f4; border-left: 4px solid #0e7c5b;
    border-radius: 11px; padding: 16px 18px; height: 100%;
    box-shadow: 0 1px 5px rgba(0,0,0,0.04);
}
.feature-icon    { font-size: 1.7rem; }
.feature-title   { font-weight: 700; color: #1a3c5e; font-size: 0.97rem;
                   margin: 5px 0 3px 0; }
.feature-desc    { font-size: 0.85rem; color: #4a6070; line-height: 1.5; }

/* ══════════════════════════════════════════════
   PROGRESS BARS — refined
══════════════════════════════════════════════ */
div[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #0e7c5b, #1a8c6f) !important;
    border-radius: 6px !important;
}
div[data-testid="stProgress"] > div {
    background: #e2ede9 !important;
    border-radius: 6px !important;
    height: 8px !important;
}

/* ══════════════════════════════════════════════
   CHARTS — contained, clean
══════════════════════════════════════════════ */
.stPlotlyChart {
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.05) !important;
}

/* ══════════════════════════════════════════════
   CHARTS — always full width
══════════════════════════════════════════════ */
.stPlotlyChart > div,
.stPlotlyChart iframe {
    max-width: 100% !important;
    width: 100% !important;
}
div[data-testid="stDataFrame"],
div[data-testid="stTable"] {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch !important;
    max-width: 100% !important;
}

/* ══════════════════════════════════════════════
   BOTTOM NAV BAR (mobile only, rendered via HTML)
══════════════════════════════════════════════ */
.mob-nav {
    display: none;
}
@media screen and (max-width: 768px) {
    .mob-nav {
        display: flex !important;
        position: fixed;
        bottom: 0; left: 0; right: 0;
        background: #0f2540;
        border-top: 1px solid #1a3c5e;
        z-index: 9999;
        height: 60px;
        align-items: stretch;
        box-shadow: 0 -2px 12px rgba(0,0,0,0.25);
    }
    .mob-nav-item {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: #7aa8c4;
        font-size: 0.58rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        cursor: pointer;
        border: none;
        background: transparent;
        padding: 4px 2px 6px;
        transition: color 0.15s, background 0.15s;
        -webkit-tap-highlight-color: transparent;
        text-decoration: none;
    }
    .mob-nav-item .mob-nav-icon {
        font-size: 1.25rem;
        margin-bottom: 2px;
        line-height: 1;
    }
    .mob-nav-item.active,
    .mob-nav-item:active {
        color: #4dd6a3;
        background: rgba(77,214,163,0.08);
    }
}

/* ══════════════════════════════════════════════
   MOBILE (≤ 768px)
══════════════════════════════════════════════ */
@media screen and (max-width: 768px) {
    /* Extra bottom padding so content isn't hidden behind bottom nav */
    .main .block-container {
        padding: 0.5rem 0.75rem 5rem 0.75rem !important;
        max-width: 100% !important;
    }

    h1 { font-size: 1.2rem !important; }
    h2 { font-size: 1.08rem !important; }
    h3 { font-size: 0.96rem !important; }

    /* Stack ALL columns on mobile */
    div[data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 0.3rem !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] {
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }

    /* Metrics — dark themed for mobile */
    div[data-testid="stMetric"] {
        background: #1a3c5e !important;
        border: 1px solid #0e7c5b !important;
        border-radius: 11px !important;
        padding: 0.7rem 0.85rem !important;
        margin-bottom: 0.35rem !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15) !important;
    }
    div[data-testid="stMetric"]:hover { transform: none !important; }
    div[data-testid="stMetric"] [data-testid="stMetricLabel"],
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] p,
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] div {
        color: #a8d8c8 !important; font-size: 0.72rem !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricValue"] div,
    div[data-testid="stMetric"] [data-testid="stMetricValue"] p {
        color: #ffffff !important;
        font-size: 1.18rem !important;
        font-weight: 800 !important;
    }

    /* Buttons — full width, thumb-friendly */
    .stButton > button {
        width: 100% !important;
        min-height: 3rem !important;
        font-size: 1rem !important;
        margin-bottom: 0.3rem !important;
    }
    .stDownloadButton > button {
        width: 100% !important;
        min-height: 3rem !important;
    }

    /* Inputs — thumb-sized, prevent iOS zoom (font-size >= 16px) */
    input, textarea, select,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {
        font-size: 16px !important;
        min-height: 3rem !important;
        width: 100% !important;
    }
    div[data-baseweb="select"] > div { min-height: 3rem !important; }
    div[data-baseweb="select"] [data-testid="stSelectboxValue"] {
        font-size: 16px !important;
    }
    .stNumberInput input { font-size: 16px !important; }

    /* Tabs — horizontal scroll, no scrollbar */
    div[data-testid="stTabs"] > div:first-child {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        white-space: nowrap !important;
        scrollbar-width: none !important;
    }
    div[data-testid="stTabs"] > div:first-child::-webkit-scrollbar {
        display: none !important;
    }
    div[data-testid="stTabs"] button[data-baseweb="tab"] {
        font-size: 0.82rem !important;
        padding: 0.4rem 0.75rem !important;
    }

    /* Charts — always scrollable horizontally */
    div[data-testid="stArrowVegaLiteChart"],
    div[data-testid="stVegaLiteChart"],
    .stPlotlyChart {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        max-width: 100% !important;
    }

    /* Stat cards — 2-column grid */
    .sc-grid {
        grid-template-columns: 1fr 1fr !important;
        gap: 8px !important;
    }
    .sc-card  { padding: 12px 13px 10px !important; }
    .sc-value { font-size: 1.05rem !important; }

    /* Expense / transaction cards */
    .exp-card        { padding: 9px 10px !important; }
    .exp-card-name   { font-size: 0.88rem !important; }
    .exp-card-amount { font-size: 0.96rem !important; }

    /* Weekly summary card */
    .week-card       { padding: 14px !important; border-radius: 13px !important; }
    .week-stat       { flex: 1 1 88px !important; padding: 8px 10px !important; }
    .week-stat-value { font-size: 0.98rem !important; }

    /* Insight cards */
    .insight-card { padding: 10px 11px !important; }
    .insight-text { font-size: 0.86rem !important; }

    /* Forms */
    div[data-testid="stForm"] { padding: 0 !important; }

    hr { margin: 0.5rem 0 !important; }
    div[data-testid="stProgress"] > div { height: 7px !important; }

    details, div[data-testid="stExpander"] { width: 100% !important; }

    /* Landing page */
    .landing-hero    { padding: 20px 14px 16px !important; border-radius: 14px !important; }
    .landing-title   { font-size: 1.45rem !important; }
    .landing-tagline { font-size: 0.86rem !important; }

    .stAlert       { font-size: 0.86rem !important; }
    .streak-banner { border-radius: 12px !important; padding: 14px 16px !important; }
    .streak-right  { text-align: left !important; }

    /* Sidebar — keep it working when toggled open, but collapsed by default */
    section[data-testid="stSidebar"] {
        min-width: 240px !important;
        max-width: 260px !important;
    }
    section[data-testid="stSidebar"] label {
        font-size: 0.9rem !important;
        padding: 8px 4px !important;
    }

    /* Prevent horizontal overflow everywhere */
    .main, .block-container, [data-testid="stAppViewContainer"] {
        overflow-x: hidden !important;
    }
}

/* ══════════════════════════════════════════════
   TABLET (769px – 1024px)
══════════════════════════════════════════════ */
@media screen and (min-width: 769px) and (max-width: 1024px) {
    .main .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[class*="stColumn"] {
        min-width: 44% !important;
        flex-wrap: wrap !important;
    }
    .stButton > button { min-height: 2.4rem !important; }
    .week-stat { flex: 1 1 125px !important; }
    .sc-grid { grid-template-columns: repeat(auto-fill, minmax(175px, 1fr)) !important; }
}
</style>"""


def inject_styles():
    """Call once at startup before any page renders."""
    st.markdown(CSS, unsafe_allow_html=True)
