from styles import render_page_header
# pages/notifications.py — Notifications inbox page
import streamlit as st
from datetime import datetime

from retention import (
    get_notifications, get_unread_count,
    mark_notifications_read, mark_notification_read,
    clear_all_notifications, get_streak,
)


# ── Type config: icon + colours for each notification type ──────────────────
_TYPE_CONFIG = {
    "reminder": {
        "bg":     "#fffbea",
        "border": "#f39c12",
        "label":  "Reminder",
        "badge":  "#f39c12",
    },
    "tip": {
        "bg":     "#e8f4fd",
        "border": "#3498db",
        "label":  "Tip",
        "badge":  "#3498db",
    },
    "milestone": {
        "bg":     "#f4f7f6",
        "border": "#0e7c5b",
        "label":  "Milestone",
        "badge":  "#0e7c5b",
    },
    "alert": {
        "bg":     "#fdf2f2",
        "border": "#e74c3c",
        "label":  "Alert",
        "badge":  "#e74c3c",
    },
    "nudge": {
        "bg":     "#fdf0ff",
        "border": "#9b59b6",
        "label":  "Nudge",
        "badge":  "#9b59b6",
    },
}
_DEFAULT_CFG = {
    "bg": "#f4f7f6", "border": "#0e7c5b", "label": "Notification", "badge": "#0e7c5b"
}

_NOTIF_CSS = """
<style>
.notif-card {
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    border-left: 4px solid #0e7c5b;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    transition: opacity 0.2s;
}
.notif-card.unread  { opacity: 1; }
.notif-card.read    { opacity: 0.55; }
.notif-icon  { font-size: 1.4rem; flex-shrink: 0; margin-top: 1px; }
.notif-body  { flex: 1; }
.notif-title {
    font-weight: 700; font-size: 0.93rem; color: #1a2e3b; margin-bottom: 3px;
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.notif-badge {
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.05em; border-radius: 20px;
    padding: 2px 9px; color: #fff;
}
.notif-text  { font-size: 0.88rem; color: #6b7f8e; line-height: 1.5; }
.notif-time  { font-size: 0.72rem; color: #95a5a6; margin-top: 4px; }
.streak-banner {
    background: linear-gradient(90deg, #1a2e3b 0%, #0e7c5b 100%);
    border-radius: 14px; padding: 18px 22px; margin-bottom: 18px;
    display: flex; justify-content: space-between; align-items: center;
    flex-wrap: wrap; gap: 12px; color: #fff;
}
.streak-left { }
.streak-num  {
    font-size: 2.4rem; font-weight: 900; color: #fff; line-height: 1;
    display: inline-block; margin-right: 8px;
}
.streak-label { font-size: 0.85rem; color: #a8d8c8; font-weight: 600; margin-top: 2px; }
.streak-sub   { font-size: 0.78rem; color: #a8d8c8; margin-top: 4px; }
.streak-right { text-align: right; }
.streak-best  { font-size: 0.78rem; color: #a8d8c8; }
.streak-best-num { font-size: 1.2rem; font-weight: 800; color: #fff; }
@media(max-width:640px) {
    .streak-banner { flex-direction: column; }
    .streak-right  { text-align: left; }
}
</style>
"""


def _format_time(ts) -> str:
    """Human-readable time string for a notification timestamp."""
    if ts is None:
        return ""
    now = datetime.now()
    if hasattr(ts, "date"):
        diff = now - ts
    else:
        return str(ts)[:16]
    total_seconds = int(diff.total_seconds())
    if total_seconds < 60:
        return "just now"
    if total_seconds < 3600:
        m = total_seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if total_seconds < 86400:
        h = total_seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = total_seconds // 86400
    if d == 1:
        return "yesterday"
    if d < 7:
        return f"{d} days ago"
    return ts.strftime("%d %b %Y") if hasattr(ts, "strftime") else str(ts)[:10]


