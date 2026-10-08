#!/usr,bin/env python3
"""
parse_wwe_ple.py
Dynamically fetches upcoming WWE Premium Live Events (PLEs) by querying
Wikipedia's Category API for current and upcoming year events.
Formats output into standard UTC calendar entries with stable UIDs.
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

WIKI_API = "https://en.wikipedia.org/w/api.php"

def sanitize_uid(title, start_utc):
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    date_part = start_utc.split('T')[0]
    return f"wwe-{clean_title}-{date_part}@wwe-ple-tracker"

def parse_date_to_utc(date_str):
    """Converts parsed dates into ISO 8601 UTC strings."""
    clean_date = re.sub(r'\[.*?\]|\(.*?\)', '', date_str).strip()
    dt = None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(clean_date, fmt)
            break
        except ValueError:
            continue

    if not dt:
        # Check for date ranges like 'August 1–2, 2026'
        m = re.search(r'([A-Z][a-z]+)\s+\d+[\u2013\-]\d+,\s+(\d{4})', clean_date)
        if m:
            try:
                dt = datetime.datetime.strptime(f"{m.group(1)} 1, {m.group(2)}", "%B %d, %Y")
            except ValueError:
                return None, None
        else:
            return None, None

    # Standard 8:00 PM ET start time -> convert to UTC (+4 hrs EDT / +5 hrs EST)
    dt_utc = dt.replace(hour=20, minute=0, tzinfo=timezone.utc) + timedelta(hours=4)
    start_utc = dt_utc.strftime("%Y%m%dT%H%M%SZ")
    end_utc = (dt_utc + timedelta(hours=4)).strftime("%Y%m%dT%H%M%SZ")
    return start_utc, end_utc

def fetch_events_from_wiki_category(year):
    """Queries Wikipedia category for events in a given year."""
    events = []
    params = {
        "action": "categorymembers",
        "cmtitle": f"Category:{year}_WWE_pay-per-view_events",
        "cmlimit": "50",
        "format": "json"
    }
    
    try:
        res = requests.get(WIKI_API, headers=HEADERS, params=params, timeout=10)
        if res.status_code != 200:
            return events
        
        pages = res.json().get("query", {}).get("categorymembers", [])
        for p in pages:
            page_title = p.get("title", "")
            if not page_title:
                continue

            # Fetch parsed page infobox to extract exact date & location
            parse_params = {
                "action": "parse",
                "page": page_title,
                "prop": "text",
                "format": "json"
            }
            p_res = requests.get(WIKI_API, headers=HEADERS, params=parse_params, timeout=10)
            if p_res.status_code != 200:
                continue
            
            html = p_res.json().get("parse", {}).get("text", {}).get("*", "")
            soup = BeautifulSoup(html, "html.parser")
            infobox = soup.find("table", class_=re.compile(r'infobox', re.I))
            
            if not infobox:
                continue

            date_val, loc_val = "", "TBA"
            for tr in infobox.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
                if th and td:
                    label = th.get_text(strip=True).lower()
                    if label == "date":
                        date_val = td.get_text(" ", strip=True)
                    elif label in ["venue", "city", "location"]:
                        loc_val = td.get_text(" ", strip=True)

            if date_val:
                start_utc, end_utc = parse_date_to_utc(date_val)
                if start_utc:
                    clean_name = re.sub(r'\s*\(\d{4}\)', '', page_title)
                    uid = sanitize_uid(clean_name, start_utc)
                    events.append({
                        "uid": uid,
                        "summary": f"WWE {clean_name}" if not clean_name.lower().startswith("wwe") else clean_name,
                        "start_utc": start_utc,
                        "end_utc": end_utc,
                        "location": re.sub(r'\[.*?\]', '', loc_val).strip(),
                        "description": f"Official WWE Event: {clean_name}. Broadcast live on Peacock / ESPN networks."
                    })

    except Exception as err:
        print(f"Error scraping category {year}: {err}")

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

    current_year = datetime.datetime.now(timezone.utc).year
    parsed_events = []
    
    # Check current year and next year categories
    for year in [current_year, current_year + 1]:
        parsed_events.extend(fetch_events_from_wiki_category(year))

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
