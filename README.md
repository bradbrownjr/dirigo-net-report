# Dirigo Net Weekly Report

Pulls the three NEDECN weekly reports and posts Maine-specific statistics to Slack for the Maine Dirigo Net announcements.

Privacy-first design: the report shows **counts only** — no individual callsigns, names, or repeater locations — so net control can read it on the air without identifying individuals.

## What it reports

- **Callsign Report** — number of Maine operators in the overall top 10
- **Talkgroup Report** — Maine Statewide (3123) usage compared to the next busiest NEDECN state talkgroup, expressed as a ratio (e.g. `5.6x`)
- **Repeater Report** — number of Maine repeaters in the overall top 10, plus an offline check (below) for specifically watched repeaters

If a report is a week or more behind, the section is marked `(Report not current)` and shows no data rather than stale numbers.

### Offline repeater check

The Repeater Report also checks the NEDECN C-Bridge [PeerWatch](http://cb.nedecn.org:42420/PeerWatchFrame) live-status feeds (Augusta, Bass Hill, and Boston) for a small watchlist of specific repeaters. Each PeerWatch port shows the linked repeater's callsign/location/RadioID only while it's actually connected — if that field is missing, the repeater is currently offline. This adds one line to the Repeater Report:

- `Offline: K1DQ Shapleigh` — if any watched repeater is found with no repeater linked
- `All watched repeaters online` — if every watched repeater was found and linked
- `Could not verify: K1DQ Shapleigh` — if a watched repeater was never found on any of the three feeds, or none of the feeds could be fetched at all

This is an intentional exception to the counts-only privacy design above — a named repeater's online/offline status is infrastructure information, not personal information about an operator.

## Prerequisites

- Python 3.9+
- A Slack webhook URL (`DIRIGO_SLACK_WEBHOOK`)
- A QRZ.com XML subscription (`QRZ_USERNAME` / `QRZ_APIKEY`) — required for the Callsign Report; without it, that section is reported as unavailable rather than a false zero

## Installation

```bash
git clone https://github.com/bradbrownjr/dirigo-net-report.git
cd dirigo-net-report
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt  # if present; stdlib-only otherwise
```

No external dependencies — the script uses only the standard library.

## Configuration

All configuration is via environment variables.

### Required

| Variable | Description |
|---|---|
| `DIRIGO_SLACK_WEBHOOK` | Incoming webhook URL for your Slack channel |

### Optional but recommended

| Variable | Description |
|---|---|
| `QRZ_USERNAME` / `QRZ_APIKEY` | QRZ.com XML API credentials, used to resolve each top-10 callsign's state. Without these set, the Callsign Report section prints "(QRZ lookup not configured...)" instead of a count — it does **not** silently report zero. |

### Optional

| Variable | Default | Description |
|---|---|---|
| `DIRIGO_CHECK_TIMES` | `[32400, 34200, 35100, 36000, 39300]` | Retry times in seconds since midnight, **America/New_York local time** (DST-aware — the same values apply whether EDT or EST is in effect). Default: 9:00, 9:30, 9:45, 10:00, 10:55 AM Eastern. Override to match your net schedule, e.g. `[32400, 36000]` for just 9:00 and 10:00 AM Eastern. |
| `DIRIGO_STATE_TGS` | `{"3123":"Maine","3150":"Vermont","3133":"New Hampshire","3125":"Massachusetts","3109":"Connecticut","3144":"Rhode Island","3136":"New York"}` | JSON map of talkgroup IDs to state names for the ratio comparison. NEDECN state talkgroup IDs follow the pattern `31` + state FIPS code. Add or remove states to match the NEDECN repeaters in your region. |
| `DIRIGO_REPEATER_WATCHLIST` | `{"K1DQ Shapleigh":"Shapleigh"}` | JSON map of display name → substring to match against each PeerWatch port's site label. Add more entries to watch additional repeaters for offline status. |

### Examples

```bash
# Set webhook
export DIRIGO_SLACK_WEBHOOK='https://hooks.slack.com/services/T00/B00/xxxx'

# QRZ credentials for the Callsign Report
export QRZ_USERNAME='yourcall'
export QRZ_APIKEY='your-qrz-xml-password'

# Override check times for a 10:00 AM net (Eastern time, DST-aware)
export DIRIGO_CHECK_TIMES='[36000]'

# Talkgroup comparison set (New England defaults shown; drop entries you don't want)
export DIRIGO_STATE_TGS='{"3123":"Maine","3150":"Vermont","3133":"New Hampshire","3125":"Massachusetts","3109":"Connecticut","3144":"Rhode Island","3136":"New York"}'
```

## Scheduling

The script is designed to run from cron. It checks the NEDECN reports, retries at the configured times if data isn't ready yet, and posts the best available result.

### Crontab entry

Start the job a bit before your earliest check time; the script itself schedules the retry checks in America/New_York local time (DST-aware), so the exact cron trigger time isn't critical as long as it's early enough. `13:00 UTC` is 9:00 AM EDT / 8:00 AM EST — always at or before the default 9:00 AM Eastern first check:

```cron
0 13 * * 0 DIRIGO_SLACK_WEBHOOK='https://hooks.slack.com/services/T00/B00/xxxx' QRZ_USERNAME='yourcall' QRZ_APIKEY='your-qrz-xml-password' /path/to/dirigo_net_report.py >> /var/log/dirigo-net-report.log 2>&1
```

Or use a wrapper script if you have multiple env vars:

```bash
#!/bin/bash
export DIRIGO_SLACK_WEBHOOK='https://hooks.slack.com/services/T00/B00/xxxx'
export QRZ_USERNAME='yourcall'
export QRZ_APIKEY='your-qrz-xml-password'
export DIRIGO_CHECK_TIMES='[32400, 34200, 35100]'
exec /path/to/dirigo_net_report.py
```

## Report URLs

- Callsign: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-CALLSIGN.html`
- Talkgroup: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-TALKGROUP.html`
- Repeater: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-REPEATER.html`

## License

MIT
