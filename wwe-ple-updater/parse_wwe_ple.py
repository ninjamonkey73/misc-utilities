#!/usr/bin/env python3
"""
parse_wwe_ple.py
Dynamically fetches upcoming WWE Premium Live Events (PLEs) from Wikipedia's
rendered List page, parses dates and venues cleanly, and outputs a populated .ics file.
"""

import os
import re
import datetime
from datetime import timezone, timedelta
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_WWE_pay-per-view_and_WWE_Network_events"

def sanitize_uid(title, start_utc):
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    date_part = start_utc.split('T')[0]
    return f"wwe-{clean_title}-{date_part}@wwe-ple-tracker"

def parse_date_to_utc(date_str):
    """Parses date strings like 'October 10, 2026' into ISO 8601 UTC strings."""
    clean_date = re.sub(r'\[.*?\]|\(.*?\)', '', date_str).strip()
    dt = None
    
    # Handle single dates
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(clean_date, fmt)
            break
        except ValueError:
            continue

    # Handle multi-day date ranges e.g. "April 18–19, 2026"
    if not dt:
        m = re.search(r'([A-Z][a-z]+)\s+(\d+)\s*[\u2013\-]\s*\d+,\s*(\d{4})', clean_date)
        if m:
            try:
                dt = datetime.datetime.strptime(f"{m.group(1)} {m.group(2)}, {m.group(3)}", "%B %d, %Y")
            except ValueError:
                pass

    if not dt:
        return None, None

    # Default 8:00 PM ET start time converted to UTC
    dt_utc = dt.replace(hour=20, minute=0, tzinfo=timezone.utc) + timedelta(hours=4)
    start_utc = dt_utc.strftime("%Y%m%dT%H%M%SZ")
    end_utc = (dt_utc + timedelta(hours=4)).strftime("%Y%m%dT%H%M%SZ")
    return start_utc, end_utc

def fetch_upcoming_events():
    """Scrapes the 'Upcoming events' table directly from Wikipedia HTML."""
    events = []
    try:
        res = requests.get(WIKI_URL, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return events

        soup = BeautifulSoup(res.text, "html.parser")
        
        # Locate all tables on the page
        tables = soup.find_all("table", class_="wikitable")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all(["td", "th"])
                if len(cols) >= 3:
                    row_text = " ".join([c.get_text(" ", strip=True) for c in cols])
                    
                    # Match dates in 2026 or 2027
                    date_match = re.search(r'([A-Z][a-z]+\s+\d+(?:[\u2013\-]\d+)?,\s+202[6-7])', row_text)
                    if date_match:
                        raw_date = date_match.group(1)
                        
                        # Title is usually in the first or second column link
                        title = ""
                        for col in cols[:2]:
                            a = col.find("a")
                            if a and a.get_text(strip=True):
                                title = a.get_text(strip=True)
                                break
                            elif col.get_text(strip=True):
                                title = col.get_text(strip=True)
                                break
                        
                        title = re.sub(r'\[.*?\]', '', title).strip()
                        if not title or title.lower() in ["event", "date", "name"]:
                            continue

                        # Extract location/venue column if present
                        location = "TBA"
                        if len(cols) >= 4:
                            location = cols[3].get_text(" ", strip=True)
                        elif len(cols) >= 3:
                            location = cols[2].get_text(" ", strip=True)
                        location = re.sub(r'\[.*?\]', '', location).strip() or "See WWE.com for venue"

                        start_utc, end_utc = parse_date_to_utc(raw_date)
                        if start_utc:
                            clean_title = f"WWE {title}" if not title.lower().startswith("wwe") else title
                            uid = sanitize_uid(title, start_utc)
                            
                            events.append({
                                "uid": uid,
                                "summary": clean_title,
                                "start_utc": start_utc,
                                "end_utc": end_utc,
                                "location": location,
                                "description": f"Official WWE Event: {title}. Broadcast live on Peacock / ESPN networks."
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

    parsed_events = fetch_upcoming_events()

    # Deduplicate by UID
    unique = {e['uid']: e for e in parsed_events}
    all_events = list(unique.values())

    # Filter out past events
    now_utc_str = datetime.datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    future_events = [e for e in all_events if e['end_utc'] >= now_utc_str]

    ics_content = generate_ics_content(future_events)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    print(f"Successfully generated {output_path} with {len(future_events)} events.")

if __name__ == "__main__":
    main()
