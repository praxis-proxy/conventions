"""Reminder scheduling, marker durability, and forgery resistance."""

import unittest
from datetime import datetime, timezone

from ..reminders import due_reminders, marker, parse_records, render
from ..tracking import Outstanding

BOT = "praxis-bot[bot]"

# 2026-06-01 is a Monday, so three business days later is Thursday the 4th.
ASSIGNED = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
THIRD_DAY = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)


class FirstReminder(unittest.TestCase):
    def test_is_not_due_before_three_business_days(self):
        almost = datetime(2026, 6, 4, 9, 59, tzinfo=timezone.utc)

        due, _ = due_reminders([owed("ada")], [], almost)

        self.assertEqual(due, [], "the third business day must complete first")

    def test_is_due_on_the_third_business_day(self):
        due, _ = due_reminders([owed("ada")], [], THIRD_DAY)

        self.assertEqual([item.stage for item in due], [1], "the first reminder is due")
        self.assertEqual(
            due[0].business_days, 3, "the message reports three business days"
        )

    def test_ignores_an_intervening_weekend(self):
        assigned = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)
        monday = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)

        due, _ = due_reminders([owed("ada", assigned)], [], monday)

        self.assertEqual(
            due, [], "Thursday to Monday is two business days, not four"
        )

    def test_reminds_each_assignee_on_their_own_schedule(self):
        later = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
        people = [owed("ada"), owed("grace", later)]

        due, _ = due_reminders(people, [], THIRD_DAY)

        self.assertEqual(
            [item.login for item in due],
            ["ada"],
            "only the assignee who has waited long enough is reminded",
        )


class FollowUp(unittest.TestCase):
    def test_is_measured_from_when_the_first_was_posted(self):
        posted = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)
        records, _ = parse_records([comment(marker("ada", ASSIGNED, 1), posted)], BOT)
        before = datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc)

        due, _ = due_reminders([owed("ada")], records, before)

        self.assertEqual(
            due,
            [],
            "a late first reminder must not make the follow-up instantly due",
        )

    def test_is_due_three_business_days_after_the_first(self):
        posted = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)
        records, _ = parse_records([comment(marker("ada", ASSIGNED, 1), posted)], BOT)
        after = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)

        due, _ = due_reminders([owed("ada")], records, after)

        self.assertEqual([item.stage for item in due], [2], "the follow-up is due")

    def test_stops_after_the_follow_up(self):
        body = "\n".join([marker("ada", ASSIGNED, 1), marker("ada", ASSIGNED, 2)])
        records, _ = parse_records([comment(body, THIRD_DAY)], BOT)
        much_later = datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc)

        due, _ = due_reminders([owed("ada")], records, much_later)

        self.assertEqual(due, [], "nobody is reminded a third time")


class RepeatRuns(unittest.TestCase):
    def test_a_rerun_does_not_remind_twice(self):
        records, _ = parse_records([comment(marker("ada", ASSIGNED, 1), THIRD_DAY)], BOT)

        due, _ = due_reminders([owed("ada")], records, THIRD_DAY)

        self.assertEqual(due, [], "the bot's own marker suppresses a repeat")

    def test_a_new_assignment_starts_a_fresh_sequence(self):
        records, _ = parse_records([comment(marker("ada", ASSIGNED, 2), THIRD_DAY)], BOT)
        reassigned = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        later = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)

        due, _ = due_reminders([owed("ada", reassigned)], records, later)

        self.assertEqual(
            [item.stage for item in due],
            [1],
            "reassignment is a new assignment, so reminders restart",
        )


class Forgery(unittest.TestCase):
    def test_ignores_a_marker_from_a_person(self):
        human = comment(marker("ada", ASSIGNED, 1), THIRD_DAY)
        human["user"] = {"login": "ada", "type": "User"}

        records, _ = parse_records([human], BOT)

        self.assertEqual(records, [], "a person cannot forge reminder state")

    def test_ignores_a_marker_from_another_bot(self):
        other = comment(marker("ada", ASSIGNED, 1), THIRD_DAY)
        other["user"] = {"login": "other-bot[bot]", "type": "Bot"}

        records, _ = parse_records([other], BOT)

        self.assertEqual(records, [], "only this app's own comments are believed")

    def test_a_forged_marker_does_not_suppress_a_reminder(self):
        human = comment(marker("ada", ASSIGNED, 2), THIRD_DAY)
        human["user"] = {"login": "ada", "type": "User"}

        records, _ = parse_records([human], BOT)
        due, _ = due_reminders([owed("ada")], records, THIRD_DAY)

        self.assertEqual(
            [item.stage for item in due],
            [1],
            "a forged stop marker must not silence the real reminder",
        )

    def test_reports_a_malformed_marker(self):
        body = "<!-- praxis-review-reminder not-json -->"

        records, notes = parse_records([comment(body, THIRD_DAY)], BOT)

        self.assertEqual(records, [], "a marker that will not decode is not state")
        self.assertTrue(notes, "a malformed marker must be reported")

    def test_reports_a_comment_with_no_created_at(self):
        broken = comment(marker("ada", ASSIGNED, 1), THIRD_DAY)
        broken["created_at"] = None

        records, notes = parse_records([broken], BOT)

        self.assertEqual(records, [], "an undatable reminder is not usable state")
        self.assertTrue(notes, "the gap must be reported")

    def test_reports_an_implausible_login(self):
        item = Outstanding("not a login", ASSIGNED, ASSIGNED)

        due, notes = due_reminders([item], [], THIRD_DAY)

        self.assertEqual(due, [], "an unexpected login is never mentioned")
        self.assertTrue(notes, "the anomaly must be reported")


class Rendering(unittest.TestCase):
    def test_round_trips_a_marker(self):
        records, notes = parse_records(
            [comment(marker("ada", ASSIGNED, 1), THIRD_DAY)], BOT
        )

        self.assertEqual(notes, [], "a marker the bot wrote must decode cleanly")
        self.assertEqual(records[0].login, "ada", "the login survives the round trip")
        self.assertEqual(
            records[0].assigned_at, ASSIGNED, "the assignment key survives"
        )
        self.assertEqual(records[0].stage, 1, "the stage survives")
        self.assertEqual(
            records[0].posted_at, THIRD_DAY, "the posting time comes from the comment"
        )

    def test_mentions_only_the_people_who_are_due(self):
        due, _ = due_reminders([owed("ada"), owed("grace")], [], THIRD_DAY)
        body = render(due)

        self.assertIn(
            "@ada — a reminder that this PR is awaiting your initial review. "
            "You were assigned 3 business days ago.",
            body,
            "the reminder must read as specified",
        )
        self.assertIn("@grace", body, "both due assignees are mentioned")

    def test_records_a_marker_for_everyone_mentioned(self):
        due, _ = due_reminders([owed("ada"), owed("grace")], [], THIRD_DAY)

        body = render(due)
        records, _ = parse_records([comment(body, THIRD_DAY)], BOT)

        self.assertEqual(
            sorted(record.login for record in records),
            ["ada", "grace"],
            "a posted reminder records state for each person it mentions",
        )


# ---------------------------------------------------------------------------
# Test Utilities
# ---------------------------------------------------------------------------


def comment(body, posted_at):
    """An issue comment authored by the bot."""
    return {
        "body": body,
        "created_at": posted_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user": {"login": BOT, "type": "Bot"},
    }


def owed(login, assigned_at=ASSIGNED):
    """Somebody who still owes an initial review."""
    return Outstanding(login, assigned_at, assigned_at)


if __name__ == "__main__":
    unittest.main()
