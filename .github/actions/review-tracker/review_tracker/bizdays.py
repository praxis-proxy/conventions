"""Calendar-day and business-day arithmetic, both evaluated in UTC.

Two clocks live here and they are deliberately different:

* `calendar_days_elapsed` is `floor((now - start) / 24 h)`. It feeds the
  project's "Oldest outstanding response (days)" field, so a wait of
  47 h 59 m reports 1.
* `business_days_elapsed` counts whole Monday-to-Friday steps and gates
  reminders. There is no holiday calendar.

UTC is the reference zone for both: every GitHub timestamp is already UTC,
runners are UTC, and there are no daylight-saving discontinuities to make a
threshold shift twice a year.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DAYS_PER_WEEK = 7
SECONDS_PER_DAY = 86400  # 24 h
WEEKDAYS_PER_WEEK = 5  # Monday through Friday


def add_business_days(start, days):
    """`start` advanced by `days` Monday-to-Friday days, keeping the time of day.

    Advancing from a weekend first walks forward to the next weekday, so three
    business days after a Saturday morning is the following Wednesday morning.
    """
    moment = start
    remaining = days

    while remaining > 0:
        moment += timedelta(days=1)
        if moment.weekday() < WEEKDAYS_PER_WEEK:
            remaining -= 1

    return moment


def business_days_elapsed(start, now):
    """Whole business days completed since `start`.

    The exact inverse of [add_business_days]: this returns the largest `n` for
    which `add_business_days(start, n) <= now`. Deriving the reminder text and
    the reminder threshold from the same function keeps them from disagreeing.
    """
    if now <= start:
        return 0

    elapsed = _weekdays_through(now.date()) - _weekdays_through(start.date())
    if now.weekday() < WEEKDAYS_PER_WEEK and now.time() < start.time():
        elapsed -= 1

    return max(elapsed, 0)


def calendar_days_elapsed(start, now):
    """Whole 24-hour periods between `start` and `now`, rounded down."""
    seconds = (now - start).total_seconds()
    if seconds <= 0:
        return 0

    return int(seconds // SECONDS_PER_DAY)


def parse_timestamp(value):
    """An ISO-8601 GitHub timestamp as an aware UTC datetime, or None.

    Returning None rather than guessing is deliberate: a caller must report the
    gap instead of substituting a different timestamp.
    """
    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _weekdays_through(day):
    """Count of Monday-to-Friday dates from the proleptic epoch through `day`.

    Ordinal 1 is a Monday, so each whole week contributes five weekdays and the
    remainder contributes at most five more.
    """
    weeks, remainder = divmod(day.toordinal(), DAYS_PER_WEEK)
    return weeks * WEEKDAYS_PER_WEEK + min(remainder, WEEKDAYS_PER_WEEK)
