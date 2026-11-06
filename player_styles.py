#!/usr/bin/env python3
"""Batting hand and bowling type for every player in a set of Cricsheet matches.

1. Reads Cricsheet match files (JSON) and collects each player's Cricsheet ID.
2. Maps it to a Cricinfo player ID with Cricsheet's people register
   (https://cricsheet.org/register/people.csv). ESPN uses the same IDs.
3. Reads each player's profile from ESPN's site API (batStyle, bowlStyle),
   saving every response so a re-run only fetches new players:
       https://site.web.api.espn.com/apis/common/v3/sports/cricket/athletes/<cricinfo_id>
4. Writes one row per player with the raw styles and normalised columns.

Example (five leagues plus the top-10 internationals since 2021):
    python player_styles.py --league-dirs data/cricsheet/ipl,data/cricsheet/bbl,data/cricsheet/sat,\
data/cricsheet/hnd_male,data/cricsheet/cpl --intl-dirs data/cricsheet/t20s_male,data/cricsheet/odis_male \
        --since 2021-01-01 --out data/players/player_styles.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

USER_AGENT = "Mozilla/5.0 (commentary-research-collector/1.1)"
ATHLETE_API = "https://site.web.api.espn.com/apis/common/v3/sports/cricket/athletes/{id}"
TOP10 = ("England,Australia,South Africa,West Indies,New Zealand,India,Pakistan,"
         "Sri Lanka,Bangladesh,Afghanistan")
FIELDS = ["cricsheet_id", "cricsheet_name", "cricinfo_id", "espn_name", "matches", "teams",
          "bat_hand", "bowl_arm", "bowl_kind", "bowl_type", "bat_style_raw", "bowl_style_raw", "status"]


def collect_players(dirs: list[Path], since: str, teams: set[str] | None) -> dict[str, dict]:
    """Cricsheet ID -> {name, matches, teams} over matches on or after `since`.
    With `teams`, only matches where both sides are in `teams` count."""
    players: dict[str, dict] = defaultdict(lambda: {"name": "", "matches": 0, "teams": Counter()})
    for folder in dirs:
        for path in folder.glob("*.json"):
            info = json.loads(path.read_text(encoding="utf-8"))["info"]
            if info["dates"][0] < since or (teams and not set(info["teams"]) <= teams):
                continue
            ids = info.get("registry", {}).get("people", {})
            for team, names in info.get("players", {}).items():
                for name in names:
                    pid = ids.get(name)
                    if pid:
                        p = players[pid]
                        p["name"] = name
                        p["matches"] += 1
                        p["teams"][team] += 1
    return players


def load_register(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as f:
        return {r["identifier"]: (r["key_cricinfo"] or r["key_cricinfo_2"]) for r in csv.DictReader(f)}


def fetch_profile(session: requests.Session, cricinfo_id: str, cache: Path, delay: float) -> dict | None:
    """The player's profile JSON, from the cache if saved before. None if ESPN has no such player."""
    saved = cache / f"{cricinfo_id}.json"
    if saved.exists():
        return json.loads(saved.read_text(encoding="utf-8"))
    for attempt in range(5):
        time.sleep(delay)
        try:
            r = session.get(ATHLETE_API.format(id=cricinfo_id), timeout=30)
        except (requests.ConnectionError, requests.Timeout):
            r = None
        if r is not None and r.status_code == 200:
            data = r.json()
            saved.write_text(json.dumps(data), encoding="utf-8")
            return data
        if r is not None and r.status_code == 404:
            return None
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"profile {cricinfo_id}: HTTP {r.status_code if r is not None else 'no response'}")


def styles(profile: dict) -> tuple[str, str]:
    a = profile.get("athlete", profile)
    bat = " | ".join(s.get("description", "") for s in a.get("batStyle") or [])
    bowl = " | ".join(s.get("description", "") for s in a.get("bowlStyle") or [])
    return bat, bowl


def normalise_bat(raw: str) -> str:
    low = raw.lower()
    return "right" if "right-hand" in low else "left" if "left-hand" in low else ""


