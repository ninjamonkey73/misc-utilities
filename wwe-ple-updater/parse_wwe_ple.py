#!/usr/bin/env python3
"""Discover and update upcoming WWE PLE home-viewing calendar entries.

On Location is used to discover official WWE hospitality/event pages. A full
announced event date and venue are parsed from the event detail page. Existing
ICS entries are retained as the identity registry and last-known-good data;
explicit broadcast times in ET update DTSTART, otherwise a new event defaults
to 8:00 PM ET. Venue-local times are not used as broadcast times.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ONLOCATION_URL = "https://onlocationexp.com/wwe"
WWE_EVENTS_URL = "https://www.wwe.com/events"
CORPORATE_NEWS_URL = "https://corporate.wwe.com/about/news"
ET = ZoneInfo("America/New_York")
DEFAULT_BROADCAST_TIME = (20, 0)
DEFAULT_DURATION = timedelta(hours=4)
REQUEST_TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WWE-PLE-Schedule/1.0; "
        "+https://github.com/ninjamonkey73/misc-utilities)"
    )
}

MONTH_PATTERN = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
FULL_DATE_RE = re.compile(
    rf"(?P<date>(?:{MONTH_PATTERN})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,\s+20\d{{2}})"
    r"\s*\|\s*(?P<city>[^|]{2,100})\s*\|\s*(?P<venue>[^|]{2,120})",
    re.IGNORECASE,
)
MONTH_YEAR_RE = re.compile(
    rf"(?P<month>(?:{MONTH_PATTERN})\.?)\s+(?P<year>20\d{{2}})"
    r"\s*\|\s*(?P<city>[^|]{2,100})",
    re.IGNORECASE,
)
ET_TIME_RE = re.compile(
    r"\b(?P<hour>0?[1-9]|1[0-2])(?::(?P<minute>[0-5]\d))?\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?)\s*"
    r"(?P<zone>ET|EST|EDT|Eastern(?:\s+Time)?)\b",
    re.IGNORECASE,
)

EVENT_ALIAS_PATH = Path(__file__).with_name("wwe_ple_event_aliases.json")
EVENT_REGISTRY = json.loads(EVENT_ALIAS_PATH.read_text(encoding="utf-8"))
SLUG_ALIASES = EVENT_REGISTRY["aliases"]
NON_PLE_PACKAGE_SLUGS = set(EVENT_REGISTRY["nonPlePackageSlugs"])
KNOWN_TITLES = {
    "mitb": "WWE Money in the Bank",
    "crownjewel": "WWE Crown Jewel",
    "survivor-series": "WWE Survivor Series: WarGames",
    "wrestlepalooza": "WWE Wrestlepalooza",
    "royalrumble": "WWE Royal Rumble",
}
EVENT_CONTEXT_TERMS = {
    "mitb": ("money", "bank"),
    "crownjewel": ("crown", "jewel"),
    "survivor-series": ("survivor", "series"),
    "wrestlepalooza": ("wrestlepalooza",),
    "royalrumble": ("royal", "rumble"),
}
NON_PLE_PACKAGE_PREFIXES = (
    "road-to-",
    "monday-night-raw-",
    "friday-night-smackdown-",
)


def event_context_terms(event_key):
    if event_key in EVENT_CONTEXT_TERMS:
        return EVENT_CONTEXT_TERMS[event_key]
    tokens = re.sub(r"-\d{4}$", "", event_key.lower()).split("-")
    return tuple(token for token in tokens if len(token) > 2 and token not in {"wwe", "tickets", "package", "packages"})


def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response, BeautifulSoup(response.content, "html.parser")


def clean_ics_text(value):
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def unescape_ics_text(value):
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def canonical_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-tickets?$", "", slug)
    slug = re.sub(r"-\d+$", "", slug)
    return SLUG_ALIASES.get(slug, slug)


def parse_ics_datetime(line):
    value = line.split(":", 1)[1].strip()
    if value.endswith("Z"):
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return parsed.astimezone(ET)
    parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
    return parsed.replace(tzinfo=ET)


def read_existing_events(path):
    """Read existing VEVENTs so updates retain stable UIDs and last-known data."""
    if not path.exists():
        return []

    events = []
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and current.get("uid") and current.get("start"):
                current["key"] = key_from_uid(current["uid"])
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue

        name, value = line.split(":", 1)
        if name == "UID":
            current["uid"] = value
        elif name == "SUMMARY":
            current["summary"] = unescape_ics_text(value)
        elif name.startswith("DTSTART"):
            current["start"] = parse_ics_datetime(line)
        elif name.startswith("DTEND"):
            current["end"] = parse_ics_datetime(line)
        elif name == "LOCATION":
            current["location"] = unescape_ics_text(value)
        elif name == "DESCRIPTION":
            current["description"] = unescape_ics_text(value)

    return events


def key_from_uid(uid):
    match = re.match(r"^wwe-(.+)-\d{4}@wwe-ple-tracker$", uid, re.IGNORECASE)
    if not match:
        return None
    return canonical_slug(match.group(1))


def is_non_ple_package(package_slug):
    normalized = re.sub(r"-\d{4}$", "", package_slug.lower())
    normalized = normalized.removeprefix("wwe-")
    return normalized in NON_PLE_PACKAGE_SLUGS or normalized.startswith(NON_PLE_PACKAGE_PREFIXES)


def links_to_onlocation_packages(soup, base_url):
    """Return unique WWE On Location PLE-package URLs from the listing."""
    found = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parts = urlsplit(url)
        if parts.netloc.lower() not in {"onlocationexp.com", "www.onlocationexp.com"}:
            continue
        url = parts._replace(query="", fragment="").geturl()
        path = parts.path.rstrip("/")
        match = re.fullmatch(r"/wwe/([a-z0-9-]+-tickets)", path, re.IGNORECASE)
        if not match:
            continue
        package_slug = match.group(1)[:-len("-tickets")].lower()
        if is_non_ple_package(package_slug):
            continue
        key = canonical_slug(package_slug)
        if not key:
            continue
        label = anchor.get_text(" ", strip=True)
        current = found.get(key)
        if current is None or len(label) > len(current[2]):
            found[key] = (package_slug, url, label)
    return found


def find_supplemental_links(packages):
    """Find matching WWE event pages and corporate releases for candidates."""
    supplemental = {key: [] for key in packages}

    try:
        response, soup = fetch(WWE_EVENTS_URL)
        for anchor in soup.find_all("a", href=True):
            url = urljoin(response.url, anchor["href"])
            path = urlsplit(url).path
            if not path.startswith("/event/"):
                continue
            key = canonical_slug(path.rsplit("/", 1)[-1])
            if key in supplemental:
                supplemental[key].append(("WWE Events", url))
    except requests.RequestException as exc:
        print(f"WARNING: WWE Events cross-check unavailable: {exc}")

    try:
        response, soup = fetch(CORPORATE_NEWS_URL)
        for anchor in soup.find_all("a", href=True):
            url = urljoin(response.url, anchor["href"])
            if "/about/news/" not in urlsplit(url).path:
                continue
            label = anchor.get_text(" ", strip=True)
            searchable = f"{label} {url}".lower()
            for key, (source_slug, _source_url, _label) in packages.items():
                terms = event_context_terms(source_slug)
                if terms and all(term.lower() in searchable for term in terms):
                    supplemental[key].append(("WWE Corporate News", url))
    except requests.RequestException as exc:
        print(f"WARNING: WWE Corporate News cross-check unavailable: {exc}")

    for key, sources in supplemental.items():
        unique = {}
        for name, url in sources:
            unique[url] = (name, url)
        supplemental[key] = list(unique.values())
    return supplemental


def title_for_event(key, package_slug, page_title, listing_label):
    label_date = re.search(
        rf"\b(?:{MONTH_PATTERN})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+20\d{{2}})?"
        rf"|\b(?:{MONTH_PATTERN})\.?\s+20\d{{2}}",
        listing_label,
        re.IGNORECASE,
    )
    label_title = listing_label[:label_date.start()] if label_date else listing_label
    candidates = (label_title, page_title, KNOWN_TITLES.get(key, ""), package_slug.replace("-", " "))
    for candidate in candidates:
        cleaned = re.sub(r"\s*[|–-]\s*On Location.*$", "", candidate, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:official\s+)?(?:ticket\s+)?packages?\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:tickets?|shop packages|more details)\b.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|:•")
        if not cleaned or cleaned.lower() in {"shop", "packages", "wwe"}:
            continue
        return cleaned if cleaned.lower().startswith("wwe ") else f"WWE {cleaned}"
    return f"WWE {key.replace('-', ' ').title()}"


def choose_full_event_details(text, event_key):
    """Find a full date | city | venue block immediately associated with this PLE."""
    matches = list(FULL_DATE_RE.finditer(text))
    if not matches:
        return None

    tokens = event_context_terms(event_key)
    event_positions = [
        match.end()
        for token in tokens
        for match in re.finditer(re.escape(token), text, re.IGNORECASE)
    ]
    scored = []
    for match in matches:
        start = max(0, match.start() - 160)
        preceding_context = text[start:match.start()].lower()
        score = sum(token.lower() in preceding_context for token in tokens)
        preceding_event_positions = [position for position in event_positions if position <= match.start()]
        distance = match.start() - max(preceding_event_positions, default=-10**9)
        if score == len(tokens) and 0 <= distance <= 35:
            scored.append((distance, match.start(), match))

    # Ignore unrelated dates elsewhere on the hospitality portal.
    if not scored:
        return None
    match = min(scored, key=lambda item: (item[0], item[1]))[2]
    try:
        event_date = datetime.strptime(match.group("date").replace(".", ""), "%B %d, %Y").date()
    except ValueError:
        try:
            event_date = datetime.strptime(match.group("date").replace(".", ""), "%b %d, %Y").date()
        except ValueError:
            return None
    city = re.sub(r"\s+", " ", match.group("city")).strip()
    venue = re.sub(r"\s+", " ", match.group("venue")).strip()
    venue = re.split(
        r"\s+(?:Ever Wanted|The stories|Closer than|Enjoy|Discover|WWE touches down|A limited)\b",
        venue,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,|-.")
    return {"date": event_date, "city": city, "venue": venue}


def extract_broadcast_time(text, event_key, event_year):
    """Return a time only when nearby source text ties it to this edition and ET broadcast."""
    tokens = event_context_terms(event_key)
    event_positions = [m.start() for token in tokens for m in re.finditer(re.escape(token), text, re.IGNORECASE)]
    if not event_positions:
        return None

    for match in ET_TIME_RE.finditer(text):
        start = max(0, match.start() - 220)
        end = min(len(text), match.end() + 120)
        context = text[start:end].lower()
        edition_context = text[max(0, match.start() - 1200):min(len(text), match.end() + 1200)]
        nearby_event = any(abs(position - match.start()) <= 700 for position in event_positions)
        matching_year = re.search(rf"\b{event_year}\b", edition_context)
        broadcast_word = re.search(r"broadcast|live|airs?|airing|on espn|peacock", context)
        if not nearby_event or not matching_year or not broadcast_word:
            continue

        hour = int(match.group("hour")) % 12
        if match.group("ampm").lower().startswith("p"):
            hour += 12
        minute = int(match.group("minute") or "0")
        return hour, minute
    return None


def parse_existing_start_time(existing):
    start = existing.get("start")
    return (start.hour, start.minute) if start else DEFAULT_BROADCAST_TIME


def venue_from_wwe_detail(text, city):
    """Use the WWE event page to trim the venue from its TIME AND LOCATION block."""
    marker = re.search(r"TIME AND LOCATION", text, re.IGNORECASE)
    if not marker:
        return None
    remainder = text[marker.end():marker.end() + 500]
    time_match = re.search(
        r"\b(?:0?[1-9]|1[0-2])(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?)\b",
        remainder,
        re.IGNORECASE,
    )
    if not time_match:
        return None
    after_time = remainder[time_match.end():]
    city_index = after_time.lower().find(city.lower())
    if city_index <= 0:
        return None
    venue = after_time[:city_index].strip(" ,|–-")
    venue = re.sub(r"\s+", " ", venue)
    venue = re.sub(r"^(?:doors? open|event starts?)\s*:?\s*", "", venue, flags=re.IGNORECASE)
    return venue or None


def event_uid(key, year, existing):
    if existing and existing.get("uid"):
        return existing["uid"]
    return f"wwe-{key}-{year}@wwe-ple-tracker"


def discover_events(output_path):
    """Discover PLEs from On Location and merge them with the existing ICS."""
    existing_events = read_existing_events(output_path)
    existing_by_key = {event["key"]: event for event in existing_events if event.get("key")}

    listing_response, listing_soup = fetch(ONLOCATION_URL)
    packages = links_to_onlocation_packages(listing_soup, listing_response.url)
    if not packages:
        raise RuntimeError("On Location returned no WWE ticket-package links; leaving the existing ICS unchanged.")

    print(f"Found {len(packages)} On Location WWE ticket-package links.")
    supplemental_links = find_supplemental_links(packages)
    discovered_by_key = {}
    parseable_count = 0
    unresolved_new_packages = []

    for key, (package_slug, package_url, listing_label) in packages.items():
        try:
            response, soup = fetch(package_url)
        except requests.RequestException as exc:
            print(f"WARNING: could not fetch {package_url}: {exc}")
            if key not in existing_by_key:
                unresolved_new_packages.append(package_slug)
            continue

        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
        old = existing_by_key.get(key)
        details = choose_full_event_details(text, package_slug)
        partial_date = MONTH_YEAR_RE.search(text) if not details else None
        if not details and not old:
            if partial_date:
                print(
                    f"WARNING: {package_slug} has only {partial_date.group('month')} "
                    f"{partial_date.group('year')}; not inventing an event day."
                )
            else:
                print(f"WARNING: no full event date found for {package_slug}; not adding it.")
            unresolved_new_packages.append(package_slug)
            continue

        if details:
            parseable_count += 1
            event_date = details["date"]
            city = details["city"]
            venue = details["venue"]
            location = f"{venue}, {city}" if city.lower() not in venue.lower() else venue
        else:
            # A partial date (e.g. month and year only) is not enough to invent a day.
            event_date = old["start"].date()
            location = old.get("location", "")
            print(f"Keeping last-known date/location for {package_slug}; source has no full date block.")

        supporting_sources = []
        supporting_pages = []
        for source_name, source_url in supplemental_links.get(key, []):
            try:
                _source_response, source_soup = fetch(source_url)
            except requests.RequestException as exc:
                print(f"WARNING: could not fetch {source_name} page {source_url}: {exc}")
                continue
            source_text = re.sub(r"\s+", " ", source_soup.get_text(" ", strip=True))
            supporting_sources.append((source_name, source_url))
            supporting_pages.append((source_name, source_url, source_text))

        # WWE's event detail page gives the venue and city in its TIME AND LOCATION
        # block. Use that to trim promotional copy following the On Location venue.
        if details:
            for source_name, _source_url, source_text in supporting_pages:
                if source_name == "WWE Events":
                    verified_venue = venue_from_wwe_detail(source_text, details["city"])
                    if verified_venue:
                        location = f"{verified_venue}, {details['city']}"
                        break

        time_sources = [text] + [source_text for _, _, source_text in supporting_pages]
        published_broadcast_time = next(
            (
                found
                for source_text in time_sources
                if (found := extract_broadcast_time(source_text, package_slug, event_date.year))
            ),
            None,
        )
        if published_broadcast_time is not None:
            broadcast_time = published_broadcast_time
            time_note = "Broadcast time explicitly identified in an official source as ET."
        elif old:
            broadcast_time = parse_existing_start_time(old)
            time_note = "Retained the previously recorded ET broadcast time; no new broadcast time was published."
        else:
            broadcast_time = DEFAULT_BROADCAST_TIME
            time_note = "Broadcast time not found in official sources; defaulted to 8:00 PM ET."

        start = datetime.combine(event_date, datetime.min.time(), tzinfo=ET).replace(
            hour=broadcast_time[0], minute=broadcast_time[1]
        )
        duration = DEFAULT_DURATION
        if old and old.get("start") and old.get("end"):
            previous_duration = old["end"] - old["start"]
            if timedelta(minutes=1) <= previous_duration <= timedelta(hours=12):
                duration = previous_duration
        end = start + duration

        uid = event_uid(key, event_date.year, old)
        summary = title_for_event(key, package_slug, page_title, listing_label)
        uid_year = re.search(r"-(\d{4})@", uid)
        edition_year = uid_year.group(1) if uid_year else str(event_date.year)
        if edition_year not in summary:
            summary = f"{summary} {edition_year}"

        if old and not published_broadcast_time and old.get("description"):
            old_description = old["description"]
            description_parts = [old_description]
            if package_url not in old_description:
                description_parts.append(f"On Location: {package_url}")
            for source_name, source_url in supporting_sources:
                if source_url not in old_description:
                    description_parts.append(f"{source_name}: {source_url}")
            if "previously recorded ET broadcast time" not in old_description.lower():
                description_parts.append(time_note)
        else:
            description_parts = ["WWE PLE home-viewing schedule.", f"On Location: {package_url}", time_note]
            description_parts.extend(f"{source_name}: {source_url}" for source_name, source_url in supporting_sources)

        discovered_by_key[key] = {
            "uid": uid,
            "key": key,
            "summary": summary,
            "start": start,
            "end": end,
            "location": location,
            "description": " ".join(description_parts),
        }
        print(f"Accepted {summary}: {event_date.isoformat()} {broadcast_time[0]:02d}:{broadcast_time[1]:02d} ET; {location}")

    if parseable_count == 0:
        raise RuntimeError("No complete event dates were parsed; leaving the existing ICS unchanged.")
    if unresolved_new_packages:
        names = ", ".join(sorted(set(unresolved_new_packages)))
        raise RuntimeError(
            f"New On Location packages lack retrievable full event dates ({names}); "
            "leaving the existing ICS unchanged."
        )

    # Keep prior future entries when a listing temporarily omits a package or only
    # provides a partial date. Matching entries above update in place by stable UID.
    merged = dict(discovered_by_key)
    now_et = datetime.now(ET)
    for old in existing_events:
        if old.get("end") and old["end"] < now_et:
            continue
        if old.get("key") not in merged:
            merged[old.get("key") or old["uid"]] = old

    future_events = [
        event for event in merged.values()
        if event.get("end") and event["end"] >= now_et
    ]
    if not future_events:
        raise RuntimeError("No future PLE events remain; leaving the existing ICS unchanged.")

    # Enforce UID uniqueness even if two source aliases resolve to the same event.
    unique_by_uid = {event["uid"]: event for event in future_events}
    return sorted(unique_by_uid.values(), key=lambda event: event["start"])


def format_ics_datetime(value):
    return value.astimezone(ET).strftime("%Y%m%dT%H%M%S")


def generate_ics_content(events):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WWE PLE Home Viewing Schedule//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-TIMEZONE:America/New_York",
    ]
    for event in events:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event['uid']}",
                f"SUMMARY:{clean_ics_text(event['summary'])}",
                f"DTSTART;TZID=America/New_York:{format_ics_datetime(event['start'])}",
                f"DTEND;TZID=America/New_York:{format_ics_datetime(event['end'])}",
                f"LOCATION:{clean_ics_text(event.get('location', ''))}",
                f"DESCRIPTION:{clean_ics_text(event.get('description', ''))}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def write_atomically(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as temp:
        temp.write(content)
        temp_path = Path(temp.name)
    os.replace(temp_path, path)


def main():
    output_path = Path(__file__).resolve().with_name("wwe_ple_schedule.ics")
    events = discover_events(output_path)
    content = generate_ics_content(events)
    write_atomically(output_path, content)
    print(f"Successfully generated {output_path} with {len(events)} future PLE events.")


if __name__ == "__main__":
    main()
