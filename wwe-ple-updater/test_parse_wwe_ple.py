"""Offline unit tests for WWE PLE identity and source-text parsing."""

import importlib.util
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("parse_wwe_ple.py")
SPEC = importlib.util.spec_from_file_location("wwe_ple_parser", MODULE_PATH)
parser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parser)


class WWEEventIdentityTests(unittest.TestCase):
    def test_known_source_slug_maps_to_existing_calendar_key(self):
        self.assertEqual(parser.canonical_slug("money-in-the-bank-tickets"), "mitb")
        self.assertEqual(parser.canonical_slug("wrestlepalooza-perth"), "wrestlepalooza")

    def test_existing_uid_survives_a_calendar_year_change(self):
        existing = {"uid": "wwe-royalrumble-2027@wwe-ple-tracker"}
        self.assertEqual(
            parser.event_uid("royalrumble", 2028, existing),
            "wwe-royalrumble-2027@wwe-ple-tracker",
        )

    def test_existing_uid_is_found_by_source_alias(self):
        self.assertEqual(
            parser.key_from_uid("wwe-mitb-2026@wwe-ple-tracker"),
            parser.canonical_slug("money-in-the-bank"),
        )

    def test_weekly_show_packages_are_excluded_but_ple_subseries_remain_eligible(self):
        self.assertTrue(parser.is_non_ple_package("wwe-monday-night-raw-2026"))
        self.assertTrue(parser.is_non_ple_package("road-to-survivor-series"))
        self.assertFalse(parser.is_non_ple_package("nxt-deadline"))


class WWEEventParsingTests(unittest.TestCase):
    def test_current_listing_title_is_used_for_renamed_event(self):
        title = parser.title_for_event(
            "survivor-series",
            "survivor-series",
            "Survivor Series Ticket Packages | On Location",
            "Survivor Series: WarGames November 28, 2026 | Houston, TX",
        )
        self.assertEqual(title, "WWE Survivor Series: WarGames")

    def test_parses_event_date_city_and_clean_venue(self):
        text = (
            "Money in the Bank Ticket Packages October 10, 2026 | "
            "New Orleans, LA | Smoothie King Center Ever Wanted To Experience WWE"
        )
        details = parser.choose_full_event_details(text, "mitb")
        self.assertIsNotNone(details)
        self.assertEqual(details["date"].isoformat(), "2026-10-10")
        self.assertEqual(details["city"], "New Orleans, LA")
        self.assertEqual(details["venue"], "Smoothie King Center")

    def test_does_not_attach_an_unrelated_full_date_to_month_only_event(self):
        text = (
            "Royal Rumble February 2027 | Phoenix, AZ "
            "Super Bowl LXI February 14, 2027 | Los Angeles, CA | SoFi Stadium"
        )
        self.assertIsNone(parser.choose_full_event_details(text, "royalrumble"))

    def test_local_venue_time_is_not_treated_as_broadcast_time(self):
        text = "Money in the Bank 2026 Saturday, October 10 | 4:30 PM Smoothie King Center"
        self.assertIsNone(parser.extract_broadcast_time(text, "mitb", 2026))

    def test_explicit_et_broadcast_time_is_parsed(self):
        text = "Money in the Bank 2026 broadcasts live at 8:30 PM ET on ESPN."
        self.assertEqual(parser.extract_broadcast_time(text, "mitb", 2026), (20, 30))

    def test_old_edition_broadcast_time_is_not_reused(self):
        text = "Money in the Bank 2025 broadcasts live at 8:30 PM ET on ESPN."
        self.assertIsNone(parser.extract_broadcast_time(text, "mitb", 2026))

    def test_ics_uses_eastern_timezone(self):
        content = parser.generate_ics_content(
            [{
                "uid": "wwe-mitb-2026@wwe-ple-tracker",
                "summary": "WWE Money in the Bank 2026",
                "start": parser.datetime(2026, 10, 10, 20, 0, tzinfo=parser.ET),
                "end": parser.datetime(2026, 10, 11, 0, 0, tzinfo=parser.ET),
                "location": "Smoothie King Center, New Orleans, LA",
                "description": "Broadcast at 8:00 PM ET",
            }]
        )
        self.assertIn("DTSTART;TZID=America/New_York:20261010T200000", content)
        self.assertIn("UID:wwe-mitb-2026@wwe-ple-tracker", content)


class WWEEventDiscoveryTests(unittest.TestCase):
    def test_undated_new_package_is_skipped_and_existing_future_event_is_retained(self):
        existing_start = parser.datetime(2099, 2, 6, 20, 0, tzinfo=parser.ET)
        existing_event = {
            "uid": "wwe-royalrumble-2099@wwe-ple-tracker",
            "key": "royalrumble",
            "summary": "WWE Royal Rumble 2099",
            "start": existing_start,
            "end": existing_start + parser.timedelta(hours=4),
            "location": "Existing Stadium, Phoenix, AZ",
            "description": "Previously recorded event.",
        }
        listing_soup = parser.BeautifulSoup(
            '<a href="https://onlocationexp.com/wwe/new-ple-tickets">New PLE tickets</a>',
            "html.parser",
        )
        package_soup = parser.BeautifulSoup(
            "New PLE February 2099 | Phoenix, AZ",
            "html.parser",
        )

        def fake_fetch(url):
            if url == parser.ONLOCATION_URL:
                return SimpleNamespace(url=parser.ONLOCATION_URL), listing_soup
            return SimpleNamespace(url=url), package_soup

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "schedule.ics"
            output_path.write_text(
                parser.generate_ics_content([existing_event]),
                encoding="utf-8",
            )
            output = StringIO()
            with patch.object(parser, "fetch", side_effect=fake_fetch), patch.object(
                parser,
                "find_supplemental_links",
                return_value={"new-ple": []},
            ), redirect_stdout(output):
                events = parser.discover_events(output_path)

        self.assertEqual([event["uid"] for event in events], [existing_event["uid"]])
        self.assertEqual(events[0]["start"], existing_start)
        self.assertIn(
            "skipping new packages without retrievable full event dates (new-ple)",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
