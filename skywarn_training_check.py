#!/usr/bin/env python3
"""SKYWARN storm spotter training session watcher.

Fetches the NWS Gray (GYX) SKYWARN page, extracts currently scheduled
training sessions from the HTML tables, deduplicates against previously
seen sessions (stored in a state file), and posts new sessions to the
Slack webhook.

Usage:
    Set DIRIGO_SLACK_WEBHOOK env var to your Slack incoming webhook URL.
    Run as a weekly cron job (Sunday morning) to catch newly added sessions.
"""
import json, os, re, sys, urllib.request
from datetime import date, datetime

URL = "https://www.weather.gov/gyx/skywarn"
WEBHOOK = os.environ.get('DIRIGO_SLACK_WEBHOOK', '')
STATE_FILE = os.environ.get('SKYWARN_STATE_FILE',
    os.path.expanduser('~/.hermes/skills/ham-radio/skywarn-training/sessions_seen.json'))

# Ensure the skills directory exists for state storage
skill_dir = os.path.dirname(STATE_FILE)
os.makedirs(skill_dir, exist_ok=True)

# Month name to number mapping
MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12,
}

# Current page info (updated at runtime)
PAGE_YEAR = None
PAGE_SEASON = None


def fetch_page(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    })
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read().decode('utf-8', errors='replace')


