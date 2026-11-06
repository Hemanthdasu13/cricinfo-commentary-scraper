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

Every day's full cricket schedule (all competitions), keeping franchise leagues
by their ESPN series ID plus head-to-heads between the listed teams:
    python find_matches.py --daily --series-ids 8048,8044 --team-id 1,2,6 --head-to-head         --start 2021-01-01 --out matches/t20_2021.txt

Several teams, keeping only matches between two of them:
    python find_matches.py --team-id 1,2,3,4,5,6,7,8,25,40 --head-to-head \
        --start 2023-11-20 --out matches/top10_h2h.txt --others-out matches/top10_vs_others.txt
"""

from __future__ import annotations

import argparse
import calendar
import html
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

USER_AGENT = "Mozilla/5.0 (commentary-research-collector/1.1)"
PAGE = "https://www.espn.com/cricket/scores/team/{team_id}/{team_slug}"
# All cricket played on a day. espn.in and espn.com serve the same page; when
# one returns errors the other often doesn't.
# ESPN's regional sites serve the same daily page from separate caches. An
# uncached date often fails with HTTP 503 on one host and loads on another.
DAILY_PAGES = tuple(f"https://{host}/cricket/scores" for host in (
    "africa.espn.com", "www.espn.com", "www.espn.com.au", "www.espn.co.uk", "www.espn.in"))
SITE = "https://www.espn.com"
# ESPN team IDs and URL names (the name part of the URL is not checked by ESPN).
TEAM_SLUGS = {
    "1": "england", "2": "australia", "3": "south-africa", "4": "west-indies", "5": "new-zealand",
    "6": "india", "7": "pakistan", "8": "sri-lanka", "9": "zimbabwe", "25": "bangladesh",
    "29": "ireland", "40": "afghanistan",
}

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


def day_matches(session, stamp: str, delay: float, attempts: int = 2) -> list[dict]:
    """All matches on one day (YYYYMMDD), trying each host in turn. A day that
    still fails is left for the slower retry passes at the end."""
    for attempt in range(attempts):
        for page in DAILY_PAGES:
            try:
                return parse(fetch(session, page, {"date": stamp}, delay, attempts=1))
            except PageError:
                continue
        if attempt < attempts - 1:
            time.sleep(3)
    raise PageError(f"both hosts failed for {stamp}")


def days_between(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def months_between(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def slug_teams_in(url: str, names: set[str]) -> bool:
    """True if both sides in 'india-vs-new-zealand-1st-t20i-...' are in `names`."""
    left, sep, right = url.rstrip("/").split("/")[-1].partition("-vs-")
    return bool(sep) and left in names and any(right.startswith(n + "-") for n in names)


def write_list(path: Path, title: str, matches: list[dict], failed: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [title, "# Generated by find_matches.py from ESPN.com fixtures (same IDs as Cricinfo)"]
    if failed:
        lines.append(f"# WARNING: these pages could not be fetched: {', '.join(failed)}")
    series = None
    for m in matches:
        if m["series"] != series:
            series = m["series"]
            lines.append(f"\n# {series}")
        lines.append(f"# {m['info']}")
        lines.append(m["url"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="List a team's completed matches for a year or date range.")
    parser.add_argument("--team-id", default="6",
                        help="ESPN team ID, or several comma-separated (India = 6; see TEAM_SLUGS)")
    parser.add_argument("--team-slug", default="team", help="Team name for the ESPN URL if not in TEAM_SLUGS")
    parser.add_argument("--head-to-head", action="store_true",
                        help="With several teams: keep only matches between two of them")
    parser.add_argument("--others-out", type=Path,
                        help="With --head-to-head: also write the excluded matches (vs other teams) here")
    parser.add_argument("--daily", action="store_true",
                        help="Read ESPN's all-cricket page for every day instead of team pages. Keeps "
                             "--series-ids matches, plus head-to-heads between --team-id teams with "
                             "--head-to-head")
    parser.add_argument("--series-ids", default="",
                        help="With --daily: ESPN series IDs to keep (franchise leagues keep the same ID "
                             "every season, e.g. IPL 8048)")
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
    team_ids = [t.strip() for t in args.team_id.split(",") if t.strip()]
    urls = {t: PAGE.format(team_id=t, team_slug=TEAM_SLUGS.get(t, args.team_slug)) for t in team_ids}
    excluded = [w.strip().lower() for w in args.exclude.split(",") if w.strip()]

    if args.start:
        start = args.start
        end = args.end or date.today()
    else:
        year = args.year or date.today().year
        start, end = date(year, 1, 1), min(args.end or date(year, 12, 31), date.today())
    span = f"{start} to {end}"
    print(f"Looking for matches from {span}")

    def add(found: list[dict], team: str) -> None:
        for m in found:
            # Month pages also show a few fixtures from neighbouring months.
            when = start_date(m["info"])
            if when and start <= when <= end:
                m["date"] = when
                by_id.setdefault(m["match_id"], m).setdefault("seen_by", set()).add(team)

    by_id: dict[str, dict] = {}
    failed: list[tuple[str, str]] = []
    series_ids = {x.strip() for x in args.series_ids.split(",") if x.strip()}
    names = {TEAM_SLUGS[t] for t in team_ids if t in TEAM_SLUGS}

    def wanted(m: dict) -> bool:
        return m["series_id"] in series_ids or (args.head_to_head and slug_teams_in(m["url"], names))

    if args.daily:
        days = list(days_between(start, end))
        for n, day in enumerate(days, 1):
            stamp = day.strftime("%Y%m%d")
            try:
                found = day_matches(session, stamp, args.delay)
            except PageError:
                failed.append(("daily", stamp))
                continue
            add([m for m in found if wanted(m)], "daily")
            if n % 30 == 0 or n == len(days):
                print(f"  {day}: day {n}/{len(days)}, {len(by_id)} matches kept, {len(failed)} days failed")
        team_ids_loop = []
    else:
        team_ids_loop = team_ids
    for team in team_ids_loop:
        print(f"Team {team} ({TEAM_SLUGS.get(team, args.team_slug)})")
        for year, month in months_between(start, end):
            found, failed_days = month_matches(session, urls[team], year, month, args.delay)
            failed += [(team, d) for d in failed_days]
            add(found, team)
            print(f"  {year}-{month:02d}: {len(found)} listed, {len(by_id)} unique so far")

    # ESPN's errors are intermittent: give failed days up to three slower passes.
    for round_no in range(1, 4):
        if not failed:
            break
        print(f"Retry pass {round_no}: {len(failed)} page(s)")
        still_failed = []
        for team, stamp in failed:
            try:
                wait = args.delay + 8 * round_no
                if team == "daily":
                    found = [m for m in day_matches(session, stamp, wait, attempts=4) if wanted(m)]
                else:
                    found = parse(fetch(session, urls[team], {"date": stamp}, wait, attempts=4))
            except PageError:
                still_failed.append((team, stamp))
                continue
            add(found, team)
            print(f"  retry {team} {stamp}: ok, {len(by_id)} unique so far")
        failed = still_failed
    still_failed = [f"team {team} {stamp}" for team, stamp in failed]
    failed = still_failed

    kept, others, skipped = [], [], []
    for m in sorted(by_id.values(), key=lambda m: (m["date"], int(m["match_id"]))):
        if m["status"] != "final":
            skipped.append(f"not finished ({m['status']})")
        elif any(w in f"{m['series']} {m['info']}".lower() for w in excluded):
            skipped.append(f"excluded: {m['series']}")
        elif args.head_to_head and not args.daily and not (len(m["seen_by"]) >= 2 or wanted(m)):
            others.append(m)  # one of our teams against someone else
            continue
        else:
            kept.append(m)
            continue
        print(f"  skip {m['match_id']} {m['info']} - {skipped[-1]}")

    teams_text = ", ".join(f"{TEAM_SLUGS.get(t, args.team_slug)} ({t})" for t in team_ids)
    what = "completed matches between these teams" if args.head_to_head else "completed matches"
    if args.daily:
        what = f"completed matches in series {args.series_ids or '-'}" +                (" or between these teams" if args.head_to_head else "")
    write_list(args.out, f"# Teams {teams_text}, {span}: {len(kept)} {what}", kept, failed)
    print(f"Wrote {len(kept)} {what} to {args.out} ({len(skipped)} skipped)")
    if args.head_to_head and args.others_out:
        write_list(args.others_out, f"# Teams {teams_text}, {span}: {len(others)} completed matches "
                                    "against other teams (not collected by default)", others, failed)
        print(f"Wrote {len(others)} matches against other teams to {args.others_out}")
    if failed:
        print(f"WARNING: {len(failed)} day(s) could not be fetched: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
