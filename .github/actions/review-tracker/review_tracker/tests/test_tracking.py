"""Reconstructing who owes an initial review, and since when."""

import unittest
from datetime import datetime, timezone

from ..tracking import summarize, track

NOW = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


class Assignment(unittest.TestCase):
    def test_tracks_an_initial_assignment(self):
        result = track(pull(["ada"]), [assigned("ada", at(1))], [])

        self.assertEqual(
            [item.login for item in result.outstanding],
            ["ada"],
            "an assignee with no review is outstanding",
        )
        self.assertEqual(
            result.outstanding[0].assigned_at,
            moment(1),
            "the wait starts at the assignment event",
        )

    def test_drops_someone_unassigned(self):
        timeline = [assigned("ada", at(1)), unassigned("ada", at(2))]

        result = track(pull([]), timeline, [])

        self.assertEqual(
            result.outstanding, (), "an unassigned person owes nothing"
        )

    def test_uses_the_latest_assignment_after_reassignment(self):
        timeline = [
            assigned("ada", at(1)),
            unassigned("ada", at(2)),
            assigned("ada", at(8)),
        ]

        result = track(pull(["ada"]), timeline, [])

        self.assertEqual(
            result.outstanding[0].assigned_at,
            moment(8),
            "reassignment restarts the wait from the new assignment",
        )

    def test_does_not_reset_on_a_repeated_assignment(self):
        timeline = [assigned("ada", at(1)), assigned("ada", at(8))]

        result = track(pull(["ada"]), timeline, [])

        self.assertEqual(
            result.outstanding[0].assigned_at,
            moment(1),
            "a duplicate assignment must not reset the timer",
        )

    def test_replays_events_out_of_order(self):
        timeline = [unassigned("ada", at(2)), assigned("ada", at(1))]

        result = track(pull([]), timeline, [])

        self.assertEqual(
            result.outstanding,
            (),
            "events are ordered by timestamp, not by API order",
        )

    def test_ignores_bot_assignees(self):
        timeline = [assigned("praxis-bot[bot]", at(1))]
        subject = pull([{"login": "praxis-bot[bot]", "type": "Bot"}])

        result = track(subject, timeline, [])

        self.assertEqual(result.outstanding, (), "apps are not asked for reviews")


class DraftAndReady(unittest.TestCase):
    def test_counts_from_ready_when_assignment_came_first(self):
        timeline = [assigned("ada", at(1)), ready(at(3))]

        result = track(pull(["ada"]), timeline, [])

        self.assertEqual(
            result.outstanding[0].effective_start,
            moment(3),
            "a wait cannot start before the pull request was ready",
        )

    def test_keeps_the_assignment_when_it_came_after_ready(self):
        timeline = [ready(at(1)), assigned("ada", at(3))]

        result = track(pull(["ada"]), timeline, [])

        self.assertEqual(
            result.outstanding[0].effective_start,
            moment(3),
            "a later assignment is when that person's wait began",
        )

    def test_the_most_recent_ready_wins(self):
        timeline = [assigned("ada", at(1)), ready(at(2)), ready(at(9))]

        result = track(pull(["ada"]), timeline, [])

        self.assertEqual(
            result.outstanding[0].effective_start,
            moment(9),
            "each return to ready restarts the clock",
        )

    def test_uses_the_assignment_when_never_a_draft(self):
        result = track(pull(["ada"]), [assigned("ada", at(1))], [])

        self.assertEqual(
            result.outstanding[0].effective_start,
            moment(1),
            "a pull request opened ready has no ready event",
        )

    def test_skips_a_draft_pull_request(self):
        subject = pull(["ada"], draft=True)

        result = track(subject, [assigned("ada", at(1))], [])

        self.assertEqual(result.outstanding, (), "drafts are not tracked")

    def test_skips_a_closed_pull_request(self):
        subject = pull(["ada"], state="closed")

        result = track(subject, [assigned("ada", at(1))], [])

        self.assertEqual(result.outstanding, (), "closed pull requests are not tracked")


