#!/usr/bin/env python3
"""Probe public WWE PLE source pages from the GitHub Actions runner.

This is diagnostic only: it reports HTTP/page metadata and matching event terms.
It does not modify the calendar or write any files.
"""

from urllib.parse import urljoin

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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WWE-PLE-Source-Probe/1.0; "
        "+https://github.com/ninjamonkey73/misc-utilities)"
    )
}


def probe_source(name: str, url: str) -> bool:
    print(f"\n=== {name} ===")
    print(f"Requested URL: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as exc:
        print(f"Request error: {type(exc).__name__}: {exc}")
        return False

    content_type = response.headers.get("Content-Type", "(missing)")
    print(f"HTTP status: {response.status_code}")
    print(f"Final URL: {response.url}")
    print(f"Content-Type: {content_type}")
    print(f"Response bytes: {len(response.content)}")

    soup = BeautifulSoup(response.content, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "(no HTML title)"
    visible_text = soup.get_text(" ", strip=True)
    html_lower = response.text.lower()
    visible_lower = visible_text.lower()

    print(f"Page title: {title}")
    print(f"HTML tables: {len(soup.find_all('table'))}")
    print(f"Links: {len(soup.find_all('a', href=True))}")
    print(f"JavaScript blocks: {len(soup.find_all('script'))}")
    print(f"JSON-LD blocks: {len(soup.find_all('script', attrs={'type': 'application/ld+json'}))}")

    matched_links = []
    for anchor in soup.find_all("a", href=True):
        link_text = anchor.get_text(" ", strip=True)
        href = urljoin(response.url, anchor["href"])
        combined = f"{link_text} {href}".lower()
        if any(term.lower() in combined for term in EVENT_TERMS):
            matched_links.append((link_text or "(no link text)", href))

    print("Event term matches (raw HTML / visible text):")
    for term in EVENT_TERMS:
        needle = term.lower()
        print(
            f"  {term}: raw_html={needle in html_lower}, "
            f"visible_text={needle in visible_lower}"
        )

    print("Matching links:")
    if matched_links:
        for link_text, href in matched_links[:12]:
            print(f"  {link_text[:100]} -> {href}")
        if len(matched_links) > 12:
            print(f"  ... and {len(matched_links) - 12} more")
    else:
        print("  (none found in returned HTML)")

    return 200 <= response.status_code < 300


def main() -> int:
    results = [probe_source(name, url) for name, url in SOURCES.items()]
    failed = len(results) - sum(results)
    print(f"\nProbe summary: {len(results) - failed}/{len(results)} sources returned HTTP 2xx.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
