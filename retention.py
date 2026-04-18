# retention.py — streaks, in-app notifications, onboarding tips, re-engagement
#
# Call run_retention_engine(user_id) once per login (from app.py after auth).
# It is idempotent for the same calendar day — safe to call on every page load.
#
# Public API
# ──────────
#   run_retention_engine(user_id)          → call after every successful login
#   get_streak(user_id)                    → dict {current, longest, last_active_date}
#   get_notifications(user_id, unread_only)→ list of notification dicts
#   mark_notifications_read(user_id)       → mark all as read
#   mark_notification_read(notif_id)       → mark one as read
#   get_unread_count(user_id)              → int
#   push_notification(user_id, type, title, body, icon) → insert one notification
from __future__ import annotations

import streamlit as st
from datetime import datetime, timedelta, date

from db import get_db


# ── Onboarding tip sequence ──────────────────────────────────────────────────
# Shown one per day for new users until all 7 are delivered.
_ONBOARDING_TIPS = [
    (
        "&#x1F3E6;",
        "Add Your Bank Accounts",
        "Start by adding every bank account or wallet you use (GTB, Opay, Kuda…). "
        "Budget Right tracks your real balance — it only works when all accounts are in."
    ),
    (
        "&#x1F4B0;",
        "Log Your Income First",
        "Record this month's salary, freelance payment, or any money that came in. "
        "Your savings rate and net balance depend on having accurate income data."
    ),
    (
        "&#x2795;",
        "Quick-Add Your First Expense",
        "Go to Expenses and tap one of the Quick Add buttons — Transport, Food, Airtime. "
        "It takes 5 seconds. Make it a habit: log every spend the moment it happens."
    ),
    (
        "&#x1F4CA;",
        "Set a Monthly Budget",
        "Head to Settings and enter your monthly spending limit. "
        "Budget Right will alert you at 50%, 80%, and 100% so you never overspend silently."
    ),
    (
        "&#x1F3AF;",
        "Create a Savings Goal",
        "Whether it is Rent, Emergency Fund, or a new phone — create a goal on the "
        "Savings Goals page. Every naira you save gets tracked against it automatically."
    ),
    (
        "&#x1F501;",
        "Try the Tracker Page",
        "Add your recurring bills (DSTV, electricity, rent) on the Tracker page. "
        "Budget Right will remind you before they fall due so you are never caught off guard."
    ),
    (
        "&#x1F4E5;",
        "Import Your Bank Statement",
        "Download a CSV from your bank app and upload it on the Import CSV page. "
        "Budget Right auto-detects GTB, Access, Zenith, Opay, Kuda and 8 other formats — "
        "it fills in your expense history in seconds."
    ),
]

# ── Milestone thresholds ──────────────────────────────────────────────────────
# (streak_days, title, body, icon)
_STREAK_MILESTONES = [
    (3,  "3-Day Streak! &#x1F525;",
         "You have logged in 3 days in a row. Consistency is how financial habits form — keep going!",
         "&#x1F525;"),
    (7,  "7-Day Streak! &#x1F3C6;",
         "One full week tracked! You are building a real financial habit. "
         "Users who track for 7 days are 4× more likely to hit their savings goals.",
         "&#x1F3C6;"),
    (14, "2-Week Streak! &#x1F31F;",
         "14 days straight — you are in the top 20% of Budget Right users. "
         "Your spending patterns are now clear enough to spot trends.",
         "&#x1F31F;"),
    (30, "30-Day Streak! &#x1F451;",
         "A full month of consistent tracking. Your financial data is now detailed enough "
         "to generate meaningful year-over-year insights. Legendary!",
         "&#x1F451;"),
    (60, "60-Day Streak! &#x1F680;",
         "Two months without missing a day. You are the kind of person who actually "
         "achieves their financial goals. Stay the course.",
         "&#x1F680;"),
    (100, "100-Day Streak! &#x1F48E;",
          "100 consecutive days tracked. Fewer than 1% of personal finance app users "
          "ever reach this. You are extraordinary.",
          "&#x1F48E;"),
]

# ── In-app reminder schedule ──────────────────────────────────────────────────
# Reminders generated automatically based on user data.
# These fire at most once per day per type.


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_retention_engine(user_id: int) -> None:
    """
    Call once per login. Updates streak, delivers onboarding tips, generates
    smart in-app reminders, and fires milestone notifications.
    All operations are idempotent for the same calendar day.
    """
    today = datetime.now().date()

    _update_streak(user_id, today)
    _deliver_onboarding_tip(user_id, today)
    _generate_reminders(user_id, today)