class Responses(unittest.TestCase):
    def test_a_review_after_assignment_stops_the_timer(self):
        reviews = [review("ada", "APPROVED", at(4))]

        result = track(pull(["ada"]), [assigned("ada", at(1))], reviews)

        self.assertEqual(result.outstanding, (), "an approval is a response")

    def test_a_review_before_assignment_does_not_count(self):
        reviews = [review("ada", "COMMENTED", at(1))]

        result = track(pull(["ada"]), [assigned("ada", at(5))], reviews)

        self.assertEqual(
            [item.login for item in result.outstanding],
            ["ada"],
            "a review predating the assignment is not a response to it",
        )

    def test_a_review_during_draft_counts(self):
        timeline = [assigned("ada", at(1)), ready(at(9))]
        reviews = [review("ada", "CHANGES_REQUESTED", at(4))]

        result = track(pull(["ada"]), timeline, reviews)

        self.assertEqual(
            result.outstanding,
            (),
            "a review given while still a draft is still an initial response",
        )

    def test_a_pending_review_does_not_count(self):
        reviews = [
            {"state": "PENDING", "user": {"login": "ada"}, "submitted_at": None}
        ]

        result = track(pull(["ada"]), [assigned("ada", at(1))], reviews)

        self.assertEqual(
            [item.login for item in result.outstanding],
            ["ada"],
            "an unsubmitted review is not a response",
        )

    def test_a_dismissed_review_still_counts(self):
        reviews = [review("ada", "DISMISSED", at(4))]

        result = track(pull(["ada"]), [assigned("ada", at(1))], reviews)

        self.assertEqual(
            result.outstanding,
            (),
            "dismissal does not un-submit the initial response",
        )

    def test_a_dismissed_review_does_not_restart_the_timer(self):
        timeline = [assigned("ada", at(1))]
        reviews = [review("ada", "DISMISSED", at(4))]

        before = track(pull(["ada"]), timeline, [review("ada", "APPROVED", at(4))])
        after = track(pull(["ada"]), timeline, reviews)

        self.assertEqual(
            after.outstanding,
            before.outstanding,
            "dismissing an approval must leave the result unchanged",
        )

    def test_a_dismissed_review_needs_evidence_it_was_submitted(self):
        reviews = [
            {"state": "DISMISSED", "user": {"login": "ada"}, "submitted_at": None}
        ]

        result = track(pull(["ada"]), [assigned("ada", at(1))], reviews)

        self.assertEqual(
            [item.login for item in result.outstanding],
            ["ada"],
            "without a submitted_at there is no evidence of a response",
        )
        self.assertTrue(
            any("submitted_at" in note for note in result.ambiguities),
            f"the missing evidence must be reported, got {result.ambiguities}",
        )

    def test_a_dismissed_review_before_assignment_does_not_count(self):
        reviews = [review("ada", "DISMISSED", at(1))]

        result = track(pull(["ada"]), [assigned("ada", at(5))], reviews)

        self.assertEqual(
            [item.login for item in result.outstanding],
            ["ada"],
            "a dismissed review predating the assignment is not a response to it",
        )

    def test_another_persons_review_does_not_count(self):
        reviews = [review("grace", "APPROVED", at(4))]

        result = track(pull(["ada"]), [assigned("ada", at(1))], reviews)

        self.assertEqual(
            [item.login for item in result.outstanding],
            ["ada"],
            "somebody else reviewing does not discharge this assignee",
        )

    def test_tracks_a_partial_response_among_assignees(self):
        timeline = [assigned("ada", at(1)), assigned("grace", at(1))]
        reviews = [review("grace", "APPROVED", at(4))]

        result = track(pull(["ada", "grace"]), timeline, reviews)

        self.assertEqual(
            [item.login for item in result.outstanding],
            ["ada"],
            "only the assignee who has not reviewed is outstanding",
        )


class IncompleteData(unittest.TestCase):
    def test_reports_a_missing_assignment_event(self):
        result = track(pull(["ada"]), [], [])

        self.assertEqual(result.outstanding, (), "nothing is assumed about the start")
        self.assertTrue(
            any("no assignment event" in note for note in result.ambiguities),
            f"the gap must be reported, got {result.ambiguities}",
        )
        self.assertFalse(result.trustworthy, "incomplete data is not trustworthy")

    def test_reports_an_unusable_assignment_timestamp(self):
        timeline = [{"event": "assigned", "assignee": {"login": "ada"}}]

        result = track(pull(["ada"]), timeline, [])

        self.assertTrue(
            any("no usable timestamp" in note for note in result.ambiguities),
            f"the gap must be reported, got {result.ambiguities}",
        )

    def test_reports_a_review_with_no_submitted_at(self):
        reviews = [
            {"state": "APPROVED", "user": {"login": "ada"}, "submitted_at": None}
        ]

        result = track(pull(["ada"]), [assigned("ada", at(1))], reviews)

        self.assertTrue(
            any("submitted_at" in note for note in result.ambiguities),
            f"the gap must be reported, got {result.ambiguities}",
        )

    def test_reports_an_unusable_ready_timestamp(self):
        timeline = [assigned("ada", at(1)), {"event": "ready_for_review"}]

        result = track(pull(["ada"]), timeline, [])

        self.assertFalse(result.trustworthy, "an unusable ready event is ambiguous")


class Summary(unittest.TestCase):
    def test_lists_everyone_and_the_longest_wait(self):
        timeline = [assigned("ada", at(1)), assigned("grace", at(5))]

        result = track(pull(["ada", "grace"]), timeline, [])
        text, oldest = summarize(result.outstanding, NOW)

        self.assertEqual(text, "ada, grace", "assignees are listed alphabetically")
        self.assertEqual(oldest, 14, "the longest wait is reported, in whole days")

    def test_clears_when_nobody_is_outstanding(self):
        self.assertEqual(
            summarize((), NOW), ("", None), "no outstanding response clears both fields"
        )


# ---------------------------------------------------------------------------
# Test Utilities
# ---------------------------------------------------------------------------


def at(day, hour=10):
    """An ISO-8601 timestamp on the given day of June 2026."""
    return f"2026-06-{day:02d}T{hour:02d}:00:00Z"


def assigned(login, when):
    """An `assigned` timeline event."""
    return {"event": "assigned", "assignee": {"login": login}, "created_at": when}


def moment(day, hour=10):
    """The datetime matching [at]."""
    return datetime(2026, 6, day, hour, 0, tzinfo=timezone.utc)


def pull(assignees, state="open", draft=False):
    """A pull request payload with the given assignees."""
    people = [
        person if isinstance(person, dict) else {"login": person, "type": "User"}
        for person in assignees
    ]
    return {"number": 1, "state": state, "draft": draft, "assignees": people}


def ready(when):
    """A `ready_for_review` timeline event."""
    return {"event": "ready_for_review", "created_at": when}


def review(login, state, when):
    """A submitted review."""
    return {"state": state, "user": {"login": login}, "submitted_at": when}


def unassigned(login, when):
    """An `unassigned` timeline event."""
    return {"event": "unassigned", "assignee": {"login": login}, "created_at": when}


if __name__ == "__main__":
    unittest.main()
