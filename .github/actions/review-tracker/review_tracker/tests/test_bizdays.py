"""Calendar-day and business-day arithmetic."""

import unittest
from datetime import date, datetime, timedelta, timezone

from ..bizdays import (
    _weekdays_through,
    add_business_days,
    business_days_elapsed,
    calendar_days_elapsed,
    parse_timestamp,
)

# 2026-06-01 is a Monday, 2026-06-05 a Friday, 2026-06-06 a Saturday.
MONDAY = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
FRIDAY = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
SATURDAY = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)


class CalendarDays(unittest.TestCase):
    def test_rounds_a_partial_day_down(self):
        later = MONDAY + timedelta(hours=47, minutes=59)

        self.assertEqual(
            calendar_days_elapsed(MONDAY, later), 1, "47h59m is one whole day"
        )

    def test_counts_an_exact_day(self):
        self.assertEqual(
            calendar_days_elapsed(MONDAY, MONDAY + timedelta(days=2)),
            2,
            "exactly 48h is two whole days",
        )

    def test_counts_weekends(self):
        self.assertEqual(
            calendar_days_elapsed(FRIDAY, FRIDAY + timedelta(days=3)),
            3,
            "calendar days include the weekend",
        )

    def test_clamps_a_future_start_to_zero(self):
        self.assertEqual(
            calendar_days_elapsed(MONDAY, MONDAY - timedelta(days=5)),
            0,
            "a start after now reports no elapsed days",
        )


class BusinessDays(unittest.TestCase):
    def test_skips_the_weekend_from_friday(self):
        self.assertEqual(
            add_business_days(FRIDAY, 3),
            datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
            "three business days after Friday is the following Wednesday",
        )

    def test_walks_a_weekend_start_forward(self):
        self.assertEqual(
            add_business_days(SATURDAY, 1),
            datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc),
            "one business day after Saturday is Monday",
        )

    def test_preserves_the_time_of_day(self):
        self.assertEqual(
            add_business_days(MONDAY, 2).time(),
            MONDAY.time(),
            "advancing business days must not shift the time of day",
        )

    def test_elapsed_ignores_the_weekend(self):
        self.assertEqual(
            business_days_elapsed(FRIDAY, FRIDAY + timedelta(days=3)),
            1,
            "Friday to Monday is one business day",
        )

    def test_elapsed_needs_the_full_day(self):
        almost = datetime(2026, 6, 3, 9, 59, tzinfo=timezone.utc)

        self.assertEqual(
            business_days_elapsed(MONDAY, almost),
            1,
            "a step is only complete once the time of day is reached",
        )

    def test_elapsed_counts_a_whole_week(self):
        self.assertEqual(
            business_days_elapsed(MONDAY, MONDAY + timedelta(days=7)),
            5,
            "seven calendar days later is five business days",
        )

    def test_elapsed_clamps_a_future_start(self):
        self.assertEqual(
            business_days_elapsed(MONDAY, MONDAY - timedelta(days=1)),
            0,
            "a start after now reports no elapsed business days",
        )

    def test_weekday_count_matches_a_direct_count(self):
        start = date(2028, 1, 1)
        base = _weekdays_through(start - timedelta(days=1))
        expected = 0

        for offset in range(400):
            day = start + timedelta(days=offset)
            if day.weekday() < 5:
                expected += 1

            self.assertEqual(
                _weekdays_through(day) - base,
                expected,
                f"the ordinal arithmetic must match a direct count through {day}",
            )

    def test_elapsed_inverts_add_business_days(self):
        for start_offset in range(0, 7 * 24, 7):
            start = MONDAY + timedelta(hours=start_offset)
            for days in range(0, 9):
                moment = add_business_days(start, days)

                self.assertEqual(
                    business_days_elapsed(start, moment),
                    days,
                    f"elapsed must invert add for {days}d from {start}",
                )
                self.assertEqual(
                    business_days_elapsed(start, moment - timedelta(seconds=1)),
                    max(days - 1, 0),
                    f"one second early is one step fewer for {days}d from {start}",
                )


class Timestamps(unittest.TestCase):
    def test_parses_the_github_z_form(self):
        self.assertEqual(
            parse_timestamp("2026-06-01T10:00:00Z"),
            MONDAY,
            "GitHub timestamps use a trailing Z",
        )

    def test_normalizes_an_offset_to_utc(self):
        self.assertEqual(
            parse_timestamp("2026-06-01T12:00:00+02:00"),
            MONDAY,
            "an offset timestamp must be converted to UTC",
        )

    def test_rejects_a_missing_timestamp(self):
        for value in (None, "", "not-a-date", 17):
            self.assertIsNone(
                parse_timestamp(value),
                f"{value!r} must not be guessed at",
            )


if __name__ == "__main__":
    unittest.main()
