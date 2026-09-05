#!/usr/bin/env python3
"""Dirigo Net weekly stats reporter.
Pulls NEDECN reports and posts to Slack webhook.
Retries at 9:00, 9:30, 9:45, 10:00, 10:30 AM EDT (13:00, 13:30, 13:45, 14:00, 14:30 UTC).
Posts partial results if one or two reports aren't ready.
"""
import json, os, sys, time, urllib.request, urllib.parse, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

WEBHOOK = os.environ.get('DIRIGO_SLACK_WEBHOOK','')
if not WEBHOOK:
    print("Missing DIRIGO_SLACK_WEBHOOK env var")
    sys.exit(1)

# Check times in UTC (9:00, 9:30, 9:45, 10:00, 10:30 AM EDT)
CHECK_TIMES = [13*3600, 13*3600+30*60, 13*3600+45*60, 13*3600+50*60, 13*3600+55*60]  # seconds since midnight UTC (9:00, 9:30, 9:45, 9:50, 9:55 AM EDT)
REPORT_URLS = {
    'callsign': 'https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-CALLSIGN.html',
    'talkgroup': 'https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-TALKGROUP.html',
    'repeater': 'https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-REPEATER.html',
}

def now_utc():
    return datetime.now(timezone.utc)

def wait_until_next_check(now):
    today_checks = [now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                    for _ in CHECK_TIMES]
    today_checks = [t + __import__('datetime').timedelta(seconds=s) for t, s in zip(today_checks, CHECK_TIMES)]
    future = [t for t in today_checks if t > now]
    if not future:
        return None  # all checks passed today
    delay = (future[0] - now).total_seconds()
    return delay

def fetch_page(url):
    req = urllib.request.urlopen(url, timeout=30)
    return req.read().decode()

def extract_date_range(text):
    m = re.search(r'from (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})', text)
    if m:
        return m.group(1), m.group(2)
    return None, None

def qrz_lookup(callsigns):
    """Look up state for a list of call signs using QRZ XML API."""
    user = os.environ.get('QRZ_USERNAME','')
    passwd = os.environ.get('QRZ_APIKEY','')
    if not user or not passwd:
        return {}
    
    base = "https://xmldata.qrz.com/xml/current/"
    url = f"{base}?username={urllib.parse.quote(user)};password={urllib.parse.quote(passwd)};agent=qrzpy1.0"
    try:
        req = urllib.request.urlopen(url, timeout=30)
        root = ET.fromstring(req.read().decode())
        key_el = root.find('.//{http://xmldata.qrz.com}Key')
        if key_el is None or not key_el.text:
            return {}
        skey = key_el.text
        
        results = {}
        for call in callsigns:
            try:
                u = f"{base}?s={urllib.parse.quote(skey)};callsign={urllib.parse.quote(call)}"
                r = urllib.request.urlopen(u, timeout=30)
                root = ET.fromstring(r.read().decode())
                c = root.find('{http://xmldata.qrz.com}Callsign')
                if c is not None:
                    state_el = c.find('{http://xmldata.qrz.com}state')
                    state = state_el.text.strip() if state_el is not None and state_el.text else ''
                    results[call] = {'state': state}
            except:
                results[call] = {}
        return results
    except:
        return {}

