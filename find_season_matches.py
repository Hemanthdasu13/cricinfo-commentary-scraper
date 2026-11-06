#!/usr/bin/env python3
"""Build a match list for whole league seasons, ready for cricinfo_commentary.py.

Each season of a league has its own Cricinfo series ID (IPL 2026 is 1510719,
from espncricinfo.com/series/ipl-2026-1510719/...). ESPN's site API lists a
season's matches by date:

    https://site.web.api.espn.com/apis/site/v2/sports/cricket/<season_id>/scoreboard?dates=YYYYMMDD

A whole-month query (dates=YYYYMM) shows which months have matches, but it
leaves some entries empty, so every day in those months is then read on its own.
A day query can also come back with a blank entry; that day is asked again.
The season's last match (the scoreboard with no date) marks where to start.

Example (IPL 2021 to 2026):
    python find_season_matches.py --season-ids 1249214,1298423,1345038,1410320,1449924,1510719 \
        --out matches/ipl_2021_2026.txt
"""

from __future__ import annotations

import argparse
import calendar
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

USER_AGENT = "Mozilla/5.0 (commentary-research-collector/1.1)"
SCOREBOARD = "https://site.web.api.espn.com/apis/site/v2/sports/cricket/{season_id}/scoreboard"
LINK_RE = re.compile(r"/cricket/series/(\d+)/\w+/(\d+)/([a-z0-9-]+)")
MAX_MONTHS_BACK = 10  # a season never spans more than this
EMPTY_MONTHS_TO_STOP = 4  # IPL 2021 paused for three months mid-season


class PageError(Exception):
    pass


def get_events(session: requests.Session, season_id: str, dates: str | None, delay: float,
               attempts: int = 4) -> tuple[list[dict], str]:
    """(events, league name) for one season and date (or no date = latest match)."""
    params = {"dates": dates} if dates else {}
    response = None
    for attempt in range(attempts):
        time.sleep(delay)
        try:
            response = session.get(SCOREBOARD.format(season_id=season_id), params=params, timeout=60)
        except (requests.ConnectionError, requests.Timeout):
            response = None
        if response is not None and response.status_code == 200:
            data = response.json()
            name = (data.get("leagues") or [{}])[0].get("name", "")
            return data.get("events", []), name
        if response is not None and response.status_code == 404:
            break
        time.sleep(5 * (attempt + 1))
    code = response.status_code if response is not None else "no response"
    raise PageError(f"HTTP {code} for season {season_id} {dates or 'latest'}")


def match_url(event: dict) -> str | None:
    for link in event.get("links", []):
        found = LINK_RE.search(link.get("href", ""))
        if found and found.group(2) == event["id"]:
            series_id, match_id, slug = found.groups()
            return f"https://www.espn.com/cricket/series/{series_id}/game/{match_id}/{slug}"
    return None


def months_back(year: int, month: int, count: int):
    for _ in range(count):
        yield year, month
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="List every completed match in whole league seasons.")
    parser.add_argument("--season-ids", required=True,
                        help="Comma-separated Cricinfo series IDs, one per season (the number at the end "
                             "of the series part of a Cricinfo URL)")
    parser.add_argument("--out", type=Path, required=True, help="Where to write the URL list")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests (default: 1.5)")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    season_ids = [s.strip() for s in args.season_ids.split(",") if s.strip()]

    lines: list[str] = []
    failed: list[str] = []
    total = 0
    for season_id in season_ids:
        latest, league = get_events(session, season_id, None, args.delay)
        latest = [e for e in latest if e.get("id") and e.get("date")]
        if not latest:
            failed.append(f"season {season_id}: no matches")
            print(f"Season {season_id}: no matches found", file=sys.stderr)
            continue
        last = date.fromisoformat(latest[0]["date"][:10])
        print(f"Season {season_id} ({league} {latest[0].get('season', {}).get('year', '')}), "
              f"last match {last}")

        # Which months have any matches (entries, even empty ones, count).
        busy, empty_run = [], 0
        for year, month in months_back(last.year, last.month, MAX_MONTHS_BACK):
            stamp = f"{year}{month:02d}"
            try:
                entries, _ = get_events(session, season_id, stamp, args.delay)
            except PageError:
                entries = [{}]  # unknown: read its days anyway
            if entries:
                busy.append((year, month))
                empty_run = 0
            else:
                empty_run += 1
                if busy and empty_run >= EMPTY_MONTHS_TO_STOP:
                    break

        events: dict[str, dict] = {}
        days = [f"{y}{m:02d}{d:02d}" for y, m in sorted(busy)
                for d in range(1, calendar.monthrange(y, m)[1] + 1)]
        missed = []
        for round_no in range(5):
            missed = []
            for stamp in days:
                try:
                    found, _ = get_events(session, season_id, stamp, args.delay + 4 * round_no)
                except PageError:
                    missed.append(stamp)
                    continue
                if any(not e.get("id") for e in found):
                    # The API sometimes returns a blank entry where a match
                    # should be; asking again returns the match.
                    missed.append(stamp)
                for e in found:
                    if e.get("id"):
                        events[e["id"]] = e
            if not missed:
                break
            print(f"  {len(missed)} day(s) failed, retrying more slowly")
            days = missed
        failed += [f"season {season_id} {d}" for d in missed]

        done = [e for e in events.values() if e.get("status", {}).get("type", {}).get("state") == "post"]
        done.sort(key=lambda e: (e.get("date", ""), int(e["id"])))
        print(f"  {len(events)} matches listed, {len(done)} completed, months "
              f"{', '.join(f'{y}-{m:02d}' for y, m in sorted(busy))}")
        lines.append(f"\n# {league} {latest[0].get('season', {}).get('year', '')} (series {season_id}): "
                     f"{len(done)} completed matches")
        for e in done:
            url = match_url(e)
            if not url:
                failed.append(f"match {e['id']}: no link")
                continue
            result = e.get("status", {}).get("summary", "")
            lines.append(f"# {e.get('date', '')[:10]} {e.get('name', '')}: {result}")
            lines.append(url)
            total += 1

    header = [f"# Seasons {', '.join(season_ids)}: {total} completed matches",
              "# Generated by find_season_matches.py from ESPN's site API (same IDs as Cricinfo)"]
    if failed:
        header.append(f"# WARNING: could not fetch: {', '.join(failed)}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    print(f"Wrote {total} completed matches to {args.out}")
    if failed:
        print(f"WARNING: {len(failed)} problem(s): {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
