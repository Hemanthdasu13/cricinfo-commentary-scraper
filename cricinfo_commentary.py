#!/usr/bin/env python3
"""Download ball-by-ball commentary for ESPNcricinfo matches.

Pass one or more match URLs, or a text file with one URL per line
(--from-file). For each match the script reads the match summary (format,
teams, result), walks every innings and every page of ESPN's play-by-play
feed, then writes:

  <output>/<match_id>.csv            one row per delivery, analysis-friendly
  <output>/<match_id>.raw.json       untouched play-by-play responses
  <output>/<match_id>.summary.json   match summary (format, teams, venue, XIs)
  <output>/all_matches.csv           every match combined (when >1 match)

If <match_id>.raw.json already exists in the output folder, it is reused
instead of downloaded again, so re-runs only fetch what is missing.

Use sparingly and only where ESPNcricinfo's terms and your intended use allow
it. The feed is undocumented and can change without notice.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

USER_AGENT = "Mozilla/5.0 (commentary-research-collector/1.1)"
API = "https://site.web.api.espn.com/apis/site/v2/sports/cricket/{series_id}/playbyplay"
SUMMARY_API = "https://site.web.api.espn.com/apis/site/v2/sports/cricket/{series_id}/summary"
MAX_INNINGS = 6  # 2 innings + room for super overs
PAGE_LIMIT = 1000  # items per request; an ODI innings is ~300-330
# The feed adds an item with this ID holding end-of-match notes (presentation
# quotes etc.). It is not a delivery, so it stays in the raw JSON only.
NOTES_ITEM_ID = "999999999999999"
# Official match class -> format. Franchise leagues are "Twenty20", T20
# internationals "T20I"; both are format t20 (the match_class column tells
# them apart).
FORMAT_CARDS = {"T20I": "t20", "TWENTY20": "t20", "ODI": "odi", "TEST": "test"}
# The Hundred is classed as Twenty20 but is 100 balls a side in sets of five,
# so it gets its own format. ESPN series IDs: men's 19601, women's 21376.
HUNDRED_SERIES = {"19601", "21376"}
SUMMARY_PARTS = ("header", "gameInfo", "rosters", "notes")  # the rest is news/video

FIELDS = [
    "series_id", "match_id", "match_label", "format", "match_class", "ball_limit", "innings", "innings_label",
    "batting_team", "over", "over_number", "ball_in_over",
    "bowler", "bowler_id", "batter", "batter_id", "non_striker", "non_striker_id",
    "runs", "play_type", "is_wicket", "dismissal_type", "dismissal_text",
    "innings_runs", "innings_wickets", "target", "short_text", "text", "pre_text", "post_text",
    "timestamp_ms", "sequence",
]

TAG_RE = re.compile(r"<[^>]+>")


def ids_from_url(url: str) -> tuple[str, str]:
    """Return (series_id, match_id) from a Cricinfo or ESPN.com match URL.

    Cricinfo: espncricinfo.com/series/<name>-<series_id>/<match-name>-<match_id>/...
    ESPN.com: espn.com/cricket/series/<series_id>/game/<match_id>/<match-name>
    (ESPN owns Cricinfo; the match IDs are the same and the feed accepts both.)
    """
    host = urlparse(url).netloc
    if "espncricinfo.com" in host or "cricinfo.com" in host:
        ids = re.findall(r"-(\d+)(?=/|$|\?)", url)
    elif "espn." in host:
        ids = list(re.search(r"/series/(\d+)/game/(\d+)", url).groups()) if "/game/" in url else []
    else:
        raise ValueError(f"Not a Cricinfo/ESPN cricket URL: {url}")
    if len(ids) < 2:
        raise ValueError(f"Could not find series and match IDs in: {url}")
    return ids[0], ids[1]


def label_from_url(url: str) -> str:
    """'india-vs-new-zealand-5th-t20i-1490238' -> 'India vs New Zealand 5th T20I'."""
    parts = [p for p in urlparse(url).path.split("/") if p and p != "ball-by-ball-commentary"]
    slug = parts[2] if "cricinfo" in urlparse(url).netloc and len(parts) > 2 else parts[-1]
    words = re.sub(r"-\d+$", "", slug).split("-")
    return " ".join(w.upper() if w in {"t20i", "odi"} else w if w == "vs" else w.capitalize() for w in words)


def clean(value: Any) -> str:
    """Strip HTML tags/entities and collapse whitespace."""
    if not value:
        return ""
    text = TAG_RE.sub(" ", str(value))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def athlete(block: Any) -> dict[str, Any]:
    return (block.get("athlete") or {}) if isinstance(block, dict) else {}


def name(block: Any) -> str:
    a = athlete(block)
    return a.get("displayName") or a.get("name") or ""


def get_json(session: requests.Session, url: str, params: dict[str, Any], what: str) -> dict[str, Any]:
    attempts = 6
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, timeout=30)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == attempts - 1:
                raise
            time.sleep(3 * (attempt + 1))
            continue
        # ESPN's edge returns sporadic 502s; back off and retry.
        if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            wait = 3 * (attempt + 1)
            print(f"    HTTP {response.status_code} on {what}, retrying in {wait}s")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("unreachable")


def get_page(session: requests.Session, series_id: str, match_id: str, period: int, page: int) -> dict[str, Any]:
    # The feed pages 25 balls at a time by default; `limit` returns a whole
    # innings in one request (same items), which is ~8x fewer requests.
    params = {"contentorigin": "espn", "event": match_id, "period": period, "page": page,
              "section": "cricinfo", "limit": PAGE_LIMIT}
    return get_json(session, API.format(series_id=series_id), params, f"innings {period} page {page}")


def get_summary(session: requests.Session, series_id: str, match_id: str) -> dict[str, Any]:
    payload = get_json(session, SUMMARY_API.format(series_id=series_id), {"event": match_id}, "match summary")
    return {k: payload[k] for k in SUMMARY_PARTS if k in payload}


def match_info(summary: dict[str, Any]) -> dict[str, Any]:
    """Format, teams and result from the match summary."""
    comp = ((summary.get("header") or {}).get("competitions") or [{}])[0]
    card = ((comp.get("class") or {}).get("generalClassCard") or "").upper()
    teams = [c.get("team") or {} for c in comp.get("competitors") or []]
    return {
        "format": FORMAT_CARDS.get(card.upper(), card.lower()),
        "match_class": (comp.get("class") or {}).get("generalClassCard") or "",
        "reduced_overs": bool(comp.get("reducedOvers")),
        "team_ids": {str(t.get("id")) for t in teams},
        "teams": " v ".join(t.get("displayName", "") for t in teams),
        "result": (comp.get("status") or {}).get("summary") or "",
    }


def format_from_ball_limit(item: dict[str, Any]) -> str:
    """Fallback when the summary is unavailable. Rain-reduced games have
    smaller limits (e.g. 108 or 150 balls), so use ranges, not exact values."""
    limit = int((item.get("innings") or {}).get("ballLimit") or 0)
    return "test" if not limit else "t20" if limit <= 120 else "odi"


def is_delivery(item: dict[str, Any], period: int | None = None) -> bool:
    if str(item.get("id")) == NOTES_ITEM_ID:
        return False
    # The API ignores out-of-range periods and may return innings 1 again.
    return period is None or item.get("period") == period


def fetch_pages(session: requests.Session, series_id: str, match_id: str, delay: float) -> list[dict]:
    """Download every page of every innings; returns the raw responses."""
    raw_pages: list[dict[str, Any]] = []
    for period in range(1, MAX_INNINGS + 1):
        page, page_count, found = 1, 1, 0
        while page <= page_count:
            payload = get_page(session, series_id, match_id, period, page)
            raw_pages.append({"period": period, "page": page, "response": payload})
            commentary = payload.get("commentary") or {}
            page_count = int(commentary.get("pageCount") or 0)
            page_items = commentary.get("items") or []
            found += sum(is_delivery(i, period) for i in page_items)
            time.sleep(delay)
            if not page_items:
                break
            page += 1
        if not found:
            break  # no such innings -> match is done
        print(f"  innings {period}: downloaded")
    return raw_pages


def items_from_pages(raw_pages: list[dict]) -> list[dict]:
    """Deliveries from raw responses: de-duplicated (pages overlap and the feed
    sometimes repeats a ball) and in order."""
    items, seen = [], set()
    for page in raw_pages:
        for item in (page["response"].get("commentary") or {}).get("items") or []:
            if not is_delivery(item, page["period"]):
                continue
            key = f"{item.get('period')}:{item.get('id')}:{item.get('sequence')}"
            if key not in seen:
                seen.add(key)
                items.append(item)
    items.sort(key=lambda i: (i.get("period", 0), i.get("sequence", 0)))
    return items


def normalise(item: dict[str, Any], series_id: str, match_id: str, label: str, fmt: str,
              match_class: str = "") -> dict[str, Any]:
    over = item.get("over") or {}
    innings = item.get("innings") or {}
    dismissal = item.get("dismissal") or {}
    return {
        "series_id": series_id,
        "match_id": match_id,
        "match_label": label,
        "format": fmt,
        "match_class": match_class,
        "ball_limit": innings.get("ballLimit", ""),
        "innings": item.get("period", ""),
        "innings_label": item.get("periodText", ""),
        "batting_team": (item.get("team") or {}).get("displayName", ""),
        "over": over.get("overs", ""),
        "over_number": over.get("number", ""),
        "ball_in_over": over.get("ball", ""),
        "bowler": name(item.get("bowler")),
        "bowler_id": athlete(item.get("bowler")).get("id", ""),
        "batter": name(item.get("batsman")),
        "batter_id": athlete(item.get("batsman")).get("id", ""),
        "non_striker": name(item.get("otherBatsman")),
        "non_striker_id": athlete(item.get("otherBatsman")).get("id", ""),
        "runs": item.get("scoreValue", ""),
        "play_type": (item.get("playType") or {}).get("description", ""),
        "is_wicket": bool(dismissal.get("dismissal")),
        "dismissal_type": dismissal.get("type", ""),
        "dismissal_text": clean(dismissal.get("text")),
        "innings_runs": innings.get("runs", ""),  # running total ("totalRuns" is runs off this ball)
        "innings_wickets": innings.get("wickets", ""),
        "target": innings.get("target") or "",
        "short_text": clean(item.get("shortText")),
        "text": clean(item.get("text")),
        "pre_text": clean(item.get("preText")),
        "post_text": clean(item.get("postText")),
        "timestamp_ms": item.get("bbbTimestamp", ""),
        "sequence": item.get("sequence", ""),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    # utf-8-sig so Excel opens names/quotes correctly
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_url_file(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ESPNcricinfo ball-by-ball commentary.")
    parser.add_argument("urls", nargs="*", help="ESPNcricinfo match URL(s)")
    parser.add_argument("--from-file", type=Path, help="Text file with one match URL per line")
    parser.add_argument("--output-dir", type=Path, default=Path("data"), help="Where to write CSV/JSON (default: data)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between API requests (default: 1.5)")
    parser.add_argument("--formats", help="Only these formats, comma-separated: t20,odi,test (default: all)")
    parser.add_argument("--teams", help="Only matches where BOTH sides are in this comma-separated list of "
                                        "ESPN team IDs (e.g. 1,2,3,4,5,6,7,8,25,40)")
    args = parser.parse_args()
    formats = {f.strip().lower() for f in args.formats.split(",")} if args.formats else None
    teams = {t.strip() for t in args.teams.split(",")} if args.teams else None

    urls = list(args.urls) + (read_url_file(args.from_file) if args.from_file else [])
    if not urls:
        parser.error("give at least one match URL or --from-file")

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    combined: list[dict[str, Any]] = []
    empty: list[str] = []
    failures = other_format = other_teams = reused = 0
    for url in urls:
        try:
            series_id, match_id = ids_from_url(url)
            label = label_from_url(url)
            print(f"{label} ({match_id})")
            summary_path = out / f"{match_id}.summary.json"
            raw_path = out / f"{match_id}.raw.json"

            if summary_path.exists():
                summary = load_json(summary_path)
            else:
                try:
                    summary = get_summary(session, series_id, match_id)
                    time.sleep(args.delay)
                except requests.RequestException as exc:
                    print(f"  summary unavailable ({exc}); format from ball limit instead")
                    summary = None
            info = match_info(summary) if summary else None
            fmt = info["format"] if info else ""
            if series_id in HUNDRED_SERIES:
                fmt = "hundred"

            if formats and fmt and fmt not in formats:
                print(f"  {fmt} - skipped (--formats {args.formats})")
                other_format += 1
                continue
            if teams and info and not info["team_ids"] <= teams:
                print(f"  {info['teams']} - skipped (not between --teams)")
                other_teams += 1
                continue

            if raw_path.exists():
                raw_pages = load_json(raw_path)
                reused += 1
                print("  reusing saved raw data")
            else:
                raw_pages = fetch_pages(session, series_id, match_id, args.delay)
        except (ValueError, requests.RequestException, json.JSONDecodeError) as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            failures += 1
            continue

        items = items_from_pages(raw_pages)
        if not fmt and items:
            fmt = format_from_ball_limit(items[0])
            if formats and fmt not in formats:
                print(f"  {fmt} - skipped (--formats {args.formats})")
                other_format += 1
                continue
        if not items:
            print("  no commentary available (abandoned or not covered) - skipped")
            empty.append(f"{label} ({match_id})")
            continue

        match_class = info["match_class"] if info else ""
        rows = [normalise(i, series_id, match_id, label, fmt, match_class) for i in items]
        save_json(raw_path, raw_pages)
        if summary:
            save_json(summary_path, summary)
        write_csv(out / f"{match_id}.csv", rows)
        combined.extend(rows)
        note = f", {info['result']}" if info and info["result"] else ""
        print(f"  saved {len(rows)} deliveries ({fmt}{', reduced overs' if info and info['reduced_overs'] else ''}{note})")

    if len(urls) > 1 and combined:
        write_csv(out / "all_matches.csv", combined)
        print(f"Combined {len(combined)} deliveries -> {out / 'all_matches.csv'}")
    if reused:
        print(f"Reused saved raw data for {reused} match(es)")
    if other_format:
        print(f"Skipped {other_format} match(es) in other formats")
    if other_teams:
        print(f"Skipped {other_teams} match(es) not between --teams")
    if empty:
        print(f"No commentary for {len(empty)} match(es): {', '.join(empty)}")
    if failures:
        print(f"{failures} match(es) FAILED - see errors above", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
