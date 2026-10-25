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


class TestPrepareRecurrenceSettings(unittest.TestCase):
    def test_daily_mode_uses_daily_days(self):
        from app.services.restart_scheduler import prepare_recurrence_settings

        result = prepare_recurrence_settings(
            "daily", {1, 15}, {0, 2}, {3, 4}, {2027}
        )

        self.assertEqual(
            result,
            ("daily", {1, 15}, set(), {3, 4}, {2027}),
        )

    def test_weekly_mode_uses_weekly_days(self):
        from app.services.restart_scheduler import prepare_recurrence_settings

        result = prepare_recurrence_settings(
            "weekly", {1, 15}, {0, 2}, {3, 4}, {2027}
        )

        self.assertEqual(
            result,
            ("weekly", set(), {0, 2}, {3, 4}, {2027}),
        )

    def test_unrecognized_mode_uses_daily_fallback(self):
        from app.services.restart_scheduler import prepare_recurrence_settings

        result = prepare_recurrence_settings(
            None, {1, 15}, {0, 2}, [], []
        )

        self.assertEqual(
            result,
            ("daily", set(), set(), set(), set()),
        )


class TestFindNextEvent(unittest.TestCase):
    def test_returns_earliest_event(self):
        from app.services.restart_scheduler import find_next_event

        tz = pytz.timezone("Asia/Manila")
        later = tz.localize(datetime(2026, 10, 25, 12, 0))
        earlier = tz.localize(datetime(2026, 10, 25, 9, 0))
        entries = [
            (later, "block_later", "12:00"),
            (earlier, "block_earlier", "09:00"),
        ]

        self.assertEqual(
            find_next_event(entries),
            (earlier, "block_earlier", "09:00"),
        )

    def test_returns_empty_result_when_no_entries(self):
        from app.services.restart_scheduler import find_next_event

        self.assertEqual(find_next_event([]), (None, None, None))


if __name__ == "__main__":
    unittest.main()
