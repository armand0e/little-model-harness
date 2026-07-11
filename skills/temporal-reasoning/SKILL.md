---
name: temporal-reasoning
description: Use for anything about dates, calendars, days of the week, durations, time zones, scheduling, ages, deadlines, or "how long between". These calculations look easy and are error factories; this skill provides safe procedures.
category: reasoning
hint: dates, durations, timezones, scheduling
---
# Temporal Reasoning — Dates, Durations, Time Zones

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

- UTC is the reference. Zones are offsets: New York UTC−5 (winter)/−4 (summer DST), Los Angeles UTC−8/−7, London UTC+0/+1, Central Europe +1/+2, India **+5:30** (half-hour zones exist; Nepal +5:45!), China +8 (one zone for the whole country, no DST), Japan +9 (no DST), Sydney +10/+11 (southern hemisphere DST is OPPOSITE: their summer is Nov–Mar).
- Method: convert to UTC, then to the target zone. 3 pm New York (summer, UTC−4) = 19:00 UTC = 12 pm Los Angeles (UTC−7) — never chain offsets casually.
- East is later-in-the-day: Tokyo is ahead of London. Crossing the date line westward from the US to Asia, you lose a day: leave SF Monday evening, land Tokyo Wednesday afternoon — flight was still ~11 h.
- DST: clocks spring forward ~March (US)/late March (EU) and fall back ~November/late October — dates differ by region, so NY↔London is usually 5 h apart but 4 h for a few weeks a year. For scheduling across zones near DST boundaries, state times in both zones explicitly.
- "Noon" = 12:00 pm; "midnight" = 12:00 am, and "midnight Tuesday" is ambiguous (start or end of Tuesday?) — use 23:59 or 00:01 in anything binding.

## Self-check

- Inclusive or exclusive — did I decide explicitly?
- Leap year in the interval? February crossed?
- DST in effect at BOTH ends of a zone conversion?
- Sanity: does the weekday/duration/age answer survive a quick recount by a different route (e.g., count weeks then remainder days)?