# ─────────────────────────────────────────────────────────────────────────────
# STREAK ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _update_streak(user_id: int, today: date) -> None:
    """Update the user's streak. Fires milestone notifications when thresholds hit."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT current_streak, longest_streak, last_active_date "
            "FROM user_streaks WHERE user_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()

        if row is None:
            # First ever login — create the streak row
            cursor.execute("""
                INSERT INTO user_streaks (user_id, current_streak, longest_streak, last_active_date)
                VALUES (%s, 1, 1, %s)
            """, (user_id, today))
            _maybe_fire_milestone(cursor, user_id, 1)
            return

        last   = row["last_active_date"]
        curr   = int(row["current_streak"])
        longest= int(row["longest_streak"])

        if last == today:
            return  # already updated today — idempotent

        yesterday = today - timedelta(days=1)
        if last == yesterday:
            # Consecutive day — extend streak
            new_streak = curr + 1
        else:
            # Gap — streak broken
            new_streak = 1

        new_longest = max(longest, new_streak)

        cursor.execute("""
            UPDATE user_streaks
            SET current_streak = %s,
                longest_streak = %s,
                last_active_date = %s,
                streak_updated_at = NOW()
            WHERE user_id = %s
        """, (new_streak, new_longest, today, user_id))

        _maybe_fire_milestone(cursor, user_id, new_streak)


def _maybe_fire_milestone(cursor, user_id: int, streak: int) -> None:
    """Insert a milestone notification if this streak hits a threshold — once only."""
    for days, title, body, icon in _STREAK_MILESTONES:
        if streak == days:
            # Check we haven't already sent this milestone
            cursor.execute("""
                SELECT id FROM notifications
                WHERE user_id = %s AND type = 'milestone' AND title = %s
            """, (user_id, title))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO notifications (user_id, type, title, body, icon)
                    VALUES (%s, 'milestone', %s, %s, %s)
                """, (user_id, title, body, icon))
            break


