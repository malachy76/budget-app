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
    Scan the user's data and generate contextual in-app reminders.
    Each reminder fires at most once per day per type.
    """
    month_start   = today.replace(day=1)
    week_start    = today - timedelta(days=today.weekday())

    with get_db() as (conn, cursor):

        # ── 1. Bills due in the next 3 days ───────────────────────────────────
        if not _already_sent_today(cursor, user_id, "Bill Due", today):
            cursor.execute("""
                SELECT name, amount, next_due FROM recurring_items
                WHERE user_id = %s AND active = 1
                  AND next_due IS NOT NULL
                  AND next_due BETWEEN %s AND %s
                ORDER BY next_due ASC LIMIT 3
            """, (user_id, today, today + timedelta(days=3)))
            due_bills = cursor.fetchall()
            if due_bills:
                for bill in due_bills:
                    days_away = (bill["next_due"] - today).days
                    due_label = "today" if days_away == 0 else f"in {days_away} day{'s' if days_away != 1 else ''}"
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, body, icon)
                        VALUES (%s, 'reminder', %s, %s, '&#x1F514;')
                    """, (
                        user_id,
                        f"Bill Due: {bill['name']}",
                        f"<strong>{bill['name']}</strong> is due {due_label} "
                        f"({bill['next_due']}) — NGN {int(bill['amount']):,}. "
                        f"Make sure you have enough balance on the account it will come from."
                    ))

        # ── 2. Budget halfway alert ────────────────────────────────────────────
        if not _already_sent_today(cursor, user_id, "Budget Alert", today):
            cursor.execute("SELECT monthly_spending_limit FROM users WHERE id = %s", (user_id,))
            limit_row = cursor.fetchone()
            spending_limit = int(limit_row["monthly_spending_limit"] or 0) if limit_row else 0
            if spending_limit > 0:
                cursor.execute("""
                    SELECT COALESCE(SUM(t.amount), 0) AS spent
                    FROM transactions t JOIN banks b ON t.bank_id = b.id
                    WHERE b.user_id = %s AND t.type = 'debit' AND t.created_at >= %s
                """, (user_id, month_start))
                spent = int(cursor.fetchone()["spent"] or 0)
                pct   = spent / spending_limit * 100
                if 50 <= pct < 55:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, body, icon)
                        VALUES (%s, 'alert', %s, %s, '&#x26A0;&#xFE0F;')
                    """, (
                        user_id,
                        "Budget Alert: 50% Used",
                        f"You have spent <strong>NGN {spent:,}</strong> — "
                        f"half your NGN {spending_limit:,} monthly budget. "
                        f"NGN {spending_limit - spent:,} remaining for the rest of the month."
                    ))
                elif 80 <= pct < 85:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, body, icon)
                        VALUES (%s, 'alert', %s, %s, '&#x1F6A8;')
                    """, (
                        user_id,
                        "Budget Alert: 80% Used",
                        f"You have used <strong>{pct:.0f}% of your monthly budget</strong> "
                        f"(NGN {spent:,} of NGN {spending_limit:,}). "
                        f"Only NGN {spending_limit - spent:,} left — slow down before you exceed it."
                    ))
                elif pct >= 100:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, body, icon)
                        VALUES (%s, 'alert', %s, %s, '&#x1F534;')
                    """, (
                        user_id,
                        "Budget Alert: Limit Exceeded",
                        f"You have exceeded your NGN {spending_limit:,} monthly budget by "
                        f"<strong>NGN {spent - spending_limit:,}</strong>. "
                        f"Review your expenses and pause non-essential spending for the rest of the month."
                    ))

        # ── 3. Streak broken nudge ─────────────────────────────────────────────
        if not _already_sent_today(cursor, user_id, "Streak Broken", today):
            cursor.execute(
                "SELECT last_active_date, current_streak FROM user_streaks WHERE user_id = %s",
                (user_id,)
            )
            streak_row = cursor.fetchone()
            if streak_row and streak_row["last_active_date"]:
                gap = (today - streak_row["last_active_date"]).days
                if gap == 2 and int(streak_row["current_streak"]) >= 3:
                    # Yesterday was missed — streak broke
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, body, icon)
                        VALUES (%s, 'nudge', %s, %s, '&#x1F614;')
                    """, (
                        user_id,
                        "Streak Broken — Come Back!",
                        f"Your {int(streak_row['current_streak'])}-day tracking streak ended yesterday. "
                        f"Don't let it stop you — start a new one today. "
                        f"Log one expense now to get back on track."
                    ))

        # ── 4. Goal almost reached ─────────────────────────────────────────────
        if not _already_sent_today(cursor, user_id, "Goal Almost", today):
            cursor.execute("""
                SELECT name, target_amount, current_amount
                FROM goals
                WHERE user_id = %s AND status = 'active'
                  AND current_amount > 0
                  AND target_amount > 0
                  AND (current_amount::float / target_amount) >= 0.9
                ORDER BY (current_amount::float / target_amount) DESC
                LIMIT 1
            """, (user_id,))
            near_goal = cursor.fetchone()
            if near_goal:
                remaining = int(near_goal["target_amount"]) - int(near_goal["current_amount"])
                pct_done  = round(int(near_goal["current_amount"]) / int(near_goal["target_amount"]) * 100)
                cursor.execute("""
                    INSERT INTO notifications (user_id, type, title, body, icon)
                    VALUES (%s, 'milestone', %s, %s, '&#x1F3AF;')
                """, (
                    user_id,
                    f"Goal Almost Complete: {near_goal['name'][:30]}",
                    f"Your <strong>{near_goal['name']}</strong> goal is <strong>{pct_done}% complete</strong>! "
                    f"Just NGN {remaining:,} left to go. "
                    f"One more contribution and you are done!"
                ))

        # ── 5. Weekly log reminder (Monday) ───────────────────────────────────
        if today.weekday() == 0:  # Monday
            if not _already_sent_today(cursor, user_id, "Weekly Check-in", today):
                cursor.execute("""
                    SELECT COUNT(*) AS n FROM expenses e
                    JOIN banks b ON e.bank_id = b.id
                    WHERE b.user_id = %s AND e.created_at >= %s
                """, (user_id, week_start - timedelta(days=7)))
                last_week_count = int(cursor.fetchone()["n"] or 0)
                cursor.execute("""
                    INSERT INTO notifications (user_id, type, title, body, icon)
                    VALUES (%s, 'reminder', %s, %s, '&#x1F4C5;')
                """, (
                    user_id,
                    "Weekly Check-in",
                    f"New week, fresh start. "
                    + (f"You logged {last_week_count} expense{'s' if last_week_count != 1 else ''} last week. "
                       if last_week_count > 0 else "")
                    + "Log your first expense of the week to keep your streak alive!"
                ))

        # ── 6. No expense in 3+ days nudge ────────────────────────────────────
        if not _already_sent_today(cursor, user_id, "No Expenses Logged", today):
            cursor.execute("""
                SELECT MAX(e.created_at) AS last_expense
                FROM expenses e JOIN banks b ON e.bank_id = b.id
                WHERE b.user_id = %s
            """, (user_id,))
            last_exp_row = cursor.fetchone()
            if last_exp_row and last_exp_row["last_expense"]:
                days_since = (today - last_exp_row["last_expense"]).days
                if days_since >= 3:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, body, icon)
                        VALUES (%s, 'nudge', %s, %s, '&#x1F4DD;')
                    """, (
                        user_id,
                        "No Expenses Logged Recently",
                        f"It has been <strong>{days_since} days</strong> since your last expense entry. "
                        f"Even if you have not spent much, logging accurately keeps your balance right. "
                        f"Tap Expenses and add anything you have spent since {last_exp_row['last_expense']}."
                    ))

        # ── 7. Month-end savings nudge (last 3 days) ──────────────────────────
        import calendar as _cal
        days_in_month = _cal.monthrange(today.year, today.month)[1]
        if days_in_month - today.day <= 2:
            if not _already_sent_today(cursor, user_id, "Month-End", today):
                cursor.execute("""
                    SELECT
                        COALESCE(SUM(CASE WHEN t.type='credit' THEN t.amount ELSE 0 END),0) AS income,
                        COALESCE(SUM(CASE WHEN t.type='debit'  THEN t.amount ELSE 0 END),0) AS spent
                    FROM transactions t JOIN banks b ON t.bank_id = b.id
                    WHERE b.user_id = %s AND t.created_at >= %s
                """, (user_id, month_start))
                mn = cursor.fetchone()
                m_income = int(mn["income"] or 0)
                m_spent  = int(mn["spent"]  or 0)
                net      = m_income - m_spent
                if net > 0:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, body, icon)
                        VALUES (%s, 'tip', %s, %s, '&#x1F4B8;')
                    """, (
                        user_id,
                        "Month-End: Move Your Surplus",
                        f"The month is almost over and you have <strong>NGN {net:,} left</strong> "
                        f"after spending. Before new-month expenses arrive, "
                        f"transfer some to a savings goal or investment. "
                        f"Even NGN {int(net * 0.3):,} moved now builds a habit."
                    ))

        # ── 8. Re-engagement nudge (7+ days since last login but seen today) ──
        if not _already_sent_today(cursor, user_id, "Welcome Back", today):
            cursor.execute(
                "SELECT last_login FROM users WHERE id = %s",
                (user_id,)
            )
            user_row = cursor.fetchone()
            if user_row and user_row["last_login"]:
                days_away = (today - user_row["last_login"]).days
                if days_away >= 7:
                    cursor.execute("""
                        SELECT COALESCE(SUM(t.amount), 0) AS spent
                        FROM transactions t JOIN banks b ON t.bank_id = b.id
                        WHERE b.user_id = %s AND t.type = 'debit' AND t.created_at >= %s
                    """, (user_id, month_start))
                    m_spent = int(cursor.fetchone()["spent"] or 0)
                    cursor.execute("""
                        INSERT INTO notifications (user_id, type, title, body, icon)
                        VALUES (%s, 'nudge', %s, %s, '&#x1F44B;')
                    """, (
                        user_id,
                        f"Welcome Back — {days_away} Days Away",
                        f"Good to see you! You were away for {days_away} days. "
                        + (f"NGN {m_spent:,} has been spent this month so far. "
                           if m_spent > 0 else "")
                        + "Take a minute to log any expenses you missed so your records stay accurate."
                    ))


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
    """Return list of notification dicts, newest first."""
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
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = %s AND read = 0",
            (user_id,)
        )
        return int(cursor.fetchone()["n"] or 0)


def mark_notifications_read(user_id: int) -> None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE notifications SET read = 1 WHERE user_id = %s AND read = 0",
            (user_id,)
        )


def mark_notification_read(notif_id: int) -> None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE notifications SET read = 1 WHERE id = %s",
            (notif_id,)
        )


def clear_all_notifications(user_id: int) -> None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "DELETE FROM notifications WHERE user_id = %s",
            (user_id,)
        )
