#!/usr/bin/env python3
"""Probe public WWE PLE listings and linked event detail pages.

Diagnostic only: reports HTTP/page metadata, candidate event links, and visible
text snippets containing likely dates or start times. It does not modify the
calendar or write any files.
"""

import re
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

SOURCES = {
    "On Location WWE": "https://onlocationexp.com/wwe",
    "WWE Corporate News": "https://corporate.wwe.com/about/news",
    "WWE Events": "https://www.wwe.com/events",
}

EVENT_TERMS = (
    "Money in the Bank",
    "Survivor Series",
    "Wrestlepalooza",
    "Royal Rumble",
)

MONTHS = (
    "Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    "Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
DATE_RE = re.compile(
    rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+20\d{{2}})?\b"
    r"|\b20\d{2}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
TIME_RE = re.compile(
    r"\b(?:0?[1-9]|1[0-2])(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?)"
    r"(?:\s*(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|UTC))?\b",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WWE-PLE-Source-Probe/1.0; "
        "+https://github.com/ninjamonkey73/misc-utilities)"
    )
}
TIMEOUT_SECONDS = 30
MAX_DETAIL_PAGES_PER_SOURCE = 20


def fetch_page(name: str, url: str):
    print(f"\n=== {name} ===")
    print(f"Requested URL: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        print(f"Request error: {type(exc).__name__}: {exc}")
        return None, None

    print(f"HTTP status: {response.status_code}")
    print(f"Final URL: {response.url}")
    print(f"Content-Type: {response.headers.get('Content-Type', '(missing)')}")
    print(f"Response bytes: {len(response.content)}")

    soup = BeautifulSoup(response.content, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "(no HTML title)"
    print(f"Page title: {title}")
    print(f"HTML tables: {len(soup.find_all('table'))}")
    print(f"Links: {len(soup.find_all('a', href=True))}")
    print(f"JavaScript blocks: {len(soup.find_all('script'))}")
    print(
        "JSON-LD blocks: "
        f"{len(soup.find_all('script', attrs={'type': 'application/ld+json'}))}"
    )
    return response, soup


def canonicalize_url(url: str) -> str:
    url, _fragment = urldefrag(url)
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def is_relevant_detail_link(source_name: str, href: str, combined_text: str) -> bool:
    lowered = href.lower()
    if source_name == "On Location WWE":
        return "/wwe/" in lowered and "ticket" in lowered
    if source_name == "WWE Events":
        return "/event/" in lowered and "road to" not in combined_text.lower()
    if source_name == "WWE Corporate News":
        return "/about/news/" in lowered
    return False


def find_detail_links(source_name: str, response, soup):
    links = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        link_text = anchor.get_text(" ", strip=True)
        href = canonicalize_url(urljoin(response.url, anchor["href"]))
        combined = f"{link_text} {href}"
        if not any(term.lower() in combined.lower() for term in EVENT_TERMS):
            continue
        if not is_relevant_detail_link(source_name, href, combined):
            continue
        if href in seen:
            continue
        seen.add(href)
        links.append((link_text or "(no link text)", href))
    return links


def print_event_matches(source_name: str, response, soup):
    visible_text = soup.get_text(" ", strip=True)
    raw_lower = response.text.lower()
    visible_lower = visible_text.lower()
    print("Event term matches (raw HTML / visible text):")
    for term in EVENT_TERMS:
        needle = term.lower()
        print(
            f"  {term}: raw_html={needle in raw_lower}, "
            f"visible_text={needle in visible_lower}"
        )

    links = find_detail_links(source_name, response, soup)
    print("Candidate event detail links:")
    if links:
        for label, href in links[:MAX_DETAIL_PAGES_PER_SOURCE]:
            print(f"  {label[:100]} -> {href}")
        if len(links) > MAX_DETAIL_PAGES_PER_SOURCE:
            print(f"  ... and {len(links) - MAX_DETAIL_PAGES_PER_SOURCE} more")
    else:
        print("  (none found in returned HTML)")
    return links[:MAX_DETAIL_PAGES_PER_SOURCE]


def print_date_time_evidence(soup):
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    matches = []
    for pattern in (DATE_RE, TIME_RE):
        for match in pattern.finditer(text):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 120)
            snippet = text[start:end].strip()
            if snippet not in matches:
                matches.append(snippet)

    print("Visible text around possible dates/start times:")
    if not matches:
        print("  (no matching date/time text found)")
        return
    for snippet in matches[:8]:
        print(f"  ...{snippet}...")
    if len(matches) > 8:
        print(f"  ... {len(matches) - 8} more matches omitted")


def probe_detail_page(source_name: str, label: str, url: str) -> bool:
    response, soup = fetch_page(f"{source_name} detail: {label[:80]}", url)
    if response is None:
        return False
    print_event_matches(source_name, response, soup)
    print_date_time_evidence(soup)
    return 200 <= response.status_code < 300


def main() -> int:
    failures = 0
    detail_targets = []

    for source_name, url in SOURCES.items():
        response, soup = fetch_page(source_name, url)
        if response is None:
            failures += 1
            continue
        if not 200 <= response.status_code < 300:
            failures += 1
        detail_targets.extend(
            (source_name, label, href)
            for label, href in print_event_matches(source_name, response, soup)
        )

    seen_details = set()
    for source_name, label, url in detail_targets:
        if url in seen_details:
            continue
        seen_details.add(url)
        if not probe_detail_page(source_name, label, url):
            failures += 1

    print(
        f"\nProbe summary: {len(SOURCES)} listing pages and "
        f"{len(seen_details)} unique detail pages checked; "
        f"{failures} request(s) failed or returned non-2xx status."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
