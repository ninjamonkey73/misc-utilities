"""Offline tests for YMCA schedule table parsing."""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from parse_schedule import (
    generate_ics_from_pdf,
    parse_lap_lane_closure_notes,
    parse_schedule_tables,
    parse_time_to_utc,
)


class ScheduleTableParsingTests(unittest.TestCase):
    def test_finds_weekdays_after_title_row_and_parses_pdf_replacement_dash(self):
        table = [
            ["", "MACCOLL YMCA", None, None],
            ["SUNDAY", None, "MONDAY", "TUESDAY"],
            ["", "LAP SWIM", None, None],
            ["7 AM \ufffd 8 AM\n6 lanes", None, "5:30 AM \u2013 10:30 AM\n6 lanes", None],
            ["", "OPEN SWIM (ACTIVITY POOL)", None, None],
            [None, None, None, "4 PM \ufffd 7 PM\nWater Slide"],
        ]

        events = parse_schedule_tables([table])

        self.assertEqual(
            events,
            [
                ("Lap Swim (6 lanes)", "SU", "7 AM", "8 AM"),
                ("Lap Swim (6 lanes)", "MO", "5:30 AM", "10:30 AM"),
                ("Open Swim w/ Water Slide", "TU", "4 PM", "7 PM"),
            ],
        )

    def test_ignores_tables_without_a_weekday_header(self):
        self.assertEqual(
            parse_schedule_tables([["MACCOLL YMCA", "LAP SWIM", "7 AM - 8 AM"]]),
            [],
        )

    def test_converts_hour_only_time_from_pdf(self):
        self.assertEqual(
            parse_time_to_utc(date(2026, 10, 4), "7 AM"),
            "20261004T110000Z",
        )

    def test_converts_hour_only_time_without_space_before_meridiem(self):
        self.assertEqual(
            parse_time_to_utc(date(2026, 10, 4), "4PM"),
            "20261004T200000Z",
        )

    def test_parses_dated_lap_lane_closure_note(self):
        notes = parse_lap_lane_closure_notes(
            "OCTOBER 2026\n*Swim Meet October 4th \ufffd Lap Lanes closing at 3:45pm*",
            date(2026, 10, 1),
            date(2026, 10, 31),
        )

        self.assertEqual(
            notes,
            [{
                "date": date(2026, 10, 4),
                "closing_time": "3:45pm",
                "description": "Swim Meet October 4th - Lap Lanes closing at 3:45pm",
            }],
        )

    def test_closure_excludes_regular_occurrence_and_adds_shortened_one_off_event(self):
        schedule_table = [
            ["SUNDAY", "MONDAY"],
            ["LAP SWIM", None],
            ["12 PM \ufffd 4:30 PM\n4 lanes", None],
        ]
        page = SimpleNamespace(
            extract_text=lambda: (
                "Indoor Pool Schedule OCTOBER 2026\n"
                "*Swim Meet October 4th \ufffd Lap Lanes closing at 3:45pm*"
            ),
            extract_tables=lambda: [schedule_table],
        )

        class FakePDF:
            pages = [page]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "schedule.ics"
            with patch("parse_schedule.pdfplumber.open", return_value=FakePDF()), patch(
                "parse_schedule.get_branch_hours", return_value={}
            ):
                generate_ics_from_pdf("unused.pdf", str(output_path))

            events = [
                event
                for event in output_path.read_text(encoding="utf-8").split("BEGIN:VEVENT")
                if "SUMMARY:Lap Swim" in event
            ]

        recurring = next(event for event in events if "RRULE:" in event)
        exception = next(event for event in events if "RRULE:" not in event)
        self.assertIn("EXDATE:20261004T160000Z", recurring)
        self.assertIn("DTSTART:20261004T160000Z", exception)
        self.assertIn("DTEND:20261004T194500Z", exception)
        self.assertIn("DESCRIPTION:Swim Meet October 4th - Lap Lanes closing at 3:45pm", exception)


if __name__ == "__main__":
    unittest.main()