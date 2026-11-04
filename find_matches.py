#!/usr/bin/env python3
"""Build a match list for one team and year, ready for cricinfo_commentary.py.

ESPNcricinfo's own website blocks automated requests, so this reads the same
fixtures from ESPN.com (ESPN owns Cricinfo, and the match IDs are identical):

    https://www.espn.com/cricket/scores/team/<team_id>/<team>?date=YYYYMM

Each month is fetched in one request. If ESPN returns an error for a month
(it sometimes does for busy months), that month is fetched day by day instead.
Only completed matches are kept.

Example (India = team 6):
    python find_matches.py --team-id 6 --year 2026 --out matches/india_2026.txt
"""

from __future__ import annotations

import argparse
import calendar
import html
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

USER_AGENT = "Mozilla/5.0 (commentary-research-collector/1.1)"
PAGE = "https://www.espn.com/cricket/scores/team/{team_id}/{team_slug}"
SITE = "https://www.espn.com"

SERIES_RE = re.compile(r'class="scoreEvent__title[^"]*"[^>]*>([^<]+)</a>')
CARD_RE = re.compile(r'<div class="cscore (cscore--\w+)')
INFO_RE = re.compile(r'class="cscore_info-overview"[^>]*>([^<]*)<')
LINK_RE = re.compile(r'href="(/cricket/series/(\d+)/game/(\d+)/[a-z0-9-]+)"')


class PageError(Exception):
    pass


def fetch(session: requests.Session, url: str, params: dict, delay: float, attempts: int = 4) -> str:
    for attempt in range(attempts):
        time.sleep(delay)
        try:
            response = session.get(url, params=params, timeout=30)
        except (requests.ConnectionError, requests.Timeout):
            response = None
        if response is not None and response.status_code == 200:
            return response.text
        if attempt < attempts - 1:
            time.sleep(3 * (attempt + 1))
    code = response.status_code if response is not None else "no response"
    raise PageError(f"HTTP {code} for {params}")


def parse(page: str) -> list[dict]:
    """Return one dict per match card on a fixtures page."""
    matches = []
    # Cards appear in order; track the most recent series header above each one.
    marks = [(m.start(), "series", m.group(1)) for m in SERIES_RE.finditer(page)]
    marks += [(m.start(), "card", m.group(1)) for m in CARD_RE.finditer(page)]
    marks.sort()
    series = ""
    for i, (pos, kind, value) in enumerate(marks):
        if kind == "series":
            series = html.unescape(value).strip()
            continue
        end = marks[i + 1][0] if i + 1 < len(marks) else len(page)
        chunk = page[pos:end]
        link = LINK_RE.search(chunk)
        if not link:
            continue
        info = INFO_RE.search(chunk)
        matches.append({
            "status": value.replace("cscore--", ""),  # final / live / pregame / ...
            "series": series,
            "info": re.sub(r"\s+", " ", html.unescape(info.group(1))).strip() if info else "",
            "url": SITE + link.group(1),
            "series_id": link.group(2),
            "match_id": link.group(3),
        })
    return matches


def month_matches(session, url, year, month, delay) -> tuple[list[dict], list[str]]:
    """Fetch one month; on error fall back to one request per day."""
    try:
        return parse(fetch(session, url, {"date": f"{year}{month:02d}"}, delay)), []
    except PageError as exc:
        print(f"  {year}-{month:02d}: month page failed ({exc}); trying day by day")
    found, failed_days = [], []
    last_day = calendar.monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        if date(year, month, day) > date.today():
            break
        stamp = f"{year}{month:02d}{day:02d}"
        try:
            found += parse(fetch(session, url, {"date": stamp}, delay, attempts=3))
        except PageError:
            failed_days.append(stamp)
    return found, failed_days


MONTHS = {m: i for i, m in enumerate(calendar.month_abbr) if m}
START_RE = re.compile(r"\b([A-Z][a-z]{2}) (\d{1,2})(?:-(?:[A-Z][a-z]{2} )?\d{1,2})?,? (\d{4})")


def start_date(info: str) -> date | None:
    """'Only Test, at New Chandigarh, Jun 6-8 2026' -> date(2026, 6, 6)."""
    m = START_RE.search(info)
    if not m or m.group(1) not in MONTHS:
        return None
    return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))


def months_between(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="List a team's completed matches for a year or date range.")
    parser.add_argument("--team-id", default="6", help="ESPN team ID (India = 6)")
    parser.add_argument("--team-slug", default="india", help="Team name as in the ESPN URL")
    parser.add_argument("--year", type=int, help="Whole calendar year (default: this year)")
    parser.add_argument("--start", type=date.fromisoformat, help="First date, YYYY-MM-DD (instead of --year)")
    parser.add_argument("--end", type=date.fromisoformat, help="Last date, YYYY-MM-DD (default: today)")
    parser.add_argument("--out", type=Path, required=True, help="Where to write the URL list")
    parser.add_argument("--exclude", default="sixes,warm-up,tour match",
                        help="Skip matches whose series name or description contains any of these "
                             "comma-separated words (default: sixes,warm-up,tour match)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests (default: 1.5)")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    url = PAGE.format(team_id=args.team_id, team_slug=args.team_slug)
    excluded = [w.strip().lower() for w in args.exclude.split(",") if w.strip()]

    if args.start:
        start = args.start
        end = args.end or date.today()
    else:
        year = args.year or date.today().year
        start, end = date(year, 1, 1), min(args.end or date(year, 12, 31), date.today())
    span = f"{start} to {end}"
    print(f"Looking for matches from {span}")

    def add(found: list[dict]) -> None:
        for m in found:
            # Month pages also show a few fixtures from neighbouring months.
            when = start_date(m["info"])
            if when and start <= when <= end:
                m["date"] = when
                by_id.setdefault(m["match_id"], m)

    by_id: dict[str, dict] = {}
    failed: list[str] = []
    for year, month in months_between(start, end):
        found, failed_days = month_matches(session, url, year, month, args.delay)
        failed += failed_days
        add(found)
        print(f"  {year}-{month:02d}: {len(found)} listed, {len(by_id)} unique so far")

    # ESPN's errors are intermittent: give failed days a slower second pass.
    still_failed = []
    for stamp in failed:
        try:
            found = parse(fetch(session, url, {"date": stamp}, args.delay + 8, attempts=4))
        except PageError:
            still_failed.append(stamp)
            continue
        add(found)
        print(f"  retry {stamp}: ok, {len(by_id)} unique so far")
    failed = still_failed

    kept, skipped = [], []
    for m in sorted(by_id.values(), key=lambda m: (m["date"], int(m["match_id"]))):
        if m["status"] != "final":
            skipped.append(f"not finished ({m['status']})")
        elif any(w in f"{m['series']} {m['info']}".lower() for w in excluded):
            skipped.append(f"excluded: {m['series']}")
        else:
            kept.append(m)
            continue
        print(f"  skip {m['match_id']} {m['info']} - {skipped[-1]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Team {args.team_slug} ({args.team_id}), {span}: {len(kept)} completed matches",
             "# Generated by find_matches.py from ESPN.com fixtures (same IDs as Cricinfo)"]
    if failed:
        lines.append(f"# WARNING: these days could not be fetched: {', '.join(failed)}")
    series = None
    for m in kept:
        if m["series"] != series:
            series = m["series"]
            lines.append(f"\n# {series}")
        lines.append(f"# {m['info']}")
        lines.append(m["url"])
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(kept)} completed matches to {args.out} ({len(skipped)} skipped)")
    if failed:
        print(f"WARNING: {len(failed)} day(s) could not be fetched: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
