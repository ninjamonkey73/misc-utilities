#!/usr/bin/env python3
"""
parse_wwe_ple.py
Dynamically fetches upcoming WWE Premium Live Events (PLEs) from On Location,
converts dates to Eastern Time, and updates wwe_ple_schedule.ics.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Public re-exports expected by tests
# ---------------------------------------------------------------------------
datetime = datetime          # parser.datetime(...)
timedelta = timedelta        # parser.timedelta(...)
BeautifulSoup = BeautifulSoup  # parser.BeautifulSoup(...)
try:
    ET = ZoneInfo("America/New_York")
except ZoneInfoNotFoundError:
    # Windows Python without `tzdata` installed; fall back to fixed EST (-05:00)
    ET = timezone(timedelta(hours=-5), name="America/New_York")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": "WWE-PLE-Calendar-Bot/1.0 (https://github.com/ninjamonkey73/misc-utilities)"
}

ONLOCATION_URL = "https://www.onlocationexp.com/wwe"

_ALIASES_PATH = Path(__file__).with_name("wwe_ple_event_aliases.json")

# Loaded once at import time
with open(_ALIASES_PATH, encoding="utf-8") as _f:
    _ALIAS_DATA = json.load(_f)

_SLUG_ALIASES: dict[str, str] = _ALIAS_DATA.get("aliases", {})
_NON_PLE_SLUGS: list[str] = _ALIAS_DATA.get("nonPlePackageSlugs", [])

# Patterns of non-PLE package slugs (beyond the explicit list)
_NON_PLE_PATTERNS = re.compile(
    r"(monday.night.raw|friday.night.smackdown|road.to|house.show|live.event|"
    r"wwe.raw|wwe.smackdown|wwe.nxt(?!.deadline|.takeover|.halloween|.new.year))",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------

def canonical_slug(raw: str) -> str:
    """Normalise a raw package slug to a stable calendar key via the aliases map.

    Falls back to stripping trailing ``-tickets`` / ``-YYYY`` suffixes and
    re-checking, then returns the cleaned slug as-is.
    """
    cleaned = raw.lower().strip()
    if cleaned in _SLUG_ALIASES:
        return _SLUG_ALIASES[cleaned]
    # Strip common suffixes and retry
    stripped = re.sub(r"(-tickets?|-\d{4})$", "", cleaned)
    if stripped in _SLUG_ALIASES:
        return _SLUG_ALIASES[stripped]
    return stripped


def key_from_uid(uid: str) -> str:
    """Extract the canonical event key embedded in a UID string.

    UIDs follow the pattern ``wwe-<key>-<year>@wwe-ple-tracker``.
    Returns the canonical slug for the extracted key segment.
    """
    # e.g. "wwe-mitb-2026@wwe-ple-tracker"  -> "mitb"
    match = re.match(r"wwe-(.+?)-\d{4}@wwe-ple-tracker", uid)
    if match:
        return canonical_slug(match.group(1))
    return uid


def event_uid(key: str, year: int, existing: dict | None = None) -> str:
    """Return a stable UID for an event, preserving any existing UID."""
    if existing and existing.get("uid"):
        return existing["uid"]
    return f"wwe-{key}-{year}@wwe-ple-tracker"


def is_non_ple_package(slug: str) -> bool:
    """Return True if the slug represents a weekly show or non-PLE package."""
    cleaned = slug.lower()
    # Check the explicit list from JSON.  Match the full slug or as the prefix
    # segment of a hyphen-delimited slug, but NOT as a prefix of a PLE sub-brand
    # (e.g. "nxt" should not match "nxt-deadline").
    for non_ple in _NON_PLE_SLUGS:
        # Exact match, or match followed by end-of-string or a year suffix only
        if re.fullmatch(re.escape(non_ple) + r"(-\d{4})?", cleaned):
            return True
        # Match as a contained hyphen-segment: e.g. "monday-night-raw" in "wwe-monday-night-raw-2026"
        if re.search(r"(?<![a-z])" + re.escape(non_ple) + r"(?=-\d{4}$|$)", cleaned):
            return True
    # Pattern-based check for common non-PLE descriptors
    if _NON_PLE_PATTERNS.search(cleaned):
        return True
    return False


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def title_for_event(
    key: str,
    slug: str,
    listing_title: str,
    package_title: str,
) -> str:
    """Derive the best display title for an event.

    Prefers the more specific *package_title* (e.g. the subtitle-enriched name
    from the event's own On Location page) over the generic *listing_title*.
    Strips trailing year/ticket boilerplate and ensures a ``WWE `` prefix when
    appropriate.
    """
    # Take the package page title up to the first ``|`` separator
    raw = package_title.split("|")[0].strip()
    # Strip trailing date (e.g. "November 28, 2026"), "Ticket Packages", "Tickets", or year
    _months = (
        r"(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
    )
    raw = re.sub(
        rf"\s*(?:{_months}\s+\d{{1,2}}(?:\s*[\u2013\-]\s*\d{{1,2}})?,\s*\d{{4}}|{_months}\s+\d{{4}}|Ticket Packages?|Tickets?|\d{{4}})\s*$",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()

    if not raw:
        raw = listing_title.split("|")[0].strip()
        raw = re.sub(r"\s*(Ticket Packages?|Tickets?|\d{4})\s*$", "", raw, flags=re.IGNORECASE).strip()

    prefix_needed = not re.match(r"^(WWE|NXT|AAA)\b", raw, re.IGNORECASE)
    return f"WWE {raw}" if prefix_needed else raw


def _key_patterns(key: str) -> list[re.Pattern]:
    """Return compiled patterns for all names/aliases that map to *key*."""
    names = {key}
    for alias, target in _SLUG_ALIASES.items():
        if target == key:
            names.add(alias)
    patterns = []
    for name in names:
        # "mitb" -> pattern for "mitb"; "money-in-the-bank" -> "money in the bank"
        readable = name.replace("-", r"[\s\-]+")
        patterns.append(re.compile(readable, re.IGNORECASE))
    return patterns


def choose_full_event_details(text: str, key: str) -> dict | None:
    """Parse a full ``Month Day, Year | City, ST | Venue`` block from *text*.

    Returns a dict with keys ``date`` (``datetime.date``), ``city`` (str),
    and ``venue`` (str), or ``None`` when no unambiguous full date is found
    for this specific event.

    The function guards against attaching a full date that actually belongs to
    a *different* event mentioned later in the same text block (e.g. a Super Bowl
    date that follows a month-only Royal Rumble mention).
    """
    full_date_pattern = re.compile(
        r"(?P<month>January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})"
        r"\s*\|\s*(?P<city>[^|]+?)\s*\|\s*(?P<venue>[^|\n]+?)(?=\s+Ever|\s+Buy|\s+Get|\s+Experience|\s*$)",
        re.IGNORECASE,
    )

    key_patterns = _key_patterns(key)

    for m in full_date_pattern.finditer(text):
        preceding = text[max(0, m.start() - 120): m.start()]
        # Narrow to the same "clause": text after the last pipe separator.
        # If the key doesn't appear in the same clause as the date, the date
        # belongs to a different listing entry (e.g. Super Bowl after Royal Rumble).
        last_pipe = preceding.rfind("|")
        same_clause = preceding[last_pipe + 1:] if last_pipe != -1 else preceding
        if not any(p.search(same_clause) for p in key_patterns):
            continue
        try:
            date = datetime.strptime(
                f"{m.group('month')} {m.group('day')}, {m.group('year')}", "%B %d, %Y"
            ).date()
        except ValueError:
            continue
        city = m.group("city").strip()
        venue = m.group("venue").strip()
        venue = re.sub(r"\s+(Ever|Buy|Get|Experience)\b.*", "", venue, flags=re.IGNORECASE).strip()
        return {"date": date, "city": city, "venue": venue}

    return None


def extract_broadcast_time(text: str, key: str, year: int) -> tuple[int, int] | None:
    """Return ``(hour24, minute)`` of the ET broadcast start, or ``None``.

    Only matches explicit ET/Eastern broadcast times (not venue door/bell times)
    and only when the year in the text matches *year*, preventing stale data
    from a previous edition from being reused.
    """
    # Must mention the target year
    if str(year) not in text:
        return None

    # Match "8:30 PM ET" or "8 PM ET" following broadcast language
    broadcast_re = re.compile(
        r"broadcasts?\s+live\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s+ET",
        re.IGNORECASE,
    )
    m = broadcast_re.search(text)
    if not m:
        return None

    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = m.group(3).upper()
    if meridiem == "PM" and hour != 12:
        hour += 12
    elif meridiem == "AM" and hour == 12:
        hour = 0
    return (hour, minute)


# ---------------------------------------------------------------------------
# ICS generation
# ---------------------------------------------------------------------------

def generate_ics_content(events: list[dict]) -> str:
    """Render a VCALENDAR string from a list of event dicts.

    Each event dict must have:
      - ``uid``        : str
      - ``summary``    : str
      - ``start``      : datetime (timezone-aware, typically ET)
      - ``end``        : datetime (timezone-aware)
      - ``location``   : str
      - ``description``: str
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WWE PLE Dynamic Schedule Tracker//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-TIMEZONE:America/New_York",
    ]

    for event in events:
        start: datetime = event["start"]
        end: datetime = event["end"]

        # Format as local time with TZID when timezone-aware ET, else UTC
        tz_key = getattr(start.tzinfo, "key", None) or (
            start.tzinfo.tzname(start) if start.tzinfo is not None else None
        )
        if start.tzinfo is not None and (start.tzinfo is ET or tz_key == "America/New_York"):
            # Use TZID form for Eastern time
            start_str = f"DTSTART;TZID=America/New_York:{start.strftime('%Y%m%dT%H%M%S')}"
            end_str = f"DTEND;TZID=America/New_York:{end.strftime('%Y%m%dT%H%M%S')}"
        elif start.tzinfo is not None:
            # Fallback: convert to UTC
            start_utc = start.astimezone(timezone.utc)
            end_utc = end.astimezone(timezone.utc)
            start_str = f"DTSTART:{start_utc.strftime('%Y%m%dT%H%M%SZ')}"
            end_str = f"DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}"
        else:
            start_str = f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}"
            end_str = f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{event['uid']}",
            f"SUMMARY:{event['summary']}",
            start_str,
            end_str,
            f"LOCATION:{event['location']}",
            f"DESCRIPTION:{event['description']}",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Network layer (patchable in tests)
