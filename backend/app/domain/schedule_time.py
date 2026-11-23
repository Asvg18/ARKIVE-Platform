"""Refusing a schedule that is already in the past.
Pure; schemas call it from their validators.
"""

from datetime import date, datetime, time, timedelta, timezone

# a fixed UTC+8 offset, not a tz-database zone: the Philippines has no
# daylight saving, and the server images may lack zoneinfo
PHILIPPINE_TIME = timezone(timedelta(hours=8), "PHT")


def now_in_philippines() -> datetime:
    return datetime.now(PHILIPPINE_TIME)


def ensure_not_in_past(date_text: str, time_text: str, *, now: datetime | None = None) -> None:
    """Raises ValueError when date_text + time_text ("2026-10-15",
    "09:00") is unreadable or earlier than now, in Philippine time. The
    panel's requirement: a schedule may not be set on a date, or at a
    time, that has already passed."""
    try:
        day = date.fromisoformat(date_text)
        clock = time.fromisoformat(time_text)
    except ValueError as exc:
        raise ValueError("Enter the date as YYYY-MM-DD and the time as HH:MM.") from exc
    current = now or now_in_philippines()
    if day < current.date():
        raise ValueError("That date has already passed. Pick today or a later date.")
    if datetime.combine(day, clock, tzinfo=PHILIPPINE_TIME) < current:
        raise ValueError("That time has already passed today. Pick a later time.")


def is_in_past(date_text: str, time_text: str, *, now: datetime | None = None) -> bool:
    """True when date_text + time_text has already started (or can't be
    read) -- for leaving a stale exam session out of what an applicant
    is offered, rather than refusing a request."""
    try:
        ensure_not_in_past(date_text, time_text, now=now)
    except ValueError:
        return True
    return False


def ensure_not_in_future(date_text: str, *, now: datetime | None = None) -> None:
    """Raises ValueError when date_text is unreadable or later than today
    (Philippine time) -- for the day something already happened, like the
    date an exam was taken."""
    try:
        day = date.fromisoformat(date_text)
    except ValueError as exc:
        raise ValueError("Enter the date as YYYY-MM-DD.") from exc
    current = now or now_in_philippines()
    if day > current.date():
        raise ValueError("That date hasn't happened yet. Pick today or an earlier date.")


def session_start(date_text: str, time_text: str) -> datetime | None:
    """The moment a session starts, in Philippine time; None when the
    date or time can't be read."""
    try:
        return datetime.combine(date.fromisoformat(date_text), time.fromisoformat(time_text), tzinfo=PHILIPPINE_TIME)
    except ValueError:
        return None


def starts_within(date_text: str, time_text: str, *, hours: float, now: datetime | None = None) -> bool:
    """True when the session starts less than `hours` from now -- or has
    already started, or can't be read. Used for the 24-hour cut-off on
    an applicant changing their exam session."""
    start = session_start(date_text, time_text)
    if start is None:
        return True
    return start - (now or now_in_philippines()) < timedelta(hours=hours)


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def format_day(date_text: str) -> str:
    """"2030-03-01" -> "Fri, 1 Mar 2030" -- the same wording the
    frontend's formatDay uses, for notifications and emails. Unreadable
    input comes back as it was."""
    try:
        day = date.fromisoformat(date_text)
    except ValueError:
        return date_text
    return f"{_WEEKDAYS[day.weekday()]}, {day.day} {_MONTHS[day.month - 1]} {day.year}"


def format_clock(time_text: str) -> str:
    """"13:30" -> "1:30 PM"; unreadable input comes back as it was."""
    try:
        clock = time.fromisoformat(time_text)
    except ValueError:
        return time_text
    hour = clock.hour % 12 or 12
    return f"{hour}:{clock.minute:02d} {'AM' if clock.hour < 12 else 'PM'}"


def format_session(date_text: str, time_text: str, end_time_text: str | None = None) -> str:
    """"Fri, 1 Mar 2030, 9:00 AM – 11:30 AM" (or just the start when the
    session has no end), for exam-session notifications and emails."""
    window = format_clock(time_text)
    if end_time_text:
        window = f"{window} – {format_clock(end_time_text)}"
    return f"{format_day(date_text)}, {window}"
