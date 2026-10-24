"""Reconstructs who owes an initial review on a pull request, and since when."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .bizdays import calendar_days_elapsed, parse_timestamp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ASSIGNMENT_EVENTS = ("assigned", "unassigned")
BOT_SUFFIX = "[bot]"
READY_EVENT = "ready_for_review"

# States that mean a review was actually submitted. DISMISSED belongs here:
# dismissal is something done to a review afterwards, and it does not un-submit
# it. PENDING is absent because an unsubmitted review is not a response.
RESPONSE_STATES = frozenset(
    {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"}
)


@dataclass(frozen=True)
class Outstanding:
    """A current assignee who has not submitted an initial review yet."""

    login: str
    assigned_at: datetime
    effective_start: datetime


@dataclass(frozen=True)
class Tracking:
    """What the tracker concluded about one pull request."""

    outstanding: tuple
    ambiguities: tuple

    @property
    def trustworthy(self):
        """True when nothing was missing or ambiguous, so acting on this is safe."""
        return not self.ambiguities


def summarize(outstanding, now):
    """The two project field values for a pull request: awaiting text and days.

    Returns `("", None)` when nobody owes a review, which the caller writes as
    a clear of both fields.
    """
    if not outstanding:
        return "", None

    text = ", ".join(item.login for item in outstanding)
    oldest = max(
        calendar_days_elapsed(item.effective_start, now) for item in outstanding
    )
    return text, oldest


def track(pull, timeline, reviews):
    """The current assignees of `pull` who still owe an initial review.

    A closed or draft pull request yields nobody, so re-running this against
    freshly fetched data immediately before posting suppresses reminders on a
    pull request that has since been closed or sent back to draft.

    A person's wait starts at their current assignment, or at the most recent
    draft-to-ready transition when that is later. A review submitted any time
    after their assignment stops their timer, including one given while the
    pull request was still a draft.

    The timer stops for good. Dismissing that review afterwards does not
    restart it, because the initial response did happen; what follows a
    dismissal is a further review round, which this version does not track.
    """
    if pull.get("state") != "open" or pull.get("draft"):
        return Tracking((), ())

    ambiguities = []
    ready_at = _latest_ready(timeline, ambiguities)
    responses = _responses(reviews, ambiguities)

    outstanding = []
    for login in _human_assignees(pull):
        assigned_at = _assignment_start(timeline, login, ambiguities)
        if assigned_at is None:
            continue

        replied_at = responses.get(login)
        if replied_at is not None and replied_at >= assigned_at:
            continue

        start = assigned_at if ready_at is None else max(assigned_at, ready_at)
        outstanding.append(Outstanding(login, assigned_at, start))

    outstanding.sort(key=lambda item: item.login)
    return Tracking(tuple(outstanding), tuple(ambiguities))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _assignment_start(timeline, login, ambiguities):
    """Start of `login`'s current uninterrupted assignment, or None.

    Events are replayed in timestamp order rather than trusting the order the
    API returned them in. Re-assigning somebody already assigned keeps the
    earlier start, so the timer is never quietly reset.
    """
    events = []
    for event in timeline:
        name = event.get("event")
        if name not in ASSIGNMENT_EVENTS:
            continue
        if (event.get("assignee") or {}).get("login") != login:
            continue

        moment = parse_timestamp(event.get("created_at"))
        if moment is None:
            ambiguities.append(f"@{login} has an {name} event with no usable timestamp")
            return None

        events.append((moment, name))

    start = None
    for moment, name in sorted(events):
        if name == "unassigned":
            start = None
        elif start is None:
            start = moment

    if start is None:
        ambiguities.append(
            f"@{login} is assigned but has no assignment event in the timeline"
        )

    return start


def _human_assignees(pull):
    """Current assignees that are people rather than apps."""
    logins = []
    for assignee in pull.get("assignees") or []:
        login = assignee.get("login")
        if not login or assignee.get("type") == "Bot" or login.endswith(BOT_SUFFIX):
            continue
        logins.append(login)

    return sorted(set(logins))


def _latest_ready(timeline, ambiguities):
    """Timestamp of the most recent draft-to-ready transition, or None."""
    latest = None
    for event in timeline:
        if event.get("event") != READY_EVENT:
            continue

        moment = parse_timestamp(event.get("created_at"))
        if moment is None:
            ambiguities.append("a ready_for_review event has no usable timestamp")
            continue

        if latest is None or moment > latest:
            latest = moment

    return latest


def _responses(reviews, ambiguities):
    """Earliest submitted review per login.

    A review only counts with a usable `submitted_at`, which is the evidence
    that it was submitted rather than merely started. A review in a counting
    state without one is reported instead of assumed either way.

    PENDING reviews are excluded by state and carry no `submitted_at` anyway,
    and ordinary issue comments are never read as reviews because they are not
    in this feed. Reviews are matched to assignees by login, and bot accounts
    are already excluded from the assignee list, so a bot review can never
    discharge a person.
    """
    earliest = {}
    for review in reviews:
        state = (review.get("state") or "").upper()
        if state not in RESPONSE_STATES:
            continue

        login = (review.get("user") or {}).get("login")
        if not login:
            continue

        moment = parse_timestamp(review.get("submitted_at"))
        if moment is None:
            ambiguities.append(f"@{login} has a {state} review with no submitted_at")
            continue

        if login not in earliest or moment < earliest[login]:
            earliest[login] = moment

    return earliest