def render_notifications(user_id: int) -> None:
    render_page_header()
    st.title("🔔 Notifications")
    st.markdown(_NOTIF_CSS, unsafe_allow_html=True)

    # ── Streak banner ─────────────────────────────────────────────────────────
    streak = get_streak(user_id)
    curr   = streak["current"]
    best   = streak["longest"]

    if curr == 0:
        flame   = "&#x1F4CA;"
        msg     = "Log in and track expenses daily to build your streak!"
        sub     = "Start tracking today to begin your streak."
    elif curr < 3:
        flame   = "&#x1F525;"
        msg     = f"{curr}-Day Streak"
        sub     = "Keep going — reach 3 days for your first milestone!"
    elif curr < 7:
        flame   = "&#x1F525;&#x1F525;"
        msg     = f"{curr}-Day Streak"
        sub     = f"Only {7 - curr} more day{'s' if 7-curr != 1 else ''} to your 7-day milestone!"
    elif curr < 14:
        flame   = "&#x1F3C6;"
        msg     = f"{curr}-Day Streak"
        sub     = "You are in the top 30% of Budget Right users!"
    elif curr < 30:
        flame   = "&#x1F31F;"
        msg     = f"{curr}-Day Streak"
        sub     = f"Incredible consistency. {30 - curr} days to the 30-day milestone!"
    else:
        flame   = "&#x1F451;"
        msg     = f"{curr}-Day Streak"
        sub     = "You are in the top 5% of all Budget Right users. Legendary."

    st.markdown(f"""
    <div class="streak-banner">
      <div class="streak-left">
        <div>
          <span class="streak-num">{flame}</span>
          <span style="font-size:1.4rem;font-weight:800;">{msg}</span>
        </div>
        <div class="streak-sub">{sub}</div>
      </div>
      <div class="streak-right">
        <div class="streak-best">Personal best</div>
        <div class="streak-best-num">{best} day{'s' if best != 1 else ''}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Notification inbox controls ───────────────────────────────────────────
    notifications = get_notifications(user_id, limit=60)
    unread_count  = sum(1 for n in notifications if not n["read"])

    head_col, btn_col1, btn_col2 = st.columns([3, 1, 1])
    with head_col:
        if unread_count > 0:
            st.caption(f"**{unread_count} unread** notification{'s' if unread_count != 1 else ''}")
        else:
            st.caption("All caught up ✓")

    with btn_col1:
        if unread_count > 0:
            if st.button("Mark all read", key="notif_mark_all_read", use_container_width=True):
                mark_notifications_read(user_id)
                st.rerun()

    with btn_col2:
        if notifications:
            if st.button("Clear all", key="notif_clear_all", use_container_width=True):
                clear_all_notifications(user_id)
                st.rerun()

    # ── Filter tabs ────────────────────────────────────────────────────────────
    type_labels = ["All", "Alerts", "Reminders", "Tips", "Milestones", "Nudges"]
    type_filter_map = {
        "All":        None,
        "Alerts":     "alert",
        "Reminders":  "reminder",
        "Tips":       "tip",
        "Milestones": "milestone",
        "Nudges":     "nudge",
    }
    tab_sel = st.radio(
        "Filter",
        type_labels,
        horizontal=True,
        label_visibility="collapsed",
        key="notif_filter"
    )
    filter_type = type_filter_map[tab_sel]

    # ── Notification list ──────────────────────────────────────────────────────
    shown = [n for n in notifications if filter_type is None or n["type"] == filter_type]

    if not shown:
        st.markdown("""
        <div style="background:#f4f7f6;border-radius:12px;padding:28px 24px;
                    text-align:center;color:#6b7f8e;margin:16px 0;">
          <div style="font-size:2.5rem;">&#x1F514;</div>
          <div style="font-weight:700;margin:8px 0 4px;color:#1a2e3b;">
            No notifications yet
          </div>
          <div style="font-size:0.92rem;">
            Log expenses, hit streaks, or set a budget to start receiving
            personalised reminders and tips here.
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    for notif in shown:
        cfg      = _TYPE_CONFIG.get(notif["type"], _DEFAULT_CFG)
        read_cls = "read" if notif["read"] else "unread"
        time_str = _format_time(notif["created_at"])
        unread_dot = (
            '<span style="display:inline-block;width:8px;height:8px;'
            'background:#e74c3c;border-radius:50%;margin-left:4px;'
            'vertical-align:middle;"></span>'
            if not notif["read"] else ""
        )

        card_col, action_col = st.columns([7, 0.6])
        with card_col:
            st.markdown(
                f'<div class="notif-card {read_cls}" '
                f'style="background:{cfg["bg"]};border-left-color:{cfg["border"]};">'
                f'<div class="notif-icon">{notif["icon"]}</div>'
                f'<div class="notif-body">'
                f'<div class="notif-title">'
                f'<span>{notif["title"]}</span>'
                f'<span class="notif-badge" style="background:{cfg["badge"]};">'
                f'{cfg["label"]}</span>'
                f'{unread_dot}'
                f'</div>'
                f'<div class="notif-text">{notif["body"]}</div>'
                f'<div class="notif-time">{time_str}</div>'
                f'</div></div>',
                unsafe_allow_html=True
            )
        with action_col:
            if not notif["read"]:
                if st.button("✓", key=f"notif_read_{notif['id']}", help="Mark as read"):
                    mark_notification_read(notif["id"])
                    st.rerun()