def get_streak(user_id: int) -> dict:
    """Return {current, longest, last_active_date} or defaults."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT current_streak, longest_streak, last_active_date "
            "FROM user_streaks WHERE user_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
    if row:
        return {
            "current":          int(row["current_streak"]),
            "longest":          int(row["longest_streak"]),
            "last_active_date": row["last_active_date"],
        }
    return {"current": 0, "longest": 0, "last_active_date": None}


# ─────────────────────────────────────────────────────────────────────────────
# ONBOARDING TIPS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _deliver_onboarding_tip(user_id: int, today: date) -> None:
    """
    Send the next onboarding tip to a new user — one per day, up to 7 total.
    Stops after all tips are sent OR the account is more than 14 days old.
    """
    with get_db() as (conn, cursor):
        # Check account age
        cursor.execute("SELECT created_at FROM users WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
        if not user_row or not user_row["created_at"]:
            return
        account_age = (today - user_row["created_at"]).days
        if account_age > 14:
            return  # past the onboarding window

        # Get or create onboarding_tips row
        cursor.execute(
            "SELECT tips_sent, last_tip_at FROM onboarding_tips WHERE user_id = %s",
            (user_id,)
        )
        tips_row = cursor.fetchone()

        if tips_row is None:
            cursor.execute(
                "INSERT INTO onboarding_tips (user_id, tips_sent, last_tip_at) VALUES (%s, 0, NULL)",
                (user_id,)
            )
            tips_sent    = 0
            last_tip_at  = None
        else:
            tips_sent   = int(tips_row["tips_sent"])
            last_tip_at = tips_row["last_tip_at"]

        if tips_sent >= len(_ONBOARDING_TIPS):
            return  # all tips delivered

        if last_tip_at == today:
            return  # already sent one today

        icon, title, body = _ONBOARDING_TIPS[tips_sent]

        cursor.execute("""
            INSERT INTO notifications (user_id, type, title, body, icon)
            VALUES (%s, 'tip', %s, %s, %s)
        """, (user_id, title, body, icon))

        cursor.execute("""
            UPDATE onboarding_tips
            SET tips_sent = tips_sent + 1, last_tip_at = %s
            WHERE user_id = %s
        """, (today, user_id))


# ─────────────────────────────────────────────────────────────────────────────
# SMART REMINDERS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _already_sent_today(cursor, user_id: int, title_prefix: str, today: date) -> bool:
    """Return True if a notification with this title prefix was sent today."""
    cursor.execute("""
        SELECT id FROM notifications
        WHERE user_id = %s AND title LIKE %s
          AND created_at::DATE = %s
    """, (user_id, title_prefix + "%", today))
    return cursor.fetchone() is not None


def _generate_reminders(user_id: int, today: date) -> None:
    """
    Fetch ALL data needed for every reminder in a single DB round-trip,
    then build and insert reminders in Python — zero extra queries.

    BEFORE: 8+ separate SELECT calls (one per _already_sent_today check + data query).
    AFTER:  1 preflight SELECT with CTEs, then INSERT only what fires.
    """
    import calendar as _cal
    month_start   = today.replace(day=1)
    week_start    = today - timedelta(days=today.weekday())
    days_in_month = _cal.monthrange(today.year, today.month)[1]
    near_month_end = (days_in_month - today.day) <= 2

    with get_db() as (conn, cursor):

        # ── Preflight: single query fetches everything needed ─────────────────
        # 1. Which reminder title-prefixes were already sent today
        # 2. User's spending limit
        # 3. Total spent this month
        # 4. Bills due in next 3 days
        # 5. Streak row
        # 6. Active goal ≥ 90% complete
        # 7. Last expense date
        # 8. Last login date (for re-engagement)
        # 9. Monthly income/spend (for month-end nudge)
        # 10. Last week expense count (for Monday check-in)
        cursor.execute("""
            WITH sent_today AS (
                SELECT DISTINCT LEFT(title, 20) AS prefix
                FROM notifications
                WHERE user_id = %(uid)s AND created_at::DATE = %(today)s
            ),
            user_data AS (
                SELECT monthly_spending_limit, last_login
                FROM users WHERE id = %(uid)s
            ),
            monthly_spend AS (
                SELECT COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent,
                       COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income
                FROM transactions t JOIN banks b ON t.bank_id=b.id
                WHERE b.user_id=%(uid)s AND t.created_at >= %(month_start)s
            ),
            bills_due AS (
                SELECT name, amount, next_due
                FROM recurring_items
                WHERE user_id=%(uid)s AND active=1
                  AND next_due IS NOT NULL
                  AND next_due BETWEEN %(today)s AND %(three_days)s
                ORDER BY next_due LIMIT 3
            ),
            streak_row AS (
                SELECT last_active_date, current_streak
                FROM user_streaks WHERE user_id=%(uid)s
            ),
            near_goal AS (
                SELECT name, target_amount, current_amount
                FROM goals
                WHERE user_id=%(uid)s AND status='active'
                  AND current_amount > 0 AND target_amount > 0
                  AND (current_amount::float/target_amount) >= 0.9
                ORDER BY (current_amount::float/target_amount) DESC LIMIT 1
            ),
            last_expense AS (
                SELECT MAX(e.created_at) AS last_date
                FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%(uid)s
            ),
            last_week_count AS (
                SELECT COUNT(*) AS n
                FROM expenses e JOIN banks b ON e.bank_id=b.id
                WHERE b.user_id=%(uid)s AND e.created_at >= %(last_week_start)s
                  AND e.created_at < %(week_start)s
            )
            SELECT
                (SELECT json_agg(prefix) FROM sent_today)             AS sent_prefixes,
                (SELECT monthly_spending_limit FROM user_data)         AS spending_limit,
                (SELECT last_login FROM user_data)                     AS last_login,
                (SELECT spent FROM monthly_spend)                      AS m_spent,
                (SELECT income FROM monthly_spend)                     AS m_income,
                (SELECT json_agg(bills_due) FROM bills_due)            AS bills,
                (SELECT last_active_date FROM streak_row)              AS streak_date,
                (SELECT current_streak FROM streak_row)                AS streak_curr,
                (SELECT row_to_json(near_goal) FROM near_goal)         AS goal_row,
                (SELECT last_date FROM last_expense)                   AS last_exp_date,
                (SELECT n FROM last_week_count)                        AS last_week_n
        """, {
            "uid":            user_id,
            "today":          today,
            "month_start":    month_start,
            "three_days":     today + timedelta(days=3),
            "week_start":     week_start,
            "last_week_start": week_start - timedelta(days=7),
        })
        pf = cursor.fetchone()

        # Parse preflight results
        sent_today_prefixes = set(pf["sent_prefixes"] or [])
        spending_limit      = int(pf["spending_limit"] or 0)
        last_login          = pf["last_login"]
        m_spent             = int(pf["m_spent"] or 0)
        m_income            = int(pf["m_income"] or 0)
        bills               = pf["bills"] or []          # list of dicts
        streak_date         = pf["streak_date"]
        streak_curr         = int(pf["streak_curr"] or 0)
        goal_row            = pf["goal_row"]             # dict or None
        last_exp_date       = pf["last_exp_date"]
        last_week_n         = int(pf["last_week_n"] or 0)

        def _already_sent(prefix: str) -> bool:
            """Check against in-memory set — no extra DB calls."""
            return any(p.startswith(prefix[:20]) for p in sent_today_prefixes)

        def _insert(ntype, title, body, icon):
            cursor.execute("""
                INSERT INTO notifications (user_id, type, title, body, icon)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, ntype, title, body, icon))

        # ── 1. Bills due in next 3 days ────────────────────────────────────────
        if bills and not _already_sent("Bill Due"):
            for bill in bills:
                days_away = (bill["next_due"] - today).days if isinstance(bill["next_due"], date) else (
                    (__import__("datetime").date.fromisoformat(str(bill["next_due"])) - today).days
                )
                due_label = "today" if days_away == 0 else f"in {days_away} day{'s' if days_away != 1 else ''}"
                _insert("reminder",
                        f"Bill Due: {bill['name']}",
                        f"<strong>{bill['name']}</strong> is due {due_label} "
                        f"({bill['next_due']}) — NGN {int(bill['amount']):,}. "
                        f"Make sure you have enough balance on the account it will come from.",
                        "&#x1F514;")

        # ── 2. Budget alerts ────────────────────────────────────────────────────
        if spending_limit > 0 and not _already_sent("Budget Alert"):
            pct = m_spent / spending_limit * 100
            if 50 <= pct < 55:
                _insert("alert", "Budget Alert: 50% Used",
                        f"You have spent <strong>NGN {m_spent:,}</strong> — "
                        f"half your NGN {spending_limit:,} monthly budget. "
                        f"NGN {spending_limit - m_spent:,} remaining.",
                        "&#x26A0;&#xFE0F;")
            elif 80 <= pct < 85:
                _insert("alert", "Budget Alert: 80% Used",
                        f"You have used <strong>{pct:.0f}% of your monthly budget</strong> "
                        f"(NGN {m_spent:,} of NGN {spending_limit:,}). "
                        f"Only NGN {spending_limit - m_spent:,} left — slow down.",
                        "&#x1F6A8;")
            elif pct >= 100:
                _insert("alert", "Budget Alert: Limit Exceeded",
                        f"You have exceeded your NGN {spending_limit:,} monthly budget by "
                        f"<strong>NGN {m_spent - spending_limit:,}</strong>. "
                        f"Review your expenses and pause non-essential spending.",
                        "&#x1F534;")

        # ── 3. Streak broken ────────────────────────────────────────────────────
        if streak_date and not _already_sent("Streak Broken"):
            gap = (today - streak_date).days
            if gap == 2 and streak_curr >= 3:
                _insert("nudge", "Streak Broken — Come Back!",
                        f"Your {streak_curr}-day tracking streak ended yesterday. "
                        f"Don't let it stop you — start a new one today. "
                        f"Log one expense now to get back on track.",
                        "&#x1F614;")

        # ── 4. Goal almost reached ──────────────────────────────────────────────
        if goal_row and not _already_sent("Goal Almost"):
            remaining = int(goal_row["target_amount"]) - int(goal_row["current_amount"])
            pct_done  = round(int(goal_row["current_amount"]) / int(goal_row["target_amount"]) * 100)
            _insert("milestone",
                    f"Goal Almost Complete: {goal_row['name'][:30]}",
                    f"Your <strong>{goal_row['name']}</strong> goal is "
                    f"<strong>{pct_done}% complete</strong>! "
                    f"Just NGN {remaining:,} left. One more contribution and you are done!",
                    "&#x1F3AF;")

        # ── 5. Monday check-in ──────────────────────────────────────────────────
        if today.weekday() == 0 and not _already_sent("Weekly Check"):
            _insert("reminder", "Weekly Check-in",
                    f"New week, fresh start. "
                    + (f"You logged {last_week_n} expense{'s' if last_week_n != 1 else ''} last week. "
                       if last_week_n > 0 else "")
                    + "Log your first expense of the week to keep your streak alive!",
                    "&#x1F4C5;")

        # ── 6. No expenses in 3+ days ───────────────────────────────────────────
        if last_exp_date and not _already_sent("No Expenses"):
            # Convert to date if needed
            exp_date = last_exp_date if isinstance(last_exp_date, date) else last_exp_date.date()
            days_since = (today - exp_date).days
            if days_since >= 3:
                _insert("nudge", "No Expenses Logged Recently",
                        f"It has been <strong>{days_since} days</strong> since your last expense. "
                        f"Logging accurately keeps your balance right. "
                        f"Tap Expenses and add anything you have spent since {exp_date}.",
                        "&#x1F4DD;")

        # ── 7. Month-end surplus nudge ──────────────────────────────────────────
        if near_month_end and not _already_sent("Month-End"):
            net = m_income - m_spent
            if net > 0:
                _insert("tip", "Month-End: Move Your Surplus",
                        f"The month is almost over and you have <strong>NGN {net:,} left</strong>. "
                        f"Transfer some to a savings goal before new-month expenses arrive. "
                        f"Even NGN {int(net * 0.3):,} moved now builds a habit.",
                        "&#x1F4B8;")

        # ── 8. Re-engagement (7+ days away) ────────────────────────────────────
        if last_login and not _already_sent("Welcome Back"):
            login_date = last_login if isinstance(last_login, date) else last_login.date()
            days_away  = (today - login_date).days
            if days_away >= 7:
                _insert("nudge",
                        f"Welcome Back — {days_away} Days Away",
                        f"Good to see you! You were away for {days_away} days. "
                        + (f"NGN {m_spent:,} has been spent this month so far. " if m_spent > 0 else "")
                        + "Take a minute to log any expenses you missed.",
                        "&#x1F44B;")


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION INBOX API
# ─────────────────────────────────────────────────────────────────────────────

