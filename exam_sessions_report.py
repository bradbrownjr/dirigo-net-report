#!/usr/bin/env python3
"""ARRL Exam Session weekly stats reporter.
Fetches ARRL exam sessions for ME and NH from arrl.org and posts to Slack webhook.
"""
import json, os, sys, re, html as html_mod, urllib.request, urllib.parse
from datetime import datetime, timezone

WEBHOOK = os.environ.get('DIRIGO_SLACK_WEBHOOK','')
if not WEBHOOK:
    print("Missing DIRIGO_SLACK_WEBHOOK env var")
    sys.exit(1)

SEARCH_URL = "https://www.arrl.org/find-an-amateur-radio-license-exam-session"
BASE_URL = "https://www.arrl.org"

def fetch_page(url, post_data=None):
    if post_data:
        data = urllib.parse.urlencode(post_data).encode()
        req = urllib.request.Request(url, data=data, method='POST', headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
    else:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read().decode()

def html_unescape_email(text):
    """Decode HTML entities in email addresses."""
    return html_mod.unescape(text)

def parse_detail_page(detail_html):
    """Extract contact info, location, time, sponsor from a detail page."""
    result = {}
    
    # Extract date - format: "EXAM SESSION</p> ... <span>09/05/2026</span>"
    date_match = re.search(r'EXAM SESSION.*?<span>(\d{1,2}/\d{1,2}/\d{4})</span>', detail_html)
    result['date'] = date_match.group(1) if date_match else ''
    
    # Extract time - format: "Time: 9:00 AM"
    time_match = re.search(r'Time:</strong>\s*(\d{1,2}:\d{2}\s*(?:AM|PM))', detail_html)
    result['time'] = time_match.group(1) if time_match else ''
    
    # Extract sponsor - format: "Sponsor:</strong> Concord ARES"
    sponsor_match = re.search(r'Sponsor:</strong>\s*(.*?)(?:Date:|<br)', detail_html, re.DOTALL)
    result['sponsor'] = re.sub(r'<[^>]+>', '', sponsor_match.group(1)).strip() if sponsor_match else ''
    result['sponsor'] = re.sub(r'\s+', ' ', result['sponsor'])
    
    # Extract location/venue - format: "Location:</strong> Bektash Shrine"
    loc_match = re.search(r'Location:</strong>\s*(.*?)(?:Time:|<br|Candidates|Registration|Accepting|Website)', detail_html, re.DOTALL)
    result['venue'] = re.sub(r'<[^>]+>', '', loc_match.group(1)).strip() if loc_match else ''
    result['venue'] = re.sub(r'\s+', ' ', result['venue'])
    
    # Extract contact name - format: "Contact:</strong> John H. Moore"
    contact_match = re.search(r'Contact:</strong>\s*(.*?)(?:Email:|Phone:|<br)', detail_html, re.DOTALL)
    result['contact'] = re.sub(r'<[^>]+>', '', contact_match.group(1)).strip() if contact_match else ''
    result['contact'] = re.sub(r'\s+', ' ', result['contact'])
    
    # Extract phone - format: "(603) 496-4482"
    phone_match = re.search(r'(\(\d{3}\)\s*\d{3}-\d{4})', detail_html)
    result['phone'] = phone_match.group(1) if phone_match else ''
    
    # Extract email (may be HTML-entity encoded)
    email_match = re.search(r'Email:\s*(.*?)(?:VEC:|<br|Website)', detail_html, re.DOTALL)
    if email_match:
        email_raw = email_match.group(1)
        email_clean = re.sub(r'<[^>]+>', '', email_raw).strip()
        result['email'] = html_unescape_email(email_clean)
    else:
        result['email'] = ''
    
    # Extract note (Walk-ins allowed / Registration Required / No Walk-ins)
    note = ''
    if 'Walk-ins allowed' in detail_html:
        note = 'Walk-ins allowed'
    elif 'Registration Required' in detail_html:
        note = 'Registration Required'
    elif 'pre-registration is required' in detail_html:
        note = 'Registration Required'
    elif 'No Walk-ins' in detail_html:
        note = 'Registration Required'
    result['note'] = note
    
    # Extract location name from the <h2> or title
    loc_name_match = re.search(r'<h2>\s*(.*?)\s*</h2>', detail_html, re.DOTALL)
    if loc_name_match:
        result['location_name'] = re.sub(r'<[^>]+>', '', loc_name_match.group(1)).strip()
    else:
        result['location_name'] = ''
    
    return result

def parse_search_results(html):
    """Extract session hrefs and location names from search results page."""
    sessions = []
    
    # Find all <li> blocks containing exam session links
    li_blocks = re.findall(r'<li>(.*?)</li>', html, re.DOTALL)
    
    seen_hrefs = set()
    
    for block in li_blocks:
        if 'exam_sessions/' not in block:
            continue
        
        # Extract the primary link and location text
        link_match = re.search(r'<a\s+href="(/exam_sessions/[^"]+)"[^>]*>([^<]+)</a>', block)
        if not link_match:
            link_match = re.search(r'<a\s+href="(/exam_sessions/[^"]+)"[^>]*>\s*<strong>([^<]+)</strong>\s*</a>', block)
            if link_match:
                href = link_match.group(1)
                location = link_match.group(2).strip()
            else:
                continue
        else:
            href = link_match.group(1)
            location = link_match.group(2).strip()
        
        if href in seen_hrefs:
            continue
        
        full_url = BASE_URL + href
        seen_hrefs.add(href)
        # Strip ZIP codes from location name: 'Windsor ME 04363' -> 'Windsor ME'
        location = __import__('re').sub(r'\s+\d{5}(?:-\d{4})?$', '', location)
        
        sessions.append({
            'href': full_url,
            'location_name': location,
        })
    
    return sessions

def format_line(s):
    """Format a single session line."""
    date = s.get('date','')
    location_name = s.get('location_name','')
    detail_href = s.get('href','')
    time_str = s.get('time','')
    venue = s.get('venue','')
    contact = s.get('contact','')
    email = s.get('email','')
    note = s.get('note','')
    sponsor = s.get('sponsor','')
    
    # Build link text
    link_text = location_name
    if sponsor and 'hamfest' in sponsor.lower():
        link_text = link_text.rstrip(' (hamfest)')
        link_text += ' (hamfest)'
    
    # Build display text inside link
    parts = [link_text]
    if not note:
        note = '(check details)'
    
    # Build the line: date | [Location](href) time at the Venue (note), contact Name at email
    line = f"- {date} | [{link_text}]({detail_href}) {time_str}"
    if venue:
        line += f" at the {venue}"
    line += f" ({note})"
    if contact and email:
        line += f", contact {contact} at {email}"
    elif contact:
        line += f", contact {contact}"
    elif email:
        line += f", contact at {email}"
    
    return line

def build_report():
    states = {'ME': 'Maine', 'NH': 'New Hampshire'}
    report_by_state = {}
    
    for state_code, state_name in states.items():
        post_data = {
            '_method': 'POST',
            'data[Search][category]': 'exam_sessions',
            'data[Location][state]': state_code,
            'data[Location][area]': '250',
        }
        html = fetch_page(SEARCH_URL, post_data)
        sessions = parse_search_results(html)
        print(f"{state_name}: found {len(sessions)} sessions in search results")
        
        # Fetch each detail page for contact info
        detailed_sessions = []
        for s in sessions:
            try:
                detail_html = fetch_page(s['href'])
                detail = parse_detail_page(detail_html)
                # Merge search result info with detail page info
                detail['href'] = s['href']
                detail['location_name'] = s['location_name']
                # Use location_name from detail page if available, else from search
                if not detail.get('location_name'):
                    detail['location_name'] = s['location_name']
                detailed_sessions.append(detail)
                print(f"  - {detail.get('date','?')} | {detail.get('location_name','?')} | venue={detail.get('venue','')[:40]} | contact={detail.get('contact','')[:30]}")
            except Exception as e:
                print(f"  Warning: failed to fetch detail for {s['href']}: {e}")
                # Fall back to search result data
                s['note'] = ''
                s['time'] = ''
                s['venue'] = ''
                s['contact'] = ''
                s['email'] = ''
                s['sponsor'] = ''
                s['date'] = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', '')
                detailed_sessions.append(s)
        
        report_by_state[state_name] = detailed_sessions
    
    # Build markdown
    md = "# Exam Sessions\n\n"
    
    for state_name in ['Maine', 'New Hampshire']:
        sessions = report_by_state.get(state_name, [])
        if not sessions:
            continue
        md += f"{state_name}\n"
        for s in sessions:
            md += format_line(s) + "\n"
        md += "\n"
    
    return md.strip()

def post_to_slack(md):
    payload = {"text": md}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(WEBHOOK, data=data, headers={'Content-Type':'application/json'})
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.status, resp.read().decode()

def main():
    print(f"Starting Exam Sessions report job at {datetime.now(timezone.utc).isoformat()}")
    report = build_report()
    status, body = post_to_slack(report)
    print(f"Posted to Slack: {status} {body}")
    print("=== REPORT ===")
    print(report)

if __name__ == '__main__':
    main()