#!/usr/bin/env python3
"""
parse_wwe_ple.py
Dynamically fetches and parses upcoming WWE Premium Live Events (PLEs)
from Wikipedia's HTML API, converts dates to standard UTC, and outputs
a populated .ics calendar file. Zero hardcoded events.
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

# Source URL: Wikipedia Action API rendering parsed HTML for WWE PPV/PLE list
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
WIKI_PARAMS = {
    "action": "parse",
    "page": "List_of_WWE_pay-per-view_and_WWE_Network_events",
    "prop": "text",
    "section": "0",  # Lead section / overview or full parse
    "format": "json"
}

def sanitize_uid(title, start_utc):
    """Generates a stable, persistent UID derived from the title slug and UTC start date."""
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    date_part = start_utc.split('T')[0]
    return f"wwe-{clean_title}-{date_part}@wwe-ple-tracker"

def parse_date_to_utc(date_str, time_str="20:00"):
    """
    Parses common event date strings (e.g., 'October 10, 2026') into ISO 8601 UTC strings.
    Assumes standard 8:00 PM ET start time for WWE PLEs unless specified.
    """
    dt = None
    # Clean up wiki citation references like [12] or trailing characters
    clean_date_str = re.sub(r'\[.*?\]', '', date_str).strip()
    
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(clean_date_str, fmt)
            break
        except ValueError:
            continue

    if not dt:
        return None, None

    # Apply 8:00 PM ET default start time -> convert to UTC (+4 hours EDT / +5 hours EST)
    hour, minute = map(int, time_str.split(":"))
    dt_local = dt.replace(hour=hour, minute=minute, tzinfo=timezone.utc) + timedelta(hours=4)

    start_utc = dt_local.strftime("%Y%m%dT%H%M%SZ")
    end_utc = (dt_local + timedelta(hours=4)).strftime("%Y%m%dT%H%M%SZ")
    return start_utc, end_utc

def fetch_dynamic_wwe_events():
    """Scrapes upcoming event rows from Wikipedia's HTML table parser."""
    events = []
    
    try:
        # Fetch entire parsed HTML text from Wikipedia API
        res = requests.get(WIKI_API_URL, headers=HEADERS, params={"action": "parse", "page": "List_of_WWE_pay-per-view_and_WWE_Network_events", "prop": "text", "format": "json"}, timeout=15)
        if res.status_code != 200:
            print(f"Error fetching Wikipedia page: HTTP {res.status_code}")
            return events

        data = res.json()
        html_content = data.get("parse", {}).get("text", {}).get("*", "")
        soup = BeautifulSoup(html_content, "html.parser")

        # Locate all wikitables on the page
        tables = soup.find_all("table", class_="wikitable")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all(["td", "th"])
                if len(cols) >= 3:
                    row_text = row.get_text(" ", strip=True)
                    
                    # Look for date patterns e.g. "October 10, 2026" or "November 28, 2026"
                    date_match = re.search(r'([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})', row_text)
                    if date_match:
                        raw_date = date_match.group(1)
                        
                        # Extract event title from anchor tag or first text cell
                        title_cell = cols[0].get_text(strip=True) if len(cols) > 0 else ""
                        title_anchor = cols[0].find("a") if len(cols) > 0 else None
                        title = title_anchor.get_text(strip=True) if title_anchor else title_cell
                        
                        # Clean up title formatting
                        title = re.sub(r'\[.*?\]', '', title).strip()
                        if not title or title.lower() in ["event", "date", "name"]:
                            continue

                        # Extract location/venue if present in subsequent columns
                        location = "TBA"
                        if len(cols) >= 3:
                            loc_text = cols[2].get_text(strip=True)
                            location = re.sub(r'\[.*?\]', '', loc_text).strip() or "See WWE.com for venue"

                        start_utc, end_utc = parse_date_to_utc(raw_date)
                        if start_utc and end_utc:
                            uid = sanitize_uid(title, start_utc)
                            
                            # Avoid duplicates
                            if not any(e["uid"] == uid for e in events):
                                events.append({
                                    "uid": uid,
                                    "summary": f"WWE {title}" if not title.lower().startswith("wwe") else title,
                                    "start_utc": start_utc,
                                    "end_utc": end_utc,
                                    "location": location,
                                    "description": f"Official WWE Event: {title}. Broadcast live on Peacock / ESPN networks."
                                })

    except Exception as err:
        print(f"Dynamic fetch error: {err}")

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

    print("Executing dynamic web scraper (Wikipedia HTML API)...")
    parsed_events = fetch_dynamic_wwe_events()

    # Filter out past events automatically based on current UTC time
    now_utc_str = datetime.datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    future_events = [e for e in parsed_events if e['end_utc'] >= now_utc_str]

    ics_content = generate_ics_content(future_events)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    print(f"Successfully scraped and generated {output_path} with {len(future_events)} future events.")

if __name__ == "__main__":
    main()