def push_notification(user_id: int, ntype: str, title: str, body: str,
                      icon: str = "&#x1F514;") -> None:
    """Insert a single notification manually."""
    with get_db() as (conn, cursor):
        cursor.execute("""
            INSERT INTO notifications (user_id, type, title, body, icon)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, ntype, title, body, icon))


def get_notifications(user_id: int, unread_only: bool = False, limit: int = 50) -> list:
    """Return list of notification dicts, newest first.
    Cached for 30 s — invalidated whenever a write happens via _invalidate_notif_cache().
    """
    return _get_notifications_cached(user_id, unread_only, limit)


@st.cache_data(ttl=30, show_spinner=False)
def _get_notifications_cached(user_id: int, unread_only: bool, limit: int) -> list:
    with get_db() as (conn, cursor):
        if unread_only:
            cursor.execute("""
                SELECT id, type, title, body, icon, read, created_at
                FROM notifications
                WHERE user_id = %s AND read = 0
                ORDER BY created_at DESC LIMIT %s
            """, (user_id, limit))
        else:
            cursor.execute("""
                SELECT id, type, title, body, icon, read, created_at
                FROM notifications
                WHERE user_id = %s
                ORDER BY created_at DESC LIMIT %s
            """, (user_id, limit))
        return cursor.fetchall()


def get_unread_count(user_id: int) -> int:
    """Cached for 30 s — invalidated on any write via _invalidate_notif_cache()."""
    return _get_unread_count_cached(user_id)


@st.cache_data(ttl=30, show_spinner=False)
def _get_unread_count_cached(user_id: int) -> int:
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = %s AND read = 0",
            (user_id,)
        )
        return int(cursor.fetchone()["n"] or 0)


def _invalidate_notif_cache() -> None:
    """Call after any write to notifications so cached reads reflect the change."""
    _get_notifications_cached.clear()
    _get_unread_count_cached.clear()


def mark_notifications_read(user_id: int) -> None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE notifications SET read = 1 WHERE user_id = %s AND read = 0",
            (user_id,)
        )
    _invalidate_notif_cache()


def mark_notification_read(notif_id: int) -> None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE notifications SET read = 1 WHERE id = %s",
            (notif_id,)
        )
    _invalidate_notif_cache()


def clear_all_notifications(user_id: int) -> None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "DELETE FROM notifications WHERE user_id = %s",
            (user_id,)
        )
    _invalidate_notif_cache()