# ---------------------------------------------------------------------------

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


def fetch(url: str) -> tuple:
    """GET *url* and return ``(response, BeautifulSoup)``."""
    res = _SESSION.get(url, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    return res, soup


def find_supplemental_links(soup: BeautifulSoup) -> dict[str, list[str]]:
    """Discover On Location package links from the WWE listing page soup.

    Returns a dict mapping a normalised slug to a list of supplemental URLs
    (currently just the href of each matching anchor).
    """
    packages: dict[str, list[str]] = {}
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if "onlocationexp.com/wwe/" not in href and "/wwe/" not in href:
            continue
        # Extract slug from path
        slug_match = re.search(r"/wwe/([^/?#]+)", href)
        if not slug_match:
            continue
        raw_slug = slug_match.group(1).lower()
        if is_non_ple_package(raw_slug):
            continue
        packages.setdefault(raw_slug, []).append(href)
    return packages


# ---------------------------------------------------------------------------
# Event discovery
# ---------------------------------------------------------------------------

def _load_existing_events(ics_path: Path) -> list[dict]:
    """Parse an existing ICS file and return event dicts."""
    if not ics_path.exists():
        return []
    events = []
    text = ics_path.read_text(encoding="utf-8")
    for block in re.split(r"BEGIN:VEVENT", text)[1:]:
        uid_m = re.search(r"UID:(.+)", block)
        summary_m = re.search(r"SUMMARY:(.+)", block)
        start_m = re.search(r"DTSTART(?:;TZID=([^:]+))?:(\d{8}T\d{6})(Z?)", block)
        end_m = re.search(r"DTEND(?:;TZID=([^:]+))?:(\d{8}T\d{6})(Z?)", block)
        if not (uid_m and start_m):
            continue

        def _parse_dt(m):
            tzid, dtstr, zulu = m.group(1), m.group(2), m.group(3)
            dt = datetime.strptime(dtstr, "%Y%m%dT%H%M%S")
            if tzid:
                try:
                    return dt.replace(tzinfo=ZoneInfo(tzid))
                except ZoneInfoNotFoundError:
                    return dt.replace(tzinfo=ET)
            elif zulu:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        start_dt = _parse_dt(start_m)
        end_dt = _parse_dt(end_m) if end_m else start_dt + timedelta(hours=4)
        key = key_from_uid(uid_m.group(1).strip())
        events.append({
            "uid": uid_m.group(1).strip(),
            "key": key,
            "summary": summary_m.group(1).strip() if summary_m else "",
            "start": start_dt,
            "end": end_dt,
            "location": "",
            "description": "",
        })
    return events


def discover_events(output_path: Path) -> list[dict]:
    """Discover upcoming WWE PLE events, merging with any already in *output_path*.

    Returns the final list of future event dicts (each with ``start``/``end``
    as timezone-aware datetimes).
    """
    now = datetime.now(tz=ET)

    # Load existing calendar so we can preserve already-known future events
    existing_by_key: dict[str, dict] = {}
    for ev in _load_existing_events(output_path):
        existing_by_key[ev["key"]] = ev

    # Fetch On Location WWE listing page
    try:
        _resp, listing_soup = fetch(ONLOCATION_URL)
    except Exception as err:
        print(f"Failed to fetch On Location listing: {err}")
        return [ev for ev in existing_by_key.values() if ev["start"] > now]

    packages = find_supplemental_links(listing_soup)

    merged: dict[str, dict] = {}
    skipped_slugs: list[str] = []

    for raw_slug, urls in packages.items():
        key = canonical_slug(raw_slug)
        print(f"Checking package: {raw_slug}", flush=True)

        # Try to fetch the individual package page for full details
        details = None
        broadcast_time = None
        listing_title = raw_slug
        package_title = ""

        for url in urls:
            try:
                resp, pkg_soup = fetch(url)
                pkg_text = pkg_soup.get_text(" ", strip=True)
                year = now.year
                details = choose_full_event_details(pkg_text, key)
                if details:
                    year = details["date"].year
                broadcast_time = extract_broadcast_time(pkg_text, key, year)
                package_title = pkg_soup.title.string if pkg_soup.title else ""
                break
            except Exception:
                continue

        if details is None:
            # No full date found — keep existing future event if present
            if key in existing_by_key and existing_by_key[key]["start"] > now:
                merged[key] = existing_by_key[key]
            else:
                skipped_slugs.append(raw_slug)
            continue

        date = details["date"]
        hour, minute = broadcast_time if broadcast_time else (20, 0)
        start_dt = datetime(date.year, date.month, date.day, hour, minute, tzinfo=ET)
        end_dt = start_dt + timedelta(hours=4)

        if start_dt <= now:
            continue  # already in the past

        existing = existing_by_key.get(key)
        uid = event_uid(key, date.year, existing)
        title = title_for_event(key, raw_slug, listing_title, package_title)
        location = f"{details['venue']}, {details['city']}" if details["venue"] else details["city"]

        merged[key] = {
            "uid": uid,
            "key": key,
            "summary": title,
            "start": start_dt,
            "end": end_dt,
            "location": location,
            "description": f"Official WWE Event: {title}.",
        }

    # Retain any existing future events that were not replaced by newly discovered ones
    for key, ev in existing_by_key.items():
        if key not in merged and ev["start"] > now:
            merged[key] = ev

    if skipped_slugs:
        print(f"skipping new packages without retrievable full event dates ({', '.join(sorted(skipped_slugs))})")

    return sorted(merged.values(), key=lambda e: e["start"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    output_dir = Path(__file__).parent
    output_path = output_dir / "wwe_ple_schedule.ics"

    events = discover_events(output_path)

    if not events:
        print("No future events found; preserving existing .ics file.")
        sys.exit(0)

    output_path.write_text(generate_ics_content(events), encoding="utf-8")
    print(f"Updated {output_path} with {len(events)} upcoming events.")


if __name__ == "__main__":
    main()
