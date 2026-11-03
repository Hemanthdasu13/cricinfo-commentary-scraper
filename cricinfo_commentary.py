#!/usr/bin/env python3
"""Download ball-by-ball commentary for ESPNcricinfo matches.

Pass one or more match URLs, or a text file with one URL per line
(--from-file). For each match the script walks every innings and every page
of ESPN's play-by-play feed, then writes:

  <output>/<match_id>.csv        one row per delivery, analysis-friendly
  <output>/<match_id>.raw.json   untouched API responses, for reprocessing
  <output>/all_matches.csv       every match combined (when >1 match)

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
MAX_INNINGS = 6  # 2 innings + room for super overs

FIELDS = [
    "series_id", "match_id", "match_label", "innings", "innings_label", "batting_team",
    "over", "over_number", "ball_in_over", "bowler", "batter", "non_striker",
    "runs", "play_type", "is_wicket", "dismissal_type", "dismissal_text",
    "innings_runs", "innings_wickets", "target", "short_text", "text", "pre_text", "post_text",
    "timestamp_ms", "sequence",
]

TAG_RE = re.compile(r"<[^>]+>")


def ids_from_url(url: str) -> tuple[str, str]:
    """Return (series_id, match_id) from a normal Cricinfo match URL."""
    if "espncricinfo.com" not in urlparse(url).netloc:
        raise ValueError(f"Not an espncricinfo.com URL: {url}")
    ids = re.findall(r"-(\d+)(?=/|$|\?)", url)
    if len(ids) < 2:
        raise ValueError(f"Could not find series and match IDs in: {url}")
    return ids[0], ids[1]


def label_from_url(url: str) -> str:
    """'india-vs-new-zealand-5th-t20i-1490238' -> 'India vs New Zealand 5th T20I'."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    slug = parts[2] if len(parts) > 2 else parts[-1]
    words = re.sub(r"-\d+$", "", slug).split("-")
    return " ".join(w.upper() if w in {"t20i", "odi"} else w if w == "vs" else w.capitalize() for w in words)


def clean(value: Any) -> str:
    """Strip HTML tags/entities and collapse whitespace."""
    if not value:
        return ""
    text = TAG_RE.sub(" ", str(value))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def name(block: Any) -> str:
    if isinstance(block, dict):
        athlete = block.get("athlete") or {}
        return athlete.get("displayName") or athlete.get("name") or ""
    return ""


def get_page(session: requests.Session, series_id: str, match_id: str, period: int, page: int) -> dict[str, Any]:
    params = {"contentorigin": "espn", "event": match_id, "period": period, "page": page, "section": "cricinfo"}
    attempts = 6
    for attempt in range(attempts):
        try:
            response = session.get(API.format(series_id=series_id), params=params, timeout=30)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == attempts - 1:
                raise
            time.sleep(3 * (attempt + 1))
            continue
        # ESPN's edge returns sporadic 502s; back off and retry.
        if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            wait = 3 * (attempt + 1)
            print(f"    HTTP {response.status_code} on innings {period} page {page}, retrying in {wait}s")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("unreachable")


def fetch_match(session: requests.Session, series_id: str, match_id: str, delay: float) -> tuple[list[dict], list[dict]]:
    items: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    seen: set[str] = set()

    for period in range(1, MAX_INNINGS + 1):
        page, page_count = 1, 1
        while page <= page_count:
            payload = get_page(session, series_id, match_id, period, page)
            raw_pages.append({"period": period, "page": page, "response": payload})
            commentary = payload.get("commentary") or {}
            page_count = int(commentary.get("pageCount") or 0)
            page_items = commentary.get("items") or []
            for item in page_items:
                # The API ignores out-of-range periods and may return innings 1 again.
                if item.get("period") != period:
                    continue
                key = f"{item.get('period')}:{item.get('id')}:{item.get('sequence')}"
                if key not in seen:
                    seen.add(key)
                    items.append(item)
            time.sleep(delay)
            if not page_items:
                break
            page += 1
        if not any(i.get("period") == period for i in items):
            break  # no such innings -> match is done
        print(f"  innings {period}: {sum(i.get('period') == period for i in items)} deliveries")

    items.sort(key=lambda i: (i.get("period", 0), i.get("sequence", 0)))
    return items, raw_pages


def normalise(item: dict[str, Any], series_id: str, match_id: str, label: str) -> dict[str, Any]:
    over = item.get("over") or {}
    innings = item.get("innings") or {}
    dismissal = item.get("dismissal") or {}
    return {
        "series_id": series_id,
        "match_id": match_id,
        "match_label": label,
        "innings": item.get("period", ""),
        "innings_label": item.get("periodText", ""),
        "batting_team": (item.get("team") or {}).get("displayName", ""),
        "over": over.get("overs", ""),
        "over_number": over.get("number", ""),
        "ball_in_over": over.get("ball", ""),
        "bowler": name(item.get("bowler")),
        "batter": name(item.get("batsman")),
        "non_striker": name(item.get("otherBatsman")),
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ESPNcricinfo ball-by-ball commentary.")
    parser.add_argument("urls", nargs="*", help="ESPNcricinfo match URL(s)")
    parser.add_argument("--from-file", type=Path, help="Text file with one match URL per line")
    parser.add_argument("--output-dir", type=Path, default=Path("data"), help="Where to write CSV/JSON (default: data)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between API requests (default: 1.5)")
    args = parser.parse_args()

    urls = list(args.urls) + (read_url_file(args.from_file) if args.from_file else [])
    if not urls:
        parser.error("give at least one match URL or --from-file")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    combined: list[dict[str, Any]] = []
    failures = 0
    for url in urls:
        try:
            series_id, match_id = ids_from_url(url)
            label = label_from_url(url)
            print(f"{label} ({match_id})")
            items, raw_pages = fetch_match(session, series_id, match_id, args.delay)
        except (ValueError, requests.RequestException, json.JSONDecodeError) as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            failures += 1
            continue

        rows = [normalise(i, series_id, match_id, label) for i in items]
        (args.output_dir / f"{match_id}.raw.json").write_text(
            json.dumps(raw_pages, ensure_ascii=False), encoding="utf-8")
        write_csv(args.output_dir / f"{match_id}.csv", rows)
        combined.extend(rows)
        print(f"  saved {len(rows)} deliveries -> {args.output_dir / f'{match_id}.csv'}")

    if len(urls) > 1 and combined:
        write_csv(args.output_dir / "all_matches.csv", combined)
        print(f"Combined {len(combined)} deliveries -> {args.output_dir / 'all_matches.csv'}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