def build_report():
    pages = {}
    for key, url in REPORT_URLS.items():
        try:
            pages[key] = fetch_page(url)
        except Exception as e:
            pages[key] = None
            print(f"Warning: failed to fetch {key}: {e}", file=sys.stderr)
    
    # Extract dates per page
    page_info = {}
    today = now_utc().date()
    days_since_saturday = (today.weekday() + 2) % 7  # Saturday=5; gives 0 on Saturday, else days since
    last_saturday = today - __import__('datetime').timedelta(days=days_since_saturday if days_since_saturday else 7)
    last_saturday_str = last_saturday.strftime('%Y-%m-%d')
    
    for key, text in pages.items():
        if text:
            s, e = extract_date_range(text)
            page_info[key] = {
                'text': text,
                'start': s,
                'end': e,
                'current': (e == last_saturday_str) if e else False,
            }
        else:
            page_info[key] = {
                'text': '',
                'start': None,
                'end': None,
                'current': False,
            }
    
    def section_note(key):
        info = page_info.get(key, {})
        if not info.get('current'):
            date_str = f"{info.get('start','?')} to {info.get('end','?')}" if info.get('start') else "unknown"
            return f" (Report not current — {date_str})"
        return ""
    
    # Parse callsign report
    me_callsigns = []
    cs_info = page_info.get('callsign', {})
    cs_text = cs_info.get('text', '')
    if cs_text:
        rows = re.findall(r'<tr[^>]*>.*?</tr>', cs_text, re.DOTALL)
        top10_callsigns = []
        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            tds = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
            if len(tds) >= 6:
                try:
                    rank = int(tds[0])
                    if rank > 10:
                        continue
                    call = tds[1]
                    top10_callsigns.append((rank, call))
                except:
                    pass
        
        if top10_callsigns:
            me_call_list = [c[1] for c in top10_callsigns]
            qrz_results = qrz_lookup(me_call_list)
            for rank, call in top10_callsigns:
                qrz = qrz_results.get(call, {})
                if qrz.get('state') == 'ME':
                    me_callsigns.append((call, rank))
    
    # Parse talkgroup report
    maine_rank = None
    above_tgs = []
    tg_info = page_info.get('talkgroup', {})
    tg_text = tg_info.get('text', '')
    tg_end_date = tg_info.get('end', last_saturday_str)
    if tg_text:
        rows = re.findall(r'<tr[^>]*>.*?</tr>', tg_text, re.DOTALL)
        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            tds = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
            if len(tds) >= 2:
                try:
                    rank = int(tds[0])
                    tg_id = tds[1]
                    if tg_id == '3123':
                        maine_rank = rank
                    elif maine_rank is None:
                        above_tgs.append(tg_id)
                except:
                    pass
    
    # Parse repeater report
    me_repeaters = []
    rpt_info = page_info.get('repeater', {})
    rpt_text = rpt_info.get('text', '')
    if rpt_text:
        rows = re.findall(r'<tr[^>]*>.*?</tr>', rpt_text, re.DOTALL)
        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            tds = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
            if len(tds) >= 7:
                try:
                    rank = int(tds[0])
                    if rank > 10:
                        continue
                    location = tds[6]
                    if location == 'ME' or location.endswith(' ME'):
                        me_repeaters.append((tds[5], rank))
                except:
                    pass
    
    # Build markdown
    def ordinal(n):
        if 11 <= n % 100 <= 13:
            return f"{n}th"
        return {1:"1st",2:"2nd",3:"3rd"}.get(n%10, f"{n}th")
    
    # Use the most recent ending date across all reports for the intro
    end_dates = [info.get('end') for info in page_info.values() if info.get('end')]
    week_ending = max(end_dates) if end_dates else last_saturday_str
    
    md = f"# ME Statistics\nThese statistics are relevant to week ending {week_ending}\n\n"
    
    cs_note = section_note('callsign')
    md += f"## Callsign Report{cs_note}\n[How many Maine hams in top ten](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-CALLSIGN.html)\n"
    if cs_info.get('current'):
        if me_callsigns:
            md += f"{len(me_callsigns)} Maine operators in the Top 10\n"
        else:
            md += "(No Maine operators in top 10 this week)\n"
    else:
        md += "(Data not yet available for this week)\n"
    
    tg_note = section_note('talkgroup')
    md += f"\n## Talkgroup Report{tg_note}\n[Maine Statewide talkgroup's usage ratio](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-TALKGROUP.html)\n"
    if tg_info.get('current'):
        if maine_rank:
            # Find Maine seconds and next highest NE state seconds
            maine_secs = 0
            next_state_secs = 0
            next_state_name = ""
            # State talkgroups to consider (excluding TAC and non-state)
            state_tgs = {
                '3123': 'Maine',
                '3150': 'Vermont',
                '3133': 'New Hampshire',
                '3125': 'Massachusetts',
                '3124': 'Maryland',
                # Add others as needed
            }
            tg_seconds = {}
            tg_rows = re.findall(r'<tr[^>]*>.*?</tr>', tg_text, re.DOTALL)
            for row in tg_rows:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                tds = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
                if len(tds) >= 4:
                    try:
                        tg_id = tds[1]
                        secs = int(tds[3]) if tds[3].isdigit() else 0
                        if tg_id in state_tgs:
                            tg_seconds[state_tgs[tg_id]] = secs
                    except:
                        pass
            
            maine_secs = tg_seconds.get('Maine', 0)
            # Find next highest (excluding Maine)
            other_secs = {k: v for k, v in tg_seconds.items() if k != 'Maine' and v > 0}
            if other_secs:
                next_state_name = max(other_secs, key=other_secs.get)
                next_state_secs = other_secs[next_state_name]
            
            if maine_secs > 0 and next_state_secs > 0:
                ratio = maine_secs / next_state_secs
                md += f"Maine Statewide is {ratio:.1f}x busier than the next statewide talk group, {next_state_name}\n"
            elif maine_secs > 0:
                md += f"Maine Statewide had {maine_secs:,} seconds with no comparable statewide talkgroup activity\n"
            else:
                md += "(Maine Statewide talk group not found in top 10 this week)\n"
        else:
            md += "(Maine Statewide talk group not found in top 10 this week)\n"
    else:
        md += "(Data not yet available for this week)\n"
    
    rpt_note = section_note('repeater')
    md += f"\n## Repeater Report{rpt_note}\n[How many Maine repeaters in top ten](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-REPEATER.html)\n"
    if rpt_info.get('current'):
        if me_repeaters:
            md += f"{len(me_repeaters)} Maine repeaters in the top 10\n"
        else:
            md += "(No Maine repeaters in top 10 this week)\n"
    else:
        md += "(Data not yet available for this week)\n"
    
    all_current = all(page_info.get(k, {}).get('current', False) for k in REPORT_URLS)
    return md, all_current

def post_to_slack(md):
    payload = {"text": md}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(WEBHOOK, data=data, headers={'Content-Type':'application/json'})
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.status, resp.read().decode()

def main():
    print(f"Starting Dirigo Net report job at {now_utc().isoformat()}")
    
    # Build the report right away (current data may already be live)
    report, all_current = build_report()
    if all_current:
        print("Report ready on first attempt.")
    else:
        print("Initial build: some data not ready or incomplete. Entering retry window.")
        # Enter retry loop
        while True:
            now = now_utc()
            delay = wait_until_next_check(now)
            if delay is None:
                print("All check windows passed. Posting best available report.")
                break
            print(f"Waiting {delay:.0f}s until next check at {(now + __import__('datetime').timedelta(seconds=delay)).isoformat()}")
            time.sleep(delay)
            report, all_current = build_report()
            if all_current:
                print("Report ready. Posting.")
                break
            print(f"Check at {now_utc().isoformat()}: still not ready.")
    
    status, body = post_to_slack(report)
    print(f"Posted to Slack: {status} {body}")
    print("=== REPORT ===")
    print(report)

if __name__ == '__main__':
    main()
