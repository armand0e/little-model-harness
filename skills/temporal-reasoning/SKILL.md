---
name: temporal-reasoning
description: Use for anything about dates, calendars, days of the week, durations, time zones, scheduling, ages, deadlines, or "how long between". These calculations look easy and are error factories; this skill provides safe procedures.
---

# Temporal Reasoning — Dates, Durations, Time Zones

## Reliable workflow

1. Parse each time as `date`, `clock time`, `calendar/time zone`, and `precision`. Resolve or state ambiguity around inclusive endpoints, midnight, fiscal calendars, and relative words such as `next`.
2. Convert named-zone times with an IANA time zone and a current time-zone database or trusted tool. Do not infer daylight-saving offsets from season alone.
3. For elapsed durations, convert instants to a common timeline such as UTC, subtract, then express the result in the requested units. For calendar periods such as `one month`, use calendar arithmetic instead of assuming a fixed number of seconds.
4. For recurring schedules, test gaps and folds around daylight-saving transitions and state whether the recurrence follows local wall time or a fixed elapsed interval.
5. Verify with a second representation: ISO 8601 timestamps with offsets, weekday recount, or a date/time library.

Return exact dates and include the zone or UTC offset. If a historical or future civil-time rule is uncertain, say that the applicable jurisdiction's rule must be checked.

## Calendar facts

- Month lengths: 31 for Jan/Mar/May/Jul/Aug/Oct/Dec; 30 for Apr/Jun/Sep/Nov; Feb 28 (29 in leap years). Knuckle mnemonic works.
- **Leap year rule**: divisible by 4 → leap, EXCEPT divisible by 100 → not, EXCEPT divisible by 400 → leap. So 2000 and 2400 leap; 1900, 2100 do not; 2024, 2028 leap.
- Year = 365 days (366 leap) = 52 weeks + 1 day (+2 leap). Consequence: a date advances one weekday per ordinary year, two per leap year (if the leap day falls in the interval). Jan 1, 2025 was Wednesday → Jan 1, 2026 is Thursday.
- Quarters: Q1 Jan–Mar, Q2 Apr–Jun, Q3 Jul–Sep, Q4 Oct–Dec. Fiscal years vary by org — ask/state which.
- Decades/centuries: the 1900s/20th century = 1900–1999 (strictly 1901–2000; use context). "Mid-century" ≈ 1950s.

## Duration arithmetic (where errors live)

- **Inclusive vs exclusive counting**: March 10 to March 15 is 5 days LATER, but 6 days if both endpoints count (a hotel stay Mar 10–15 is 5 nights, 6 calendar days). Decide which the question wants FIRST. "Day 1 to day 8" of a course = 8 days inclusive, 7 elapsed.
- Count month-by-month for long spans, don't guess: Jan 15 → Apr 15 is 90 days (16 remaining in Jan +28 Feb +31 Mar +15... check: 16+28+31+15 = 90 ✓ non-leap).
- Weekday of a future date: days-mod-7. 45 days after a Tuesday: 45 mod 7 = 3 → Friday.
- Age: has this year's birthday happened yet? Born Aug 5, 1990, today Jul 9, 2026 → still 35, turns 36 in August. Age ≠ current year − birth year (that's the maximum, only after the birthday).
- Clock arithmetic: work in 24 h format; convert immediately (7:30 pm = 19:30). Duration across midnight: 22:45 to 06:15 = (24:00−22:45)+(6:15) = 1:15+6:15 = 7 h 30 m.
- "Every N days" vs "every Nth day-of-week" differ; biweekly is ambiguous (twice a week or every two weeks) — clarify or state your reading.

## Time zones

- UTC is the reference, but a civil time zone is a dated rule set, not a permanent offset. Use names such as `America/New_York` and `Asia/Kolkata`, not abbreviations such as `EST` or `IST`. Half- and quarter-hour offsets exist.
- Method: resolve the source local time on its date, convert to UTC, then convert to the target named zone. A 3 pm New York to Los Angeles example is often a three-hour difference, but verify the actual date because rules and transition dates can differ.
- East is generally later in civil time: Tokyo is ahead of London. Crossing the date line westward from the US to Asia advances the calendar date by a day; elapsed flight time remains ordinary.
- DST: clocks spring forward ~March (US)/late March (EU) and fall back ~November/late October — dates differ by region, so NY↔London is usually 5 h apart but 4 h for a few weeks a year. For scheduling across zones near DST boundaries, state times in both zones explicitly.
- "Noon" = 12:00 pm; "midnight" = 12:00 am, and "midnight Tuesday" is ambiguous (start or end of Tuesday?) — use 23:59 or 00:01 in anything binding.

## Self-check

- Inclusive or exclusive — did I decide explicitly?
- Leap year in the interval? February crossed?
- DST in effect at BOTH ends of a zone conversion?
- Sanity: does the weekday/duration/age answer survive a quick recount by a different route (e.g., count weeks then remainder days)?
