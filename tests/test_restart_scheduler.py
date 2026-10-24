import unittest
from datetime import datetime

import pytz

from app.services.restart_scheduler import next_occurrence_search


class TestNextOccurrenceSearch(unittest.TestCase):
    def setUp(self) -> None:
        self.tz = pytz.timezone("Asia/Manila")

    def test_daily_schedule_returns_next_occurrence(self):
        now = self.tz.localize(datetime(2026, 10, 24, 10, 0))

        result = next_occurrence_search(
            now=now,
            hour=11,
            minute=30,
            recurrence="daily",
            selected_days=set(),
            selected_weekdays=set(),
            selected_months=set(),
            selected_years=set(),
            tz=self.tz,
        )

        self.assertEqual(
            result,
            self.tz.localize(datetime(2026, 10, 24, 11, 30)),
        )

    def test_daily_schedule_skips_time_that_has_passed(self):
        now = self.tz.localize(datetime(2026, 10, 24, 12, 0))

        result = next_occurrence_search(
            now=now,
            hour=11,
            minute=30,
            recurrence="daily",
            selected_days=set(),
            selected_weekdays=set(),
            selected_months=set(),
            selected_years=set(),
            tz=self.tz,
        )

        self.assertEqual(
            result,
            self.tz.localize(datetime(2026, 10, 25, 11, 30)),
        )

    def test_weekly_schedule_selects_requested_weekday(self):
        # October 24, 2026 is Saturday; weekday 0 means Monday.
        now = self.tz.localize(datetime(2026, 10, 24, 10, 0))

        result = next_occurrence_search(
            now=now,
            hour=9,
            minute=0,
            recurrence="weekly",
            selected_days=set(),
            selected_weekdays={0},
            selected_months=set(),
            selected_years=set(),
            tz=self.tz,
        )

        self.assertEqual(
            result,
            self.tz.localize(datetime(2026, 10, 26, 9, 0)),
        )

    def test_selected_month_restricts_occurrence(self):
        now = self.tz.localize(datetime(2026, 10, 24, 10, 0))

        result = next_occurrence_search(
            now=now,
            hour=11,
            minute=0,
            recurrence="daily",
            selected_days=set(),
            selected_weekdays=set(),
            selected_months={11},
            selected_years=set(),
            tz=self.tz,
        )

        self.assertEqual(
            result,
            self.tz.localize(datetime(2026, 11, 1, 11, 0)),
        )

    def test_selected_year_restricts_occurrence(self):
        now = self.tz.localize(datetime(2026, 12, 31, 10, 0))

        result = next_occurrence_search(
            now=now,
            hour=11,
            minute=0,
            recurrence="daily",
            selected_days=set(),
            selected_weekdays=set(),
            selected_months=set(),
            selected_years={2027},
            tz=self.tz,
        )

        self.assertEqual(
            result,
            self.tz.localize(datetime(2027, 1, 1, 11, 0)),
        )

    def test_day_beyond_month_length_maps_to_first_of_next_month(self):
        # November has 30 days, so selecting day 31 maps to December 1.
        now = self.tz.localize(datetime(2026, 11, 30, 12, 0))

        result = next_occurrence_search(
            now=now,
            hour=9,
            minute=0,
            recurrence="daily",
            selected_days={31},
            selected_weekdays=set(),
            selected_months=set(),
            selected_years=set(),
            tz=self.tz,
        )

        self.assertEqual(
            result,
            self.tz.localize(datetime(2026, 12, 1, 9, 0)),
        )


if __name__ == "__main__":
    unittest.main()
