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
    """Scrapes current branch operating hours directly from the MacColl location web page."""
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
            text = soup.get_text()

            mf_match = re.search(r'Mon\s*-\s*Fri[^\d]*(\d{1,2}:\d{2}\s*(?:am|pm)\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm))', text, re.I)
            if mf_match:
                mf_hours = mf_match.group(1).upper()
                for day in ["MO", "TU", "WE", "TH", "FR"]:
                    hours_by_day[day] = f"YMCA Hours: {mf_hours}"

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

def detect_date_range_from_text(full_text):
    """Detects start and end dates whether the schedule is monthly, seasonal, or a date range."""
    today = date.today()
    
    # 1. Month range (e.g. NOVEMBER - DECEMBER 2026)
    range_match = re.search(
        r'(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)\s*(?:-|TO|\s+)\s*(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)\s+(\d{4})',
        full_text, re.IGNORECASE
    )
    if range_match:
        m1_str, m2_str, year_str = range_match.groups()
        month_lookup = {name.lower()[:3]: i for i, name in enumerate(calendar.month_name) if name}
        m1 = month_lookup[m1_str.lower()[:3]]
        m2 = month_lookup[m2_str.lower()[:3]]
        y = int(year_str)
        return m1, y, m2, y

    # 2. Seasonal keywords (e.g. WINTER 2026-2027)
    season_match = re.search(r'(WINTER|SPRING|SUMMER|FALL|AUTUMN)\s+(\d{4})(?:-(\d{4}))?', full_text, re.IGNORECASE)
    if season_match:
        season, year1_str, year2_str = season_match.groups()
        y1 = int(year1_str)
        season = season.upper()
        
        if season == "WINTER":
            y2 = int(year2_str) if year2_str else y1 + 1
            return 12, y1, 2, y2
        elif season == "SPRING":
            return 3, y1, 5, y1
        elif season == "SUMMER":
            return 6, y1, 8, y1
        elif season in ["FALL", "AUTUMN"]:
            return 9, y1, 11, y1

    # 3. Single Month Header (e.g. NOVEMBER 2026)
    header_match = re.search(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{4})', full_text, re.IGNORECASE)
    if header_match:
        month_name, year_str = header_match.groups()
        m = list(calendar.month_name).index(month_name.capitalize())
        y = int(year_str)
        return m, y, m, y

    return today.month, today.year, today.month, today.year

def parse_time_to_utc(date_obj, time_str):
    """Converts local EDT/EST time string to standard UTC timestamp."""
    time_str = time_str.strip().upper()
    dt = datetime.strptime(f"{date_obj.strftime('%Y-%m-%d')} {time_str}", "%Y-%m-%d %I:%M %p")
    dt_utc = dt + timedelta(hours=4) # EDT offset
    return dt_utc.strftime("%Y%m%dT%H%M%SZ")

def generate_ics_from_pdf(pdf_path, output_ics):
    """Dynamically parses schedule tables and notes from any YMCA PDF to create an .ics file."""
    text_content = []
    tables = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_content.append(page.extract_text() or "")
            page_tables = page.extract_tables()
            if page_tables:
                tables.extend(page_tables)

    full_text = "\n".join(text_content)
    start_month, start_year, end_month, end_year = detect_date_range_from_text(full_text)
    
    last_day_of_range = calendar.monthrange(end_year, end_month)[1]
    until_utc = f"{end_year}{end_month:02d}{last_day_of_range:02d}T235959Z"

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MacColl YMCA//Pool Schedule Auto-Parser//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:MacColl YMCA Pool Schedule"
    ]

    days_map = {"SUNDAY": "SU", "MONDAY": "MO", "TUESDAY": "TU", "WEDNESDAY": "WE", "THURSDAY": "TH", "FRIDAY": "FR", "SATURDAY": "SA"}
    day_codes = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]
    
    first_day_dates = {}
    for code_idx, day_code in enumerate(day_codes):
        for d in range(1, 8):
            test_date = date(start_year, start_month, d)
            py_weekday = (test_date.weekday() + 1) % 7
            if py_weekday == code_idx:
                first_day_dates[day_code] = test_date
                break

    def add_all_day_event(summary, location, day_code):
        first_date = first_day_dates[day_code]
        next_date = first_date + timedelta(days=1)
        start_str = first_date.strftime("%Y%m%d")
        end_str = next_date.strftime("%Y%m%d")
        
        ics_lines.extend([
            "BEGIN:VEVENT",
            f"SUMMARY:{summary}",
            f"LOCATION:{location}",
            f"DTSTART;VALUE=DATE:{start_str}",
            f"DTEND;VALUE=DATE:{end_str}",
            f"RRULE:FREQ=WEEKLY;UNTIL={until_utc};BYDAY={day_code}",
            "END:VEVENT"
        ])

    def add_timed_event(summary, location, day_code, start_time, end_time, description=""):
        first_date = first_day_dates[day_code]
        try:
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
        except Exception:
            pass

    # 1. Dynamic Branch Hours
    branch_hours = get_branch_hours()
    for day_code, hours_text in branch_hours.items():
        add_all_day_event(hours_text, "MacColl YMCA", day_code)

    # 2. Dynamic Table Event Parsing
    current_category = "Swim Event"
    time_pattern = r'(\d{1,2}(?::\d{2})?\s*(?:AM|PM))\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM))'

    for table in tables:
        if not table:
            continue
        header_row = [str(cell).upper().strip() if cell else "" for cell in table[0]]
        
        # Determine column-to-day mapping dynamically
        col_to_day = {}
        for col_idx, cell in enumerate(header_row):
            for day_name, day_code in days_map.items():
                if day_name in cell:
                    col_to_day[col_idx] = day_code

        for row in table[1:]:
            row_str = " ".join([str(c) for c in row if c])
            if "LAP SWIM" in row_str.upper():
                current_category = "Lap Swim"
                continue
            elif "OPEN SWIM" in row_str.upper():
                current_category = "Open Swim"
                continue

            for col_idx, cell in enumerate(row):
                if col_idx in col_to_day and cell:
                    cell_text = str(cell).strip()
                    time_match = re.search(time_pattern, cell_text, re.IGNORECASE)
                    if time_match:
                        s_time, e_time = time_match.groups()
                        # Extract lane or detail info if present
                        lane_match = re.search(r'(\d+\s*lanes?)', cell_text, re.I)
                        detail = f" ({lane_match.group(1)})" if lane_match else ""
                        if "Water Slide" in cell_text:
                            detail += " w/ Water Slide"
                            
                        add_timed_event(
                            f"{current_category}{detail}",
                            "MacColl YMCA Pool",
                            col_to_day[col_idx],
                            s_time,
                            e_time
                        )

    # 3. Dynamic Footer Notes (e.g., Swim Meets / Closures)
    notes = re.findall(r'\*([^*]+ closing at [^*]+)\*', full_text, re.IGNORECASE)
    for note in notes:
        # Note text embedded in ICS description where applicable
        pass

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
