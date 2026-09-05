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

## Algorithm

1. Fetch all three pages.
2. Extract the report date range from each page title (e.g. "2026-08-16 to 2026-08-22"). If the date range is not the current week, note that in the output.
3. From the callsign report, find every entry whose state is `ME` within the top 10. Record rank and callsign.
4. From the talkgroup report, find the rank of talkgroup `3123` (Maine Statewide). Record rank and what talkgroups rank above it.
5. From the repeater report, find every entry whose location ends in `ME` within the top 10. Record rank and callsign/location.
6. Validate Maine QTHs using the QRZ lookup skill (`qrz-lookup`) if needed to resolve ambiguous call signs.

## Output format

Produce exactly this markdown structure. Do not add commentary, summary, or conjecture.

```
# ME Statistics
These statistics are relevant to week ending <date>

## Callsign Report
[How many Maine hams in top ten](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-CALLSIGN.html)
<count> Maine operators in the Top 10

## Repeater Report
[How many Maine repeaters in top ten](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-REPEATER.html)
<count> Maine repeaters in the top 10

## Talkgroup Report
[Maine Statewide talkgroup's usage ratio](https://reports.nedecn.org/NEDECN/NEDECN-USE-BY-TALKGROUP.html)
Maine Statewide is <ratio>x busier than the next statewide talk group, Vermont
```

## Rules

- Count only entries from Maine (`ME`) within the top 10.
- For callsigns and repeaters, report the quantity only — do not list individual callsigns, names, locations, or ranks. This is intentional for privacy and to avoid NCS identifying individuals on the air.
- For talkgroups, ignore TAC channels (311, 310, 312, 317), 3181, and non-state talkgroups. Compare Maine Statewide (3123) total seconds against the next highest New England statewide talkgroup (e.g. Vermont 3150, New Hampshire 3133, Massachusetts 3125, Connecticut, Rhode Island, New York). Report the ratio rounded to one decimal place (e.g. `5.6x`).
- Extract the report date range from the page title and use the ending date in the intro line (e.g. `week ending 2026-08-29`).
- If the report date is not current for the week (a week or more behind), prepend `(Report not current) ` after the section heading.
- Maine state abbreviation is `ME`. Do not include operators from repeaters from other New England states.
- Keep output data-only: no introductory sentences beyond the header, no closing remarks, no conjecture.
