#!/usr/bin/env python3
"""
parse_wwe_ple.py
Dynamically scrapes upcoming WWE Premium Live Events (PLEs) from web sources,
parses event details, converts timestamps to standard UTC strings (YYYYMMDDTHHMMSSZ),
and outputs a clean .ics file with stable UIDs.
"""

import os
import re
import datetime
from datetime import timezone, timedelta
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Key phrases identifying PLEs / major supercards
PLE_KEYWORDS = [
    "royal rumble", "elimination chamber", "wrestlemania", "backlash",
    "night of champions", "money in the bank", "summerslam", "bash in berlin",
    "bad blood", "crown jewel", "survivor series", "wargames", "wrestlepalooza",
    "worlds collide", "saturday night's main event", "stand & deliver",
    "halloween havoc", "deadline", "vengeance day", "great american bash"
]

def sanitize_uid(title, start_utc):
    """Generates a persistent UID derived from the title slug and UTC start date."""
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    date_part = start_utc.split('T')[0]
    return f"wwe-{clean_title}-{date_part}@wwe-ple-tracker"

def parse_date_to_utc(date_str, time_str="20:00"):
    """
    Parses common event date/time strings into ISO 8601 UTC strings (YYYYMMDDTHHMMSSZ).
    Assumes standard ET (UTC-5/UTC-4) broadcast times for WWE PLEs unless specified.
    """
    # Quick regex extract for standard date shapes (e.g. Oct 10, 2026 or 2026-10-10)
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        try:
            dt = datetime.datetime.strptime(date_str, "%b %d, %Y")
        except ValueError:
            # Fallback to current UTC if unparseable
            dt = datetime.datetime.now(timezone.utc)

    # Standard default PLE time is 8:00 PM ET (20:00) -> approx 00:00 UTC next day (UTC+4/5)
    hour, minute = map(int, time_str.split(":"))
    dt_local = dt.replace(hour=hour, minute=minute, tzinfo=timezone.utc)
    
    # Standard format for .ics UTC
    start_utc = dt_local.strftime("%Y%m%dT%H%M%SZ")
    end_utc = (dt_local + timedelta(hours=4)).strftime("%Y%m%dT%H%M%SZ")
    
    return start_utc, end_utc

def fetch_live_wwe_events():
    """
    Scrapes upcoming event listings from WWE event pages and major aggregator sources.
    Filters exclusively for Premium Live Events and major supercards.
    """
    events = []
    
    # Primary Source: Scrape WWE's public event portal / ticketing feeds
    urls = [
        "https://www.wwe.com/shows",
        "https://onlocationexp.com/wwe"
    ]

    for url in urls:
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, "html.parser")
            
            # Search anchor tags, headings, and event card elements
            for element in soup.find_all(['div', 'article', 'a'], class_=re.compile(r'event|card|show', re.I)):
                text = element.get_text(" ", strip=True)
                text_lower = text.lower()

                # Filter out regular weekly RAW/SmackDown/NXT house shows
                if any(kw in text_lower for kw in PLE_KEYWORDS) and not any(skip in text_lower for skip in ["raw", "smackdown", "live tour", "ticket"]):
                    
                    # Extract title
                    title_match = re.search(r'(Royal Rumble|Elimination Chamber|WrestleMania|Backlash|Money in the Bank|SummerSlam|Crown Jewel|Survivor Series|Wrestlepalooza|Worlds Collide|Sunday Night\'s Main Event)', text, re.I)
                    title = title_match.group(0) if title_match else "WWE Premium Live Event"

                    # Extract location if visible
                    loc_match = re.search(r'([A-Za-z\s]+,\s*[A-Z]{2}|[A-Za-z\s]+,\s*[A-Za-z\s]+)', text)
                    location = loc_match.group(0) if loc_match else "See WWE.com for venue"

                    # Extract year/date
                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}', text)
                    if date_match:
                        raw_date = date_match.group(0)
                        start_utc, end_utc = parse_date_to_utc(raw_date)
                        uid = sanitize_uid(title, start_utc)

                        # Avoid duplicates in output array
                        if not any(e['uid'] == uid for e in events):
                            events.append({
                                "uid": uid,
                                "summary": f"WWE {title}",
                                "start_utc": start_utc,
                                "end_utc": end_utc,
                                "location": location,
                                "description": f"Official WWE Premium Live Event: {title}. Broadcast live on ESPN networks / Peacock / Netflix."
                            })
        except Exception as err:
            print(f"Warning: Failed to parse feed from {url}: {err}")

    return events

def generate_ics_content(events):
    """Formats event dictionaries into valid ICS file format with standard UTC dates."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WWE PLE Dynamic Schedule Updater//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]

    for event in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{event['uid']}")
        lines.append(f"SUMMARY:{event['summary']}")
        lines.append(f"DTSTART:{event['start_utc']}")
        lines.append(f"DTEND:{event['end_utc']}")
        lines.append(f"LOCATION:{event['location']}")
        lines.append(f"DESCRIPTION:{event['description']}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"

def main():
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "wwe_ple_schedule.ics")

    print("Fetching live WWE schedule dynamically...")
    parsed_events = fetch_live_wwe_events()

    # Filter out past events automatically based on current UTC time
    now_utc_str = datetime.datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    future_events = [e for e in parsed_events if e['end_utc'] >= now_utc_str]

    if not future_events:
        print("No future events found during scraping. Preserving current file.")
        return

    ics_content = generate_ics_content(future_events)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    print(f"Successfully scraped and generated {output_path} with {len(future_events)} dynamic events.")

if __name__ == "__main__":
    main()
