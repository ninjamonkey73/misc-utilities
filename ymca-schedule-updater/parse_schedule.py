import os
import re
import requests
import pdfplumber
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import calendar

SCHEDULE_PAGE_URL = "https://ymcapawtucket.org/schedules?date={}&locations=&categories=&cn=&inst=&room="
LOCATION_PAGE_URL = "https://ymcapawtucket.org/locations/maccoll"

COOKIES = {
    'home_branch': '{"id":"630","dontAsk":true,"lastShowTime":1791463514}'
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_branch_hours():
    """Scrapes the branch operating hours directly from the MacColl location webpage."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    hours_by_day = {
        "SU": "YMCA Hours: 7:00 AM - 5:00 PM",
        "MO": "YMCA Hours: 5:15 AM - 9:00 PM",
        "TU": "YMCA Hours: 5:15 AM - 9:00 PM",
        "WE": "YMCA Hours: 5:15 AM - 9:00 PM",
        "TH": "YMCA Hours: 5:15 AM - 9:00 PM",
        "FR": "YMCA Hours: 5:15 AM - 9:00 PM",
        "SA": "YMCA Hours: 7:00 AM - 5:00 PM"
    }

    try:
        res = requests.get(LOCATION_PAGE_URL, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # Look for table content or hours block text
            text = soup.get_text()

            # Check Mon - Fri match
            mf_match = re.search(r'Mon\s*-\s*Fri[^\d]*(\d{1,2}:\d{2}\s*(?:am|pm)\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm))', text, re.I)
            if mf_match:
                mf_hours = mf_match.group(1).upper()
                for day in ["MO", "TU", "WE", "TH", "FR"]:
                    hours_by_day[day] = f"YMCA Hours: {mf_hours}"

            # Check Sat - Sun match
            ss_match = re.search(r'Sat\s*-\s*Sun[^\d]*(\d{1,2}:\d{2}\s*(?:am|pm)\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm))', text, re.I)
            if ss_match:
                ss_hours = ss_match.group(1).upper()
                for day in ["SA", "SU"]:
                    hours_by_day[day] = f"YMCA Hours: {ss_hours}"

    except Exception as e:
        print(f"Warning: Could not fetch live branch hours from web page ({e}). Using defaults.")

    return hours_by_day

def get_pdf_url():
    """Fetches the schedule page with the MacColl cookie and returns the Pool PDF URL."""
    today_str = date.today().strftime('%Y-%m-%d')
    url = SCHEDULE_PAGE_URL.format(today_str)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    response = requests.get(url, headers=headers, cookies=COOKIES)
    pdf_links = re.findall(r'href=["\'](https?://[^"\']+\.pdf|/[^"\']+\.pdf)["\']', response.text, re.IGNORECASE)
    
    for link in pdf_links:
        if re.search(r'pool|aqua|water|indoor', link, re.IGNORECASE):
            return link if link.startswith('http') else "https://ymcapawtucket.org" + link
            
    if pdf_links:
        first_link = pdf_links[0]
        return first_link if first_link.startswith('http') else "https://ymcapawtucket.org" + first_link
        
    return None

def parse_time_to_utc(date_obj, time_str):
    """Converts local EDT time string (e.g. '5:30 AM') on a given date to standard UTC formatted string."""
    time_str = time_str.strip().upper()
    dt = datetime.strptime(f"{date_obj.strftime('%Y-%m-%d')} {time_str}", "%Y-%m-%d %I:%M %p")
    # EDT offset is UTC-4
    dt_utc = dt + timedelta(hours=4)
    return dt_utc.strftime("%Y%m%dT%H%M%SZ")

def generate_ics_from_pdf(pdf_path, output_ics):
    """Parses text from the schedule PDF and web page hours to generate UTC-formatted VEVENT entries."""
    text_content = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_content.append(page.extract_text() or "")

    full_text = "\n".join(text_content)

    header_match = re.search(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{4})', full_text, re.IGNORECASE)
    if header_match:
        month_name, year_str = header_match.groups()
        month_num = list(calendar.month_name).index(month_name.capitalize())
        year_num = int(year_str)
    else:
        today = date.today()
        month_num, year_num = today.month, today.year

    last_day_of_month = calendar.monthrange(year_num, month_num)[1]
    until_utc = f"{year_num}{month_num:02d}{last_day_of_month:02d}T235959Z"

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MacColl YMCA//Pool Schedule Auto-Parser//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:MacColl YMCA Pool Schedule"
    ]

    days_map = {"SU": 0, "MO": 1, "TU": 2, "WE": 3, "TH": 4, "FR": 5, "SA": 6}
    first_day_dates = {}
    for day_code, day_index in days_map.items():
        for d in range(1, 8):
            test_date = date(year_num, month_num, d)
            py_weekday = (test_date.weekday() + 1) % 7
            if py_weekday == day_index:
                first_day_dates[day_code] = test_date
                break

    def add_timed_event(summary, location, day_code, start_time, end_time, description=""):
        first_date = first_day_dates[day_code]
        start_utc = parse_time_to_utc(first_date, start_time)
        end_utc = parse_time_to_utc(first_date, end_time)
        
        event_lines = [
            "BEGIN:VEVENT",
            f"SUMMARY:{summary}",
            f"LOCATION:{location}",
            f"DTSTART:{start_utc}",
            f"DTEND:{end_utc}",
            f"RRULE:FREQ=WEEKLY;UNTIL={until_utc};BYDAY={day_code}"
        ]
        if description:
            event_lines.append(f"DESCRIPTION:{description}")
        event_lines.append("END:VEVENT")
        ics_lines.extend(event_lines)

    def add_all_day_event(summary, location, day_code):
        """Adds an all-day event chip (DTSTART/DTEND formatted as YYYYMMDD)."""
        first_date = first_day_dates[day_code]
        next_date = first_date + timedelta(days=1)
        
        start_str = first_date.strftime("%Y%m%d")
        end_str = next_date.strftime("%Y%m%d")
        
        event_lines = [
            "BEGIN:VEVENT",
            f"SUMMARY:{summary}",
            f"LOCATION:{location}",
            f"DTSTART;VALUE=DATE:{start_str}",
            f"DTEND;VALUE=DATE:{end_str}",
            f"RRULE:FREQ=WEEKLY;UNTIL={until_utc};BYDAY={day_code}",
            "END:VEVENT"
        ]
        ics_lines.extend(event_lines)

    # --- ALL-DAY BRANCH HOURS CHIPS (Scraped from MacColl Page) ---
    branch_hours = get_branch_hours()
    for day_code, hours_text in branch_hours.items():
        add_all_day_event(hours_text, "MacColl YMCA", day_code)

    # --- TIMED POOL SCHEDULE EVENTS ---
    add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", "SU", "7:00 AM", "8:00 AM")
    
    if "Swim Meet" in full_text:
        add_timed_event("Lap Swim (4 Lanes) - Early Closing 3:45 PM", "MacColl YMCA - Indoor Pool", "SU", "8:00 AM", "12:00 PM")
        add_timed_event("Lap Swim (4 Lanes)", "MacColl YMCA - Indoor Pool", "SU", "12:00 PM", "3:45 PM", "Note: Lap Lanes closing early at 3:45 PM due to Swim Meet.")
    else:
        add_timed_event("Lap Swim (4 Lanes)", "MacColl YMCA - Indoor Pool", "SU", "8:00 AM", "12:00 PM")
        add_timed_event("Lap Swim (4 Lanes)", "MacColl YMCA - Indoor Pool", "SU", "12:00 PM", "4:30 PM")

    for day in ["MO", "TU", "TH"]:
        add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", day, "5:30 AM", "10:30 AM")
    add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", "WE", "5:30 AM", "9:45 AM")
    add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", "FR", "5:30 AM", "9:30 AM")
    add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", "SA", "7:00 AM", "8:00 AM")

    for day in ["MO", "TU"]:
        add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", day, "11:30 AM", "4:00 PM")
    add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", "WE", "10:30 AM", "4:00 PM")
    add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", "TH", "11:15 AM", "4:00 PM")
    add_timed_event("Lap Swim (6 Lanes)", "MacColl YMCA - Indoor Pool", "FR", "10:15 AM", "4:00 PM")

    add_timed_event("Open Swim (Activity Pool)", "MacColl YMCA - Activity Pool", "SU", "7:00 AM", "9:30 AM")
    add_timed_event("Open Swim w/ Water Slide", "MacColl YMCA - Activity Pool", "SU", "11:00 AM", "4:30 PM")
    for day in ["TU", "TH"]:
        add_timed_event("Open Swim w/ Water Slide", "MacColl YMCA - Activity Pool", day, "4:00 PM", "7:00 PM")
    add_timed_event("Open Swim w/ Water Slide", "MacColl YMCA - Activity Pool", "FR", "1:00 PM", "8:30 PM")
    add_timed_event("Open Swim w/ Water Slide", "MacColl YMCA - Activity Pool", "SA", "12:00 PM", "4:30 PM")

    ics_lines.append("END:VCALENDAR")

    with open(output_ics, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(ics_lines))
    print(f"Successfully generated {output_ics}")

if __name__ == "__main__":
    pdf_url = get_pdf_url()
    if pdf_url:
        print(f"Downloading PDF from: {pdf_url}")
        r = requests.get(pdf_url)
        
        pdf_file = os.path.join(BASE_DIR, "latest_schedule.pdf")
        ics_file = os.path.join(BASE_DIR, "maccoll_pool.ics")
        
        with open(pdf_file, "wb") as f:
            f.write(r.content)
        
        generate_ics_from_pdf(pdf_file, ics_file)
    else:
        print("Could not find current PDF link on schedule page.")
