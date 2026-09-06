---
name: nedecn-dirigo-net-report
description: "Build Dirigo Net weekly stats from NEDECN reports."
version: 1.0.0
author: Brad Brown Jr
license: MIT
metadata:
  hermes:
    tags: [ham-radio, nedecn, dirigo-net, dmr, maine, announcements]
---

# NEDECN Dirigo Net Weekly Report

Pull the three NEDECN weekly reports and format Maine-specific statistics for the ME Dirigo Net announcements posted in ECT Logger.

## When to Use

Use this skill whenever the user needs the ME Dirigo Net weekly announcements section, asks for the NEDECN statistics report, or needs Maine-specific callsign/talkgroup/repeater rankings for the net.

## Trigger

Load this skill when the user asks for Dirigo Net weekly stats, ME Statistics, NEDECN report, or net announcement data.

## Inputs

None — all data comes from the live report pages.

## Report pages

- Callsign: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-CALLSIGN.html`
- Talkgroup: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-TALKGROUP.html`
- Repeater: `https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-REPEATER.html`

## PeerWatch live-status feeds

- Augusta: `http://207.246.80.187:42420/data.txt?param=ajaxpeerwatchpage`
- Bass Hill: `http://45.76.4.145:42420/data.txt?param=ajaxpeerwatchpage`
- Boston: `http://cb.nedecn.org:42420/data.txt?param=ajaxpeerwatchpage`

Each line is one C-Bridge port: `<site label>\t<master-ID button>\t<repeater button>`. The repeater button (callsign/location/RadioID) is present only while a repeater is actually linked to that port; a port with no third field currently has no repeater linked (offline).

## Algorithm

1. Fetch all three report pages.
2. Extract the report date range from each page title (e.g. "2026-08-16 to 2026-08-22"). If the date range is not the current week, note that in the output.
3. From the callsign report, find every entry whose state is `ME` within the top 10. Record rank and callsign.
4. From the talkgroup report, find the rank of talkgroup `3123` (Maine Statewide) and its seconds, and the seconds of the next busiest New England state talkgroup.
5. From the repeater report, find every entry whose location ends in `ME` within the top 10. Record rank and callsign/location.
6. Validate Maine QTHs using the QRZ lookup skill (`qrz-lookup`) if needed to resolve ambiguous call signs.
7. Fetch the three PeerWatch feeds and check each watched repeater's site label (default: Shapleigh) for a linked repeater button. If a watched repeater is found on a feed with no repeater button, it's offline. If every watched repeater is found and linked, report all clear. If a watched repeater is never found on any feed (or none of the feeds could be fetched), report it as unverified rather than assuming either state.

## Output format

Produce exactly this markdown structure. Do not add commentary, summary, or conjecture.

```
# ME Statistics
These statistics are relevant to week ending <date>

## Callsign Report
[How many Maine hams in top ten](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-CALLSIGN.html)
<count> Maine operators in the Top 10

## Talkgroup Report
[Maine Statewide talkgroup's usage ratio](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-TALKGROUP.html)
Maine Statewide is <ratio>x busier than the next statewide talk group, Vermont

## Repeater Report
[How many Maine repeaters in top ten](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-REPEATER.html)
<count> Maine repeaters in the top 10
Offline: <comma-separated watched repeater names> | All watched repeaters online
Could not verify: <comma-separated watched repeater names, only if any are unverifiable>
```

## Rules

- Count only entries from Maine (`ME`) within the top 10.
- For callsigns and repeaters, report the quantity only — do not list individual callsigns, names, locations, or ranks. This is intentional for privacy and to avoid NCS identifying individuals on the air.
- The offline-repeater status line is an intentional exception to the counts-only rule above: it names specific watched repeaters (infrastructure status, not personal information about an operator). Report `Offline: <names>` if any are found unlinked, or `All watched repeaters online` if every watched repeater was found and linked. Report a separate `Could not verify: <names>` line for any watched repeater never found on any feed, or if none of the feeds could be fetched — never assume online or offline in that case.
- For talkgroups, ignore TAC channels (311, 310, 312, 317), 3181, and non-state talkgroups. Compare Maine Statewide (3123) total seconds against the next highest New England statewide talkgroup (e.g. Vermont 3150, New Hampshire 3133, Massachusetts 3125, Connecticut, Rhode Island, New York). Report the ratio rounded to one decimal place (e.g. `5.6x`).
- Extract the report date range from the page title and use the ending date in the intro line (e.g. `week ending 2026-08-29`).
- If the report date is not current for the week (a week or more behind), prepend `(Report not current) ` after the section heading.
- Maine state abbreviation is `ME`. Do not include operators from repeaters from other New England states.
- Keep output data-only: no introductory sentences beyond the header, no closing remarks, no conjecture.
