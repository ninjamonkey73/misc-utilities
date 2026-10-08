#!/usr/bin/env python3
"""
parse_wwe_ple.py
Dynamically fetches upcoming WWE Premium Live Events (PLEs) from public web endpoints,
converts timestamps to standard UTC strings (YYYYMMDDTHHMMSSZ),
and generates a populated .ics file with persistent UIDs.
"""

import os
import re
import json
import datetime
from datetime import timezone, timedelta
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
    """Generates a stable, persistent UID derived from the title slug and UTC start date."""
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    date_part = start_utc.split('T')[0]
    return f"wwe-{clean_title}-{date_part}@wwe-ple-tracker"

def parse_date_to_utc(date_str, time_str="20:00"):
    """
    Parses common event date strings into ISO 8601 UTC strings (YYYYMMDDTHHMMSSZ).
    Assumes standard ET broadcast times for WWE PLEs unless specified.
    """
    dt = None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.datetime.strptime(date_str.split('.')[0], fmt)
            break
        except ValueError:
            continue

    if not dt:
        dt = datetime.datetime.now(timezone.utc)

    if dt.tzinfo is None:
        hour, minute = map(int, time_str.split(":"))
        dt = dt.replace(hour=hour, minute=minute, tzinfo=timezone.utc) + timedelta(hours=4)

    start_utc = dt.strftime("%Y%m%dT%H%M%SZ")
    end_utc = (dt + timedelta(hours=4)).strftime("%Y%m%dT%H%M%SZ")
    return start_utc, end_utc

def fetch_wikipedia_ple_events():
    """
    Fetches upcoming WWE PLEs from Wikipedia's structured API.
    Wikipedia maintains an updated table of scheduled WWE events.
    """
    events = []
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "parse",
        "page": "List_of_WWE_pay-per-view_and_WWE_Network_events",
        "prop": "wikitext",
        "format": "json"
    }

    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
            
            # Parse table rows for upcoming events
            rows = re.findall(r'\|-\s*\n(.*?\n)(?=\|-|\=\=)', wikitext, re.DOTALL)
            for row in rows:
                if any(kw in row.lower() for kw in PLE_KEYWORDS):
                    # Extract Event Title
                    title_match = re.search(r'\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]', row)
                    title = title_match.group(1) if title_match else None
                    
                    # Extract Date
                    date_match = re.search(r'([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})', row)
                    
                    # Extract Location / Venue
                    loc_match = re.search(r'\||\s*([A-Za-z0-9\s,\.\-]+(?:Arena|Center|Stadium|Dome|Park|Hall)[^\|\n]*)', row)
                    location = loc_match.group(1).strip() if loc_match else "See WWE.com for venue"

                    if title and date_match:
                        raw_date = date_match.group(1)
                        start_utc, end_utc = parse_date_to_utc(raw_date)
                        uid = sanitize_uid(title, start_utc)

                        events.append({
                            "uid": uid,
                            "summary": f"WWE {title}",
                            "start_utc": start_utc,
                            "end_utc": end_utc,
                            "location": location,
                            "description": f"Official WWE Event: {title}. Broadcast live on ESPN networks / Peacock."
                        })
    except Exception as err:
        print(f"Error fetching from Wikipedia API: {err}")

    return events

def generate_ics_content(events):
    """Formats event dictionaries into valid ICS file format."""
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
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "wwe_ple_schedule.ics")

    print("Fetching live WWE schedule dynamically via API...")
    parsed_events = fetch_wikipedia_ple_events()

    # Deduplicate events by UID
    unique_events = {}
    for e in parsed_events:
        unique_events[e["uid"]] = e
    final_events = list(unique_events.values())

    # Filter out past events automatically based on current UTC time
    now_utc_str = datetime.datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    future_events = [e for e in final_events if e['end_utc'] >= now_utc_str]

    display_events = future_events if future_events else final_events

    ics_content = generate_ics_content(display_events)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    print(f"Successfully generated {output_path} with {len(display_events)} events.")

if __name__ == "__main__":
    main()