def clean_html(text):
    """Strip HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('\xa0', ' ')
    text = text.replace('&gt;', '>')
    text = text.replace('&lt;', '<')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_page_header(html):
    """Extract the year and season from the page header.

    Looks for HTML like:
      Currently Scheduled 2026&nbsp;Training Sessions</strong> - Spring Training Schedule

    Returns (year, season) tuple or (None, None) if not found.
    """
    global PAGE_YEAR, PAGE_SEASON

    # Try to find the full header including season
    # The HTML may have tags breaking up the text, e.g.:
    #   Currently Scheduled 2026&nbsp;Training Sessions</strong> - Spring Training Schedule</h2>
    header_pattern = re.search(
        r'Currently Scheduled\s*(\d{4})\s*[^<]*Training Sessions[^<]*</[^>]*>\s*-\s*([A-Za-z]+)\s+Training Schedule',
        html, re.IGNORECASE | re.DOTALL
    )
    if header_pattern:
        year = int(header_pattern.group(1))
        season = header_pattern.group(2).capitalize()
        PAGE_YEAR = year
        PAGE_SEASON = season
        return year, season

    # Fallback: extract just the year
    year_pattern = re.search(r'Currently Scheduled\s*(\d{4})', html, re.IGNORECASE)
    if year_pattern:
        year = int(year_pattern.group(1))
        PAGE_YEAR = year
        return year, None

    return None, None


def parse_date(date_str, default_year):
    """Parse a date string like 'May 11th' using the given default year.

    Uses manual month lookup instead of strptime to avoid ambiguity
    warnings on year-less dates in Python 3.15+.

    Returns a datetime.date or None if parsing fails.
    """
    if not date_str:
        return None

    # Normalize: strip ordinal suffixes (st, nd, rd, th)
    cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned.strip())

    # Try "Month Day" pattern (e.g., "May 11", "Sep 5")
    match = re.match(r'^([A-Za-z]+)\s+(\d+)$', cleaned)
    if match:
        month_str = match.group(1).lower()
        day = int(match.group(2))
        month = MONTHS.get(month_str)
        if month:
            return date(default_year, month, day)

    # Try "Month Day, Year" pattern (e.g., "May 11, 2026")
    match = re.match(r'^([A-Za-z]+)\s+(\d+),\s*(\d{4})$', cleaned)
    if match:
        month_str = match.group(1).lower()
        day = int(match.group(2))
        year = int(match.group(3))
        month = MONTHS.get(month_str)
        if month:
            return date(year, month, day)

    return None


def is_upcoming(date_str, default_year):
    """Check if a session date is upcoming (today or in the future).

    Returns True, False, or None (if date can't be parsed).
    """
    session_date = parse_date(date_str, default_year)
    if session_date is None:
        return None

    today = datetime.now().date()
    return session_date >= today


def extract_session_tables(html):
    """Extract training session tables from the SKYWARN page.

    The page has tables with training sessions. Each session row has 6 cells:
    County, City, Date, Time, Location, Registration.
    Section header rows (like 'Severe SKYWARN Weather Spotter (Basic)')
    span all columns via colspan='6'.
    """
    tables = re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL | re.IGNORECASE)

    sessions = []
    current_section = "Training Session"

    for table_html in tables:
        if 'County' not in table_html and 'Registration' not in table_html:
            continue

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)

        for row_html in rows:
            # Check for section header (colspan='6')
            section_match = re.search(
                r'<th[^>]*colspan=["\']6["\'][^>]*>(.*?)</th>',
                row_html, re.DOTALL | re.IGNORECASE
            )
            if section_match:
                section_text = clean_html(section_match.group(1))
                if section_text:
                    current_section = section_text
                continue

            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL | re.IGNORECASE)

            if len(cells) < 6:
                continue

            clean_cells = [clean_html(cell) for cell in cells]

            if not any(c.strip() for c in clean_cells):
                continue

            if clean_cells[0].lower().startswith('county'):
                continue

            county = clean_cells[0]
            city = clean_cells[1]
            date_str = clean_cells[2]
            time_str = clean_cells[3]
            location = clean_cells[4]
            registration = clean_cells[5]

            if not county:
                county = 'Virtual'
            if not city:
                city = 'Virtual'

            reg_link = ''
            link_match = re.search(r'href=["\']([^"\']+)["\']', cells[5])
            if link_match:
                reg_link = link_match.group(1)

            session = {
                'section': current_section,
                'county': county,
                'city': city,
                'date': date_str,
                'time': time_str,
                'location': location,
                'registration': registration,
                'reg_link': reg_link,
            }
            sessions.append(session)

    return sessions


def load_seen():
    """Load previously seen session IDs from state file."""
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen_ids):
    """Save seen session IDs to state file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(sorted(seen_ids), f, indent=2)


def session_id(session):
    """Generate a unique ID for a session."""
    return f"{session['section']}|{session['date']}|{session['time']}|{session['location']}"


def format_session_line(s, year=None):
    """Format a session as a Slack-friendly line."""
    parts = [f"**{s['section']}**"]

    # Include year if available for clarity
    date_display = s['date']
    if date_display and year:
        date_display = f"{date_display} ({year})"

    if date_display:
        parts.append(date_display)
    if s['time']:
        parts.append(s['time'])
    if s['location']:
        parts.append(s['location'])

    line = f"- {' | '.join(parts)}"

    if s['reg_link']:
        line += f" | <{s['reg_link']}|Register>"
    elif s['registration']:
        line += f" | {s['registration']}"

    return line


def post_to_slack(text):
    """Post a message to the Slack webhook."""
    payload = {"text": text}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(WEBHOOK, data=data, headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.status, resp.read().decode()


def main():
    if not WEBHOOK:
        print("Missing DIRIGO_SLACK_WEBHOOK env var")
        sys.exit(1)

    now = datetime.now()
    print(f"Starting SKYWARN training check at {now.isoformat()}")

    # Fetch the page
    try:
        html = fetch_page(URL)
        print(f"Fetched {len(html)} chars from {URL}")
    except Exception as e:
        print(f"Failed to fetch page: {e}")
        sys.exit(1)

    # Extract year and season from the page header
    year, season = extract_page_header(html)
    if year:
        season_str = season if season else "Unknown season"
        print(f"Page header: {year} {season_str} Training Sessions")
    else:
        year = now.year  # Fallback to current year
        print("Warning: Could not extract year from page header, using current year")

    # Extract sessions
    sessions = extract_session_tables(html)
    print(f"Found {len(sessions)} training sessions")

    # Classify sessions as upcoming or past
    upcoming_ids = []
    past_ids = []
    unknown_ids = []
    for s in sessions:
        upcoming = is_upcoming(s['date'], year)
        sid = session_id(s)
        if upcoming is True:
            upcoming_ids.append(sid)
        elif upcoming is False:
            past_ids.append(sid)
        else:
            unknown_ids.append(sid)

    upcoming_count = len(upcoming_ids)
    past_count = len(past_ids)
    print(f"Upcoming: {upcoming_count}, Past: {past_count}, Unknown: {len(unknown_ids)}")

    # Check against previously seen
    seen = load_seen()
    new_sessions = []
    new_upcoming = []

    for s in sessions:
        sid = session_id(s)
        if sid not in seen:
            new_sessions.append(s)
            seen.add(sid)
            # Check if this new session is upcoming
            upcoming = is_upcoming(s['date'], year)
            if upcoming is True:
                new_upcoming.append(s)
            elif upcoming is None:
                # If we can't determine, treat new sessions as worth reporting
                new_upcoming.append(s)

    if new_sessions:
        print(f"Found {len(new_sessions)} new sessions (since last check)")

        if new_upcoming:
            # We have new sessions that are upcoming — post to Slack
            season_header = f" {season}" if season else ""
            md = f"# SKYWARN Training Sessions - Newly Scheduled ({year}{season_header})\n\n"
            md += f"Fetched from {URL} at {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            for s in new_upcoming:
                md += format_session_line(s, year) + "\n"

            # Summary counts
            md += f"\nTotal sessions currently listed: {len(sessions)} ({upcoming_count} upcoming, {past_count} past)"

            status, body = post_to_slack(md)
            print(f"Posted to Slack: {status} {body}")
        else:
            # All new sessions are past — just log, no Slack notification
            print("All new sessions are in the past — not posting to Slack")
    else:
        print("No new sessions since last check")

    # Always save updated state
    save_seen(seen)
    print(f"State saved to {STATE_FILE}")


if __name__ == '__main__':
    main()