def normalise_bowl(raw: str) -> tuple[str, str, str]:
    """(arm, kind, type) from the first listed bowling style, e.g.
    'Right-arm fast-medium' -> ('right', 'pace', 'fast-medium')."""
    first = raw.split(" | ")[0].strip().lower()
    if not first:
        return "", "", ""
    arm = "left" if "left-arm" in first else "right"
    if "orthodox" in first:
        return arm, "spin", "left-arm orthodox" if arm == "left" else "orthodox"
    if "wrist" in first or "chinaman" in first:
        return arm, "spin", "left-arm wrist spin" if arm == "left" else "wrist spin"
    if "legbreak" in first or "leg break" in first or "googly" in first:
        return arm, "spin", "leg-break"
    if "offbreak" in first or "off break" in first:
        return arm, "spin", "off-break"
    for kind in ("fast-medium", "medium-fast", "fast", "medium"):
        if kind in first:
            return arm, "pace", kind
    if "slow" in first:
        return arm, "spin", "slow"
    return arm, "", "other"


def main() -> int:
    parser = argparse.ArgumentParser(description="Batting hand and bowling type for Cricsheet players.")
    parser.add_argument("--league-dirs", default="", help="Comma-separated Cricsheet folders, every match kept")
    parser.add_argument("--intl-dirs", default="",
                        help="Comma-separated Cricsheet folders where both teams must be in --teams")
    parser.add_argument("--teams", default=TOP10, help="Comma-separated team names for --intl-dirs")
    parser.add_argument("--since", default="2021-01-01", help="First match date, YYYY-MM-DD")
    parser.add_argument("--register", type=Path, default=Path("data/cricsheet/people.csv"))
    parser.add_argument("--cache", type=Path, default=Path("data/players/athletes"))
    parser.add_argument("--out", type=Path, default=Path("data/players/player_styles.csv"))
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests (default: 1.5)")
    args = parser.parse_args()

    split = lambda s: [Path(p.strip()) for p in s.split(",") if p.strip()]
    players = collect_players(split(args.league_dirs), args.since, None)
    teams = {t.strip() for t in args.teams.split(",") if t.strip()}
    for pid, p in collect_players(split(args.intl_dirs), args.since, teams).items():
        mine = players[pid]
        mine["name"] = p["name"]
        mine["matches"] += p["matches"]
        mine["teams"].update(p["teams"])
    register = load_register(args.register)
    print(f"{len(players)} players in the selected matches")

    args.cache.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    rows, status = [], Counter()
    for n, (pid, p) in enumerate(sorted(players.items(), key=lambda kv: -kv[1]["matches"]), 1):
        row = {"cricsheet_id": pid, "cricsheet_name": p["name"], "matches": p["matches"],
               "teams": "; ".join(t for t, _ in p["teams"].most_common(4))}
        cricinfo_id = register.get(pid, "")
        row["cricinfo_id"] = cricinfo_id
        if not cricinfo_id:
            row["status"] = "no cricinfo id in register"
        else:
            try:
                profile = fetch_profile(session, cricinfo_id, args.cache, args.delay)
            except RuntimeError as e:
                profile, row["status"] = None, f"failed: {e}"
            if profile is None and "status" not in row:
                row["status"] = "no ESPN profile"
            elif profile is not None:
                a = profile.get("athlete", profile)
                bat, bowl = styles(profile)
                row.update(espn_name=a.get("displayName", ""), bat_style_raw=bat, bowl_style_raw=bowl,
                           bat_hand=normalise_bat(bat))
                row["bowl_arm"], row["bowl_kind"], row["bowl_type"] = normalise_bowl(bowl)
                row["status"] = "ok"
        status[row["status"].split(":")[0]] += 1
        rows.append(row)
        if n % 100 == 0 or n == len(players):
            print(f"  {n}/{len(players)} players, {dict(status)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    ok = [r for r in rows if r.get("status") == "ok"]
    print(f"Wrote {len(rows)} players to {args.out}")
    print("Batting hand:", dict(Counter(r["bat_hand"] or "unknown" for r in ok)))
    print("Bowling type:", dict(Counter(r["bowl_type"] or "none" for r in ok).most_common()))
    failed = [r for r in rows if r.get("status", "").startswith("failed")]
    if failed:
        print(f"WARNING: {len(failed)} profiles could not be fetched; re-run to retry", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
