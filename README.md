# Dirigo Net Weekly Report

Pulls the three NEDECN weekly reports and posts Maine-specific statistics to Slack for the Maine Dirigo Net announcements.

Privacy-first design: the report shows **counts only** — no individual callsigns, names, or repeater locations — so net control can read it on the air without identifying individuals.

## What it reports

- **Callsign Report** — number of Maine operators in the overall top 10
- **Repeater Report** — number of Maine repeaters in the overall top 10
- **Talkgroup Report** — Maine Statewide (3123) usage compared to the next busiest NEDECN state talkgroup, expressed as a ratio (e.g. `5.6x`)

If a report is a week or more behind, the section is marked `(Report not current)` and shows no data rather than stale numbers.

## Prerequisites

- Python 3.9+
- A Slack webhook URL (`DIRIGO_SLACK_WEBHOOK`)

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

### Optional

| Variable | Default | Description |
|---|---|---|
| `DIRIGO_CHECK_TIMES` | `[46800, 47100, 47400, 50400, 52740]` | Retry times in seconds since midnight UTC. Default: 9:00, 9:30, 9:45, 10:00, 10:55 AM EDT. Override to match your net schedule, e.g. `[46800, 47400]` for just 9:00 and 10:00 AM EDT. |
| `DIRIGO_STATE_TGS` | `{"3123":"Maine","3150":"Vermont","3133":"New Hampshire","3125":"Massachusetts"}` | JSON map of talkgroup IDs to state names for the ratio comparison. Add or remove states to match the NEDECN repeaters in your region. |

### Examples

```bash
# Set webhook
export DIRIGO_SLACK_WEBHOOK='https://hooks.slack.com/services/T00/B00/xxxx'

# Override check times for a 10:00 AM net (14:00 UTC)
export DIRIGO_CHECK_TIMES='[50400]'

# Include Connecticut and Rhode Island in talkgroup comparison
export DIRIGO_STATE_TGS='{"3123":"Maine","3150":"Vermont","3133":"New Hampshire","3125":"Massachusetts","3126":"Connecticut","3127":"Rhode Island"}'
```

## Scheduling

The script is designed to run from cron. It checks the NEDECN reports, retries at the configured times if data isn't ready yet, and posts the best available result.

### Crontab entry

Run every Sunday starting at 9:00 AM EDT:

```cron
0 13 * * 0 DIRIGO_SLACK_WEBHOOK='https://hooks.slack.com/services/T00/B00/xxxx' /path/to/dirigo_net_report.py >> /var/log/dirigo-net-report.log 2>&1
```

Or use a wrapper script if you have multiple env vars:

```bash
#!/bin/bash
export DIRIGO_SLACK_WEBHOOK='https://hooks.slack.com/services/T00/B00/xxxx'
export DIRIGO_CHECK_TIMES='[46800, 47100, 47400]'
exec /path/to/dirigo_net_report.py
```

## Report URLs

- Callsign: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-CALLSIGN.html`
- Talkgroup: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-TALKGROUP.html`
- Repeater: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-REPEATER.html`

## License

MIT
