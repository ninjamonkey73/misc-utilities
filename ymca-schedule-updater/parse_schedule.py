import os
import re
import requests
import pdfplumber
from datetime import datetime, date
import calendar

# Target YMCA URL and Location Cookie
SCHEDULE_PAGE_URL = "https://ymcapawtucket.org/schedules?date={}&locations=&categories=&cn=&inst=&room="

# YMCA Cookie for MacColl Branch
COOKIES = {
    'home_branch': '{"id":"630","dontAsk":true,"lastShowTime":1791463514}'
}

# Define base directory relative to this script file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_pdf_url():
    """Fetches the schedule page passing the MacColl home_branch cookie and extracts the PDF link."""
    today_str = date.today().strftime('%Y-%m-%d')
    url = SCHEDULE_PAGE_URL.format(today_str)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    response = requests.get(url, headers=headers, cookies=COOKIES)
    
    # Search for direct absolute PDF links
    match = re.search(r'href=["\'](https?://[^"\']+\.pdf)["\']', response.text, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Fallback to relative PDF links
    match_rel = re.search(r'href=["\'](/[^"\']+\.pdf)["\']', response.text, re.IGNORECASE)
    if match_rel:
        return "https://ymcapawtucket.org" + match_rel.group(1)
        
    return None

def generate_ics_from_pdf(pdf_path, output_ics):
    """Parses text from the downloaded schedule PDF and generates a standard UTC-formatted .ics file."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    # Basic ICS Header with UTC time formatting
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MacColl YMCA//Pool Schedule Auto-Parser//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:MacColl YMCA Pool Schedule"
    ]

    # Parsing logic tailored to MacColl PDF layout goes here
    # Extracted event blocks are appended as VEVENT entries in pure UTC format
    
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
        print("Could not find current PDF link on schedule page. Verify if cookie or page structure changed.")
