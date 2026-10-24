"""Reminder scheduling and the bot-authored comment markers that record it.

Reminder state is durable because it lives in the bot's own comments on the
pull request, so a re-run, a concurrent run, or a lost workflow log cannot
cause a second reminder. Only comments authored by the app's own bot account
are believed, so a marker pasted by a person is ignored rather than trusted
as proof that a reminder was already sent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from .bizdays import add_business_days, business_days_elapsed, parse_timestamp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FINAL_STAGE = 2  # first reminder, then one follow-up, then silence
FIRST_REMINDER_BUSINESS_DAYS = 3
FOLLOW_UP_BUSINESS_DAYS = 3
LOGIN_PATTERN = re.compile(r"\A[A-Za-z0-9](?:-?[A-Za-z0-9]){0,38}\Z")
MARKER_PREFIX = "<!-- praxis-review-reminder "
MARKER_SUFFIX = " -->"


@dataclass(frozen=True)
class Due:
    """A reminder that has come due and should be posted now."""

    login: str
    assigned_at: datetime
    business_days: int
    stage: int


@dataclass(frozen=True)
class Record:
    """Proof the bot posted one reminder, recovered from its own comment."""

    login: str
    assigned_at: datetime
    posted_at: datetime
    stage: int


def due_reminders(outstanding, records, now):
    """Reminders owed right now, and anything too ambiguous to act on.

    Each person is keyed by the start of their current assignment, so a
    reassignment begins a fresh sequence while a draft-and-ready cycle does
    not: toggling draft resets the clock but never the reminder budget.
    """
    due = []
    ambiguities = []

    for item in outstanding:
        if not LOGIN_PATTERN.match(item.login):
            ambiguities.append(f"assignee login {item.login!r} is not a valid login")
            continue

        stage = _next_stage(item, records, now)
        if stage is None:
            continue

        elapsed = business_days_elapsed(item.effective_start, now)
        due.append(Due(item.login, item.assigned_at, elapsed, stage))

    return due, ambiguities


def marker(login, assigned_at, stage):
    """The machine-readable record proving the bot reminded somebody."""
    payload = json.dumps(
        {"assigned_at": _iso(assigned_at), "login": login, "stage": stage},
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{MARKER_PREFIX}{payload}{MARKER_SUFFIX}"


def parse_records(comments, bot_login):
    """Reminder records recovered from comments the bot itself authored."""
    records = []
    ambiguities = []

    for comment in comments:
        user = comment.get("user") or {}
        if user.get("type") != "Bot" or user.get("login") != bot_login:
            continue

        posted_at = parse_timestamp(comment.get("created_at"))
        for line in (comment.get("body") or "").splitlines():
            stripped = line.strip()
            if not stripped.startswith(MARKER_PREFIX):
                continue
            if not stripped.endswith(MARKER_SUFFIX):
                continue

            if posted_at is None:
                ambiguities.append("a bot reminder comment has no usable created_at")
                break

            record = _decode(stripped, posted_at)
            if record is None:
                ambiguities.append("a bot reminder marker could not be decoded")
                continue

            records.append(record)

    return records, ambiguities


def render(due):
    """The reminder comment body covering everyone whose reminder is due."""
    lines = [marker(item.login, item.assigned_at, item.stage) for item in due]
    lines.append("")

    # The wait is counted from the assignment or from the most recent
    # draft-to-ready transition, whichever is later, so the message says how
    # long the review has been owed rather than how long ago it was assigned.
    for item in due:
        unit = "day" if item.business_days == 1 else "days"
        lines.append(
            f"@{item.login} — This PR has been awaiting your initial review "
            f"for {item.business_days} business {unit}."
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _decode(line, posted_at):
    """One marker line as a Record, or None when it is malformed."""
    raw = line[len(MARKER_PREFIX) : -len(MARKER_SUFFIX)]

    try:
        payload = json.loads(raw)
    except ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    assigned_at = parse_timestamp(payload.get("assigned_at"))
    login = payload.get("login")
    stage = payload.get("stage")
    if assigned_at is None or not isinstance(login, str):
        return None
    if not isinstance(stage, int) or isinstance(stage, bool):
        return None

    return Record(login, assigned_at, posted_at, stage)


def _iso(moment):
    """A UTC timestamp in the `Z` form GitHub uses."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_stage(item, records, now):
    """The reminder stage owed for this assignment, or None when none is.

    The follow-up is measured from when the first reminder was actually
    posted, not from the assignment, so a late first reminder does not make
    the follow-up immediately due as well.
    """
    mine = [
        record
        for record in records
        if record.login == item.login and record.assigned_at == item.assigned_at
    ]

    posted = max((record.stage for record in mine), default=0)
    if posted >= FINAL_STAGE:
        return None

    if posted == 0:
        anchor = item.effective_start
        threshold = FIRST_REMINDER_BUSINESS_DAYS
    else:
        anchor = min(record.posted_at for record in mine if record.stage == posted)
        threshold = FOLLOW_UP_BUSINESS_DAYS

    if add_business_days(anchor, threshold) > now:
        return None

    return posted + 1
