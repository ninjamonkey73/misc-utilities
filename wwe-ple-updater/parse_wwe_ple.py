#!/usr/bin/env python3
"""
parse_wwe_ple.py
Dynamically fetches upcoming WWE Premium Live Events (PLEs) from Wikipedia's
MediaWiki Action API, converts dates to UTC, and updates wwe_ple_schedule.ics.
"""

import os
import re
import sys
import datetime
from datetime import timezone, timedelta
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "WWE-PLE-Calendar-Bot/1.0 (https://github.com/ninjamonkey73/misc-utilities)"
}

WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGE_TITLE = "List_of_WWE_pay-per-view_and_livestreaming_supercards"


def sanitize_uid(title, start_utc):
    clean_title = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
    date_part = start_utc.split("T")[0]
    return f"wwe-{clean_title}-{date_part}@wwe-ple-tracker"


def parse_date_to_utc(date_str, year):
    """Parses date strings like 'November 28' or 'December 12' with a year into UTC."""
    clean_date = re.sub(r"\[.*?\]|\(.*?\)", "", date_str).strip()
    # Handle multi-day ranges like "April 18–19" by taking the first day
    clean_date = re.sub(r"(\w+\s+\d+)\s*[\u2013\-]\s*\d+", r"\1", clean_date)

    dt = None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            dt = datetime.datetime.strptime(f"{clean_date}, {year}", fmt)
            break
        except ValueError:
            continue

    if not dt:
        return None, None

    # Default 8:00 PM ET start -> 01:00 UTC next day (standard offset)
    dt_utc = dt.replace(hour=20, minute=0, tzinfo=timezone.utc) + timedelta(hours=5)
    start_utc = dt_utc.strftime("%Y%m%dT%H%M%SZ")
    end_utc = (dt_utc + timedelta(hours=4)).strftime("%Y%m%dT%H%M%SZ")
    return start_utc, end_utc


def fetch_upcoming_events():
    """Queries Wikipedia's Action API for current and next year supercard tables."""
    events = []
    current_year = datetime.datetime.now(timezone.utc).year
    target_years = {str(current_year), str(current_year + 1)}

    params = {
        "action": "parse",
        "page": PAGE_TITLE,
        "prop": "text",
        "format": "json"
    }

    try:
        res = requests.get(WIKI_API, headers=HEADERS, params=params, timeout=15)
        res.raise_for_status()
        html = res.json().get("parse", {}).get("text", {}).get("*", "")
        soup = BeautifulSoup(html, "html.parser")

        for heading in soup.find_all(["h2", "h3"]):
            heading_text = heading.get_text(" ", strip=True)
            year_match = next((y for y in target_years if y in heading_text), None)
            if not year_match:
                continue

            table = heading.find_next("table", class_="wikitable")
            if not table:
                continue

            for row in table.find_all("tr")[1:]:
                cols = row.find_all(["td", "th"])
                if len(cols) < 3:
                    continue

                raw_date = cols[0].get_text(" ", strip=True)
                raw_event = cols[1].get_text(" ", strip=True)
                venue = re.sub(r"\[.*?\]", "", cols[2].get_text(" ", strip=True)).strip()
                city = re.sub(r"\[.*?\]", "", cols[3].get_text(" ", strip=True)).strip() if len(cols) > 3 else ""

                title = re.sub(r"\[.*?\]", "", raw_event).strip()
                if not title or title.lower() in {"event", "tba", "tbd"}:
                    continue

                start_utc, end_utc = parse_date_to_utc(raw_date, year_match)
                if not start_utc:
                    continue

                location = ", ".join(part for part in [venue, city] if part) or "TBA"
                summary = f"WWE {title}" if not title.lower().startswith(("wwe", "nxt", "aaa")) else title

                events.append({
                    "uid": sanitize_uid(title, start_utc),
                    "summary": summary,
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                    "location": location,
                    "description": f"Official WWE Event: {title}."
                })

    except Exception as err:
        print(f"Scraper error: {err}")

    return events


def generate_ics_content(events):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WWE PLE Dynamic Schedule Tracker//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]
    for event in events:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{event['uid']}",
            f"SUMMARY:{event['summary']}",
            f"DTSTART:{event['start_utc']}",
            f"DTEND:{event['end_utc']}",
            f"LOCATION:{event['location']}",
            f"DESCRIPTION:{event['description']}",
            "END:VEVENT"
        ])
    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"


def main():
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "wwe_ple_schedule.ics")

    parsed_events = fetch_upcoming_events()
    unique_events = list({e["uid"]: e for e in parsed_events}.values())

    now_utc_str = datetime.datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    future_events = [e for e in unique_events if e["end_utc"] >= now_utc_str]

    if not future_events:
        print("No future events parsed; preserving existing .ics file.")
        sys.exit(0)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(generate_ics_content(future_events))

    print(f"Updated {output_path} with {len(future_events)} upcoming events.")


if __name__ == "__main__":
    main()